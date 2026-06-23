"""Tests for ExportService.

Coverage:
    1. init creates JobService and sets project_root
    2. start_export returns job_id
    3. start_export creates run directory
    4. start_export command contains model_path
    5. start_export missing best.pt raises
    6. start_export with custom config
    7. get_exported_models returns empty list for empty models dir
    8. get_exported_models returns ModelArtifacts for valid models
    9. get_exported_models skips directories without _READY marker
    10. get_exported_models handles corrupt model.json
    11. _build_export_command structure
    12. project_root and job_service properties
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Trigger UltralyticsProvider registration (required by AlgorithmRegistry)
import anylabeling.platform.adapters.ultralytics  # noqa: F401

from anylabeling.platform.adapters.registry import AlgorithmRegistry
from anylabeling.platform.adapters.ultralytics.provider import UltralyticsProvider
from anylabeling.platform.application.export_service import ExportService
from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.domain.model import ModelArtifact
from anylabeling.platform.domain.run import Run


@pytest.fixture(autouse=True)
def _ensure_provider_registered():
    """Re-register UltralyticsProvider (other tests may call clear())."""
    try:
        AlgorithmRegistry.get_provider("ultralytics_yolo_detect")
    except KeyError:
        AlgorithmRegistry.register(UltralyticsProvider())


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_job_service() -> MagicMock:
    """A mocked JobService that records create_job calls."""
    svc = MagicMock(spec=JobService)
    svc.create_job.return_value = "job_fake_export_001"
    return svc


@pytest.fixture
def export_service(
    mock_job_service: MagicMock,
    tmp_path: Path,
) -> ExportService:
    """ExportService with mocked JobService and temp project root."""
    return ExportService(mock_job_service, project_root=tmp_path)


@pytest.fixture
def run_with_best_pt(tmp_path: Path) -> Run:
    """A Run with a real best.pt on disk."""
    run_dir = tmp_path / "runs" / "run_test001"
    weights_dir = run_dir / "train" / "weights"
    weights_dir.mkdir(parents=True)
    (weights_dir / "best.pt").write_text("fake_model", encoding="utf-8")
    return Run(
        id="run_test001",
        output_dir=str(run_dir),
        status="completed",
        task_family="detection_hbb",
    )


@pytest.fixture
def run_without_best_pt() -> Run:
    """A Run without best.pt (no output_dir)."""
    return Run(
        id="run_test002",
        output_dir=None,
        status="completed",
    )


@pytest.fixture
def run_with_invalid_output_dir(tmp_path: Path) -> Run:
    """A Run whose output_dir exists but contains no best.pt."""
    run_dir = tmp_path / "runs" / "run_test003"
    run_dir.mkdir(parents=True)
    return Run(
        id="run_test003",
        output_dir=str(run_dir),
        status="completed",
    )


# ============================================================================
# 1. ExportService init
# ============================================================================


class TestExportServiceInit:
    """Test ExportService initialization."""

    def test_init_creates_job_service(
        self,
        export_service: ExportService,
        mock_job_service: MagicMock,
    ):
        """Init should store the JobService reference."""
        assert export_service.job_service is mock_job_service

    def test_init_sets_project_root(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """Init should store and expose project_root as a Path."""
        assert isinstance(export_service.project_root, Path)
        assert export_service.project_root == tmp_path

    def test_init_accepts_string_project_root(self, mock_job_service: MagicMock):
        """Init should accept a string project_root and convert to Path."""
        svc = ExportService(mock_job_service, project_root="/tmp/test_proj")
        assert isinstance(svc.project_root, Path)
        assert svc.project_root == Path("/tmp/test_proj")


# ============================================================================
# 2. start_export
# ============================================================================


class TestStartExport:
    """Test the start_export orchestration method."""

    def test_start_export_returns_job_id(
        self,
        export_service: ExportService,
        run_with_best_pt: Run,
    ):
        """start_export should return the job_id from JobService."""
        job_id = export_service.start_export(run_with_best_pt)
        assert job_id == "job_fake_export_001"

    def test_start_export_creates_run_directory(
        self,
        export_service: ExportService,
        run_with_best_pt: Run,
    ):
        """start_export should create the models directory structure."""
        export_service.start_export(run_with_best_pt)
        models_dir = export_service.project_root / "models"
        assert models_dir.exists()
        assert any(models_dir.iterdir()), "Expected model subdirectory to be created"

    def test_start_export_command_contains_model_path(
        self,
        export_service: ExportService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
    ):
        """The command passed to JobService should reference the model path."""
        export_service.start_export(run_with_best_pt)
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, command = call_args[0]
        assert "best.pt" in " ".join(command)

    def test_start_export_missing_best_pt_raises(
        self,
        export_service: ExportService,
        run_without_best_pt: Run,
    ):
        """start_export should raise ValueError when best.pt is not found."""
        with pytest.raises(ValueError, match="No best.pt found"):
            export_service.start_export(run_without_best_pt)

    def test_start_export_missing_best_pt_raises_for_empty_dir(
        self,
        export_service: ExportService,
        run_with_invalid_output_dir: Run,
    ):
        """start_export should raise ValueError when output_dir exists but
        contains no best.pt."""
        with pytest.raises(ValueError, match="No best.pt found"):
            export_service.start_export(run_with_invalid_output_dir)

    def test_start_export_with_custom_config(
        self,
        export_service: ExportService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
    ):
        """start_export should pass custom export_config through."""
        custom_config = {"half": True, "imgsz": 320, "simplify": False}
        export_service.start_export(run_with_best_pt, export_config=custom_config)

        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, command = call_args[0]
        export_kwargs = job_request.params["export_kwargs"]
        assert export_kwargs["half"] is True
        assert export_kwargs["imgsz"] == 320
        assert export_kwargs["simplify"] is False

    def test_start_export_with_labels(
        self,
        export_service: ExportService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
    ):
        """start_export should pass labels through to the job params."""
        labels = ["cat", "dog", "bird"]
        export_service.start_export(run_with_best_pt, labels=labels)

        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["labels"] == labels

    def test_start_export_job_kind_is_export(
        self,
        export_service: ExportService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
    ):
        """The JobRequest should have job_kind='export'."""
        export_service.start_export(run_with_best_pt)
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.job_kind == "export"

    def test_start_export_job_params_contain_run_id(
        self,
        export_service: ExportService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
    ):
        """The JobRequest params must contain the run_id."""
        export_service.start_export(run_with_best_pt)
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["run_id"] == "run_test001"

    def test_start_export_with_empty_config(
        self,
        export_service: ExportService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
    ):
        """start_export should use defaults when export_config is None or empty."""
        export_service.start_export(run_with_best_pt, export_config={})
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        export_kwargs = job_request.params["export_kwargs"]
        # Defaults
        assert export_kwargs["imgsz"] == 640
        assert export_kwargs["simplify"] is True
        assert export_kwargs["half"] is False
        assert export_kwargs["format"] == "onnx"

    def test_start_export_default_labels_is_empty_list(
        self,
        export_service: ExportService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
    ):
        """When labels is not provided, params should contain an empty list."""
        export_service.start_export(run_with_best_pt)
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["labels"] == []


# ============================================================================
# 3. get_exported_models
# ============================================================================


class TestGetExportedModels:
    """Test the get_exported_models method."""

    def test_returns_empty_list_for_empty_models_dir(
        self,
        export_service: ExportService,
    ):
        """When models/ does not exist, return an empty list."""
        models = export_service.get_exported_models()
        assert models == []

    def test_returns_model_artifacts_for_valid_models(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """Should return ModelArtifact objects for directories with _READY."""
        models_root = tmp_path / "models"
        model_dir = models_root / "model_abc123"
        model_dir.mkdir(parents=True)

        # Write the required marker and metadata
        (model_dir / "_READY").write_text("", encoding="utf-8")
        (model_dir / "model.json").write_text(
            json.dumps({
                "model_id": "model_abc123",
                "run_id": "run_xyz",
                "format": "onnx",
                "labels": ["cat", "dog"],
            }),
            encoding="utf-8",
        )

        artifacts = export_service.get_exported_models()
        assert len(artifacts) == 1
        assert isinstance(artifacts[0], ModelArtifact)
        assert artifacts[0].id == "model_abc123"
        assert artifacts[0].run_id == "run_xyz"
        assert artifacts[0].format == "onnx"

    def test_skips_directories_without_ready_marker(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """Directories without _READY marker should be skipped."""
        models_root = tmp_path / "models"
        # Create one valid and one incomplete model dir
        valid_dir = models_root / "model_valid"
        valid_dir.mkdir(parents=True)
        (valid_dir / "_READY").write_text("", encoding="utf-8")
        (valid_dir / "model.json").write_text(
            json.dumps({"model_id": "model_valid"}),
            encoding="utf-8",
        )

        incomplete_dir = models_root / "model_incomplete"
        incomplete_dir.mkdir(parents=True)
        (incomplete_dir / "model.json").write_text(
            json.dumps({"model_id": "model_incomplete"}),
            encoding="utf-8",
        )

        artifacts = export_service.get_exported_models()
        assert len(artifacts) == 1
        assert artifacts[0].id == "model_valid"

    def test_handles_corrupt_model_json(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """Corrupt model.json should not crash; should return minimal artifact."""
        models_root = tmp_path / "models"
        model_dir = models_root / "model_bad_json"
        model_dir.mkdir(parents=True)
        (model_dir / "_READY").write_text("", encoding="utf-8")
        (model_dir / "model.json").write_text(
            "not valid json {{{",
            encoding="utf-8",
        )

        artifacts = export_service.get_exported_models()
        assert len(artifacts) == 1
        assert artifacts[0].id == "model_bad_json"  # falls back to dir name

    def test_handles_missing_model_json(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """A directory with _READY but no model.json should still be returned."""
        models_root = tmp_path / "models"
        model_dir = models_root / "model_no_json"
        model_dir.mkdir(parents=True)
        (model_dir / "_READY").write_text("", encoding="utf-8")

        artifacts = export_service.get_exported_models()
        assert len(artifacts) == 1
        assert artifacts[0].id == "model_no_json"

    def test_skips_non_directory_entries(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """Files in models/ should be skipped (only directories considered)."""
        models_root = tmp_path / "models"
        models_root.mkdir(parents=True)
        (models_root / "some_file.txt").write_text("not a model dir", encoding="utf-8")

        artifacts = export_service.get_exported_models()
        assert artifacts == []

    def test_labels_from_separate_labels_json(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """Labels from labels.json should be used when model.json has no labels."""
        models_root = tmp_path / "models"
        model_dir = models_root / "model_with_labels"
        model_dir.mkdir(parents=True)
        (model_dir / "_READY").write_text("", encoding="utf-8")
        (model_dir / "model.json").write_text(
            json.dumps({"model_id": "model_with_labels", "run_id": "r1"}),
            encoding="utf-8",
        )
        (model_dir / "labels.json").write_text(
            json.dumps([
                {"id": 0, "name": "cat"},
                {"id": 1, "name": "dog"},
            ]),
            encoding="utf-8",
        )

        artifacts = export_service.get_exported_models()
        assert len(artifacts) == 1
        assert artifacts[0].labels == ["cat", "dog"]

    def test_model_json_labels_take_precedence_over_labels_json(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """Labels in model.json should not be overwritten by labels.json."""
        models_root = tmp_path / "models"
        model_dir = models_root / "model_priority"
        model_dir.mkdir(parents=True)
        (model_dir / "_READY").write_text("", encoding="utf-8")
        (model_dir / "model.json").write_text(
            json.dumps({
                "model_id": "model_priority",
                "run_id": "r1",
                "labels": ["car", "truck"],
            }),
            encoding="utf-8",
        )
        (model_dir / "labels.json").write_text(
            json.dumps([
                {"id": 0, "name": "cat"},
                {"id": 1, "name": "dog"},
            ]),
            encoding="utf-8",
        )

        artifacts = export_service.get_exported_models()
        assert len(artifacts) == 1
        assert artifacts[0].labels == ["car", "truck"]

    def test_handles_corrupt_labels_json(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """Corrupt labels.json should not crash the method."""
        models_root = tmp_path / "models"
        model_dir = models_root / "model_corrupt_labels"
        model_dir.mkdir(parents=True)
        (model_dir / "_READY").write_text("", encoding="utf-8")
        (model_dir / "model.json").write_text(
            json.dumps({"model_id": "model_corrupt_labels"}),
            encoding="utf-8",
        )
        (model_dir / "labels.json").write_text(
            "not valid json >>>",
            encoding="utf-8",
        )

        artifacts = export_service.get_exported_models()
        assert len(artifacts) == 1
        # Labels should be empty since both sources are invalid
        assert artifacts[0].labels == []

    def test_multiple_models_sorted(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """Multiple model directories should all be returned."""
        models_root = tmp_path / "models"
        for mid in ["model_a", "model_b", "model_c"]:
            model_dir = models_root / mid
            model_dir.mkdir(parents=True)
            (model_dir / "_READY").write_text("", encoding="utf-8")
            (model_dir / "model.json").write_text(
                json.dumps({"model_id": mid}),
                encoding="utf-8",
            )

        artifacts = export_service.get_exported_models()
        assert len(artifacts) == 3
        returned_ids = [a.id for a in artifacts]
        assert "model_a" in returned_ids
        assert "model_b" in returned_ids
        assert "model_c" in returned_ids

    def test_returns_preprocess_and_postprocess(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """preprocess.json and postprocess.json should be read when present."""
        models_root = tmp_path / "models"
        model_dir = models_root / "model_proc"
        model_dir.mkdir(parents=True)
        (model_dir / "_READY").write_text("", encoding="utf-8")
        (model_dir / "model.json").write_text(
            json.dumps({"model_id": "model_proc"}),
            encoding="utf-8",
        )
        (model_dir / "preprocess.json").write_text(
            json.dumps({"imgsz": 640, "mean": [0, 0, 0]}),
            encoding="utf-8",
        )
        (model_dir / "postprocess.json").write_text(
            json.dumps({"conf_threshold": 0.5}),
            encoding="utf-8",
        )

        artifacts = export_service.get_exported_models()
        assert len(artifacts) == 1
        assert artifacts[0].preprocess == {"imgsz": 640, "mean": [0, 0, 0]}
        assert artifacts[0].postprocess == {"conf_threshold": 0.5}

    def test_onnx_check_loaded(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """onnx_check.json should be read when present."""
        models_root = tmp_path / "models"
        model_dir = models_root / "model_onnx_check"
        model_dir.mkdir(parents=True)
        (model_dir / "_READY").write_text("", encoding="utf-8")
        (model_dir / "model.json").write_text(
            json.dumps({"model_id": "model_onnx_check"}),
            encoding="utf-8",
        )
        (model_dir / "onnx_check.json").write_text(
            json.dumps({"load_ok": True, "passed": True}),
            encoding="utf-8",
        )

        artifacts = export_service.get_exported_models()
        assert len(artifacts) == 1
        assert artifacts[0].onnx_check == {"load_ok": True, "passed": True}


# ============================================================================
# 4. _build_export_command
# ============================================================================


class TestBuildExportCommand:
    """Test the _build_export_command static method."""

    def test_command_is_list_of_strings(self):
        """The returned command must be a list of strings."""
        cmd = ExportService._build_export_command("best.pt", {"format": "onnx"})
        assert isinstance(cmd, list)
        for part in cmd:
            assert isinstance(part, str)

    def test_command_starts_with_python_executable(self):
        """The first element should be sys.executable."""
        cmd = ExportService._build_export_command("best.pt", {"format": "onnx"})
        assert cmd[0] == sys.executable
        assert cmd[1] == "-c"

    def test_command_contains_model_path(self):
        """The inline script must contain the model path."""
        cmd = ExportService._build_export_command(
            "/path/to/best.pt", {"format": "onnx"}
        )
        script = cmd[2]
        assert "/path/to/best.pt" in script

    def test_command_contains_export_kwargs(self):
        """The inline script must serialize kwargs as JSON."""
        cmd = ExportService._build_export_command(
            "best.pt", {"format": "onnx", "imgsz": 320}
        )
        script = cmd[2]
        assert "format" in script
        assert "imgsz" in script

    def test_command_uses_model_export(self):
        """The inline script must call model.export(**kwargs)."""
        cmd = ExportService._build_export_command("best.pt", {"format": "onnx"})
        script = cmd[2]
        assert "model.export(**kwargs)" in script
        assert "from ultralytics import YOLO" in script

    def test_command_with_all_kwargs(self):
        """Command should serialize all export kwargs correctly."""
        kwargs = {
            "format": "onnx",
            "imgsz": 640,
            "simplify": True,
            "half": False,
            "dynamic": True,
            "batch": 1,
            "opset": 12,
        }
        cmd = ExportService._build_export_command("best.pt", kwargs)
        script = cmd[2]
        # Check that each key appears in the serialized JSON
        for key in kwargs:
            assert key in script


# ============================================================================
# 5. _resolve_best_pt
# ============================================================================


class TestResolveBestPt:
    """Test the _resolve_best_pt static method."""

    def test_resolves_best_pt_from_run(
        self,
        run_with_best_pt: Run,
    ):
        """Should return the path to best.pt when it exists."""
        path = ExportService._resolve_best_pt(run_with_best_pt)
        assert path is not None
        assert path.endswith("best.pt")
        assert Path(path).exists()

    def test_returns_none_when_output_dir_is_none(
        self,
        run_without_best_pt: Run,
    ):
        """Should return None when output_dir is None."""
        path = ExportService._resolve_best_pt(run_without_best_pt)
        assert path is None

    def test_returns_none_when_best_pt_missing(
        self,
        run_with_invalid_output_dir: Run,
    ):
        """Should return None when best.pt does not exist in output_dir."""
        path = ExportService._resolve_best_pt(run_with_invalid_output_dir)
        assert path is None


# ============================================================================
# 6. Properties
# ============================================================================


class TestExportServiceProperties:
    """Test ExportService properties."""

    def test_project_root_is_path(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """project_root property should return a Path."""
        assert isinstance(export_service.project_root, Path)
        assert export_service.project_root == tmp_path

    def test_job_service_is_preserved(
        self,
        export_service: ExportService,
        mock_job_service: MagicMock,
    ):
        """job_service property should return the original JobService."""
        assert export_service.job_service is mock_job_service


# ============================================================================
# 7. save_export_artifacts (delegates to adapter)
# ============================================================================


class TestSaveExportArtifacts:
    """Test save_export_artifacts method (post-job callback)."""

    def test_save_export_artifacts_creates_model_dir(
        self,
        export_service: ExportService,
        tmp_path: Path,
    ):
        """Should delegate to the adapter and create a model directory."""
        # Setup: create a fake ONNX file to copy from
        export_src_dir = tmp_path / "export_output"
        export_src_dir.mkdir(parents=True)
        fake_onnx = export_src_dir / "best.onnx"
        fake_onnx.write_text("fake onnx content", encoding="utf-8")

        fake_pt = export_src_dir / "best.pt"
        fake_pt.write_text("fake pt content", encoding="utf-8")

        artifact = export_service.save_export_artifacts(
            export_path=str(fake_onnx),
            model_path=str(fake_pt),
            model_id="model_save_test",
            labels=["cat", "dog"],
            run_id="run_xyz",
        )

        assert isinstance(artifact, ModelArtifact)
        assert artifact.id == "model_save_test"
        assert artifact.run_id == "run_xyz"
        assert artifact.format == "onnx"
        assert artifact.labels == ["cat", "dog"]

        # Verify the model directory was created
        model_dir = tmp_path / "models" / "model_save_test"
        assert model_dir.exists()
        assert (model_dir / "_READY").exists()
        assert (model_dir / "model.json").exists()
        assert (model_dir / "labels.json").exists()
        assert (model_dir / "preprocess.json").exists()
        assert (model_dir / "postprocess.json").exists()


__all__: list[str] = []

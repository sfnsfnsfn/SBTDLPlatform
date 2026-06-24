"""Tests for EvaluationService.

Coverage:
    1. init creates JobService and sets project_root
    2. evaluate_tile_native returns job_id
    3. evaluate_tile_native missing best.pt raises
    4. evaluate_tile_native command contains data_yaml
    5. evaluate_tile_native respects split parameter
    6. evaluate_tile_native respects device, batch, imgsz parameters
    7. _resolve_best_pt resolves from run
    8. _resolve_best_pt raises when not found
    9. _resolve_best_pt raises when output_dir is None
    10. _build_val_command structure
    11. project_root and job_service properties
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anylabeling.platform.adapters.registry import AlgorithmRegistry
from anylabeling.platform.adapters.ultralytics.provider import UltralyticsProvider
from anylabeling.platform.application.evaluation_service import EvaluationService
from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.run import Run

# Trigger UltralyticsProvider registration (required by AlgorithmRegistry)
import anylabeling.platform.adapters.ultralytics  # noqa: F401


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
    svc.create_job.return_value = "job_fake_eval_001"
    return svc


@pytest.fixture
def evaluation_service(
    mock_job_service: MagicMock,
    tmp_path: Path,
) -> EvaluationService:
    """EvaluationService with mocked JobService and temp project root."""
    return EvaluationService(mock_job_service, project_root=tmp_path)


@pytest.fixture
def run_with_best_pt(tmp_path: Path) -> Run:
    """A Run with a real best.pt on disk."""
    run_dir = tmp_path / "runs" / "run_eval001"
    weights_dir = run_dir / "train" / "weights"
    weights_dir.mkdir(parents=True)
    (weights_dir / "best.pt").write_text("fake_model", encoding="utf-8")
    return Run(
        id="run_eval001",
        output_dir=str(run_dir),
        status="completed",
        task_family="detection_hbb",
    )


@pytest.fixture
def run_without_best_pt() -> Run:
    """A Run without best.pt (no output_dir)."""
    return Run(
        id="run_eval002",
        output_dir=None,
        status="completed",
    )


@pytest.fixture
def run_with_empty_output_dir(tmp_path: Path) -> Run:
    """A Run whose output_dir exists but contains no best.pt."""
    run_dir = tmp_path / "runs" / "run_eval003"
    run_dir.mkdir(parents=True)
    return Run(
        id="run_eval003",
        output_dir=str(run_dir),
        status="completed",
    )


@pytest.fixture
def dataset_build_with_data_yaml(tmp_path: Path) -> DatasetBuild:
    """A DatasetBuild with a real data.yaml on disk."""
    build_dir = tmp_path / "dataset_builds" / "build_eval001"
    build_dir.mkdir(parents=True)
    yaml_content = textwrap.dedent("""\
        path: {build_dir}
        train: images/train
        val: images/val
        test: images/test
        nc: 2
        names:
          0: cat
          1: dog
    """).replace("{build_dir}", str(build_dir))
    (build_dir / "data.yaml").write_text(yaml_content, encoding="utf-8")
    return DatasetBuild(
        id="build_eval001",
        task_spec_id="task_det_001",
        source_asset_manifest_hash="abc",
        annotation_manifest_hash="def",
        split_seed=42,
        split_strategy="random_by_asset",
        output_path=str(build_dir),
    )


@pytest.fixture
def dataset_build_without_data_yaml(tmp_path: Path) -> DatasetBuild:
    """A DatasetBuild with an empty output path (no data.yaml)."""
    build_dir = tmp_path / "dataset_builds" / "build_eval002"
    build_dir.mkdir(parents=True)
    return DatasetBuild(
        id="build_eval002",
        task_spec_id="task_det_002",
        source_asset_manifest_hash="abc",
        annotation_manifest_hash="def",
        split_seed=42,
        split_strategy="random_by_asset",
        output_path=str(build_dir),
    )


# ============================================================================
# 1. EvaluationService init
# ============================================================================


class TestEvaluationServiceInit:
    """Test EvaluationService initialization."""

    def test_init_creates_job_service(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
    ):
        """Init should store the JobService reference."""
        assert evaluation_service.job_service is mock_job_service

    def test_init_sets_project_root(
        self,
        evaluation_service: EvaluationService,
        tmp_path: Path,
    ):
        """Init should store and expose project_root as a Path."""
        assert isinstance(evaluation_service.project_root, Path)
        assert evaluation_service.project_root == tmp_path

    def test_init_accepts_string_project_root(self, mock_job_service: MagicMock):
        """Init should accept a string project_root and convert to Path."""
        svc = EvaluationService(mock_job_service, project_root="/tmp/eval_proj")
        assert isinstance(svc.project_root, Path)
        assert svc.project_root == Path("/tmp/eval_proj")


# ============================================================================
# 2. evaluate_tile_native
# ============================================================================


class TestEvaluateTileNative:
    """Test the evaluate_tile_native orchestration method."""

    def test_evaluate_returns_job_id(
        self,
        evaluation_service: EvaluationService,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """evaluate_tile_native should return the job_id from JobService."""
        job_id = evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
        )
        assert job_id == "job_fake_eval_001"

    def test_evaluate_missing_best_pt_raises(
        self,
        evaluation_service: EvaluationService,
        run_without_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """evaluate_tile_native should raise ValueError when best.pt is missing."""
        with pytest.raises(ValueError, match="No best.pt found"):
            evaluation_service.evaluate_tile_native(
                run_without_best_pt,
                dataset_build_with_data_yaml,
            )

    def test_evaluate_missing_best_pt_raises_for_empty_dir(
        self,
        evaluation_service: EvaluationService,
        run_with_empty_output_dir: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """evaluate_tile_native should raise ValueError when output_dir lacks best.pt."""
        with pytest.raises(ValueError, match="No best.pt found"):
            evaluation_service.evaluate_tile_native(
                run_with_empty_output_dir,
                dataset_build_with_data_yaml,
            )

    def test_evaluate_command_contains_data_yaml(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """The command should contain the data.yaml path."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, command = call_args[0]
        assert "data.yaml" in " ".join(command)

    def test_evaluate_respects_split_parameter(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """The split parameter should appear in val_kwargs."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
            split="test",
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["val_kwargs"]["split"] == "test"

    def test_evaluate_default_split_is_val(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """Default split should be 'val'."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["val_kwargs"]["split"] == "val"

    def test_evaluate_respects_device_parameter(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """The device parameter should appear in val_kwargs."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
            device="cpu",
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["val_kwargs"]["device"] == "cpu"

    def test_evaluate_respects_batch_parameter(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """The batch parameter should appear in val_kwargs."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
            batch=8,
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["val_kwargs"]["batch"] == 8

    def test_evaluate_respects_imgsz_parameter(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """The imgsz parameter should appear in val_kwargs."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
            imgsz=320,
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["val_kwargs"]["imgsz"] == 320

    def test_evaluate_job_kind_is_evaluation(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """The JobRequest should have job_kind='evaluation'."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.job_kind == "evaluation"

    def test_evaluate_job_params_contain_run_id(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """The JobRequest params must contain the run_id."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["run_id"] == "run_eval001"

    def test_evaluate_calls_create_job_once(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """evaluate_tile_native should call JobService.create_job exactly once."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
        )
        assert mock_job_service.create_job.call_count == 1

    def test_evaluate_val_kwargs_contain_data(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """The val_kwargs must contain the 'data' key pointing to data.yaml."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert "data" in job_request.params["val_kwargs"]
        assert "data.yaml" in job_request.params["val_kwargs"]["data"]

    def test_evaluate_val_kwargs_contains_output_dir(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """The val_kwargs project should match the run's output_dir."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert "project" in job_request.params["val_kwargs"]

    def test_evaluate_val_kwargs_contains_exist_ok(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """The val_kwargs should set exist_ok=True."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["val_kwargs"]["exist_ok"] is True


# ============================================================================
# 3. _resolve_best_pt
# ============================================================================


class TestResolveBestPt:
    """Test the _resolve_best_pt static method."""

    def test_resolves_best_pt_from_run(
        self,
        run_with_best_pt: Run,
    ):
        """Should return the path to best.pt when it exists."""
        path = EvaluationService._resolve_best_pt(run_with_best_pt)
        assert path is not None
        assert path.endswith("best.pt")
        assert Path(path).exists()

    def test_raises_when_best_pt_not_found(
        self,
        run_with_empty_output_dir: Run,
    ):
        """Should return None when best.pt does not exist in output_dir."""
        path = EvaluationService._resolve_best_pt(run_with_empty_output_dir)
        assert path is None

    def test_raises_when_run_output_dir_none(
        self,
        run_without_best_pt: Run,
    ):
        """Should return None when output_dir is None."""
        path = EvaluationService._resolve_best_pt(run_without_best_pt)
        assert path is None

    def test_resolves_absolute_path(
        self,
        tmp_path: Path,
    ):
        """The resolved path should be absolute."""
        run_dir = tmp_path / "runs" / "run_abs"
        weights_dir = run_dir / "train" / "weights"
        weights_dir.mkdir(parents=True)
        (weights_dir / "best.pt").write_text("fake", encoding="utf-8")

        run = Run(
            id="run_abs",
            output_dir=str(run_dir),
        )
        path = EvaluationService._resolve_best_pt(run)
        assert path is not None
        assert Path(path).is_absolute()


# ============================================================================
# 4. _build_val_command
# ============================================================================


class TestBuildValCommand:
    """Test the _build_val_command static method."""

    def test_command_is_list_of_strings(self):
        """The returned command must be a list of strings."""
        cmd = EvaluationService._build_val_command(
            "best.pt",
            {"data": "/data/data.yaml", "split": "val"},
        )
        assert isinstance(cmd, list)
        for part in cmd:
            assert isinstance(part, str)

    def test_command_starts_with_python_executable(self):
        """The first element should be sys.executable."""
        cmd = EvaluationService._build_val_command(
            "best.pt",
            {"data": "/data/data.yaml"},
        )
        assert cmd[0] == sys.executable
        assert cmd[1] == "-c"

    def test_command_contains_model_path(self):
        """The inline script must contain the model path."""
        cmd = EvaluationService._build_val_command(
            "/path/to/best.pt",
            {"data": "/data/data.yaml"},
        )
        script = cmd[2]
        assert "/path/to/best.pt" in script

    def test_command_contains_val_kwargs(self):
        """The inline script must serialize kwargs as JSON."""
        cmd = EvaluationService._build_val_command(
            "best.pt",
            {"data": "/data/data.yaml", "batch": 8, "device": "cpu"},
        )
        script = cmd[2]
        assert "data" in script
        assert "batch" in script
        assert "device" in script

    def test_command_uses_model_val(self):
        """The inline script must call model.val(**kwargs)."""
        cmd = EvaluationService._build_val_command(
            "best.pt",
            {"data": "/data/data.yaml"},
        )
        script = cmd[2]
        assert "model.val(**kwargs)" in script
        assert "from ultralytics import YOLO" in script

    def test_command_handles_special_characters_in_model_path(self):
        """Command should handle paths with spaces or special chars."""
        cmd = EvaluationService._build_val_command(
            "C:\\path with spaces\\best.pt",
            {"data": "/data/data.yaml"},
        )
        script = cmd[2]
        assert "C:\\\\path with spaces\\\\best.pt" in script or "C:\\path with spaces\\best.pt" in script


# ============================================================================
# 5. Properties
# ============================================================================


class TestEvaluationServiceProperties:
    """Test EvaluationService properties."""

    def test_project_root_is_path(
        self,
        evaluation_service: EvaluationService,
        tmp_path: Path,
    ):
        """project_root property should return a Path."""
        assert isinstance(evaluation_service.project_root, Path)
        assert evaluation_service.project_root == tmp_path

    def test_job_service_is_preserved(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
    ):
        """job_service property should return the original JobService."""
        assert evaluation_service.job_service is mock_job_service


# ============================================================================
# 6. Edge cases
# ============================================================================


class TestEdgeCases:
    """Edge case tests for EvaluationService."""

    def test_evaluate_with_dataset_build_without_data_yaml(
        self,
        evaluation_service: EvaluationService,
        run_with_best_pt: Run,
        dataset_build_without_data_yaml: DatasetBuild,
    ):
        """evaluate_tile_native should not crash when data.yaml doesn't exist —
        it only resolves the path, existence is not checked by the service."""
        job_id = evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_without_data_yaml,
        )
        assert job_id == "job_fake_eval_001"

    def test_evaluate_respects_split_train(
        self,
        evaluation_service: EvaluationService,
        mock_job_service: MagicMock,
        run_with_best_pt: Run,
        dataset_build_with_data_yaml: DatasetBuild,
    ):
        """split='train' should be passed through."""
        evaluation_service.evaluate_tile_native(
            run_with_best_pt,
            dataset_build_with_data_yaml,
            split="train",
        )
        call_args = mock_job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.params["val_kwargs"]["split"] == "train"


__all__: list[str] = []

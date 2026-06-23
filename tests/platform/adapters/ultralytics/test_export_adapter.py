"""Tests for UltralyticsExportAdapter.

Coverage:
    1. build_export_kwargs format is always "onnx"
    2. build_export_kwargs simplify defaults to True
    3. build_export_kwargs contains expected keys with correct types
    4. build_export_kwargs custom values are propagated
    5. build_export_kwargs opset default (None = not present)
    6. save_export_artifacts creates directory structure
    7. save_export_artifacts writes model.json
    8. save_export_artifacts writes labels.json
    9. save_export_artifacts creates _READY marker
    10. save_export_artifacts returns ModelArtifact
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anylabeling.platform.adapters.ultralytics.export_adapter import (
    UltralyticsExportAdapter,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def adapter() -> UltralyticsExportAdapter:
    """Fresh UltralyticsExportAdapter instance."""
    return UltralyticsExportAdapter()


# ============================================================================
# 1. build_export_kwargs — format is always onnx
# ============================================================================


class TestBuildExportKwargsFormat:
    """Verify format is always 'onnx'."""

    def test_build_export_kwargs_format_is_onnx(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        """The format must always be 'onnx'."""
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
        )
        assert kwargs["format"] == "onnx"


# ============================================================================
# 2. build_export_kwargs — simplify defaults to True
# ============================================================================


class TestBuildExportKwargsSimplify:
    """Verify simplify default."""

    def test_build_export_kwargs_simplify_default_true(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        """simplify should default to True."""
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
        )
        assert kwargs["simplify"] is True


# ============================================================================
# 3. build_export_kwargs — required keys
# ============================================================================


class TestBuildExportKwargsRequiredKeys:
    """Verify all required keys are present."""

    def test_all_required_keys_present(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        """Every expected key must be in the kwargs dict."""
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
        )
        expected_keys = ["format", "imgsz", "simplify", "half", "dynamic", "batch"]
        for key in expected_keys:
            assert key in kwargs, f"Missing key: {key}"


# ============================================================================
# 4. build_export_kwargs — default values
# ============================================================================


class TestBuildExportKwargsDefaults:
    """Verify default values in build_export_kwargs."""

    def test_imgsz_default_is_640(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
        )
        assert kwargs["imgsz"] == 640

    def test_half_default_is_false(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
        )
        assert kwargs["half"] is False

    def test_dynamic_default_is_false(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
        )
        assert kwargs["dynamic"] is False

    def test_batch_default_is_1(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
        )
        assert kwargs["batch"] == 1

    def test_opset_not_present_by_default(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        """opset should NOT be present when not provided."""
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
        )
        assert "opset" not in kwargs


# ============================================================================
# 5. build_export_kwargs — value propagation
# ============================================================================


class TestBuildExportKwargsValues:
    """Verify custom values are propagated correctly."""

    def test_custom_imgsz(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
            imgsz=320,
        )
        assert kwargs["imgsz"] == 320

    def test_half_enabled(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
            half=True,
        )
        assert kwargs["half"] is True

    def test_dynamic_enabled(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
            dynamic=True,
        )
        assert kwargs["dynamic"] is True

    def test_custom_opset(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
            opset=12,
        )
        assert kwargs["opset"] == 12

    def test_custom_batch(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
            batch=4,
        )
        assert kwargs["batch"] == 4

    def test_simplify_can_be_disabled(
        self,
        adapter: UltralyticsExportAdapter,
    ):
        kwargs = adapter.build_export_kwargs(
            model_path="/models/best.pt",
            output_dir="/output",
            simplify=False,
        )
        assert kwargs["simplify"] is False


# ============================================================================
# 6. save_export_artifacts — directory structure
# ============================================================================


class TestSaveExportArtifactsDirectoryStructure:
    """Verify save_export_artifacts creates the expected directory layout."""

    def test_save_export_artifacts_creates_directory_structure(
        self,
        adapter: UltralyticsExportAdapter,
        tmp_path: Path,
    ):
        """Should create models/<id>/ with expected files."""
        model_dir = tmp_path / "input"
        model_dir.mkdir(parents=True)
        export_onnx = model_dir / "best.onnx"
        export_onnx.write_text("fake onnx", encoding="utf-8")
        model_pt = model_dir / "best.pt"
        model_pt.write_text("fake pt", encoding="utf-8")

        artifact = adapter.save_export_artifacts(
            export_path=str(export_onnx),
            model_path=str(model_pt),
            output_dir=str(tmp_path),
            model_id="model_abc123",
            labels=["cat", "dog"],
            run_id="run_xyz",
        )

        target_dir = tmp_path / "models" / "model_abc123"
        assert target_dir.exists()
        assert (target_dir / "best.onnx").exists()
        assert (target_dir / "best.pt").exists()
        assert (target_dir / "model.json").exists()
        assert (target_dir / "labels.json").exists()
        assert (target_dir / "preprocess.json").exists()
        assert (target_dir / "postprocess.json").exists()
        assert (target_dir / "onnx_check.json").exists()
        assert (target_dir / "_READY").exists()

        # Verify artifact
        assert artifact.id == "model_abc123"
        assert artifact.format == "onnx"

    def test_save_export_artifacts_writes_model_json(
        self,
        adapter: UltralyticsExportAdapter,
        tmp_path: Path,
    ):
        """model.json should contain the correct metadata."""
        model_dir = tmp_path / "input"
        model_dir.mkdir(parents=True)
        export_onnx = model_dir / "best.onnx"
        export_onnx.write_text("fake onnx", encoding="utf-8")
        model_pt = model_dir / "best.pt"
        model_pt.write_text("fake pt", encoding="utf-8")

        adapter.save_export_artifacts(
            export_path=str(export_onnx),
            model_path=str(model_pt),
            output_dir=str(tmp_path),
            model_id="model_test",
            labels=["car", "person"],
            run_id="run_001",
        )

        model_json_path = tmp_path / "models" / "model_test" / "model.json"
        data = json.loads(model_json_path.read_text(encoding="utf-8"))
        assert data["model_id"] == "model_test"
        assert data["run_id"] == "run_001"
        assert data["format"] == "onnx"
        assert data["labels"] == ["car", "person"]

    def test_save_export_artifacts_writes_labels_json(
        self,
        adapter: UltralyticsExportAdapter,
        tmp_path: Path,
    ):
        """labels.json should contain indexed label entries."""
        model_dir = tmp_path / "input"
        model_dir.mkdir(parents=True)
        export_onnx = model_dir / "best.onnx"
        export_onnx.write_text("fake onnx", encoding="utf-8")
        model_pt = model_dir / "best.pt"
        model_pt.write_text("fake pt", encoding="utf-8")

        adapter.save_export_artifacts(
            export_path=str(export_onnx),
            model_path=str(model_pt),
            output_dir=str(tmp_path),
            model_id="model_labels",
            labels=["apple", "banana", "cherry"],
        )

        labels_json_path = tmp_path / "models" / "model_labels" / "labels.json"
        data = json.loads(labels_json_path.read_text(encoding="utf-8"))
        assert data == [
            {"id": 0, "name": "apple"},
            {"id": 1, "name": "banana"},
            {"id": 2, "name": "cherry"},
        ]

    def test_save_export_artifacts_creates_ready_marker(
        self,
        adapter: UltralyticsExportAdapter,
        tmp_path: Path,
    ):
        """_READY marker file should exist after save."""
        model_dir = tmp_path / "input"
        model_dir.mkdir(parents=True)
        export_onnx = model_dir / "best.onnx"
        export_onnx.write_text("fake onnx", encoding="utf-8")
        model_pt = model_dir / "best.pt"
        model_pt.write_text("fake pt", encoding="utf-8")

        adapter.save_export_artifacts(
            export_path=str(export_onnx),
            model_path=str(model_pt),
            output_dir=str(tmp_path),
            model_id="model_ready",
            labels=["cat"],
        )

        ready_path = tmp_path / "models" / "model_ready" / "_READY"
        assert ready_path.exists()

    def test_save_export_artifacts_returns_modelartifact(
        self,
        adapter: UltralyticsExportAdapter,
        tmp_path: Path,
    ):
        """Should return a ModelArtifact with correct fields."""
        model_dir = tmp_path / "input"
        model_dir.mkdir(parents=True)
        export_onnx = model_dir / "best.onnx"
        export_onnx.write_text("fake onnx", encoding="utf-8")
        model_pt = model_dir / "best.pt"
        model_pt.write_text("fake pt", encoding="utf-8")

        artifact = adapter.save_export_artifacts(
            export_path=str(export_onnx),
            model_path=str(model_pt),
            output_dir=str(tmp_path),
            model_id="model_ret",
            labels=["dog", "bird"],
            run_id="run_xyz",
        )

        assert artifact.id == "model_ret"
        assert artifact.run_id == "run_xyz"
        assert artifact.format == "onnx"
        assert artifact.labels == ["dog", "bird"]
        assert "models" in artifact.path
        assert isinstance(artifact.preprocess, dict)
        assert isinstance(artifact.postprocess, dict)
        assert isinstance(artifact.onnx_check, dict)
        assert "passed" in artifact.onnx_check

    def test_save_export_artifacts_writes_preprocess_json(
        self,
        adapter: UltralyticsExportAdapter,
        tmp_path: Path,
    ):
        """preprocess.json should be written with normalization config."""
        model_dir = tmp_path / "input"
        model_dir.mkdir(parents=True)
        export_onnx = model_dir / "best.onnx"
        export_onnx.write_text("fake onnx", encoding="utf-8")
        model_pt = model_dir / "best.pt"
        model_pt.write_text("fake pt", encoding="utf-8")

        adapter.save_export_artifacts(
            export_path=str(export_onnx),
            model_path=str(model_pt),
            output_dir=str(tmp_path),
            model_id="model_pre",
            labels=["cat"],
        )

        pre_json = tmp_path / "models" / "model_pre" / "preprocess.json"
        data = json.loads(pre_json.read_text(encoding="utf-8"))
        assert data["imgsz"] == 640
        assert data["normalize"] is True

    def test_save_export_artifacts_writes_postprocess_json(
        self,
        adapter: UltralyticsExportAdapter,
        tmp_path: Path,
    ):
        """postprocess.json should be written with NMS config."""
        model_dir = tmp_path / "input"
        model_dir.mkdir(parents=True)
        export_onnx = model_dir / "best.onnx"
        export_onnx.write_text("fake onnx", encoding="utf-8")
        model_pt = model_dir / "best.pt"
        model_pt.write_text("fake pt", encoding="utf-8")

        adapter.save_export_artifacts(
            export_path=str(export_onnx),
            model_path=str(model_pt),
            output_dir=str(tmp_path),
            model_id="model_post",
            labels=["cat"],
        )

        post_json = tmp_path / "models" / "model_post" / "postprocess.json"
        data = json.loads(post_json.read_text(encoding="utf-8"))
        assert "conf_threshold" in data
        assert "nms_iou_threshold" in data


# ============================================================================
# 7. save_export_artifacts — empty labels
# ============================================================================


class TestSaveExportArtifactsEmptyLabels:
    """Verify save_export_artifacts handles empty labels."""

    def test_empty_labels(
        self,
        adapter: UltralyticsExportAdapter,
        tmp_path: Path,
    ):
        """Should handle empty labels list gracefully."""
        model_dir = tmp_path / "input"
        model_dir.mkdir(parents=True)
        export_onnx = model_dir / "best.onnx"
        export_onnx.write_text("fake onnx", encoding="utf-8")
        model_pt = model_dir / "best.pt"
        model_pt.write_text("fake pt", encoding="utf-8")

        artifact = adapter.save_export_artifacts(
            export_path=str(export_onnx),
            model_path=str(model_pt),
            output_dir=str(tmp_path),
            model_id="model_empty",
            labels=[],
        )

        assert artifact.labels == []

        labels_json_path = tmp_path / "models" / "model_empty" / "labels.json"
        data = json.loads(labels_json_path.read_text(encoding="utf-8"))
        assert data == []


__all__: list[str] = []

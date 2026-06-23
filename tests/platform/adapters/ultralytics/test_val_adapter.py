"""Tests for UltralyticsValAdapter.

Coverage:
    1. build_val_kwargs contains all required keys
    2. build_val_kwargs split defaults to "val"
    3. build_val_kwargs respects parameter values
    4. Edge cases (empty output_dir, custom device, etc.)
"""

from __future__ import annotations

import pytest

from anylabeling.platform.adapters.ultralytics.val_adapter import (
    UltralyticsValAdapter,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def adapter() -> UltralyticsValAdapter:
    """Fresh UltralyticsValAdapter instance."""
    return UltralyticsValAdapter()


# ============================================================================
# 1. Required keys
# ============================================================================


class TestBuildValKwargsRequiredKeys:
    """Verify that build_val_kwargs returns all expected top-level keys."""

    REQUIRED_KEYS = [
        "data",
        "split",
        "batch",
        "imgsz",
        "device",
        "project",
        "name",
        "exist_ok",
    ]

    def test_build_val_kwargs_contains_required_keys(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """Every required key must be in the returned kwargs dict."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="/runs/run_abc",
        )
        for key in self.REQUIRED_KEYS:
            assert key in kwargs, f"Missing key: {key}"


# ============================================================================
# 2. Split defaults to "val"
# ============================================================================


class TestBuildValKwargsDefaults:
    """Verify default values in build_val_kwargs."""

    def test_split_defaults_to_val(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """When split is not specified, it should default to 'val'."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="/runs/test",
        )
        assert kwargs["split"] == "val"

    def test_name_is_always_val(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """The 'name' key should always be 'val'."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="/runs/test",
        )
        assert kwargs["name"] == "val"

    def test_exist_ok_is_true(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """exist_ok should default to True."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="/runs/test",
        )
        assert kwargs["exist_ok"] is True

    def test_device_defaults_to_zero(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """device should default to '0'."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="/runs/test",
        )
        assert kwargs["device"] == "0"

    def test_batch_defaults_to_16(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """batch should default to 16."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="/runs/test",
        )
        assert kwargs["batch"] == 16

    def test_imgsz_defaults_to_640(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """imgsz should default to 640."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="/runs/test",
        )
        assert kwargs["imgsz"] == 640


# ============================================================================
# 3. Value propagation
# ============================================================================


class TestBuildValKwargsValues:
    """Verify that parameter values are correctly propagated to kwargs."""

    def test_data_path_matches_input(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """data should be set to the data_yaml argument."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/custom/data.yaml",
            output_dir="/runs/test",
        )
        assert kwargs["data"] == "/custom/data.yaml"

    def test_project_set_to_output_dir(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """project should be set to the output_dir argument."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="/custom/output",
        )
        assert kwargs["project"] == "/custom/output"

    def test_custom_split_preserved(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """When split is provided, it should be used."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            split="test",
            output_dir="/runs/test",
        )
        assert kwargs["split"] == "test"

    def test_custom_device_preserved(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """When device is provided, it should be used."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            device="cpu",
            output_dir="/runs/test",
        )
        assert kwargs["device"] == "cpu"

    def test_custom_batch_preserved(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """When batch is provided, it should be used."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            batch=8,
            output_dir="/runs/test",
        )
        assert kwargs["batch"] == 8

    def test_custom_imgsz_preserved(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """When imgsz is provided, it should be used."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            imgsz=320,
            output_dir="/runs/test",
        )
        assert kwargs["imgsz"] == 320


# ============================================================================
# 4. Edge cases
# ============================================================================


class TestBuildValKwargsEdgeCases:
    """Test edge cases for build_val_kwargs."""

    def test_empty_output_dir_derives_from_model_path(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """When output_dir is empty, it should derive from model_path's parent."""
        from pathlib import Path

        model_path = str(Path("/runs/run_abc/train/weights/best.pt"))
        kwargs = adapter.build_val_kwargs(
            model_path=model_path,
            data_yaml="/data/data.yaml",
            output_dir="",
        )
        # project should be the parent directory of model_path
        expected_parent = str(Path("/runs/run_abc/train/weights"))
        assert kwargs["project"] == expected_parent

    def test_empty_output_dir_falls_back_to_model_path_parent(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """When output_dir is empty string, it should be derived from model_path."""
        from pathlib import Path

        model_path = str(Path("/foo/bar/best.pt"))
        kwargs = adapter.build_val_kwargs(
            model_path=model_path,
            data_yaml="/data/data.yaml",
            output_dir="",
        )
        assert kwargs["project"] == str(Path("/foo/bar"))

    def test_model_path_unchanged(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """model_path should NOT be in the kwargs (it's passed separately)."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="/runs/test",
        )
        assert "model_path" not in kwargs
        assert "model" not in kwargs


class TestBuildValKwargsTypeChecks:
    """Verify types of kwargs values."""

    def test_all_values_have_correct_types(
        self,
        adapter: UltralyticsValAdapter,
    ):
        """Ensure each kwargs value has the expected type."""
        kwargs = adapter.build_val_kwargs(
            model_path="/models/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="/runs/test",
        )
        assert isinstance(kwargs["data"], str)
        assert isinstance(kwargs["split"], str)
        assert isinstance(kwargs["batch"], int)
        assert isinstance(kwargs["imgsz"], int)
        assert isinstance(kwargs["device"], str)
        assert isinstance(kwargs["project"], str)
        assert isinstance(kwargs["name"], str)
        assert isinstance(kwargs["exist_ok"], bool)


__all__: list[str] = []

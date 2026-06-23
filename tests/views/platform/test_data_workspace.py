"""TDD: Data Workspace UI tests.

Tests for M2.7 Data Workspace: asset list display, tile/split parameter
inputs, DatasetBuild trigger, and parameter validation.
"""

from __future__ import annotations

import os
import sys
import pytest


# ---------------------------------------------------------------------------
# Non-GUI tests (runnable without QApplication)
# ---------------------------------------------------------------------------


class TestDatasetViewModel:
    """Unit tests for DatasetViewModel — no GUI required."""

    @pytest.fixture
    def vm(self):
        from anylabeling.views.platform.view_models.dataset_vm import DatasetViewModel

        return DatasetViewModel()

    def test_default_tile_width(self, vm):
        assert vm.tile_width == 1024

    def test_default_tile_height(self, vm):
        assert vm.tile_height == 1024

    def test_default_overlap_percent(self, vm):
        assert vm.overlap_percent == 20

    def test_default_split_seed(self, vm):
        assert vm.split_seed == 42

    def test_default_split_ratios(self, vm):
        assert vm.train_ratio == 0.7
        assert vm.val_ratio == 0.2
        assert vm.test_ratio == 0.1

    def test_set_tile_width(self, vm):
        vm.tile_width = 512
        assert vm.tile_width == 512

    def test_set_overlap_percent(self, vm):
        vm.overlap_percent = 10
        assert vm.overlap_percent == 10

    def test_overlap_to_pixels(self, vm):
        vm.tile_width = 1024
        vm.overlap_percent = 20
        assert vm.overlap_x_pixels == 204

    def test_overlap_pixels_zero_for_zero_percent(self, vm):
        vm.overlap_percent = 0
        assert vm.overlap_x_pixels == 0

    def test_can_build_requires_assets(self, vm):
        assert vm.can_build() is False

    def test_can_build_requires_task_spec(self, vm):
        vm.asset_count = 5
        assert vm.can_build() is False

    def test_can_build_true_when_prerequisites_met(self, vm):
        vm.asset_count = 5
        vm.task_spec_id = "test_task"
        assert vm.can_build() is True

    def test_split_ratios_sum_to_one(self, vm):
        total = vm.train_ratio + vm.val_ratio + vm.test_ratio
        assert abs(total - 1.0) < 0.001

    def test_invalid_tile_width_raises(self, vm):
        with pytest.raises(ValueError):
            vm.tile_width = 0

    def test_invalid_overlap_raises(self, vm):
        with pytest.raises(ValueError):
            vm.overlap_percent = 100

    def test_build_request_contains_required_fields(self, vm):
        vm.tile_width = 1024
        vm.tile_height = 1024
        vm.overlap_percent = 20
        vm.split_seed = 42
        vm.task_spec_id = "test_task"
        req = vm.build_request()
        assert "tile_width" in req
        assert "tile_height" in req
        assert "overlap_x" in req
        assert "overlap_y" in req
        assert "split_seed" in req
        assert "train_ratio" in req
        assert "val_ratio" in req
        assert "test_ratio" in req

    def test_build_request_overlap_in_pixels(self, vm):
        vm.tile_width = 640
        vm.tile_height = 640
        vm.overlap_percent = 25
        req = vm.build_request()
        assert req["overlap_x"] == 160
        assert req["overlap_y"] == 160


class TestDataWorkspaceHelpers:
    """Unit tests for helper functions."""

    def test_validate_split_ratios_valid(self):
        from anylabeling.views.platform.data_workspace import _validate_split_ratios

        assert len(_validate_split_ratios(0.7, 0.2, 0.1)) == 0

    def test_validate_split_ratios_not_sum_one(self):
        from anylabeling.views.platform.data_workspace import _validate_split_ratios

        assert len(_validate_split_ratios(0.5, 0.3, 0.1)) > 0

    def test_validate_split_ratios_zero_train(self):
        from anylabeling.views.platform.data_workspace import _validate_split_ratios

        assert len(_validate_split_ratios(0.0, 0.5, 0.5)) > 0


# ---------------------------------------------------------------------------
# GUI tests (skip if no display)
# ---------------------------------------------------------------------------

_HAS_DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@pytest.mark.skipif(not _HAS_DISPLAY, reason="Requires display")
class TestDataWorkspaceGUI:
    """GUI tests for DataWorkspace widget."""

    @pytest.fixture
    def workspace(self, qapp):
        from anylabeling.views.platform.data_workspace import DataWorkspace

        return DataWorkspace()

    def test_widget_created(self, workspace):
        from PyQt6.QtWidgets import QWidget

        assert isinstance(workspace, QWidget)

    def test_has_asset_list(self, workspace):
        assert workspace._asset_list is not None

    def test_has_tile_params_group(self, workspace):
        assert workspace._tile_group is not None

    def test_has_build_button(self, workspace):
        assert workspace._build_btn is not None

    def test_build_button_disabled_initially(self, workspace):
        assert not workspace._build_btn.isEnabled()

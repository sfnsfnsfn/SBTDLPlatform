"""TDD: Export Workspace UI tests."""

from __future__ import annotations

import os
import pytest


class TestExportWorkspaceImports:
    def test_module_importable(self):
        from anylabeling.views.platform import export_workspace  # noqa: F401


_HAS_DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@pytest.mark.skipif(not _HAS_DISPLAY, reason="Requires display")
class TestExportWorkspaceGUI:
    @pytest.fixture
    def workspace(self, qapp):
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        return ExportWorkspace()

    def test_widget(self, workspace):
        from PyQt6.QtWidgets import QWidget
        assert isinstance(workspace, QWidget)

    def test_export_btn(self, workspace):
        assert workspace._export_btn is not None

    def test_btn_disabled(self, workspace):
        assert not workspace._export_btn.isEnabled()

    def test_imgsz_sb(self, workspace):
        assert workspace._imgsz_sb is not None

    def test_simplify_cb(self, workspace):
        assert workspace._simplify_cb is not None

    def test_target_buttons_exist(self, workspace):
        """Phase 4: target environment buttons should exist."""
        assert hasattr(workspace, "_target_btns")
        assert len(workspace._target_btns) >= 2

    def test_compat_labels_exist(self, workspace):
        """Phase 4: compatibility check labels should exist."""
        assert hasattr(workspace, "_compat_labels")
        assert len(workspace._compat_labels) == 5

    def test_selftest_group_exists(self, workspace):
        """Phase 4: self-test section should exist."""
        assert hasattr(workspace, "_selftest_group")
        assert hasattr(workspace, "_selftest_progress")

    def test_completion_group_hidden(self, workspace):
        """Phase 4: completion page should be hidden initially."""
        assert hasattr(workspace, "_completion_group")
        assert not workspace._completion_group.isVisible()

    def test_format_label_exists(self, workspace):
        """Phase 4: format label should show ONNX only."""
        assert hasattr(workspace, "_format_label")

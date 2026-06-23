"""TDD: Export Workspace — Phase 4 ONNX-only tests."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

try:
    from PyQt6 import QtWidgets

    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

pytestmark = pytest.mark.skipif(not _HAS_PYQT, reason="PyQt6 not available")


def _make_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


@pytest.fixture
def mock_provider():
    """Create a mock AlgorithmProvider with export_adapter."""
    provider = MagicMock()
    export_adapter = MagicMock()
    export_adapter.get_supported_formats.return_value = ["onnx"]
    provider.export_adapter = export_adapter
    return provider


class TestExportWorkspacePhaseFour:
    def test_target_buttons_exist(self, mock_provider):
        """ExportWorkspace should have target environment buttons."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        app = _make_app()
        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_target_btns"), (
            "Should have target buttons dict"
        )
        assert len(widget._target_btns) >= 2
        widget.close()

    def test_default_target_is_onnx_generic(self, mock_provider):
        """onnx_generic target should be selected by default."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        app = _make_app()
        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert widget._selected_target == "onnx_generic"
        assert widget._target_btns["onnx_generic"].isChecked()
        widget.close()

    def test_simplify_cb_exists(self, mock_provider):
        """Simplify checkbox should still exist."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        app = _make_app()
        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_simplify_cb")
        assert widget._simplify_cb.isChecked()
        widget.close()

    def test_compatibility_labels_exist(self, mock_provider):
        """Compatibility check labels should exist."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        app = _make_app()
        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_compat_labels")
        assert len(widget._compat_labels) == 5
        widget.close()

    def test_selftest_section_exists(self, mock_provider):
        """Self-test section should exist."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        app = _make_app()
        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_selftest_group")
        assert hasattr(widget, "_selftest_progress")
        widget.close()

    def test_no_encrypt_widgets(self, mock_provider):
        """Encryption widgets should be removed in Phase 4."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        app = _make_app()
        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert not hasattr(widget, "_encrypt_model_cb")
        assert not hasattr(widget, "_encrypt_password_edit")
        widget.close()

    def test_no_format_checkboxes(self, mock_provider):
        """Multi-format checkboxes should be removed in Phase 4."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        app = _make_app()
        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert not hasattr(widget, "_format_checkboxes")
        widget.close()

    def test_export_btn_disabled_without_run(self, mock_provider):
        """Export button should be disabled when no run is selected."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        app = _make_app()
        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert not widget._export_btn.isEnabled()
        widget.close()

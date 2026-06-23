"""Phase 4 tests — ExportWorkspace ONNX-only + ModelRegistryService.

Coverage:
    1. Target environment selection (4 buttons, default, state update)
    2. Compatibility check indicators (5 checks, dash/checkmark)
    3. Deployment preview tree (10 items, PRD §7.10)
    4. Export options (labels.json, preprocess.json, no encrypt/inference)
    5. Self-test UI section (group, progress bar, result label)
    6. Completion page (hidden to visible, field population)
    7. Delivery package structure (10 items)
    8. Auto-register checkbox
    9. ModelRegistryService register / list / unregister
    10. ExportService ONNX-only (default format, empty formats error)
    11. ONNX self-test (missing ort, missing model, all pass)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

try:
    from PyQt6 import QtWidgets

    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

pytestmark = pytest.mark.skipif(not _HAS_PYQT, reason="PyQt6 not available")


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    export_adapter = MagicMock()
    export_adapter.get_supported_formats.return_value = ["onnx"]
    provider.export_adapter = export_adapter
    return provider


# -- Target environment selection --


class TestTargetEnvironmentSelection:
    """Test target environment selector per PRD §7.10."""

    def test_target_buttons_exist(self, mock_provider, qapp):
        """All 4 target buttons should be created."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_target_btns")
        btn_ids = list(widget._target_btns.keys())
        expected = [
            "onnx_generic",
            "windows_cpu",
            "platform_prelabel",
            "custom",
        ]
        for tid in expected:
            assert tid in btn_ids, f"Missing target button: {tid}"
        assert len(btn_ids) == 4
        widget.close()

    def test_default_target_is_onnx_generic(self, mock_provider, qapp):
        """onnx_generic should be checked by default."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert widget._target_btns["onnx_generic"].isChecked()
        assert widget._selected_target == "onnx_generic"
        widget.close()

    def test_target_selection_updates_state(self, mock_provider, qapp):
        """Clicking a different target should update _selected_target."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        widget._target_btns["windows_cpu"].click()
        assert widget._selected_target == "windows_cpu"
        assert not widget._target_btns["onnx_generic"].isChecked()
        assert widget._target_btns["windows_cpu"].isChecked()
        widget.close()


# -- Compatibility check --


class TestCompatibilityCheck:
    """Test compatibility check indicators."""

    def test_all_five_checks_exist(self, mock_provider, qapp):
        """5 compatibility check labels should exist."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_compat_labels")
        expected_keys = {
            "task_support",
            "weight_integrity",
            "input_size",
            "labels",
            "pre_post",
        }
        assert set(widget._compat_labels.keys()) == expected_keys
        widget.close()

    def test_checks_show_dash_when_no_run(self, mock_provider, qapp):
        """When no run is selected, checks should show em-dash."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        for check_id, icon in widget._compat_labels.items():
            assert icon.text() == chr(0x2014), (
                f"Check {check_id!r} should show em-dash, got {icon.text()!r}"
            )
        widget.close()


# -- Deploy preview tree --


class TestDeployPreviewTree:
    """Test the deploy preview tree widget."""

    def test_deploy_preview_tree_exists(self, mock_provider):
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_deploy_tree")
        assert isinstance(widget._deploy_tree, QtWidgets.QTreeWidget)
        widget.close()

    def test_deploy_preview_shows_expected_files(self, mock_provider, qapp):
        """Deploy preview should list key deployment files."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        tree = widget._deploy_tree
        assert tree.topLevelItemCount() > 0

        def collect_texts(item, acc):
            acc.append(item.text(0))
            for i in range(item.childCount()):
                collect_texts(item.child(i), acc)

        all_texts: list[str] = []
        for i in range(tree.topLevelItemCount()):
            collect_texts(tree.topLevelItem(i), all_texts)

        expected_items = [
            "deployment/",
            "model.onnx",
            "labels.json",
            "preprocess.json",
            "postprocess.json",
            "model_manifest.json",
            "checksum.sha256",
            "validation_report.json",
            "sample/input.png",
            "sample/output.png",
            "README",
        ]
        for expected in expected_items:
            assert any(expected in t for t in all_texts), (
                f"Missing {expected!r} in deploy tree"
            )
        widget.close()


# -- Export options --


class TestExportOptions:
    """Test export options UI — Phase 4 ONNX-only, no encrypt/inference."""

    def test_export_options_exist(self, mock_provider):
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_include_labels_cb")
        assert hasattr(widget, "_include_preprocess_cb")
        widget.close()

    def test_include_options_checked_by_default(self, mock_provider):
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert widget._include_labels_cb.isChecked()
        assert widget._include_preprocess_cb.isChecked()
        widget.close()

    def test_no_inference_checkbox(self, mock_provider, qapp):
        """inference.py was removed in Phase 4."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert not hasattr(widget, "_include_inference_cb")
        widget.close()

    def test_no_encrypt_checkbox(self, mock_provider, qapp):
        """Encryption was removed in Phase 4."""
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert not hasattr(widget, "_encrypt_model_cb")
        assert not hasattr(widget, "_encrypt_password_edit")
        widget.close()


# -- Self-test section --


class TestSelfTestSection:
    """Test the ONNX self-test UI section."""

    def test_selftest_group_exists(self, mock_provider):
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_selftest_group")
        assert isinstance(widget._selftest_group, QtWidgets.QGroupBox)
        widget.close()

    def test_progress_bar_initially_hidden(self, mock_provider):
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_selftest_progress")
        assert not widget._selftest_progress.isVisible()
        widget.close()

    def test_result_label_initially_hidden(self, mock_provider):
        from anylabeling.views.platform.export_workspace import ExportWorkspace

        widget = ExportWorkspace()
        widget.set_provider(mock_provider)
        assert hasattr(widget, "_selftest_result")
        assert not widget._selftest_result.isVisible()
        widget.close()

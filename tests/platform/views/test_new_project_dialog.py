"""Tests for NewProjectDialog (Phase B — lightweight version).

Coverage:
    1. Default template is "defect"
    2. Template change updates key
    3. Empty project name blocks creation
    4. Invalid directory blocks creation
    5. get_result() returns (name, parent_dir, description, template_key)
    6. "Configure Later" template returns None as template_key
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# If PyQt6 is not available, skip all GUI tests.
try:
    from PyQt6 import QtWidgets
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

if _HAS_PYQT:
    from anylabeling.views.platform.new_project_dialog import (
        NewProjectDialog,
        _TEMPLATE_PRESETS,
        _TEMPLATE_KEYS,
    )


pytestmark = pytest.mark.skipif(not _HAS_PYQT, reason="PyQt6 not available")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app():
    """Create a QApplication if one doesn't exist."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


def _enter_name(dialog: NewProjectDialog, name: str):
    dialog._name_edit.setText(name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNewProjectDialogDefaults:
    """Tests for initial dialog state."""

    def test_default_template_is_defect(self):
        """Dialog initializes with Defect detection template selected."""
        app = _make_app()
        dialog = NewProjectDialog()
        assert dialog._current_template_key == "defect"
        dialog.close()

    def test_has_five_templates(self):
        """Dialog has 5 template options."""
        assert len(_TEMPLATE_KEYS) == 5
        assert "defect" in _TEMPLATE_KEYS
        assert "ocr" in _TEMPLATE_KEYS
        assert "detection" in _TEMPLATE_KEYS
        assert "classification" in _TEMPLATE_KEYS
        assert "later" in _TEMPLATE_KEYS


class TestTemplateSwitching:
    """Tests for template radio behavior."""

    def test_switch_to_ocr_updates_key(self):
        """Selecting OCR updates _current_template_key."""
        app = _make_app()
        dialog = NewProjectDialog()
        ocr_idx = _TEMPLATE_KEYS.index("ocr")
        dialog._on_template_changed(ocr_idx)
        assert dialog._current_template_key == "ocr"
        dialog.close()

    def test_switch_to_later_updates_key(self):
        """Selecting 'Configure Later' updates key."""
        app = _make_app()
        dialog = NewProjectDialog()
        later_idx = _TEMPLATE_KEYS.index("later")
        dialog._on_template_changed(later_idx)
        assert dialog._current_template_key == "later"
        dialog.close()


class TestValidation:
    """Tests for input validation before creation."""

    def test_empty_name_rejected(self):
        """Empty project name shows warning and does not accept."""
        app = _make_app()
        dialog = NewProjectDialog()
        _enter_name(dialog, "")

        with patch.object(QtWidgets.QMessageBox, "warning") as mock_warn:
            dialog._on_create()
            assert mock_warn.called
            assert dialog.result() != QtWidgets.QDialog.DialogCode.Accepted
        dialog.close()

    def test_invalid_dir_rejected(self):
        """Non-existent directory shows warning and does not accept."""
        app = _make_app()
        dialog = NewProjectDialog()
        dialog._parent_dir = "/nonexistent/path/xyz"
        _enter_name(dialog, "test_project")

        with patch.object(QtWidgets.QMessageBox, "warning") as mock_warn:
            dialog._on_create()
            assert mock_warn.called
            assert dialog.result() != QtWidgets.QDialog.DialogCode.Accepted
        dialog.close()

    def test_no_labels_always_accepted(self):
        """Empty labels NO LONGER blocks creation (labels optional in new flow)."""
        app = _make_app()
        dialog = NewProjectDialog()
        _enter_name(dialog, "test_project")
        dialog._parent_dir = os.path.expanduser("~")

        # Should accept without any labels
        dialog._on_create()
        assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted
        dialog.close()


class TestGetResult:
    """Tests for get_result() return value."""

    def test_get_result_returns_4_tuple(self):
        """Accepted dialog returns (name, parent_dir, description, template_key)."""
        app = _make_app()
        dialog = NewProjectDialog()
        _enter_name(dialog, "my_defect_project")
        dialog._parent_dir = os.path.expanduser("~")
        dialog._desc_edit.setPlainText("A defect detection project")

        dialog.accept()
        result = dialog.get_result()

        assert result is not None
        name, parent_dir, description, template_key = result
        assert name == "my_defect_project"
        assert isinstance(parent_dir, str)
        assert description == "A defect detection project"
        assert template_key == "defect"
        dialog.close()

    def test_get_result_ocr_template(self):
        """OCR template returns 'ocr' as template_key."""
        app = _make_app()
        dialog = NewProjectDialog()
        _enter_name(dialog, "my_ocr_project")
        dialog._parent_dir = os.path.expanduser("~")

        ocr_idx = _TEMPLATE_KEYS.index("ocr")
        dialog._on_template_changed(ocr_idx)

        dialog.accept()
        result = dialog.get_result()

        assert result is not None
        _, _, _, template_key = result
        assert template_key == "ocr"
        dialog.close()

    def test_get_result_later_returns_none_template(self):
        """'Configure Later' template returns None template_key."""
        app = _make_app()
        dialog = NewProjectDialog()
        _enter_name(dialog, "my_project")
        dialog._parent_dir = os.path.expanduser("~")

        later_idx = _TEMPLATE_KEYS.index("later")
        dialog._on_template_changed(later_idx)

        dialog.accept()
        result = dialog.get_result()

        assert result is not None
        _, _, _, template_key = result
        assert template_key is None
        dialog.close()

    def test_get_result_detection_template(self):
        """Detection template returns 'detection' as template_key."""
        app = _make_app()
        dialog = NewProjectDialog()
        _enter_name(dialog, "my_detection_project")
        dialog._parent_dir = os.path.expanduser("~")

        det_idx = _TEMPLATE_KEYS.index("detection")
        dialog._on_template_changed(det_idx)

        dialog.accept()
        result = dialog.get_result()

        assert result is not None
        _, _, _, template_key = result
        assert template_key == "detection"
        dialog.close()


class TestTemplatePresets:
    """Tests for _TEMPLATE_PRESETS configuration."""

    def test_all_presets_have_required_keys(self):
        """Every preset has family, display_zh, display_en."""
        required = {"family", "display_zh", "display_en"}
        for key, preset in _TEMPLATE_PRESETS.items():
            missing = required - set(preset.keys())
            assert not missing, f"Preset '{key}' missing: {missing}"

    def test_defect_preset_is_detection_hbb(self):
        """Defect preset maps to detection_hbb family."""
        assert _TEMPLATE_PRESETS["defect"]["family"] == "detection_hbb"

    def test_ocr_preset_is_ocr(self):
        """OCR preset maps to ocr family."""
        assert _TEMPLATE_PRESETS["ocr"]["family"] == "ocr"

    def test_later_preset_has_null_family(self):
        """'Configure Later' preset has None family."""
        assert _TEMPLATE_PRESETS["later"]["family"] is None

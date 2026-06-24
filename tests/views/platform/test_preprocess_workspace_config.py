"""TDD tests for A0-4: Disabled augmentations not written to build config."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# QApplication helper (borrowed from test_train_workspace.py)
# ---------------------------------------------------------------------------


def _qapp_available() -> bool:
    """Return True if QApplication can be instantiated."""
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            # On Windows, QApplication can typically be created without DISPLAY
            # Try creating one to see if it works
            import os

            if os.name == "nt":
                return True
            if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                return True
            return False
        return True
    except ImportError:
        return False


def _create_qapp():
    """Create a QApplication instance if one doesn't exist."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


_HAS_QAPP = _qapp_available()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    if not _HAS_QAPP:
        pytest.skip("Requires QApplication")
    return _create_qapp()


@pytest.fixture
def workspace(qapp):
    from anylabeling.views.platform.preprocess_workspace import (
        PreprocessWorkspace,
    )

    return PreprocessWorkspace()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDisabledAugmentationNotInConfig:
    """A0-4: Disabled augmentation checkboxes must not write to config."""

    def test_default_augmentations_empty(self, workspace):
        """A0-4: Default config should have empty augmentations."""
        config = workspace._get_current_config()
        assert (
            len(config.augmentations) == 0
        ), f"Expected empty augmentations, got: {config.augmentations}"

    def test_all_augmentation_checkboxes_disabled(self, workspace):
        """A0-4: All augmentation checkboxes should be disabled."""
        assert not workspace._hflip_cb.isEnabled()
        assert not workspace._vflip_cb.isEnabled()
        assert not workspace._brightness_cb.isEnabled()
        assert not workspace._rotate_cb.isEnabled()

    def test_all_augmentation_checkboxes_unchecked(self, workspace):
        """A0-4: All disabled augmentation checkboxes should be unchecked."""
        assert not workspace._hflip_cb.isChecked(), "hflip should be unchecked"
        assert not workspace._vflip_cb.isChecked(), "vflip should be unchecked"
        assert (
            not workspace._brightness_cb.isChecked()
        ), "brightness should be unchecked"
        assert (
            not workspace._rotate_cb.isChecked()
        ), "rotate should be unchecked"

    def test_augmentation_tooltips_mention_planned(self, workspace):
        """A0-4: Disabled augmentation tooltips should indicate planned status."""
        tooltip = workspace._hflip_cb.toolTip()
        assert (
            "planned" in tooltip.lower() or "规划中" in tooltip
        ), f"Tooltip should indicate planned status, got: {tooltip}"

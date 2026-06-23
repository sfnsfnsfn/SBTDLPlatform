"""Tests for ErrorBanner widget."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))


def _qapp_available() -> bool:
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                return True
            return False
        return True
    except ImportError:
        return False


def _create_qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


_HAS_QAPP = _qapp_available()
skip_without_display = pytest.mark.skipif(
    not _HAS_QAPP, reason="Requires display (QApplication)"
)


class TestErrorBanner:
    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        return _create_qapp()

    @pytest.fixture
    def banner(self, qapp):
        from anylabeling.views.platform.shell.error_banner import ErrorBanner
        return ErrorBanner()

    def test_banner_starts_hidden(self, banner):
        assert not banner.isVisible()

    def test_show_error_makes_visible(self, banner):
        banner.show_error("Test Error", "what", "impact", "fix")
        assert banner.isVisible()

    def test_show_warning_makes_visible(self, banner):
        banner.show_warning("Warning", "Be careful")
        assert banner.isVisible()

    def test_show_info_makes_visible(self, banner):
        banner.show_info("Info", "FYI")
        assert banner.isVisible()

    def test_dismiss_hides_and_emits(self, banner):
        banner.show_error("Err", "what", "impact", "fix")
        dismissed = []
        banner.dismissed.connect(lambda: dismissed.append(True))
        banner.dismiss()
        assert not banner.isVisible()
        assert len(dismissed) == 1

    def test_clear_hides_without_signal(self, banner):
        banner.show_error("Err", "what", "impact", "fix")
        dismissed = []
        banner.dismissed.connect(lambda: dismissed.append(True))
        banner.clear()
        assert not banner.isVisible()
        assert len(dismissed) == 0

    def test_toggle_button_hidden_without_traceback(self, banner):
        banner.show_error("Err", "what", "impact", "fix", traceback="")
        assert not banner._toggle_btn.isVisible()

    def test_toggle_button_visible_with_traceback(self, banner):
        banner.show_error("Err", "what", "impact", "fix", traceback="tb")
        assert banner._toggle_btn.isVisible()

    def test_traceback_toggle_expands(self, banner):
        banner.show_error("Err", "what", "impact", "fix", traceback="tb")
        assert not banner._traceback_edit.isVisible()
        banner._on_toggle_traceback()
        assert banner._traceback_edit.isVisible()

    def test_retry_button_emits_signal(self, banner):
        banner.show_error("Err", "what", "impact", "fix", retry_action="Retry")
        retries = []
        banner.retry_requested.connect(lambda: retries.append(True))
        assert banner._retry_btn.isVisible()
        banner._retry_btn.click()
        assert len(retries) == 1

    def test_retry_button_hidden_without_action(self, banner):
        banner.show_error("Err", "what", "impact", "fix")
        assert not banner._retry_btn.isVisible()

    def test_second_error_replaces_first(self, banner):
        banner.show_error("First", "w1", "i1", "f1")
        banner.show_error("Second", "w2", "i2", "f2")
        assert banner.isVisible()
        assert "Second" in banner._title_label.text()

"""Tests for TaskCenterDrawer widget."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

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


class TestTaskCenterDrawer:
    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        return _create_qapp()

    @pytest.fixture
    def drawer(self, qapp):
        from anylabeling.views.platform.shell.task_center_drawer import (
            TaskCenterDrawer,
        )
        return TaskCenterDrawer()

    @pytest.fixture
    def mock_job_service(self):
        service = MagicMock()
        service.list_jobs.return_value = [
            {"job_id": "job_001_abcdef", "job_kind": "training", "state": "running"},
            {"job_id": "job_002_ghijkl", "job_kind": "export", "state": "completed"},
            {"job_id": "job_003_mnopqr", "job_kind": "evaluation", "state": "failed"},
            {"job_id": "job_004_stuvwx", "job_kind": "inference", "state": "queued"},
        ]
        return service

    def test_drawer_starts_hidden(self, drawer):
        assert not drawer.is_visible()

    def test_show_drawer_starts_polling(self, drawer, mock_job_service):
        drawer.set_job_service(mock_job_service)
        drawer.show_drawer()
        assert drawer.is_visible()
        assert drawer._poll_timer.isActive()

    def test_hide_drawer_stops_polling(self, drawer, mock_job_service):
        drawer.set_job_service(mock_job_service)
        drawer.show_drawer()
        drawer.hide_drawer()
        assert not drawer.is_visible()
        assert not drawer._poll_timer.isActive()

    def test_toggle_switches_visibility(self, drawer, mock_job_service):
        drawer.set_job_service(mock_job_service)
        drawer.toggle()
        assert drawer.is_visible()
        drawer.toggle()
        assert not drawer.is_visible()

    def test_set_job_service_none_clears(self, drawer, mock_job_service):
        drawer.set_job_service(mock_job_service)
        drawer.show_drawer()
        drawer.set_job_service(None)
        assert drawer._jobs == []

    def test_refresh_renders_jobs(self, drawer, mock_job_service):
        drawer.set_job_service(mock_job_service)
        drawer._refresh()
        assert len(drawer._jobs) == 4

    def test_filter_all_shows_all(self, drawer, mock_job_service):
        drawer.set_job_service(mock_job_service)
        drawer._refresh()
        filtered = drawer._filter_jobs(drawer._jobs)
        assert len(filtered) == 4

    def test_filter_running(self, drawer):
        jobs = [{"job_id": "1", "state": "running"}, {"job_id": "2", "state": "completed"}]
        drawer._active_filter = "running"
        filtered = drawer._filter_jobs(jobs)
        assert len(filtered) == 1
        assert filtered[0]["job_id"] == "1"

    def test_filter_failed(self, drawer):
        jobs = [
            {"job_id": "1", "state": "failed"},
            {"job_id": "2", "state": "cancelled"},
            {"job_id": "3", "state": "completed"},
        ]
        drawer._active_filter = "failed"
        filtered = drawer._filter_jobs(jobs)
        assert len(filtered) == 2

    def test_cancel_button_emits_signal(self, drawer, mock_job_service):
        drawer.set_job_service(mock_job_service)
        cancelled = []
        drawer.job_cancel_requested.connect(lambda jid: cancelled.append(jid))
        drawer._on_cancel_job("job_001")
        assert cancelled == ["job_001"]

    def test_retry_button_emits_signal(self, drawer):
        retries = []
        drawer.job_retry_requested.connect(lambda jid: retries.append(jid))
        drawer._on_retry_job("job_003")
        assert retries == ["job_003"]

    def test_clear_completed_removes_from_display(self, drawer, mock_job_service):
        drawer.set_job_service(mock_job_service)
        drawer._refresh()
        drawer._on_clear_completed()
        remaining_states = {j.get("state") for j in drawer._jobs}
        assert "completed" not in remaining_states
        assert "failed" not in remaining_states

    def test_closed_signal_emitted(self, drawer):
        closed = []
        drawer.drawer_closed.connect(lambda: closed.append(True))
        drawer.show_drawer()
        drawer.hide_drawer()
        assert len(closed) == 1

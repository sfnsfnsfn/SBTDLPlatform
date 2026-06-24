"""Tests for F2-2: PreprocessWorkspace reads/writes dataset_builds via ProjectContext."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# QApplication helper
# ---------------------------------------------------------------------------


def _qapp_available() -> bool:
    """Return True if QApplication can be instantiated."""
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
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
# Fake sqlite3.Row helper
# ---------------------------------------------------------------------------


class FakeRow:
    """Fake sqlite3.Row that supports dict-style access for testing."""

    def __init__(self, **kwargs):
        self._data = kwargs

    def __getitem__(self, key):
        return self._data[key]


class FakeDatasetBuildRecord:
    """Minimal stand-in for DatasetBuildRecord when the module is unavailable.

    Exposes only the fields that PreprocessWorkspace._load_history_from_db
    accesses from ``list_completed()`` results.
    """

    def __init__(
        self,
        id: str,
        task_family: str = "detection_hbb",
        output_path: str = "",
        status: str = "completed",
        completed_at: str | None = None,
        created_at: str | None = None,
    ):
        self.id = id
        self.task_family = task_family
        self.output_path = output_path
        self.status = status
        self.completed_at = completed_at
        self.created_at = created_at


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPreprocessWorkspaceDbHistory:
    """F2-2: PreprocessWorkspace reads/writes dataset_builds via ProjectContext."""

    # ------------------------------------------------------------------
    # test_set_context_stores_reference
    # ------------------------------------------------------------------

    def test_set_context_stores_reference(self, workspace):
        """set_context should store the context reference."""
        context = MagicMock()
        workspace.set_context(context)
        assert workspace._context is context

    # ------------------------------------------------------------------
    # test_completed_builds_appear_in_history
    # ------------------------------------------------------------------

    def test_completed_builds_appear_in_history(
        self, workspace, tmp_path
    ):
        """Completed builds from DB should appear in the history table."""
        build_id = "build_completed_001"
        output_path = str(
            tmp_path / "dataset_builds" / "build_completed_001"
        )

        completed_record = FakeDatasetBuildRecord(
            id=build_id,
            task_family="detection_hbb",
            output_path=output_path,
            status="completed",
            completed_at="2026-06-24T10:00:00",
            created_at="2026-06-24T09:00:00",
        )

        context = MagicMock()
        context.dataset_builds.list_completed.return_value = [
            completed_record
        ]
        context.db.query_all.return_value = []

        workspace.set_context(context)
        workspace._refresh_history()

        # Should have one row for the completed build
        assert workspace._history_table.rowCount() == 1

        # Build ID in first column
        id_item = workspace._history_table.item(0, 0)
        assert id_item is not None
        assert build_id in id_item.text()

        # Status should show "Ready"
        status_item = workspace._history_table.item(0, 4)
        assert status_item is not None
        assert "Ready" in status_item.text() or "就绪" in status_item.text()

    # ------------------------------------------------------------------
    # test_failed_build_shows_error_not_for_training
    # ------------------------------------------------------------------

    def test_failed_build_shows_error_not_for_training(
        self, workspace, tmp_path
    ):
        """Failed builds from DB should be visible but marked not available."""
        from PyQt6 import QtWidgets

        build_id = "build_failed_001"
        output_path = str(
            tmp_path / "dataset_builds" / "build_failed_001"
        )

        context = MagicMock()
        context.dataset_builds.list_completed.return_value = []

        # Simulate a failed build row from the DB
        failed_row = FakeRow(
            id=build_id,
            output_path=output_path,
            completed_at="2026-06-24T10:30:00",
            created_at="2026-06-24T09:30:00",
            error_message="OOM during materialization",
        )
        context.db.query_all.return_value = [failed_row]

        workspace.set_context(context)
        workspace._refresh_history()

        # Failed build should appear in the table
        assert workspace._history_table.rowCount() >= 1

        id_item = workspace._history_table.item(0, 0)
        assert id_item is not None
        assert build_id in id_item.text()

        # Status should show "Failed"
        status_item = workspace._history_table.item(0, 4)
        assert status_item is not None
        assert (
            "Failed" in status_item.text() or "失败" in status_item.text()
        )

        # "Use Config" button should be visible but disabled
        actions_widget = workspace._history_table.cellWidget(0, 5)
        assert actions_widget is not None

        use_btn = actions_widget.findChild(QtWidgets.QPushButton)
        assert use_btn is not None
        assert not use_btn.isEnabled()

        # Tooltip should indicate it's not available for training
        tooltip = use_btn.toolTip().lower()
        assert "not available" in tooltip or "训练" in tooltip

    # ------------------------------------------------------------------
    # test_no_context_fallback
    # ------------------------------------------------------------------

    def test_no_context_fallback(self, workspace, tmp_path):
        """Without context, workspace falls back to filesystem-based history."""
        builds_dir = tmp_path / "dataset_builds"
        build_dir = builds_dir / "build_fs_001"
        build_dir.mkdir(parents=True, exist_ok=True)

        build_json_path = build_dir / "build.json"
        build_json_path.write_text(
            json.dumps({
                "id": "build_fs_001",
                "created_at": "2026-06-24T10:00:00",
            }),
            encoding="utf-8",
        )

        # _READY marker signals completed build
        (build_dir / "_READY").write_text("ok\n", encoding="utf-8")

        workspace.set_project_path(str(tmp_path))
        # No context set — should fall back to filesystem
        workspace._refresh_history()

        assert workspace._history_table.rowCount() == 1

        id_item = workspace._history_table.item(0, 0)
        assert id_item is not None
        assert "build_fs_001" in id_item.text()

        # Status should show "Ready"
        status_item = workspace._history_table.item(0, 4)
        assert status_item is not None
        assert "Ready" in status_item.text() or "就绪" in status_item.text()

    # ------------------------------------------------------------------
    # test_context_takes_priority_over_project_path
    # ------------------------------------------------------------------

    def test_context_takes_priority_over_project_path(
        self, workspace, tmp_path
    ):
        """When both context and project_path are set, context takes priority.

        DB-backed builds should appear, not filesystem builds.
        """
        # --- Filesystem setup: a completed build (should be ignored) ---
        builds_dir = tmp_path / "dataset_builds"
        fs_build_dir = builds_dir / "build_fs_ignored"
        fs_build_dir.mkdir(parents=True, exist_ok=True)
        (fs_build_dir / "build.json").write_text(
            json.dumps({
                "id": "build_fs_ignored",
                "created_at": "2026-06-24T09:00:00",
            }),
            encoding="utf-8",
        )
        (fs_build_dir / "_READY").write_text("ok\n", encoding="utf-8")

        # --- DB setup: a completed build ---
        db_build_id = "build_from_db_001"
        db_output_path = str(
            tmp_path / "dataset_builds" / "build_from_db_001"
        )

        context = MagicMock()
        context.dataset_builds.list_completed.return_value = [
            FakeDatasetBuildRecord(
                id=db_build_id,
                task_family="detection_hbb",
                output_path=db_output_path,
                status="completed",
                completed_at="2026-06-24T11:00:00",
            )
        ]
        context.db.query_all.return_value = []

        # Set both project_path AND context
        workspace.set_project_path(str(tmp_path))
        workspace.set_context(context)
        workspace._refresh_history()

        # Should see only the DB-backed build
        assert workspace._history_table.rowCount() == 1

        id_item = workspace._history_table.item(0, 0)
        assert id_item is not None
        assert db_build_id in id_item.text()
        assert "build_fs_ignored" not in id_item.text()

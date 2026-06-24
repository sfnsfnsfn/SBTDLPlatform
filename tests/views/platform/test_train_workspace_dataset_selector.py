"""Tests for F2-3: TrainWorkspace dataset selector only lists completed builds from DB.

Test strategy:
- All tests require QApplication (GUI widget interaction)
- Uses mocked ProjectContext with SQLiteDatasetBuildRepository stub
- Verifies that only completed builds appear in the dataset combo
- Verifies that empty completed-builds list disables the Start button
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def qapp():
    if not _HAS_QAPP:
        pytest.skip("Requires QApplication")
    app = _create_qapp()
    yield app


@pytest.fixture
def workspace(qapp):
    """A bare TrainWorkspace without any context set."""
    from anylabeling.views.platform.train_workspace import TrainWorkspace

    return TrainWorkspace()


@pytest.fixture
def completed_build():
    """A DatasetBuildRecord with status='completed'."""
    from anylabeling.platform.domain.records import DatasetBuildRecord

    return DatasetBuildRecord(
        id="build_completed_v1",
        task_family="detection_hbb",
        output_path="/tmp/builds/completed_v1",
        status="completed",
        completed_at="2026-06-24T10:00:00",
    )


@pytest.fixture
def failed_build():
    """A DatasetBuildRecord with status='failed'."""
    from anylabeling.platform.domain.records import DatasetBuildRecord

    return DatasetBuildRecord(
        id="build_failed_v1",
        task_family="detection_hbb",
        output_path="/tmp/builds/failed_v1",
        status="failed",
        completed_at="2026-06-24T09:00:00",
        error_message="Something went wrong",
    )


@pytest.fixture
def running_build():
    """A DatasetBuildRecord with status='running'."""
    from anylabeling.platform.domain.records import DatasetBuildRecord

    return DatasetBuildRecord(
        id="build_running_v1",
        task_family="detection_hbb",
        output_path="/tmp/builds/running_v1",
        status="running",
    )


@pytest.fixture
def pending_build():
    """A DatasetBuildRecord with status='pending'."""
    from anylabeling.platform.domain.records import DatasetBuildRecord

    return DatasetBuildRecord(
        id="build_pending_v1",
        task_family="detection_hbb",
        output_path="/tmp/builds/pending_v1",
        status="pending",
    )


def _make_mock_context(records: list) -> MagicMock:
    """Create a mock ProjectContext whose dataset_builds.list_completed()
    returns the given records."""
    mock_repo = MagicMock()
    mock_repo.list_completed.return_value = records
    ctx = MagicMock()
    ctx.dataset_builds = mock_repo
    return ctx


# ============================================================================
# Tests
# ============================================================================


class TestDatasetSelectorF2:
    """Tests for F2-3: DB-backed dataset selector in TrainWorkspace."""

    # ------------------------------------------------------------------
    # 1. Completed build appears in selector
    # ------------------------------------------------------------------

    def test_completed_build_appears_in_selector(
        self, workspace, completed_build,
    ):
        """A completed DatasetBuildRecord appears in the dataset combo."""
        ctx = _make_mock_context([completed_build])
        workspace.set_context(ctx)

        assert workspace._combo_dataset.count() == 1
        item_data = workspace._combo_dataset.itemData(0)
        assert item_data is completed_build
        assert workspace._combo_dataset.currentText() == "build_completed_v1"

    # ------------------------------------------------------------------
    # 2. Failed build excluded from selector
    # ------------------------------------------------------------------

    def test_failed_build_excluded_from_selector(
        self, workspace, completed_build, failed_build,
    ):
        """A failed DatasetBuildRecord must NOT appear in the dataset combo
        (only completed builds are returned by list_completed)."""
        ctx = _make_mock_context([completed_build])
        workspace.set_context(ctx)

        assert workspace._combo_dataset.count() == 1
        item_data = workspace._combo_dataset.itemData(0)
        assert item_data is completed_build
        assert item_data.id != failed_build.id

    # ------------------------------------------------------------------
    # 3. Running build excluded from selector
    # ------------------------------------------------------------------

    def test_running_build_excluded_from_selector(
        self, workspace, completed_build, running_build,
    ):
        """A running DatasetBuildRecord must NOT appear in the dataset combo."""
        ctx = _make_mock_context([completed_build])
        workspace.set_context(ctx)

        assert workspace._combo_dataset.count() == 1
        item_data = workspace._combo_dataset.itemData(0)
        assert item_data is completed_build
        assert item_data.id != running_build.id

    # ------------------------------------------------------------------
    # 4. No completed builds disables Start button
    # ------------------------------------------------------------------

    def test_no_completed_builds_disables_start(
        self, workspace,
    ):
        """When list_completed() returns an empty list, the dataset combo
        is empty and the Start button must be disabled with the expected
        tooltip."""
        ctx = _make_mock_context([])
        workspace.set_context(ctx)

        assert workspace._combo_dataset.count() == 0
        assert not workspace._btn_start.isEnabled()
        tooltip = workspace._btn_start.toolTip()
        assert "No completed dataset builds" in tooltip

    # ------------------------------------------------------------------
    # 5. set_context stores reference
    # ------------------------------------------------------------------

    def test_set_context_stores_reference(
        self, workspace,
    ):
        """set_context stores the context object on the workspace."""
        ctx = _make_mock_context([])
        workspace.set_context(ctx)
        assert workspace._context is ctx

    # ------------------------------------------------------------------
    # 6. Pending build excluded from selector
    # ------------------------------------------------------------------

    def test_pending_build_excluded_from_selector(
        self, workspace, completed_build, pending_build,
    ):
        """A pending DatasetBuildRecord must NOT appear in the dataset combo."""
        ctx = _make_mock_context([completed_build])
        workspace.set_context(ctx)

        assert workspace._combo_dataset.count() == 1
        item_data = workspace._combo_dataset.itemData(0)
        assert item_data is completed_build
        assert item_data.id != pending_build.id

    # ------------------------------------------------------------------
    # 7. Multiple completed builds all appear
    # ------------------------------------------------------------------

    def test_multiple_completed_builds_appear(
        self, workspace,
    ):
        """Multiple completed builds all appear in the dataset combo."""
        from anylabeling.platform.domain.records import DatasetBuildRecord

        builds = [
            DatasetBuildRecord(
                id=f"build_v{i}",
                task_family="detection_hbb",
                output_path=f"/tmp/builds/v{i}",
                status="completed",
            )
            for i in range(3)
        ]
        ctx = _make_mock_context(builds)
        workspace.set_context(ctx)

        assert workspace._combo_dataset.count() == 3
        for i in range(3):
            assert workspace._combo_dataset.itemData(i).id == f"build_v{i}"

    # ------------------------------------------------------------------
    # 8. Context is None preserves existing behavior
    # ------------------------------------------------------------------

    def test_set_context_none_does_not_populate(
        self, workspace,
    ):
        """When set_context is called with None, the dataset combo remains
        empty (no DB query is performed)."""
        workspace.set_context(None)
        assert workspace._combo_dataset.count() == 0

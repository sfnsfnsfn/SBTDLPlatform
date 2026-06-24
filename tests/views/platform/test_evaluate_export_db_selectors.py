"""Tests for F2-4: EvaluateWorkspace and ExportWorkspace use DB selectors.

Both workspaces gain a ``set_context(context)`` method that stores the
context reference and triggers selector population from the database
rather than the filesystem.

- EvaluateWorkspace: ``context.runs.list_completed()``
- ExportWorkspace:  ``context.models.list_ready()``
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


def _qapp_available() -> bool:
    """Return True if QApplication can be instantiated."""
    try:
        from PyQt6.QtWidgets import QApplication  # noqa: F401

        app = QApplication.instance()
        if app is not None:
            return True
        QApplication(sys.argv)
        return True
    except Exception:
        return False


_HAS_QAPP = _qapp_available()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication instance for the session (skip if unavailable)."""
    if not _HAS_QAPP:
        pytest.skip("Requires QApplication")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def mock_context():
    """Create a mock ProjectContext with empty repository stubs."""
    ctx = MagicMock()
    ctx.runs.list_completed.return_value = []
    ctx.models.list_ready.return_value = []
    return ctx


# ---------------------------------------------------------------------------
# EvaluateWorkspace tests
# ---------------------------------------------------------------------------


class TestEvaluateWorkspaceDB:
    """EvaluateWorkspace uses context.runs.list_completed()."""

    @pytest.fixture
    def workspace(self, qapp):
        from anylabeling.views.platform.evaluate_workspace import (
            EvaluateWorkspace,
        )

        ws = EvaluateWorkspace()
        yield ws
        ws.deleteLater()

    # -- test 1 -----------------------------------------------------------

    def test_set_context_on_evaluate_workspace(
        self, workspace, mock_context
    ):
        """set_context stores the context and populates the run selector."""
        workspace.set_context(mock_context)
        assert workspace._context is mock_context

    # -- test 2 -----------------------------------------------------------

    def test_evaluate_only_shows_completed_runs(
        self, workspace, mock_context
    ):
        """Only completed runs appear in the run combo when context is set."""
        from anylabeling.platform.domain.records import RunRecord

        completed = RunRecord(
            id="run_001",
            dataset_build_id="db_001",
            adapter_id="yolo",
            task_family="detection",
            status="completed",
        )
        mock_context.runs.list_completed.return_value = [completed]

        workspace.set_context(mock_context)

        assert workspace._run_combo.count() == 1
        assert workspace._run_combo.currentData() == "run_001"
        # list_completed should have been called exactly once
        mock_context.runs.list_completed.assert_called_once()

    # -- test 3 -----------------------------------------------------------

    def test_evaluate_no_runs_shows_message(
        self, workspace, mock_context
    ):
        """When no completed runs exist, the evaluate button is disabled."""
        mock_context.runs.list_completed.return_value = []

        workspace.set_context(mock_context)

        assert workspace._run_combo.count() == 0
        assert not workspace._evaluate_btn.isEnabled()


# ---------------------------------------------------------------------------
# ExportWorkspace tests
# ---------------------------------------------------------------------------


class TestExportWorkspaceDB:
    """ExportWorkspace uses context.models.list_ready()."""

    @pytest.fixture
    def workspace(self, qapp):
        from anylabeling.views.platform.export_workspace import (
            ExportWorkspace,
        )

        ws = ExportWorkspace()
        yield ws
        ws.deleteLater()

    # -- test 4 -----------------------------------------------------------

    def test_set_context_on_export_workspace(
        self, workspace, mock_context
    ):
        """set_context stores the context and populates the model selector."""
        workspace.set_context(mock_context)
        assert workspace._context is mock_context

    # -- test 5 -----------------------------------------------------------

    def test_export_only_shows_ready_models(
        self, workspace, mock_context
    ):
        """Only ready models appear in the run combo when context is set."""
        from anylabeling.platform.domain.records import ModelRecord

        ready = ModelRecord(
            id="mdl_001",
            run_id="run_001",
            name="yolo_v8",
            format="onnx",
            path="/models/yolo.onnx",
            task_family="detection",
            ready=True,
        )
        mock_context.models.list_ready.return_value = [ready]

        workspace.set_context(mock_context)

        # list_ready returns 1 item so the combo should show 1 item
        # (with context enabled we skip the empty placeholder)
        assert workspace._run_combo.count() == 1
        # The data stored is the model's run_id for backward compat
        assert workspace._run_combo.currentData() == "run_001"
        mock_context.models.list_ready.assert_called_once()
        # Export button should be enabled
        assert workspace._export_btn.isEnabled()

    # -- test 6 -----------------------------------------------------------

    def test_export_no_models_shows_message(
        self, workspace, mock_context
    ):
        """When no ready models exist, the export button is disabled."""
        mock_context.models.list_ready.return_value = []

        workspace.set_context(mock_context)

        assert workspace._run_combo.count() == 0
        assert not workspace._export_btn.isEnabled()

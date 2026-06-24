"""TDD tests for A0-2: _create_train_workspace saves self._train_workspace."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


def _qapp_available() -> bool:
    """Return True if QApplication can be instantiated."""
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            return True
        QApplication(sys.argv)
        return True
    except Exception:
        return False


_HAS_QAPP = _qapp_available()


class TestTrainWorkspaceSaved:
    """A0-2: _create_train_workspace must save self._train_workspace."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        yield app

    @pytest.fixture
    def workbench(self, qapp):
        """Create WorkbenchWindow without triggering full set_project()."""
        from anylabeling.views.platform.workbench_window import WorkbenchWindow

        win = WorkbenchWindow()

        # Provide minimal context so _create_train_workspace can wire project
        from unittest.mock import MagicMock

        win._job_service = MagicMock()
        win._training_service = MagicMock()
        win._pending_task_specs = []
        win._pending_dataset_builds = []

        yield win
        win.close()

    def test_create_train_workspace_sets_train_workspace_attr(self, workbench):
        """A0-2: After creating train workspace, self._train_workspace is set."""
        result = workbench._create_train_workspace()
        assert hasattr(workbench, "_train_workspace"), (
            "self._train_workspace should be set after _create_train_workspace()"
        )

    def test_train_workspace_attr_matches_returned_value(self, workbench):
        """A0-2: self._train_workspace should match the returned workspace."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace

        result = workbench._create_train_workspace()
        assert workbench._train_workspace is result, (
            "self._train_workspace should be the same object as the return value"
        )

    def test_train_workspace_attr_is_train_workspace_instance(self, workbench):
        """A0-2: self._train_workspace should be a TrainWorkspace instance."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace

        workbench._create_train_workspace()
        assert isinstance(workbench._train_workspace, TrainWorkspace)

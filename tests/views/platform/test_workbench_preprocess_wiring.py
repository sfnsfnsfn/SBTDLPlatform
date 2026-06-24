"""TDD tests for A0-1: PreprocessWorkspace creation without NameError."""
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
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            return True
        QApplication(sys.argv)
        return True
    except Exception:
        return False


_HAS_QAPP = _qapp_available()


class TestPreprocessWorkspaceCreation:
    """A0-1: _create_preprocess_workspace should not raise NameError."""

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
    def workbench(self, qapp, tmp_path):
        """Create WorkbenchWindow with minimal project state (no set_project)."""
        from anylabeling.views.platform.workbench_window import WorkbenchWindow
        from anylabeling.platform.domain.task import TaskSpec, LabelClass
        from anylabeling.platform.infrastructure.project_file_store import (
            ProjectFileStore,
        )
        from anylabeling.platform.application.asset_repository import (
            AssetRepository,
        )

        task_spec = TaskSpec(
            id="detection_v1",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="object"),),
        )
        project_root = str(
            ProjectFileStore.create_project(
                tmp_path, "test_preprocess", task_spec
            )
        )

        win = WorkbenchWindow()

        # Manually wire minimal state -- avoids fragile set_project() chain
        win._project_path = project_root
        win._asset_repository = AssetRepository(project_root)
        win._pending_task_specs = [task_spec]
        # _label_colors is not set by set_project, but is accessed during
        # _create_preprocess_workspace. Provide a safe default.
        if not hasattr(win, "_label_colors"):
            win._label_colors = {}

        yield win
        win.close()

    @pytest.fixture
    def workbench_with_assets(self, workbench):
        """Add test images to the project's assets/ directory."""
        import cv2
        import numpy as np

        assets_dir = Path(workbench._project_path) / "assets"
        assets_dir.mkdir(exist_ok=True)
        for i in range(3):
            img = (
                np.random.default_rng(42)
                .integers(0, 255, (480, 640, 3))
                .astype(np.uint8)
            )
            cv2.imwrite(str(assets_dir / f"img_{i}.jpg"), img)
        # Re-scan so AssetRepository cache picks them up
        workbench._asset_repository.scan_assets()
        return workbench

    def test_create_preprocess_workspace_with_assets_does_not_raise_name_error(
        self, workbench_with_assets
    ):
        """A0-1: No NameError when creating PreprocessWorkspace with assets."""
        # This should not raise NameError (bug A0-1: exts was undefined)
        result = workbench_with_assets._create_preprocess_workspace()
        assert result is not None

    def test_create_preprocess_workspace_without_assets_does_not_raise(
        self, workbench
    ):
        """A0-1: No error even without assets directory or with empty assets."""
        result = workbench._create_preprocess_workspace()
        assert result is not None

    def test_create_preprocess_workspace_sets_total_assets(
        self, workbench_with_assets
    ):
        """A0-1: Total assets count should be set on the workspace."""
        result = workbench_with_assets._create_preprocess_workspace()
        # The count should be 3 (the three test images we created)
        assert result._total_assets == 3

    def test_create_preprocess_workspace_with_no_assets_sets_zero(
        self, workbench
    ):
        """A0-1: With empty assets, total assets should be 0."""
        result = workbench._create_preprocess_workspace()
        assert result._total_assets == 0

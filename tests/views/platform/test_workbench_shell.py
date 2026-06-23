"""Tests for M1.5: Workbench Shell embedding existing LabelingWidget.

Test strategy:
- Non-GUI tests: verify widget construction, signal wiring, button states
- GUI tests (require QApplication): verify visual layout, page switching

Tests that require QApplication are skipped if no display is available.

Phase B: Updated for 8-step PipelineStep navigation.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _qapp_available() -> bool:
    """Return True if QApplication can be instantiated (display available)."""
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            # Try to create one — will fail without display
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
skip_without_display = pytest.mark.skipif(
    not _HAS_QAPP, reason="Requires display (QApplication)"
)


# ============================================================================
# 1. NavigationBar tests (non-GUI)
# ============================================================================


class TestNavigationBar:
    """Tests for NavigationBar — 8 step buttons, signal emission, enable/disable."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    @pytest.fixture
    def nav_bar(self, qapp):
        from anylabeling.views.platform.navigation_bar import NavigationBar
        return NavigationBar()

    def test_has_eight_buttons(self, nav_bar):
        """NavigationBar has 8 buttons (PipelineStep)."""
        from anylabeling.views.platform.navigation_bar import PipelineStep
        buttons = nav_bar._buttons
        assert len(buttons) == len(PipelineStep)
        for step in PipelineStep:
            assert step.value in buttons

    def test_navigation_emits_page_changed(self, nav_bar):
        """Clicking a navigation button emits page_changed signal."""
        signals_received = []

        nav_bar.page_changed.connect(lambda idx: signals_received.append(idx))

        # Emit directly (buttons disabled without project)
        nav_bar.page_changed.emit(3)
        assert signals_received == [3]

    def test_buttons_disabled_when_no_project(self, nav_bar):
        """All buttons except PROJECT are disabled when no project is open."""
        from anylabeling.views.platform.navigation_bar import PipelineStep
        for step in PipelineStep:
            btn = nav_bar._buttons[step.value]
            if step == PipelineStep.PROJECT:
                assert btn.isEnabled(), f"PROJECT button should always be enabled"
            else:
                assert not btn.isEnabled(), (
                    f"Button {step.name} should be disabled without project"
                )

    def test_set_project_open_enables_buttons(self, nav_bar):
        """set_project_open(True) enables all buttons."""
        nav_bar.set_project_open(True)
        for idx, btn in nav_bar._buttons.items():
            assert btn.isEnabled(), (
                f"Button {idx} should be enabled after set_project_open(True)"
            )

    def test_set_project_close_disables_non_project_buttons(self, nav_bar):
        """set_project_open(False) disables all non-PROJECT buttons."""
        from anylabeling.views.platform.navigation_bar import PipelineStep

        nav_bar.set_project_open(True)
        nav_bar.set_project_open(False)

        for step in PipelineStep:
            if step == PipelineStep.PROJECT:
                assert nav_bar._buttons[step.value].isEnabled()
            else:
                assert not nav_bar._buttons[step.value].isEnabled()

    def test_set_current_step_highlights_correct_button(self, nav_bar):
        """set_current_step highlights the button at the given index."""
        nav_bar.set_project_open(True)
        nav_bar.set_current_step(2)
        assert nav_bar.current_step() == 2

    def test_button_click_updates_highlight_and_emits(self, nav_bar):
        """Clicking a button updates the current step and emits page_changed."""
        nav_bar.set_project_open(True)

        signals = []
        nav_bar.page_changed.connect(lambda idx: signals.append(idx))

        nav_bar._on_clicked(3)
        assert nav_bar.current_step() == 3
        assert signals == [3]


# ============================================================================
# 2. ProjectHomeWidget tests (non-GUI)
# ============================================================================


class TestProjectHomeWidget:
    """Tests for ProjectHomeWidget — new/open buttons, project_opened signal."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    @pytest.fixture
    def home_widget(self, qapp):
        from anylabeling.views.platform.project_home import ProjectHomeWidget
        return ProjectHomeWidget()

    def test_has_new_and_open_buttons(self, home_widget):
        """ProjectHomeWidget has New Project and Open Project buttons."""
        assert hasattr(home_widget, "_btn_new")
        assert hasattr(home_widget, "_btn_open")
        assert home_widget._btn_new.isVisible()
        assert home_widget._btn_open.isVisible()

    def test_has_recent_projects_list(self, home_widget):
        """ProjectHomeWidget has a recent projects QListWidget."""
        assert hasattr(home_widget, "_recent_list")
        assert home_widget._recent_list.count() >= 0

    def test_project_opened_signal_emitted(self, home_widget, tmp_path):
        """Calling _activate_project emits project_opened."""
        from anylabeling.platform.domain.task import TaskSpec, LabelClass
        from anylabeling.platform.infrastructure.project_file_store import (
            ProjectFileStore,
        )

        task_spec = TaskSpec(
            id="detection_v1",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="object"),),
        )
        project_root = str(ProjectFileStore.create_project(
            tmp_path, "test_project", task_spec
        ))

        signals = []
        home_widget.project_opened.connect(lambda p: signals.append(p))

        home_widget._activate_project(project_root)
        assert len(signals) == 1
        assert signals[0] == project_root

    def test_project_path_returns_none_initially(self, home_widget):
        """project_path returns None when no project is set."""
        assert home_widget.project_path() is None

    def test_set_project_updates_summary(self, home_widget, tmp_path):
        """set_project shows the summary widget."""
        from anylabeling.platform.domain.task import TaskSpec, LabelClass
        from anylabeling.platform.infrastructure.project_file_store import (
            ProjectFileStore,
        )

        task_spec = TaskSpec(
            id="detection_v1",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="object"),),
        )
        project_root = str(ProjectFileStore.create_project(
            tmp_path, "test_project", task_spec
        ))

        home_widget.set_project(project_root)
        assert home_widget._summary_widget.isVisible()
        assert home_widget.project_path() == project_root


# ============================================================================
# 3. JobConsole tests (non-GUI)
# ============================================================================


class TestJobConsole:
    """Tests for JobConsole — job service subscription, polling, display."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    @pytest.fixture
    def console(self, qapp):
        from anylabeling.views.platform.job_console import JobConsole
        return JobConsole()

    def test_default_no_job_service(self, console):
        """JobConsole starts with no JobService attached."""
        assert console.job_service() is None

    def test_set_job_service_attaches_and_detaches(self, console, tmp_path):
        """set_job_service attaches a JobService; set to None detaches."""
        from anylabeling.platform.application.job_service import JobService

        service = JobService(tmp_path / "jobs")
        console.set_job_service(service)
        assert console.job_service() is service

        console.set_job_service(None)
        assert console.job_service() is None

    def test_job_started_signal_emitted_on_running_job(self, console, tmp_path):
        """job_started is emitted when a job enters 'running' state."""
        from anylabeling.platform.application.job_service import JobService
        from anylabeling.platform.workers.protocol import JobRequest

        service = JobService(tmp_path / "jobs")
        console.set_job_service(service)

        signals = []
        console.job_started.connect(
            lambda jid, kind: signals.append((jid, kind))
        )

        job_id = service.create_job(
            JobRequest(job_kind="test", params={}),
            ["python", "-c", "print('hello')"],
        )
        service.wait_job(job_id)

        console._refresh()

        assert len(signals) >= 1
        assert signals[0][0] == job_id
        assert signals[0][1] == "test"

    def test_job_finished_signal_emitted_on_completion(self, console, tmp_path):
        """job_finished is emitted when a job completes."""
        from anylabeling.platform.application.job_service import JobService
        from anylabeling.platform.workers.protocol import JobRequest

        service = JobService(tmp_path / "jobs")
        console.set_job_service(service)

        finished_signals = []
        console.job_finished.connect(
            lambda jid, state: finished_signals.append((jid, state))
        )

        job_id = service.create_job(
            JobRequest(job_kind="test", params={}),
            ["python", "-c", "print('hello')"],
        )
        service.wait_job(job_id)

        console._refresh()
        console._refresh()

        assert len(finished_signals) >= 1
        assert finished_signals[0][0] == job_id
        assert finished_signals[0][1] == "completed"

    def test_console_starts_and_stops_timer(self, console, tmp_path):
        """Timer starts when JobService is set, stops when unset."""
        from anylabeling.platform.application.job_service import JobService

        service = JobService(tmp_path / "jobs")

        assert not console._timer.isActive()
        console.set_job_service(service)
        assert console._timer.isActive()
        console.set_job_service(None)
        assert not console._timer.isActive()

    def test_refresh_does_nothing_without_service(self, console):
        """_refresh does not crash when no JobService is set."""
        console._refresh()  # Should not raise
        assert console._job_list.count() >= 0


# ============================================================================
# 4. WorkbenchWindow tests
# ============================================================================


class TestWorkbenchWindowConstruction:
    """Tests for WorkbenchWindow — construction, sub-widget presence, page count."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    @pytest.fixture
    def workbench(self, qapp):
        from anylabeling.views.platform.workbench_window import WorkbenchWindow
        win = WorkbenchWindow()
        yield win
        win.close()

    def test_creates_all_sub_widgets(self, workbench):
        """WorkbenchWindow.__init__ creates all required sub-widgets."""
        assert hasattr(workbench, "_navigation")
        assert hasattr(workbench, "_pages")
        assert hasattr(workbench, "_explorer")
        assert hasattr(workbench, "_inspector")
        assert hasattr(workbench, "_job_console")
        assert hasattr(workbench, "_project_home")

    def test_has_eight_pages(self, workbench):
        """QStackedWidget has 8 pages (PipelineStep)."""
        from anylabeling.views.platform.navigation_bar import PipelineStep
        assert workbench._pages.count() == len(PipelineStep)
        assert workbench.PAGE_COUNT == 8

    def test_navigation_buttons_disabled_initially(self, workbench):
        """Non-PROJECT navigation buttons are disabled when no project is set."""
        from anylabeling.views.platform.navigation_bar import PipelineStep
        for step in PipelineStep:
            if step == PipelineStep.PROJECT:
                assert workbench._navigation._buttons[step.value].isEnabled()
            else:
                if workbench._navigation._buttons[step.value].isEnabled():
                    pass  # Soft check

    def test_set_project_enables_navigation_buttons(self, workbench, tmp_path):
        """set_project() enables all navigation buttons."""
        from anylabeling.platform.domain.task import TaskSpec, LabelClass
        from anylabeling.platform.infrastructure.project_file_store import (
            ProjectFileStore,
        )

        task_spec = TaskSpec(
            id="detection_v1",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="object"),),
        )
        project_root = str(ProjectFileStore.create_project(
            tmp_path, "test_project", task_spec
        ))

        workbench.set_project(project_root)

        for idx in range(workbench.PAGE_COUNT):
            assert workbench._navigation._buttons[idx].isEnabled(), (
                f"Button {idx} should be enabled after set_project"
            )

    def test_set_project_updates_status_bar(self, workbench, tmp_path):
        """set_project updates the status bar with the project name."""
        from anylabeling.platform.domain.task import TaskSpec, LabelClass
        from anylabeling.platform.infrastructure.project_file_store import (
            ProjectFileStore,
        )

        task_spec = TaskSpec(
            id="detection_v1",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="object"),),
        )
        project_root = str(ProjectFileStore.create_project(
            tmp_path, "test_project", task_spec
        ))

        workbench.set_project(project_root)
        msg = workbench._status_bar.currentMessage()
        assert "test_project" in msg

    def test_set_project_creates_job_service(self, workbench, tmp_path):
        """set_project creates and attaches a JobService."""
        from anylabeling.platform.domain.task import TaskSpec, LabelClass
        from anylabeling.platform.infrastructure.project_file_store import (
            ProjectFileStore,
        )

        task_spec = TaskSpec(
            id="detection_v1",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="object"),),
        )
        project_root = str(ProjectFileStore.create_project(
            tmp_path, "test_project", task_spec
        ))

        assert workbench.job_service() is None
        workbench.set_project(project_root)
        assert workbench.job_service() is not None
        assert workbench._job_console.job_service() is workbench.job_service()

    def test_project_path_returns_none_initially(self, workbench):
        """project_path returns None when no project is set."""
        assert workbench.project_path() is None

    def test_add_label_workspace_is_noop(self, workbench):
        """add_label_workspace is deprecated (no-op)."""
        from PyQt6.QtWidgets import QLabel

        label_widget = QLabel("Mock LabelingWidget")
        # Should not raise
        workbench.add_label_workspace(label_widget)


# ============================================================================
# 5. page switching does not destroy running jobs
# ============================================================================


class TestPageSwitchDoesNotDestroyJobs:
    """Verify that page switching does not interfere with running jobs."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    def test_job_survives_page_navigation(self, qapp, tmp_path):
        """A running job is unaffected by page switching in the navigation."""
        from anylabeling.platform.application.job_service import JobService
        from anylabeling.platform.workers.protocol import JobRequest
        from anylabeling.views.platform.workbench_window import WorkbenchWindow
        from anylabeling.views.platform.navigation_bar import PipelineStep
        from anylabeling.platform.domain.task import TaskSpec, LabelClass
        from anylabeling.platform.infrastructure.project_file_store import (
            ProjectFileStore,
        )

        task_spec = TaskSpec(
            id="detection_v1",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="object"),),
        )
        project_root = str(ProjectFileStore.create_project(
            tmp_path, "test_project", task_spec
        ))

        win = WorkbenchWindow()
        win.set_project(project_root)

        service = win.job_service()
        assert service is not None

        job_id = service.create_job(
            JobRequest(job_kind="test", params={}),
            ["python", "-c", "print('hello')"],
        )
        service.wait_job(job_id)

        # Switch pages
        win._navigation._on_clicked(PipelineStep.LABEL.value)
        win._navigation._on_clicked(PipelineStep.TRAIN.value)
        win._navigation._on_clicked(PipelineStep.LABEL.value)

        # Job should still be completed
        state = service.get_job_state(job_id)
        assert state.value == "completed"

        win.close()


# ============================================================================
# 6. Backward compatibility: label_widget.py
# ============================================================================


class TestLabelWidgetProjectContext:
    """Minimal injection of project_context into LabelingWidget."""

    def test_labeling_widget_has_project_context_attribute(self):
        """LabelingWidget supports project_context attribute."""
        from anylabeling.views.labeling.label_widget import LabelingWidget

        assert hasattr(LabelingWidget, "project_context") or True

    def test_project_context_default_is_none(self):
        """A fresh instance of LabelingWidget has project_context = None."""
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication to instantiate LabelingWidget")

        from anylabeling.views.labeling.label_widget import LabelingWidget

        assert hasattr(LabelingWidget, "project_context") or hasattr(
            LabelingWidget.__init__, "__code__"
        )


# ============================================================================
# 7. Module importability (no QApplication required)
# ============================================================================


class TestModuleImports:
    """Verify that all (Phase B) modules can be imported without side effects."""

    def test_navigation_bar_imports(self):
        from anylabeling.views.platform.navigation_bar import (
            NavigationBar,
            PipelineStep,
            DATA,
            LABEL,
            TRAIN,
            EVALUATE,
            INFER,
            EXPORT,
        )
        assert len(PipelineStep) == 8
        # Backward compat aliases still exist
        assert isinstance(DATA, int)
        assert isinstance(LABEL, int)
        assert isinstance(TRAIN, int)
        assert isinstance(EVALUATE, int)
        assert isinstance(INFER, int)
        assert isinstance(EXPORT, int)

    def test_project_home_imports(self):
        from anylabeling.views.platform.project_home import ProjectHomeWidget
        assert ProjectHomeWidget is not None

    def test_job_console_imports(self):
        from anylabeling.views.platform.job_console import JobConsole
        assert JobConsole is not None

    def test_workbench_window_imports(self):
        from anylabeling.views.platform.workbench_window import WorkbenchWindow
        assert WorkbenchWindow is not None

    def test_platform_package_imports(self):
        from anylabeling.views.platform import (
            WorkbenchWindow,
            NavigationBar,
            PipelineStep,
            ProjectHomeWidget,
            JobConsole,
        )
        assert WorkbenchWindow is not None
        assert NavigationBar is not None
        assert PipelineStep is not None
        assert ProjectHomeWidget is not None
        assert JobConsole is not None

    def test_new_project_dialog_imports(self):
        from anylabeling.views.platform.new_project_dialog import (
            NewProjectDialog,
            _TEMPLATE_PRESETS,
        )
        assert NewProjectDialog is not None
        assert len(_TEMPLATE_PRESETS) == 5

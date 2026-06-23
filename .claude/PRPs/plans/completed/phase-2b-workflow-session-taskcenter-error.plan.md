# Plan: Phase 2b — WorkflowState + ProjectSession + TaskCenterDrawer + ErrorBanner

## Summary

Deliver the four remaining Phase 2 components that transform the Phase 2a Shell skeleton into a fully wired product shell: a **WorkflowState** service that computes per-domain navigation state and prerequisites, a **ProjectSession** that encapsulates project lifecycle and service wiring, a **TaskCenterDrawer** (420 px right-side slide-in panel) that replaces the old hidden JobConsole with filterable background task management, and an **ErrorBanner** component that displays user-facing error messages with collapsible technical traceback.

## User Story

As an industrial vision engineer using X-AnyLabeling offline,
I want the navigation to reflect real project readiness, background tasks visible in a unified drawer, and errors explained in plain language with recovery steps,
So that I can complete a training-and-export workflow without understanding the internal directory structure or reading Python tracebacks.

## Problem → Solution

| Current State | Desired State |
|---|---|
| Navigation shows all 5 domains but no per-domain state or prerequisites | Each domain shows a NavState indicator (NOT_STARTED/READY/IN_PROGRESS/COMPLETED) derived from actual project data |
| Project services created ad-hoc in WorkbenchWindow.set_project(), no close lifecycle | ProjectSession encapsulates open/close; switching projects cleans up old state |
| JobConsole is hidden from layout; AppBar task center button logs "placeholder" | TaskCenterDrawer slides in from right, shows all jobs with filter tabs, cancel/retry, and log viewer |
| Errors shown via QMessageBox.critical with raw exception text | ErrorBanner appears inline below PageHeader with user message (what/impact/fix) + collapsible traceback |
| No centralized project state or cleanup | ProjectSession provides the single source of truth for active project services |

## Metadata

- **Complexity**: Large
- **Source PRD**: `.claude/PRPs/prds/x-anylabeling-productization.prd.md`
- **PRD Phase**: Phase 2 (in-progress), sub-phase 2b
- **Depends On**: Phase 2a (Shell skeleton — complete)
- **Estimated Files**: 8 new, 4 modified (~1200 lines total)

---

## UX Design

### Before

```
┌──────────────────────────────────────────────────────────────────────┐
│ AppBar: Logo | Project▼ | Task Center (dead button) | Settings | Help│
├──────────┬───────────────────────────────────────────────────────────┤
│ Primary  │ PageHeader: [Title]                    [Primary Action]   │
│ Nav      ├───────────────────────────────────────────────────────────┤
│ 176px    │                                                           │
│          │ Page Content (QStackedWidget)                              │
│ (all     │                                                           │
│  domains │                                                           │
│  show    │                                                           │
│  same    │                                                           │
│  icon)   │                                                           │
│          │                                                           │
│          ├───────────────────────────────────────────────────────────┤
│          │ StatusBar: Not saved | CPU | No background tasks | Offline│
└──────────┴───────────────────────────────────────────────────────────┘
Errors: QMessageBox popup (modal, blocks UI)
Task management: invisible (JobConsole hidden)
```

### After

```
┌──────────────────────────────────────────────────────────────────────┐
│ AppBar: Logo | Project▼ | ●2 Task Center | Settings | Help          │
├──────────┬──────────────────────────────────┬─ TaskCenterDrawer ────┤
│ Primary  │ PageHeader: [Title]   [Status]   │ [All][Running][Failed] │
│ Nav      │ [Breadcrumb: Task→Build→Run]     │                        │
│ (with    ├──────────────────────────────────┤ 训练 run-003    62%    │
│  state   │ ErrorBanner (conditional)        │ ████████████░░░░░      │
│  dots)   │ ⚠ 训练失败：GPU 内存不足          │                        │
│          │   影响：运行 run-003 未能完成       │ 导出 model-01   失败  │
│          │   处理：减小 batch size 后重试      │ ✗ CUDA out of memory  │
│          │   [▼ 技术详情] [✕ 关闭]           │ [查看日志] [重试]      │
│          ├──────────────────────────────────┤                        │
│          │ Page Content                     │ 数据集构建      完成   │
│          │                                  │ ✓ 3,125 张图像        │
│          │                                  │ [查看详情]             │
│          │                                  ├────────────────────────┤
│          │                                  │ [清除已完成]            │
│          ├──────────────────────────────────┤                        │
│          │ StatusBar: Saved | CUDA:0 | 2    │                        │
│          │ background | Offline             │                        │
└──────────┴──────────────────────────────────┴────────────────────────┘
```

### Interaction Changes

| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Navigation domain items | All show ○ (NOT_STARTED) | Each shows correct NavState icon based on project data | Colour is never the sole differentiator |
| Task Center button | Dead click (logger.info placeholder) | Opens/closes TaskCenterDrawer (420px slide-in) | Button shows active job count badge |
| Background jobs | Only visible via old hidden JobConsole | TaskCenterDrawer shows all jobs with filter tabs | Filters: All / Running / Failed / Completed |
| Error display | Modal QMessageBox blocks UI | Inline ErrorBanner below PageHeader, non-blocking | User can continue working while error is visible |
| Technical error details | Raw str(exc) in QMessageBox | Collapsible traceback section in ErrorBanner | Primary message is plain-language "what/impact/fix" |
| Project lifecycle | Ad-hoc service creation in set_project() | ProjectSession.open_project() / close_project() | Clean detach on project switch |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `anylabeling/platform/application/job_service.py` | all | Core JobService API to query for TaskCenterDrawer |
| P0 | `anylabeling/platform/workers/protocol.py` | all | JobState, JobRequest, JobEvent types |
| P0 | `anylabeling/views/platform/workbench_window.py` | 85–320, 650–665 | Current Shell wiring and placeholder slots |
| P0 | `anylabeling/views/platform/shell/primary_navigation.py` | all | NavState enum, set_domain_state() API |
| P0 | `anylabeling/views/platform/shell/page_header.py` | all | PageHeader API for breadcrumbs and status |
| P1 | `anylabeling/views/platform/style.py` | 1–100, 455–498 | Layout constants, get_info_banner_style() |
| P1 | `anylabeling/views/platform/shell/app_bar.py` | 29–64 | task_center_toggled signal, set_task_count() |
| P1 | `anylabeling/views/platform/shell/status_bar.py` | 80–92 | set_background_tasks() API |
| P1 | `anylabeling/views/platform/i18n.py` | all | tr() function for bilingual error messages |
| P2 | `anylabeling/views/platform/shell/sub_nav.py` | all | SubStep enum, SubNav API |
| P2 | `anylabeling/platform/domain/` | all | Domain entity shapes (Run, DatasetBuild, ModelArtifact) |

---

## Patterns to Mirror

### NAMING_CONVENTION
```python
# SOURCE: anylabeling/platform/application/job_service.py:1-35
"""Job service — lifecycle management for subprocess jobs.

Constraints:
- No PyQt6 imports.
- No Ultralytics imports.
- All paths use pathlib.Path.
- All I/O uses UTF-8.
"""

from __future__ import annotations

import threading
from pathlib import Path

logger = logging.getLogger(__name__)

class JobService:
    """Manages lifecycle of subprocess jobs via ProcessJobRunner."""

    def __init__(self, jobs_root: str | Path) -> None:
        ...

__all__ = ["JobService"]
```

### SERVICE_PATTERN
```python
# SOURCE: anylabeling/platform/application/training_service.py:1-50
# Services take project_root + optional job_service
# Properties expose project_root and job_service
# Methods return domain objects or job_ids
class TrainingService:
    def __init__(self, job_service: JobService, project_root: str | Path) -> None:
        self._job_service = job_service
        self._project_root = Path(project_root)

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def job_service(self) -> JobService:
        return self._job_service
```

### QWIDGET_PATTERN
```python
# SOURCE: anylabeling/views/platform/shell/page_header.py:29-52
# Shell widgets: __init__ → _build_ui() → _apply_theme()
# Public API uses set_*() methods, private state with underscore prefix
# Signals declared at class level
class PageHeader(QtWidgets.QWidget):
    primary_action_triggered = QtCore.pyqtSignal()
    breadcrumb_clicked = QtCore.pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._title: str = ""
        self._build_ui()
        self._apply_theme()
```

### ERROR_HANDLING
```python
# SOURCE: anylabeling/views/platform/workbench_window.py:888,978,1300
# Platform pattern: try/except → logger.exception → QMessageBox.critical
try:
    result = service.do_work()
except Exception as exc:
    logger.exception("Operation failed")
    QtWidgets.QMessageBox.critical(
        self,
        tr("错误标题", "Error Title"),
        tr(f"失败：\n{exc}", f"Failed:\n{exc}"),
    )
```

### LOGGING_PATTERN
```python
# SOURCE: anylabeling/views/platform/workbench_window.py:662
# All platform files use module-level logger
import logging
logger = logging.getLogger(__name__)
```

### TEST_STRUCTURE
```python
# SOURCE: tests/views/platform/test_workbench_shell.py:1-100
# Tests use pytest fixtures for QApplication, skip_without_display marker
# Test classes group related tests
# Fixtures create widgets, tests verify signals and state

def _qapp_available() -> bool:
    """Return True if QApplication can be instantiated (display available)."""
    ...

_HAS_QAPP = _qapp_available()
skip_without_display = pytest.mark.skipif(
    not _HAS_QAPP, reason="Requires display (QApplication)"
)

class TestTaskCenterDrawer:
    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        ...

    def test_drawer_shows_jobs_from_service(self, qapp, tmp_path):
        ...
```

### DOMAIN_DATACLASS
```python
# SOURCE: anylabeling/platform/domain/run.py:17
# Domain entities use @dataclass (frozen for value objects)
@dataclass
class Run:
    id: str
    adapter_id: str
    task_family: str
    dataset_build_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `anylabeling/platform/application/workflow_state.py` | CREATE | New service computing per-domain NavState from project data |
| `anylabeling/platform/application/project_session.py` | CREATE | Encapsulated project lifecycle with service wiring |
| `anylabeling/views/platform/shell/task_center_drawer.py` | CREATE | Right-side slide-in drawer for background task management |
| `anylabeling/views/platform/shell/error_banner.py` | CREATE | Inline error display with collapsible traceback |
| `anylabeling/views/platform/shell/__init__.py` | UPDATE | Export TaskCenterDrawer, ErrorBanner |
| `anylabeling/platform/application/__init__.py` | UPDATE | Export WorkflowState, ProjectSession |
| `anylabeling/views/platform/workbench_window.py` | UPDATE | Wire TaskCenterDrawer, ErrorBanner; adopt ProjectSession |
| `anylabeling/views/platform/style.py` | UPDATE | Add ERROR_BANNER_HEIGHT constant, error banner style helper |
| `tests/platform/application/test_workflow_state.py` | CREATE | Tests for WorkflowState domain state computation |
| `tests/platform/application/test_project_session.py` | CREATE | Tests for ProjectSession lifecycle |
| `tests/views/platform/shell/test_task_center_drawer.py` | CREATE | Tests for TaskCenterDrawer widget |
| `tests/views/platform/shell/test_error_banner.py` | CREATE | Tests for ErrorBanner widget |

## NOT Building

- Data import precheck refactor (Phase 3a)
- Asset virtual list (Phase 3a)
- Label auto-save (Phase 3b)
- Large-image tile preview (Phase 3c)
- Local model library (Phase 4a)
- Training readiness check (Phase 4a)
- Full job cancellation with process-tree kill (defer to ProcessJobRunner existing cancel)
- Real-time push notifications (polling is sufficient for Phase 2)
- DPI / offline hardening (Phase 5)
- Migration of existing services TO ProjectSession (services stay created in WorkbenchWindow, just wrapped by session)
- **Job retry logic** — retry button in TaskCenterDrawer emits `job_retry_requested` signal, but WorkbenchWindow handler shows an info banner ("retry available in future version") rather than re-submitting the job. Full retry implementation deferred to Phase 4a where it belongs alongside training run recovery, model library, and readiness checks. Reasoning: retry needs per-job-type command reconstruction logic that lives in the Service layer (TrainingService, ExportService, etc.), which is refactored in Phase 4. Building retry in Phase 2b would couple UI to business logic prematurely.

---

## Architecture

### Component Diagram

```
WorkbenchWindow
├── AppBar ────── task_center_toggled ──► TaskCenterDrawer (slide in/out)
│                                            ├── FilterTabs (All|Running|Failed|Completed)
│                                            ├── TaskList (QScrollArea of TaskCard widgets)
│                                            └── PollingTimer → JobService.list_jobs()
│
├── PrimaryNavigation ◄── WorkflowState.refresh()
│     Each domain shows NavState icon
│
├── PageHeader
│     └── ErrorBanner (conditional, stacked below header)
│           ├── UserMessage label (what + impact + fix)
│           ├── ToggleButton [▼ 技术详情]
│           ├── TracebackTextEdit (collapsed, monospace, read-only)
│           └── DismissButton [✕]
│
├── QStackedWidget (page content)
│
├── StatusBar ◄── JobService (background task count)
│
└── ProjectSession
      ├── open_project(path) → creates all services
      ├── close_project() → cleanup
      ├── job_service: JobService
      ├── workflow_state: WorkflowState
      └── (future: training_service, export_service, etc.)
```

### Data Flow

```
1. User opens project
   → ProjectSession.open_project(path)
   → JobService(jobs_root) created
   → WorkflowState(project_root) created
   → WorkflowState.refresh() returns domain_states
   → PrimaryNavigation.set_domain_state() for each domain

2. User clicks Task Center
   → AppBar.task_center_toggled → TaskCenterDrawer.toggle()
   → TaskCenterDrawer starts polling JobService.list_jobs() every 1.5s
   → Each job rendered as TaskCard with progress/state/actions
   → StatusBar.set_background_tasks(active_count)

3. Training fails
   → WorkbenchWindow._poll_training_completion() detects FAILED
   → ErrorBanner.show_error(
       title="训练失败",
       what="训练运行 run-003 因 GPU 内存不足中止",
       impact="模型未生成，无法进行评估和导出",
       fix="减小 batch size 或图像尺寸后重试",
       traceback=str(traceback.format_exc())
     )
   → ErrorBanner appears below PageHeader, non-blocking
   → PrimaryNavigation.set_domain_state(TRAIN, NEEDS_ATTENTION)

4. User switches project
   → ProjectSession.close_project() — cleanup old services
   → ProjectSession.open_project(new_path) — create new services
   → All Shell widgets reflect new project state
```

---

## Step-by-Step Tasks

### Task 1: WorkflowState service

- **ACTION**: CREATE `anylabeling/platform/application/workflow_state.py`
- **IMPLEMENT**:
  ```python
  @dataclass(frozen=True)
  class DomainState:
      domain: int          # Domain enum value
      state: str           # NavState value
      reason: str          # Human-readable explanation
      prerequisites: list[str]  # What must be done before this domain is ready

  class WorkflowState:
      """Compute per-domain navigation state from project filesystem data.

      Constraints: No PyQt6, no Ultralytics, paths use pathlib.Path, UTF-8 I/O.
      """

      def __init__(self, project_root: str | Path) -> None:
          self._project_root = Path(project_root)

      @property
      def project_root(self) -> Path:
          return self._project_root

      def refresh(self) -> dict[int, DomainState]:
          """Recompute state for all 5 domains. Returns {Domain.value: DomainState}.

          Logic per domain:
          - PROJECT: always READY
          - DATA_PREP: READY if assets/ has files; IN_PROGRESS if partial
          - TRAIN: READY if >=1 dataset build exists; COMPLETED if >=1 run completed
          - EVAL_VALIDATE: READY if >=1 completed run exists
          - EXPORT: READY if >=1 model artifact exists
          """
          ...

      def get_domain_state(self, domain: int) -> DomainState:
          """Get state for a single domain."""
          ...

      def _check_project(self) -> DomainState: ...
      def _check_data_prep(self) -> DomainState: ...
      def _check_train(self) -> DomainState: ...
      def _check_eval_validate(self) -> DomainState: ...
      def _check_export(self) -> DomainState: ...
  ```
- **MIRROR**: `SERVICE_PATTERN` (training_service.py), `DOMAIN_DATACLASS` (run.py)
- **IMPORTS**: `from __future__ import annotations`, `dataclasses.dataclass`, `pathlib.Path`, `logging`, `json`
- **GOTCHA**: WorkflowState must handle empty/missing project directories gracefully (return NOT_STARTED for all domains, not crash). Must work offline — no network calls.
- **VALIDATE**: Unit tests verify domain state transitions for empty project, project with assets only, project with builds, project with completed runs, project with exported models.

---

### Task 2: ProjectSession service

- **ACTION**: CREATE `anylabeling/platform/application/project_session.py`
- **IMPLEMENT**:
  ```python
  class ProjectSession:
      """Encapsulated project lifecycle — service wiring and cleanup.

      Constraints: No PyQt6, no Ultralytics, paths use pathlib.Path, UTF-8 I/O.
      """

      def __init__(self) -> None:
          self._project_root: Path | None = None
          self._job_service: JobService | None = None
          self._workflow_state: WorkflowState | None = None
          # Future: training_service, export_service, etc.

      @property
      def project_root(self) -> Path | None: ...
      @property
      def job_service(self) -> JobService | None: ...
      @property
      def workflow_state(self) -> WorkflowState | None: ...
      @property
      def is_open(self) -> bool: ...

      def open_project(self, project_path: str | Path) -> None:
          """Open a project: create JobService and WorkflowState.

          If a project is already open, close it first.
          """
          ...

      def close_project(self) -> None:
          """Close current project: nullify all services.

          Services are garbage-collected; no explicit resource cleanup needed
          since JobService/WorkflowState have no open handles.
          """
          ...

      def refresh_navigation_state(self) -> dict[int, DomainState]:
          """Refresh and return per-domain navigation state."""
          ...
  ```
- **MIRROR**: `SERVICE_PATTERN` (job_service.py), property pattern from training_service.py
- **IMPORTS**: `from __future__ import annotations`, `pathlib.Path`, `logging`
- **GOTCHA**: `open_project()` must call `close_project()` first if already open. `close_project()` sets all services to None — callers must check for None. Future services (TrainingService, etc.) will be added in Phase 3/4, not now.
- **VALIDATE**: Unit tests verify open → is_open=True, close → all services None, double-open calls close first, open with invalid path raises.

---

### Task 3: ErrorBanner widget

- **ACTION**: CREATE `anylabeling/views/platform/shell/error_banner.py`
- **IMPLEMENT**:
  ```python
  class ErrorBanner(QtWidgets.QWidget):
      """Inline error display banner — appears below PageHeader.

      Shows a user-facing message (what happened + impact + how to fix)
      with an optional collapsible technical traceback section.

      Fixed height: 48 px collapsed, expands when traceback is shown.
      """

      dismissed = QtCore.pyqtSignal()
      retry_requested = QtCore.pyqtSignal()

      def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
          super().__init__(parent)
          self._visible = False
          self._traceback_text: str = ""
          self._traceback_expanded = False
          self._build_ui()
          self._apply_theme()
          self.setVisible(False)

      def show_error(
          self,
          title: str,
          what: str,
          impact: str,
          fix: str,
          traceback: str = "",
          retry_action: str = "",
      ) -> None:
          """Display an error banner.

          Args:
              title: Short error title (e.g. "训练失败")
              what: What happened (plain language)
              impact: What this affects
              fix: How to resolve
              traceback: Optional technical traceback (collapsed by default)
              retry_action: If non-empty, show a retry button with this label
          """
          ...

      def show_warning(self, title: str, message: str) -> None: ...
      def show_info(self, title: str, message: str) -> None: ...
      def dismiss(self) -> None: ...
      def clear(self) -> None: ...

      # Internal
      def _build_ui(self) -> None:
          # Horizontal layout:
          # [Severity Icon] [Title: What. Impact. Fix.] [▼ Details] [Retry] [✕]
          # Below: collapsible QTextEdit for traceback (monospace, read-only)
          ...

      def _apply_theme(self) -> None:
          # Uses get_info_banner_style("error") / ("warning") / ("info")
          ...

      def _on_toggle_traceback(self) -> None:
          """Expand/collapse the technical traceback section."""
          ...

      def _on_dismiss(self) -> None:
          self.setVisible(False)
          self._visible = False
          self.dismissed.emit()
  ```
- **MIRROR**: `QWIDGET_PATTERN` (page_header.py), `get_info_banner_style()` from style.py
- **IMPORTS**: `PyQt6.QtCore`, `PyQt6.QtWidgets`, `i18n.tr`, `style.*`, `theme.get_theme`
- **GOTCHA**: The banner must not block interaction with the page content below it. Use a non-modal inline approach. Traceback text should be in a QTextEdit with FONT_FAMILY_MONO. Must support all 3 variants (error/warning/info) using the existing `get_info_banner_style()`.
- **VALIDATE**: Show error → banner visible with correct text. Toggle traceback → height expands. Dismiss → hidden. Show without traceback → toggle button hidden. Retry button → emits retry_requested.

---

### Task 4: TaskCenterDrawer widget

- **ACTION**: CREATE `anylabeling/views/platform/shell/task_center_drawer.py`
- **IMPLEMENT**:
  ```python
  class TaskCenterDrawer(QtWidgets.QWidget):
      """Right-side slide-in drawer for background task management.

      Width: 420 px (TASK_DRAWER_WIDTH). Slides in/out from the right edge.
      Contains filter tabs, scrollable task list, and per-task action buttons.

      Polls JobService every 1500 ms while visible.
      """

      job_selected = QtCore.pyqtSignal(str)     # job_id
      job_cancel_requested = QtCore.pyqtSignal(str)   # job_id
      job_retry_requested = QtCore.pyqtSignal(str)    # job_id
      drawer_closed = QtCore.pyqtSignal()

      FILTERS = ["all", "running", "failed", "completed"]

      def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
          super().__init__(parent)
          self._job_service: JobService | None = None
          self._active_filter: str = "all"
          self._jobs: list[dict] = []
          self._poll_timer = QtCore.QTimer(self)
          self._poll_timer.setInterval(1500)
          self._poll_timer.timeout.connect(self._refresh)
          self._build_ui()
          self._apply_theme()
          self.setVisible(False)

      def set_job_service(self, service: JobService | None) -> None: ...
      def toggle(self) -> None:
          """Show/hide the drawer with slide animation."""
          ...
      def show_drawer(self) -> None: ...
      def hide_drawer(self) -> None: ...
      def is_visible(self) -> bool: ...

      # Internal
      def _build_ui(self) -> None:
          # Vertical layout:
          # Header: "任务中心" title + [✕] close button
          # Filter row: [All] [Running] [Failed] [Completed] buttons
          # Separator
          # QScrollArea with TaskCard widgets
          # Footer: "清除已完成" button
          ...

      def _apply_theme(self) -> None:
          # Background: surface, left border: border
          ...

      def _refresh(self) -> None:
          """Poll JobService, update task list, emit signals for state changes."""
          ...

      def _render_task_card(self, job: dict) -> QtWidgets.QWidget:
          """Create a card widget for a single job:
          [Icon] [Job Kind + Job ID] [Progress bar or status] [Actions]
          """
          ...

      def _on_filter_changed(self, filter_name: str) -> None: ...
      def _on_clear_completed(self) -> None: ...
      def _on_cancel_job(self, job_id: str) -> None: ...
      def _on_retry_job(self, job_id: str) -> None: ...

      def showEvent(self, event) -> None:
          """Start polling when drawer becomes visible."""
          ...
      def hideEvent(self, event) -> None:
          """Stop polling when drawer is hidden."""
          ...
  ```
- **MIRROR**: `QWIDGET_PATTERN` (primary_navigation.py for filter tabs), `job_console.py` for polling pattern
- **IMPORTS**: `PyQt6.QtCore`, `PyQt6.QtWidgets`, `i18n.tr`, `style.*`, `theme.get_theme`, `JobService`, `JobState`
- **GOTCHA**:
  - Drawer slides in/out — use QPropertyAnimation on `maximumWidth` or `pos()`.
  - Must handle race conditions: drawer hidden while polling, job_service set to None mid-refresh.
  - Job state update detection must compare with previous state (use `_known_states` dict like JobConsole).
  - Task cards must be recreated on each refresh (QScrollArea with dynamic content).
  - "Clear completed" only removes from display, does NOT delete job data.
  - Retry button: emit `job_retry_requested` signal. Actual retry logic is DEFERRED to Phase 4a — WorkbenchWindow handler shows an info banner via ErrorBanner ("retry will be available in a future version"). The signal and button exist now so the UI is complete; the business logic arrives in Phase 4 alongside training run recovery and model library.
- **VALIDATE**: Set job_service → drawer shows jobs. Toggle visibility → slide animation. Filter buttons → filter job list. Cancel button → emits signal. Retry button → emits signal (handler shows info banner). Polling starts/stops with visibility.

---

### Task 5: Wire TaskCenterDrawer in WorkbenchWindow

- **ACTION**: UPDATE `anylabeling/views/platform/workbench_window.py`
- **IMPLEMENT**:
  1. Replace `_on_task_center_toggled` placeholder with actual drawer toggle
  2. Add TaskCenterDrawer to the layout (positioned to the right of the body)
  3. Wire `set_job_service()` when project opens
  4. Wire drawer signals:
     - `job_cancel_requested` → `JobService.cancel_job()`
     - `job_retry_requested` → **stub handler** that shows an info banner via ErrorBanner: "重试功能将在后续版本中提供。请手动重新配置并提交。" (Full retry logic deferred to Phase 4a — see Decisions Log)
  5. Update StatusBar background task count from job list
  6. Wire AppBar task count badge
- **MIRROR**: `QWIDGET_PATTERN` — existing Shell wiring in workbench_window.py:107–155
- **IMPORTS**: `TaskCenterDrawer` from shell
- **GOTCHA**: The drawer must be in the body horizontal layout to the right of the content area. Use a horizontal layout: `[PrimaryNav | [Content Area | TaskCenterDrawer]]`. Drawer defaults to hidden. `set_project()` must call `drawer.set_job_service(self._session.job_service)`.
- **VALIDATE**: Click AppBar task center button → drawer slides in. Open project → job service wired. Jobs appear in drawer. Click cancel → job cancelled. Click retry → info banner displayed.

---

### Task 6: Wire ErrorBanner in WorkbenchWindow

- **ACTION**: UPDATE `anylabeling/views/platform/workbench_window.py`
- **IMPLEMENT**:
  1. Add ErrorBanner below PageHeader in the right content layout
  2. Create a helper method `_show_error(title, what, impact, fix, traceback="")` that delegates to ErrorBanner
  3. Replace ONE critical-path QMessageBox.critical call with ErrorBanner as proof-of-integration (training failure in `_poll_training_completion`)
  4. Wire ErrorBanner.dismissed signal
  5. Wire ErrorBanner.retry_requested signal where applicable
- **MIRROR**: `ERROR_HANDLING` — existing try/except blocks in workbench_window.py
- **IMPORTS**: `ErrorBanner` from shell
- **GOTCHA**:
  - Do NOT replace all QMessageBox calls — only 1–2 critical-path errors (training failure, export failure).
  - ErrorBanner sits between PageHeader and QStackedWidget in the layout.
  - Traceback text should be formatted with `traceback.format_exc()`.
  - Banner must auto-hide when user navigates to a different domain (connect to `_on_domain_changed`).
- **VALIDATE**: Trigger a training failure → ErrorBanner appears with user message. Toggle traceback → expands. Dismiss → banner hides. Navigate away → auto-hides.

---

### Task 7: Wire WorkflowState + ProjectSession in WorkbenchWindow

- **ACTION**: UPDATE `anylabeling/views/platform/workbench_window.py`
- **IMPLEMENT**:
  1. Create ProjectSession in `__init__`
  2. In `set_project()`: call `self._session.open_project(project_path)` instead of creating services directly
  3. After opening: call `self._session.refresh_navigation_state()` and update PrimaryNavigation
  4. Add a `_refresh_nav_states()` helper that maps DomainState → PrimaryNavigation.set_domain_state()
  5. In `closeEvent()`: call `self._session.close_project()`
  6. Update references from `self._job_service` to `self._session.job_service`
- **MIRROR**: `SERVICE_PATTERN` — existing service creation in workbench_window.py:228–237
- **IMPORTS**: `ProjectSession`, `WorkflowState` from application
- **GOTCHA**:
  - `self._job_service` is referenced in many places (poll methods, service creation). Replace all with `self._session.job_service` — add null check since it's None when no project open.
  - `self._dataset_build_service` is also direct — keep it as a separate reference for now (ProjectSession will absorb it in Phase 3).
  - Navigation state refresh should happen: after project open, after dataset build completes, after training completes, after export completes.
- **VALIDATE**: Open project → nav states update. Close project → services nullified. Switch projects → old state cleaned, new state loaded.

---

### Task 8: Update shell __init__.py and application __init__.py exports

- **ACTION**: UPDATE `anylabeling/views/platform/shell/__init__.py` and `anylabeling/platform/application/__init__.py`
- **IMPLEMENT**:
  - Add `TaskCenterDrawer`, `ErrorBanner` to shell exports
  - Add `WorkflowState`, `ProjectSession` to application exports
- **MIRROR**: `NAMING_CONVENTION` — existing __init__.py patterns
- **GOTCHA**: None — purely additive.
- **VALIDATE**: Import from package level works: `from anylabeling.views.platform.shell import TaskCenterDrawer`

---

### Task 9: Write unit tests

- **ACTION**: CREATE 4 test files
- **IMPLEMENT**:
  1. `tests/platform/application/test_workflow_state.py` — test each `_check_*` method with tmp_path fixtures
  2. `tests/platform/application/test_project_session.py` — test open/close lifecycle
  3. `tests/views/platform/shell/test_task_center_drawer.py` — test widget construction, job rendering, filter signals
  4. `tests/views/platform/shell/test_error_banner.py` — test show/dismiss/toggle traceback
- **MIRROR**: `TEST_STRUCTURE` (test_workbench_shell.py)
- **GOTCHA**: Tests requiring QApplication must use `skip_without_display`. Use `tmp_path` for filesystem fixtures. Mock JobService for TaskCenterDrawer tests. WorkflowState tests do NOT need QApplication.
- **VALIDATE**: `pytest tests/platform/application/test_workflow_state.py tests/platform/application/test_project_session.py tests/views/platform/shell/ -v`

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| WorkflowState: empty project | Empty project_root | All domains NOT_STARTED | Yes — empty dir |
| WorkflowState: assets only | project with assets/ containing files | PROJECT=READY, DATA_PREP=READY, rest NOT_STARTED | No |
| WorkflowState: has dataset build | project with dataset_builds/ | TRAIN=READY | No |
| WorkflowState: has completed run | project with runs/*/run.json (status=completed) | TRAIN=COMPLETED, EVAL_VALIDATE=READY | No |
| WorkflowState: has model artifact | project with models/ + _READY | EXPORT=READY | No |
| ProjectSession: open → is_open | open_project(tmp_path) | is_open=True, job_service not None | No |
| ProjectSession: close | close_project() | is_open=False, all services None | No |
| ProjectSession: double open | open_project(a), open_project(b) | session reflects project b | Yes |
| ProjectSession: close when not open | close_project() | no-op, no error | Yes |
| ErrorBanner: show_error | show_error(...) | Visible with title, what, impact, fix | No |
| ErrorBanner: toggle traceback | show_error(traceback="...") → click toggle | Traceback QTextEdit visible | No |
| ErrorBanner: dismiss | show_error() → click dismiss | Banner hidden, dismissed signal emitted | No |
| ErrorBanner: no traceback | show_error(traceback="") | Toggle button hidden | Yes |
| TaskCenterDrawer: render jobs | set_job_service → refresh | Task cards rendered for each job | No |
| TaskCenterDrawer: filter | click "Failed" tab | Only failed jobs visible | No |
| TaskCenterDrawer: cancel signal | click cancel on job card | job_cancel_requested emitted with job_id | No |
| TaskCenterDrawer: polling | setVisible(True) | Timer starts; setVisible(False) → timer stops | No |

### Edge Cases Checklist
- [x] Empty project directory → WorkflowState returns NOT_STARTED for all
- [x] Corrupted project.json → WorkflowState returns NOT_STARTED (no crash)
- [x] Missing jobs/ directory → JobService handles gracefully (creates it)
- [x] TaskCenterDrawer with no JobService → empty state message
- [x] TaskCenterDrawer rapidly toggled → no animation glitch
- [x] ErrorBanner shown twice → second call replaces first
- [x] ProjectSession opened with invalid path → raises ValueError
- [x] Navigation state refresh called before project open → all NOT_STARTED

---

## Validation Commands

### Static Analysis
```bash
python -c "from anylabeling.platform.application.workflow_state import WorkflowState; print('OK')"
python -c "from anylabeling.platform.application.project_session import ProjectSession; print('OK')"
python -c "from anylabeling.views.platform.shell import TaskCenterDrawer, ErrorBanner; print('OK')"
```
EXPECT: All imports succeed, no ImportError

### Unit Tests
```bash
pytest tests/platform/application/test_workflow_state.py tests/platform/application/test_project_session.py -v
pytest tests/views/platform/shell/test_task_center_drawer.py tests/views/platform/shell/test_error_banner.py -v
```
EXPECT: All tests pass

### Full Test Suite (regression)
```bash
pytest tests/platform/ -x -m "not slow"
```
EXPECT: No regressions from Phase 2a tests

### Manual Validation
- [ ] Open project → PrimaryNavigation domain items show correct NavState icons
- [ ] Click AppBar "Task Center" → drawer slides in from right
- [ ] Tasks appear in drawer with correct states and progress
- [ ] Filter tabs (All/Running/Failed/Completed) work correctly
- [ ] Click cancel on running job → job transitions to cancelling → cancelled
- [ ] Trigger a training error → ErrorBanner appears below PageHeader
- [ ] ErrorBanner shows user-friendly message (not raw traceback)
- [ ] Click "▼ Technical Details" → traceback expands
- [ ] Click dismiss → ErrorBanner hides
- [ ] Switch projects → old state cleaned, new state loaded
- [ ] StatusBar shows correct background task count

---

## Acceptance Criteria
- [ ] WorkflowState computes correct NavState for all 5 domains based on real project data
- [ ] ProjectSession encapsulates project open/close lifecycle
- [ ] TaskCenterDrawer shows all jobs from JobService with filter tabs and cancel/retry
- [ ] ErrorBanner shows user-facing error messages with collapsible traceback
- [ ] AppBar task center badge shows active job count
- [ ] StatusBar background task count updates from JobService
- [ ] PrimaryNavigation domain icons reflect WorkflowState
- [ ] Task center drawer polling starts/stops with visibility
- [ ] All tasks completed
- [ ] All validation commands pass
- [ ] Tests written and passing
- [ ] No type errors
- [ ] No lint errors
- [ ] No regression in existing 884 tests

## Completion Checklist
- [ ] Code follows discovered patterns (SERVICE_PATTERN, QWIDGET_PATTERN, NAMING_CONVENTION)
- [ ] Error handling matches codebase style (logger.exception + user message)
- [ ] Logging follows codebase conventions (logging.getLogger(__name__))
- [ ] Tests follow test patterns (pytest fixtures, skip_without_display, AAA)
- [ ] No hardcoded values (use style.py constants)
- [ ] No PyQt6 imports in application layer
- [ ] No Ultralytics imports in application layer
- [ ] Documentation updated (shell/__init__.py exports)
- [ ] No unnecessary scope additions
- [ ] Self-contained — no questions needed during implementation

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| TaskCenterDrawer slide animation glitchy on Windows | Medium | Low | Fall back to instant show/hide without animation if QPropertyAnimation causes flicker |
| JobService polling causes UI lag with many jobs | Low | Medium | Limit poll frequency to 1.5s; lazy-render task cards not visible in scroll area |
| WorkflowState logic too simplistic for real-world edge cases | Medium | Low | Each `_check_*` method inspects filesystem directly; add logging for unexpected states |
| ProjectSession.close_project() leaves dangling references | Low | High | Set ALL service references to None; add `is_open` guard on all public methods |
| ErrorBanner layout conflicts with PageHeader fixed height | Low | Medium | Place ErrorBanner OUTSIDE PageHeader (sibling in layout, not child); adjust vertical layout spacing |

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Job retry logic placement | Defer to Phase 4a | (A) Build generic retry in Phase 2b via command.json persistence + JobService.retry_job(); (B) Show info banner stub now, implement in Phase 4a | Per-job-type command reconstruction belongs in the Service layer (TrainingService, ExportService, etc.), which is refactored in Phase 4. Building retry in Phase 2b would couple TaskCenterDrawer (UI) to business logic prematurely. Phase 4a already requires training run recovery — retry fits naturally alongside that work. Phase 2b implements the complete UI (button + signal) so no UI rework is needed later. |

## Notes

- **Polling vs push**: JobService uses file-based state (state.json). Polling is the only option without rewriting the job infrastructure. Phase 4 may introduce a push mechanism.
- **ProjectSession scope**: In this phase, ProjectSession only owns JobService and WorkflowState. TrainingService, ExportService, etc. remain created in WorkbenchWindow (to be moved in Phase 3/4 when those services are refactored).
- **ErrorBanner scope**: Phase 2b replaces 1–2 critical-path QMessageBox calls as proof-of-integration. Full migration of all error displays to ErrorBanner is Phase 3–4 work.
- **TaskCenterDrawer vs old JobConsole**: The old JobConsole code is preserved (hidden, not deleted). TaskCenterDrawer is additive. Old JobConsole will be removed in Phase 5 cleanup.
- **Agent orchestration**: This plan is designed for single-agent sequential execution. Each task builds on the previous one (Task 1 → Task 3, Task 2 → Task 7). Tasks 3 and 4 can be parallelized if using sub-agents.

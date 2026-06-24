"""Task center drawer — right-side slide-in panel for background tasks.

Shows all background jobs from JobService with filter tabs, progress
indicators, and per-task actions (cancel, retry, view logs).

Width: 420 px (TASK_DRAWER_WIDTH). Polls JobService every 1500 ms
while visible.
"""

from __future__ import annotations

import logging

from PyQt6 import QtCore, QtWidgets

from anylabeling.platform.application.job_service import JobService
from anylabeling.views.labeling.utils.theme import get_theme
from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_FAMILY_MONO,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    TASK_DRAWER_WIDTH,
    get_state_color,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FILTERS = ["all", "running", "failed", "completed"]

_STATE_ICONS: dict[str, str] = {
    "queued": "⏳",
    "starting": "🔄",
    "running": "▶",
    "completed": "✓",
    "failed": "✗",
    "cancelling": "⏹",
    "cancelled": "✗",
    "unknown": "?",
}

_JOB_KIND_LABELS_ZH: dict[str, str] = {
    "training": "训练",
    "export": "导出",
    "evaluation": "评估",
    "inference": "推理",
    "dataset_build": "数据集构建",
}

_JOB_KIND_LABELS_EN: dict[str, str] = {
    "training": "Training",
    "export": "Export",
    "evaluation": "Evaluation",
    "inference": "Inference",
    "dataset_build": "Dataset Build",
}


def _job_kind_label(kind: str) -> str:
    return tr(
        _JOB_KIND_LABELS_ZH.get(kind, kind),
        _JOB_KIND_LABELS_EN.get(kind, kind),
    )


def _state_label(state: str) -> str:
    labels_zh = {
        "queued": "排队中",
        "starting": "启动中",
        "running": "运行中",
        "completed": "已完成",
        "failed": "失败",
        "cancelling": "取消中",
        "cancelled": "已取消",
    }
    labels_en = {
        "queued": "Queued",
        "starting": "Starting",
        "running": "Running",
        "completed": "Completed",
        "failed": "Failed",
        "cancelling": "Cancelling",
        "cancelled": "Cancelled",
    }
    return tr(labels_zh.get(state, state), labels_en.get(state, state))


# ---------------------------------------------------------------------------
# TaskCenterDrawer
# ---------------------------------------------------------------------------


class TaskCenterDrawer(QtWidgets.QWidget):
    """Right-side slide-in drawer for background task management.

    Signals:
        job_selected(str): A job was clicked (carries job_id).
        job_cancel_requested(str): User wants to cancel a job.
        job_retry_requested(str): User wants to retry a job.
        drawer_closed: The drawer was closed.
    """

    job_selected = QtCore.pyqtSignal(str)
    job_cancel_requested = QtCore.pyqtSignal(str)
    job_retry_requested = QtCore.pyqtSignal(str)
    drawer_closed = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self._job_service: JobService | None = None
        self._job_repository = None
        self._active_filter: str = "all"
        self._jobs: list[dict] = []
        self._known_states: dict[str, str] = {}
        self._hidden_job_ids: set[str] = set()
        self._visible: bool = False

        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(1500)
        self._poll_timer.timeout.connect(self._refresh)

        self._build_ui()
        self._apply_theme()
        self.setFixedWidth(TASK_DRAWER_WIDTH)
        self.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_job_service(self, service: JobService | None) -> None:
        """Set or clear the JobService to display."""
        self._job_service = service
        if service is None:
            self._jobs.clear()
            self._known_states.clear()
            self._hidden_job_ids.clear()
            self._render_task_list()

    def set_job_repository(self, repo) -> None:
        self._job_repository = repo

    def toggle(self) -> None:
        """Show or hide the drawer."""
        if self._visible:
            self.hide_drawer()
        else:
            self.show_drawer()

    def show_drawer(self) -> None:
        """Show the drawer and start polling."""
        self._visible = True
        self.setVisible(True)
        self._poll_timer.start()
        self._refresh()

    def hide_drawer(self) -> None:
        """Hide the drawer and stop polling."""
        self._visible = False
        self._poll_timer.stop()
        self.setVisible(False)
        self.drawer_closed.emit()

    def is_visible(self) -> bool:
        return self._visible

    # ------------------------------------------------------------------
    # Internal — UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(16, 12, 12, 12)
        header.setSpacing(8)

        title = QtWidgets.QLabel(tr("任务中心", "Task Center"))
        title.setStyleSheet(
            f"font-size: {FONT_SIZE_BODY}px; font-weight: 700; "
            f"font-family: {FONT_FAMILY};"
        )
        header.addWidget(title)
        header.addStretch(1)

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setFlat(True)
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide_drawer)
        header.addWidget(close_btn)

        layout.addLayout(header)

        # Filter tabs
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.setContentsMargins(12, 0, 12, 8)
        filter_layout.setSpacing(4)

        self._filter_buttons: dict[str, QtWidgets.QPushButton] = {}
        filter_labels_zh = {
            "all": "全部",
            "running": "运行中",
            "failed": "失败",
            "completed": "已完成",
        }
        filter_labels_en = {
            "all": "All",
            "running": "Running",
            "failed": "Failed",
            "completed": "Completed",
        }
        for fname in FILTERS:
            btn = QtWidgets.QPushButton(
                tr(filter_labels_zh[fname], filter_labels_en[fname])
            )
            btn.setFlat(True)
            btn.setCheckable(True)
            btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda checked, fn=fname: self._on_filter_changed(fn)
            )
            btn.setChecked(fname == "all")
            self._filter_buttons[fname] = btn
            filter_layout.addWidget(btn)

        filter_layout.addStretch(1)
        layout.addLayout(filter_layout)

        # Separator
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        t = get_theme()
        sep.setStyleSheet(f"color: {t.get('border', '#d9d9d9')};")
        layout.addWidget(sep)

        # Task list
        self._task_list_area = QtWidgets.QScrollArea()
        self._task_list_area.setWidgetResizable(True)
        self._task_list_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._task_list_container = QtWidgets.QWidget()
        self._task_list_layout = QtWidgets.QVBoxLayout()
        self._task_list_layout.setContentsMargins(8, 8, 8, 8)
        self._task_list_layout.setSpacing(4)
        self._task_list_layout.addStretch(1)
        self._task_list_container.setLayout(self._task_list_layout)
        self._task_list_area.setWidget(self._task_list_container)
        layout.addWidget(self._task_list_area, stretch=1)

        # Footer
        footer = QtWidgets.QHBoxLayout()
        footer.setContentsMargins(12, 8, 12, 8)

        self._clear_btn = QtWidgets.QPushButton(
            tr("清除已完成", "Clear completed")
        )
        self._clear_btn.setFlat(True)
        self._clear_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._on_clear_completed)
        footer.addWidget(self._clear_btn)
        footer.addStretch(1)

        layout.addLayout(footer)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Internal — theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        t = get_theme()
        self.setStyleSheet(f"""
            TaskCenterDrawer {{
                background-color: {t.get("surface", "#fff")};
                border-left: 1px solid {t.get("border", "#d9d9d9")};
            }}
        """)

        for fname, btn in self._filter_buttons.items():
            self._apply_filter_button_style(btn, fname)

        self._clear_btn.setStyleSheet(
            f"color: {t.get('text_secondary', '#999')}; border: none; "
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"font-family: {FONT_FAMILY};"
        )

    def _apply_filter_button_style(
        self, btn: QtWidgets.QPushButton, filter_name: str
    ) -> None:
        t = get_theme()
        active = filter_name == self._active_filter
        if active:
            bg = t.get("primary", "#1677ff")
            fg = "#ffffff"
        else:
            bg = "transparent"
            fg = t.get("text", "#333")

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: {"none" if active else
                    f"1px solid {t.get('border', '#d9d9d9')}"};
                border-radius: 4px;
                padding: 4px 12px;
                font-size: {FONT_SIZE_CAPTION}px;
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                background-color: {t.get("primary", "#1677ff") + "22"
                    if not active else bg};
            }}
        """)

    # ------------------------------------------------------------------
    # Internal — refresh
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Poll JobService and update the task list."""
        if self._job_service is None:
            return

        try:
            jobs = self._job_service.list_jobs()
        except Exception:
            logger.exception("Failed to list jobs in TaskCenterDrawer")
            return

        # Detect state changes and new jobs
        current_ids = {j.get("job_id", "") for j in jobs}
        old_ids = set(self._known_states.keys())

        for job in jobs:
            jid = job.get("job_id", "")
            new_state = job.get("state", "unknown")
            old_state = self._known_states.get(jid)
            if old_state and old_state != new_state:
                logger.debug(
                    "Job %s: %s → %s", jid, old_state, new_state
                )
            self._known_states[jid] = new_state

        # Reset hidden job IDs when new jobs appear
        if current_ids - old_ids:
            self._hidden_job_ids.clear()

        # Prune known states for jobs no longer in the list
        for stale_id in old_ids - current_ids:
            del self._known_states[stale_id]
            self._hidden_job_ids.discard(stale_id)

        self._jobs = jobs
        self._render_task_list()

    def _render_task_list(self) -> None:
        """Rebuild the task card list from current jobs."""
        # Clear existing cards (keep the stretch)
        while self._task_list_layout.count():
            item = self._task_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Filter jobs (by active filter tab and hidden set)
        filtered = [
            j for j in self._filter_jobs(self._jobs)
            if j.get("job_id", "") not in self._hidden_job_ids
        ]

        if not filtered:
            empty_label = QtWidgets.QLabel(tr("暂无任务", "No tasks"))
            empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            t = get_theme()
            empty_label.setStyleSheet(
                f"color: {t.get('text_secondary', '#999')}; "
                f"font-size: {FONT_SIZE_CAPTION}px; "
                f"font-family: {FONT_FAMILY}; padding: 24px;"
            )
            self._task_list_layout.addWidget(empty_label)
        else:
            for job in filtered:
                card = self._render_task_card(job)
                self._task_list_layout.addWidget(card)

        self._task_list_layout.addStretch(1)

    def _render_task_card(self, job: dict) -> QtWidgets.QWidget:
        """Create a card widget for a single job."""
        t = get_theme()
        jid = job.get("job_id", "?")
        kind = job.get("job_kind", "unknown")
        state = job.get("state", "unknown")
        icon = _STATE_ICONS.get(state, "?")

        card = QtWidgets.QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background-color: {t.get("background", "#fafafa")};
                border: 1px solid {t.get("border", "#d9d9d9")};
                border-radius: 6px;
            }}
        """)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Row 0: icon + kind + job_id
        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(6)

        icon_label = QtWidgets.QLabel(icon)
        icon_label.setFixedWidth(20)
        top_row.addWidget(icon_label)

        kind_label = QtWidgets.QLabel(
            f"{_job_kind_label(kind)}  {jid[:12]}"
        )
        kind_label.setStyleSheet(
            f"font-weight: 600; font-size: {FONT_SIZE_CAPTION}px; "
            f"color: {t.get('text', '#333')}; "
            f"font-family: {FONT_FAMILY}; border: none; "
            f"background: transparent;"
        )
        top_row.addWidget(kind_label, stretch=1)

        state_color = get_state_color(state)
        state_label = QtWidgets.QLabel(_state_label(state))
        state_label.setStyleSheet(
            f"font-weight: 700; font-size: {FONT_SIZE_CAPTION}px; "
            f"color: {state_color}; "
            f"font-family: {FONT_FAMILY}; border: none; "
            f"background: transparent;"
        )
        top_row.addWidget(state_label)

        layout.addLayout(top_row)

        # Row 1: actions
        actions_row = QtWidgets.QHBoxLayout()
        actions_row.setSpacing(8)

        if state not in {"completed", "failed", "cancelled"}:
            cancel_btn = QtWidgets.QPushButton(tr("停止", "Cancel"))
            cancel_btn.setFlat(True)
            cancel_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            cancel_btn.setStyleSheet(
                f"color: {t.get('error', '#cf1322')}; border: none; "
                f"font-size: {FONT_SIZE_CAPTION}px; "
                f"font-family: {FONT_FAMILY}; background: transparent;"
            )
            cancel_btn.clicked.connect(
                lambda checked, j=jid: self._on_cancel_job(j)
            )
            actions_row.addWidget(cancel_btn)

        if state in {"failed", "cancelled"}:
            retry_btn = QtWidgets.QPushButton(tr("重试", "Retry"))
            retry_btn.setFlat(True)
            retry_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            retry_btn.setStyleSheet(
                f"color: {t.get('primary', '#1677ff')}; border: none; "
                f"font-size: {FONT_SIZE_CAPTION}px; "
                f"font-family: {FONT_FAMILY}; background: transparent;"
            )
            retry_btn.clicked.connect(
                lambda checked, j=jid: self._on_retry_job(j)
            )
            actions_row.addWidget(retry_btn)

        actions_row.addStretch(1)

        layout.addLayout(actions_row)
        card.setLayout(layout)
        return card

    def _filter_jobs(self, jobs: list[dict]) -> list[dict]:
        """Filter jobs by active filter tab."""
        if self._active_filter == "all":
            return jobs
        if self._active_filter == "running":
            return [
                j for j in jobs
                if j.get("state") in {"queued", "starting", "running"}
            ]
        if self._active_filter == "failed":
            return [
                j for j in jobs
                if j.get("state") in {"failed", "cancelled"}
            ]
        if self._active_filter == "completed":
            return [
                j for j in jobs
                if j.get("state") == "completed"
            ]
        return jobs

    # ------------------------------------------------------------------
    # Internal — slots
    # ------------------------------------------------------------------

    def _on_filter_changed(self, filter_name: str) -> None:
        self._active_filter = filter_name
        for fname, btn in self._filter_buttons.items():
            btn.setChecked(fname == filter_name)
            self._apply_filter_button_style(btn, fname)
        self._render_task_list()

    def _on_clear_completed(self) -> None:
        """Remove completed/cancelled/failed jobs from display."""
        terminal_states = {"completed", "failed", "cancelled"}
        for j in self._jobs:
            if j.get("state") in terminal_states:
                self._hidden_job_ids.add(j.get("job_id", ""))
        self._render_task_list()

    def _on_cancel_job(self, job_id: str) -> None:
        logger.info("Cancel requested for job %s", job_id)
        self.job_cancel_requested.emit(job_id)

    def _on_retry_job(self, job_id: str) -> None:
        logger.info("Retry requested for job %s (deferred to Phase 4)", job_id)
        self.job_retry_requested.emit(job_id)

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._poll_timer.stop()
        super().hideEvent(event)

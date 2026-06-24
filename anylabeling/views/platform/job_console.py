"""Job console -- bottom panel showing job status, progress, and logs.

Subscribes to JobService events (not disk scanning).
"""

from __future__ import annotations

import logging
from typing import Dict

from PyQt6 import QtCore, QtWidgets

from anylabeling.platform.application.job_service import JobService
from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_CAPTION,
    get_ghost_button_style,
    get_list_widget_style,
    get_log_view_style,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)

_REFRESH_INTERVAL = 2000

_STATE_ICONS: dict[str, str] = {
    "queued": "⏳",
    "starting": "▶",
    "running": "▶",
    "completed": "✅",
    "failed": "❌",
    "cancelling": "⏹",
    "cancelled": "⏹",
}

_STATE_TOOLTIPS_EN: dict[str, str] = {
    "queued": "Queued",
    "starting": "Starting",
    "running": "Running",
    "completed": "Completed",
    "failed": "Failed",
    "cancelling": "Cancelling",
    "cancelled": "Cancelled",
}

_STATE_TOOLTIPS_ZH: dict[str, str] = {
    "queued": "排队中",
    "starting": "启动中",
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
    "cancelling": "取消中",
    "cancelled": "已取消",
}


class JobConsole(QtWidgets.QWidget):
    """Bottom panel showing job status, progress, and logs."""

    job_started = QtCore.pyqtSignal(str, str)
    job_finished = QtCore.pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._job_service: JobService | None = None

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title = QtWidgets.QLabel(tr("任务", "Jobs"))
        title.setStyleSheet(
            f"font-weight: bold; font-size: {FONT_SIZE_CAPTION + 1}px;"
            f"color: {get_theme()['text']}; font-family: {FONT_FAMILY};"
        )
        header.addWidget(title)

        header.addStretch()

        self._btn_clear = QtWidgets.QPushButton(tr("清除已完成", "Clear Finished"))
        self._btn_clear.setFlat(True)
        self._btn_clear.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._btn_clear.clicked.connect(self._on_clear_finished)
        self._btn_clear.setStyleSheet(get_ghost_button_style())
        header.addWidget(self._btn_clear)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        self._job_list = QtWidgets.QListWidget()
        self._job_list.setMaximumWidth(320)
        self._job_list.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._job_list.currentRowChanged.connect(self._on_job_selected)
        self._job_list.setStyleSheet(get_list_widget_style())
        splitter.addWidget(self._job_list)

        self._log_view = QtWidgets.QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setPlaceholderText(tr(
            "选择一个任务以查看其日志\n\n提示：在「训练」页面启动训练后，任务将出现在这里",
            "Select a job to view its logs\n\nTip: Start training in the Train page and jobs will appear here"
        ))
        self._log_view.setStyleSheet(get_log_view_style())
        splitter.addWidget(self._log_view)

        splitter.setSizes([300, 600])

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)
        layout.addLayout(header)
        layout.addWidget(splitter)
        self.setLayout(layout)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.setInterval(_REFRESH_INTERVAL)

        self._known_states: Dict[str, str] = {}
        self._selected_job_id: str | None = None
        self._refresh_failures: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_job_service(self, service: JobService | None) -> None:
        self._job_service = service
        if service is not None:
            self._timer.start()
            self._refresh()
        else:
            self._timer.stop()

    def job_service(self) -> JobService | None:
        return self._job_service

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh(self):
        if self._job_service is None:
            return

        try:
            jobs = self._job_service.list_jobs()
        except Exception as exc:
            logger.warning("Failed to refresh job list: %s", exc, exc_info=True)
            self._refresh_failures += 1
            if self._refresh_failures >= 3:
                self._job_list.blockSignals(True)
                self._job_list.clear()
                self._job_list.addItem(
                    tr("⚠ 刷新任务出错 — 请检查任务服务连接",
                       "⚠ Error refreshing jobs — check job service connection")
                )
                self._job_list.blockSignals(False)
                self._refresh_failures = 0
            return
        else:
            self._refresh_failures = 0

        for job in jobs:
            jid = job["job_id"]
            new_state = job["state"]
            old_state = self._known_states.get(jid)

            if old_state != new_state:
                if new_state == "running" and old_state not in ("running",):
                    self.job_started.emit(jid, job["job_kind"])
                if new_state in ("completed", "failed", "cancelled"):
                    if old_state not in ("completed", "failed", "cancelled"):
                        self.job_finished.emit(jid, new_state)
                self._known_states[jid] = new_state

        self._job_list.blockSignals(True)
        previous_selection = self._selected_job_id
        self._job_list.clear()

        for job in jobs:
            icon = _STATE_ICONS.get(job["state"], "?")
            text = _format_job_line(job)
            item = QtWidgets.QListWidgetItem(f"{icon}  {text}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, job["job_id"])
            state = job["state"]
            item.setToolTip(tr(
                _STATE_TOOLTIPS_ZH.get(state, state),
                _STATE_TOOLTIPS_EN.get(state, state),
            ))
            self._job_list.addItem(item)

            if job["job_id"] == previous_selection:
                self._job_list.setCurrentItem(item)

        self._job_list.blockSignals(False)

    def _on_job_selected(self, row: int):
        if row < 0:
            self._log_view.clear()
            self._selected_job_id = None
            return

        item = self._job_list.item(row)
        if item is None:
            return

        job_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self._selected_job_id = job_id
        self._load_logs(job_id)

    def _load_logs(self, job_id: str):
        if self._job_service is None:
            self._log_view.setPlainText(tr("（未连接任务服务）", "(No job service connected)"))
            return

        try:
            stdout, stderr = self._job_service.get_job_logs(job_id)
            text_parts = []
            if stdout:
                text_parts.append("--- stdout ---\n" + stdout)
            if stderr:
                text_parts.append("--- stderr ---\n" + stderr)
            if not text_parts:
                text_parts.append(tr("（暂无日志）", "(No logs yet)"))
            self._log_view.setPlainText("\n\n".join(text_parts))
        except Exception as exc:
            self._log_view.setPlainText(
                tr(f"（加载日志出错：{exc}）", f"(Error loading logs: {exc})")
            )

    def _on_clear_finished(self):
        finished = {"completed", "failed", "cancelled"}
        to_remove = []
        for i in range(self._job_list.count()):
            item = self._job_list.item(i)
            state = ""
            if item:
                for s, icon in _STATE_ICONS.items():
                    if item.text().startswith(icon):
                        state = s
                        break
            if state in finished:
                to_remove.append(item.data(QtCore.Qt.ItemDataRole.UserRole))

        for jid in to_remove:
            self._known_states.pop(jid, None)

        self._refresh()


def _format_job_line(job: dict) -> str:
    jid = job.get("job_id", "?")
    kind = job.get("job_kind", "?")
    short_id = jid[-8:] if len(jid) > 8 else jid
    return f"{kind} ({short_id})"

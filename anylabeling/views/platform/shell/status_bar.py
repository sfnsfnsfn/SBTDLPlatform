"""Status bar — bottom-of-window status strip (24 px)."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_CAPTION,
    STATUS_BAR_HEIGHT,
)
from anylabeling.views.labeling.utils.theme import get_theme


class StatusBar(QtWidgets.QWidget):
    """Bottom status bar — fixed 24 px height.

    Four segments (left to right)::

        [保存状态] | [设备] | [后台任务] | [离线状态]

    Save status is clickable when in error state (emits ``save_retry_requested``).
    """

    save_retry_requested = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self._save_error = False

        self._build_ui()
        self._apply_theme()

        # Install event filter for clickable save-retry
        self._save_label.installEventFilter(self)

        # Initial state
        self.set_save_status(tr("未保存", "Not saved"))
        self.set_device(tr("CPU", "CPU"))
        self.set_background_tasks(0)
        self.set_offline_status(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_save_status(self, status: str) -> None:
        """Set the save/project status text.

        Args:
            status: "已保存" / "正在保存…" / "保存失败—重试"
        """
        is_error = (
            tr("失败", "fail") in status
            or tr("重试", "retry") in status
        )
        t = get_theme()
        if is_error:
            self._save_error = True
            self._save_label.setStyleSheet(
                f"color: {t['error']}; font-size: {FONT_SIZE_CAPTION}px; "
                f"font-family: {FONT_FAMILY}; text-decoration: underline;"
            )
            self._save_label.setCursor(
                QtCore.Qt.CursorShape.PointingHandCursor
            )
        else:
            self._save_error = False
            self._apply_label_style(self._save_label)
            self._save_label.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

        self._save_label.setText(status)

    def set_device(self, device: str) -> None:
        """Set the compute device (e.g. "CPU", "CUDA: RTX 4090")."""
        self._device_label.setText(device)

    def set_background_tasks(
        self, count: int, summary: str = ""
    ) -> None:
        """Set the background task indicator."""
        if count > 0:
            text = tr(
                f"后台任务: {count}", f"Background: {count}"
            )
            if summary:
                text += f" ({summary})"
        else:
            text = tr("无后台任务", "No background tasks")
        self._tasks_label.setText(text)

    def set_offline_status(self, offline: bool) -> None:
        """Set the offline/online status indicator."""
        t = get_theme()
        if offline:
            self._offline_label.setText(tr("离线", "Offline"))
            self._offline_label.setStyleSheet(
                f"color: {t['success']}; font-size: {FONT_SIZE_CAPTION}px; "
                f"font-family: {FONT_FAMILY};"
            )
        else:
            self._offline_label.setText(tr("在线", "Online"))
            self._offline_label.setStyleSheet(
                f"color: {t['text_secondary']}; "
                f"font-size: {FONT_SIZE_CAPTION}px; "
                f"font-family: {FONT_FAMILY};"
            )

    # ------------------------------------------------------------------
    # Internal — UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setFixedHeight(STATUS_BAR_HEIGHT)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(16)

        # Segment 1: Save status
        self._save_label = QtWidgets.QLabel()
        layout.addWidget(self._save_label)

        layout.addWidget(self._make_separator())

        # Segment 2: Device
        self._device_label = QtWidgets.QLabel()
        layout.addWidget(self._device_label)

        layout.addWidget(self._make_separator())

        # Segment 3: Background tasks
        self._tasks_label = QtWidgets.QLabel()
        layout.addWidget(self._tasks_label)

        layout.addWidget(self._make_separator())

        # Segment 4: Offline status
        self._offline_label = QtWidgets.QLabel()
        layout.addWidget(self._offline_label)

        layout.addStretch(1)
        self.setLayout(layout)

    @staticmethod
    def _make_separator() -> QtWidgets.QLabel:
        t = get_theme()
        sep = QtWidgets.QLabel("|")
        sep.setStyleSheet(
            f"color: {t['border']}; font-size: {FONT_SIZE_CAPTION}px;"
        )
        return sep

    # ------------------------------------------------------------------
    # Internal — theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        t = get_theme()
        self.setStyleSheet(f"""
            StatusBar {{
                background-color: {t["surface"]};
                border-top: 1px solid {t["border"]};
            }}
        """)
        for lbl in (
            self._save_label,
            self._device_label,
            self._tasks_label,
        ):
            self._apply_label_style(lbl)

    def _apply_label_style(self, label: QtWidgets.QLabel) -> None:
        t = get_theme()
        label.setStyleSheet(
            f"color: {t['text_secondary']}; "
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"font-family: {FONT_FAMILY};"
        )

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def eventFilter(
        self, obj: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        """Handle clicks on the save-status label when in error state."""
        if (
            obj is self._save_label
            and self._save_error
            and event.type() == QtCore.QEvent.Type.MouseButtonPress
        ):
            self.save_retry_requested.emit()
            return True
        return super().eventFilter(obj, event)

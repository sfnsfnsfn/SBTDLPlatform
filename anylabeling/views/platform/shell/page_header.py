"""Page header — unified title area for every domain page.

Fixed height 56 px. Layout::

    [Title (18px)] [Subtitle (12px)] ... [Status] [Primary Action Button]
         [Breadcrumb trail (clickable)]

The primary action button describes the user's OUTCOME, not the action itself
(e.g. "开始训练" not "执行").
"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_HERO,
    PAGE_HEADER_HEIGHT,
    get_primary_button_style,
    get_ghost_button_style,
)
from anylabeling.views.labeling.utils.theme import get_theme


class PageHeader(QtWidgets.QWidget):
    """Unified page header for all 5 domains.

    Emits ``primary_action_triggered`` when the main action button is clicked.
    Breadcrumb items emit ``breadcrumb_clicked(str)`` with the target key.
    """

    primary_action_triggered = QtCore.pyqtSignal()
    breadcrumb_clicked = QtCore.pyqtSignal(str)  # target domain/step key

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self._title: str = ""
        self._subtitle: str = ""
        self._breadcrumbs: list[tuple[str, str]] = []
        self._status_text: str = ""
        self._action_label: str = ""
        self._state_summary: str = ""

        self._build_ui()
        self._apply_theme()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_title(self, title: str) -> None:
        """Set the main page title (18 px, bold)."""
        self._title = title
        self._title_label.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        """Set the small subtitle below/beside the title."""
        self._subtitle = subtitle
        self._subtitle_label.setText(subtitle)
        self._subtitle_label.setVisible(bool(subtitle))

    def set_breadcrumb(self, items: list[tuple[str, str]]) -> None:
        """Set clickable breadcrumb trail.

        Args:
            items: List of (label, target_key) pairs, e.g.
                [("实例分割 v3", "task"), ("build-003", "build")]
        """
        self._breadcrumbs = items
        self._rebuild_breadcrumbs()

    def set_status(self, status: str) -> None:
        """Set a status label in the header."""
        self._status_text = status
        self._status_label.setText(status)
        self._status_label.setVisible(bool(status))

    def set_primary_action(
        self, label: str, enabled: bool = True
    ) -> None:
        """Set the primary action button label and enable state."""
        self._action_label = label
        self._primary_btn.setText(label)
        self._primary_btn.setEnabled(enabled)
        self._primary_btn.setVisible(True)

    def clear_primary_action(self) -> None:
        """Hide the primary action button."""
        self._primary_btn.setVisible(False)
        self._action_label = ""

    def set_state_summary(self, text: str) -> None:
        """Set a summary line below the breadcrumb (data prep stats)."""
        self._state_summary = text
        self._summary_label.setText(text)
        self._summary_label.setVisible(bool(text))

    # ------------------------------------------------------------------
    # Internal — UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setFixedHeight(PAGE_HEADER_HEIGHT)

        outer = QtWidgets.QHBoxLayout()
        outer.setContentsMargins(20, 4, 16, 4)
        outer.setSpacing(8)

        # Left column: title + breadcrumb + summary
        left = QtWidgets.QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(2)

        # Row 0: Title + Subtitle
        title_row = QtWidgets.QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        self._title_label = QtWidgets.QLabel()
        self._subtitle_label = QtWidgets.QLabel()
        self._subtitle_label.setStyleSheet(
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"font-family: {FONT_FAMILY};"
        )
        self._subtitle_label.setVisible(False)

        title_row.addWidget(self._title_label)
        title_row.addWidget(self._subtitle_label)
        title_row.addStretch(1)

        # Row 1: Breadcrumb
        self._breadcrumb_layout = QtWidgets.QHBoxLayout()
        self._breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        self._breadcrumb_layout.setSpacing(4)

        # Row 2: Summary (optional)
        self._summary_label = QtWidgets.QLabel()
        self._summary_label.setStyleSheet(
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"font-family: {FONT_FAMILY};"
        )
        self._summary_label.setVisible(False)

        left.addLayout(title_row)
        left.addLayout(self._breadcrumb_layout)
        left.addWidget(self._summary_label)

        outer.addLayout(left, stretch=1)

        # Right: Status + Primary action
        self._status_label = QtWidgets.QLabel()
        self._status_label.setVisible(False)
        outer.addWidget(self._status_label)

        self._primary_btn = QtWidgets.QPushButton()
        self._primary_btn.setStyleSheet(get_primary_button_style())
        self._primary_btn.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self._primary_btn.clicked.connect(
            self.primary_action_triggered.emit
        )
        self._primary_btn.setVisible(False)
        outer.addWidget(self._primary_btn)

        self.setLayout(outer)

    # ------------------------------------------------------------------
    # Internal — theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        t = get_theme()
        self.setStyleSheet(f"""
            PageHeader {{
                background-color: {t["background"]};
                border-bottom: 1px solid {t["border"]};
            }}
        """)
        self._title_label.setStyleSheet(
            f"font-size: {FONT_SIZE_HERO}px; font-weight: 700; "
            f"color: {t['text']}; font-family: {FONT_FAMILY};"
        )
        self._status_label.setStyleSheet(
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"color: {t['text_secondary']}; font-family: {FONT_FAMILY};"
        )

    def _rebuild_breadcrumbs(self) -> None:
        # Clear existing breadcrumb widgets
        while self._breadcrumb_layout.count():
            item = self._breadcrumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._breadcrumbs:
            return

        t = get_theme()
        for i, (label, target) in enumerate(self._breadcrumbs):
            if i > 0:
                sep = QtWidgets.QLabel("/")
                sep.setStyleSheet(
                    f"color: {t['text_secondary']}; "
                    f"font-size: {FONT_SIZE_CAPTION}px; "
                    f"font-family: {FONT_FAMILY};"
                )
                self._breadcrumb_layout.addWidget(sep)

            btn = QtWidgets.QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(get_ghost_button_style())
            btn.clicked.connect(
                lambda checked, tgt=target: self.breadcrumb_clicked.emit(tgt)
            )
            self._breadcrumb_layout.addWidget(btn)

        self._breadcrumb_layout.addStretch(1)

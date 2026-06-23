"""Error banner — inline non-blocking error display below PageHeader.

Shows a user-facing message (what happened, impact, how to fix) with
an optional collapsible technical traceback section.

Uses the existing ``get_info_banner_style()`` for theme-aware colours.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.labeling.utils.theme import get_theme
from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_FAMILY_MONO,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
)

MAX_TRACEBACK_CHARS = 10000


class ErrorBanner(QtWidgets.QWidget):
    """Inline error/warning/info display banner.

    Appears below the PageHeader. The primary message is plain-language
    ("what happened + impact + how to fix"). Technical traceback is
    hidden behind a collapsible toggle.

    Signals:
        dismissed: Emitted when the user clicks the close button.
        retry_requested: Emitted when the user clicks the retry button.
    """

    dismissed = QtCore.pyqtSignal()
    retry_requested = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self._variant: str = "error"
        self._traceback_text: str = ""
        self._traceback_expanded: bool = False

        self._build_ui()
        self._apply_theme()
        self.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
            title: Short error title (e.g. "训练失败").
            what: What happened (plain language).
            impact: What this affects.
            fix: How to resolve.
            traceback: Optional technical traceback (collapsed by default).
            retry_action: If non-empty, show a retry button with this label.
        """
        self._variant = "error"
        self._traceback_text = traceback
        self._traceback_expanded = False

        message_parts = []
        if what:
            message_parts.append(
                tr(f"发生了什么：{what}", f"What: {what}")
            )
        if impact:
            message_parts.append(
                tr(f"影响：{impact}", f"Impact: {impact}")
            )
        if fix:
            message_parts.append(
                tr(f"如何处理：{fix}", f"Fix: {fix}")
            )

        self._title_label.setText(title)
        self._message_label.setText("  —  ".join(message_parts))
        self._toggle_btn.setVisible(bool(traceback))
        self._retry_btn.setVisible(bool(retry_action))
        if retry_action:
            self._retry_btn.setText(retry_action)
        if len(traceback) > MAX_TRACEBACK_CHARS:
            traceback = traceback[:MAX_TRACEBACK_CHARS] + "\n\n... (truncated)"
        self._traceback_edit.setPlainText(traceback)
        self._traceback_edit.setVisible(False)

        self._apply_theme()
        self.setVisible(True)

    def show_warning(self, title: str, message: str) -> None:
        """Display a warning banner."""
        self._variant = "warning"
        self._traceback_text = ""
        self._traceback_expanded = False

        self._title_label.setText(title)
        self._message_label.setText(message)
        self._toggle_btn.setVisible(False)
        self._retry_btn.setVisible(False)
        self._traceback_edit.setVisible(False)

        self._apply_theme()
        self.setVisible(True)

    def show_info(self, title: str, message: str) -> None:
        """Display an info banner."""
        self._variant = "info"
        self._traceback_text = ""
        self._traceback_expanded = False

        self._title_label.setText(title)
        self._message_label.setText(message)
        self._toggle_btn.setVisible(False)
        self._retry_btn.setVisible(False)
        self._traceback_edit.setVisible(False)

        self._apply_theme()
        self.setVisible(True)

    def dismiss(self) -> None:
        """Hide the banner and emit ``dismissed``."""
        self.setVisible(False)
        self.dismissed.emit()

    def clear(self) -> None:
        """Hide the banner without emitting signals."""
        self.setVisible(False)

    # ------------------------------------------------------------------
    # Internal — UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QtWidgets.QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # Row 0: icon + title + message + buttons
        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(12, 8, 12, 8)
        top_row.setSpacing(8)

        self._icon_label = QtWidgets.QLabel()
        self._icon_label.setFixedWidth(20)
        self._icon_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter
        )
        top_row.addWidget(self._icon_label)

        self._title_label = QtWidgets.QLabel()
        self._title_label.setStyleSheet(
            f"font-weight: 700; font-size: {FONT_SIZE_BODY}px; "
            f"font-family: {FONT_FAMILY};"
        )
        top_row.addWidget(self._title_label)

        self._message_label = QtWidgets.QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet(
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"font-family: {FONT_FAMILY};"
        )
        top_row.addWidget(self._message_label, stretch=1)

        self._toggle_btn = QtWidgets.QPushButton(
            tr("▼ 技术详情", "▼ Details")
        )
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self._toggle_btn.clicked.connect(self._on_toggle_traceback)
        self._toggle_btn.setVisible(False)
        top_row.addWidget(self._toggle_btn)

        self._retry_btn = QtWidgets.QPushButton()
        self._retry_btn.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self._retry_btn.clicked.connect(self.retry_requested.emit)
        self._retry_btn.setVisible(False)
        top_row.addWidget(self._retry_btn)

        self._dismiss_btn = QtWidgets.QPushButton("✕")
        self._dismiss_btn.setFlat(True)
        self._dismiss_btn.setFixedSize(24, 24)
        self._dismiss_btn.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self._dismiss_btn.clicked.connect(self.dismiss)
        top_row.addWidget(self._dismiss_btn)

        outer.addLayout(top_row)

        # Row 1: collapsible traceback
        self._traceback_edit = QtWidgets.QTextEdit()
        self._traceback_edit.setReadOnly(True)
        self._traceback_edit.setMaximumHeight(200)
        self._traceback_edit.setVisible(False)
        outer.addWidget(self._traceback_edit)

        self.setLayout(outer)

    # ------------------------------------------------------------------
    # Internal — theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        t = get_theme()

        # Icon per variant
        icons = {"error": "⚠", "warning": "⚠", "info": "ℹ"}
        self._icon_label.setText(icons.get(self._variant, "ℹ"))

        # Banner background — construct ErrorBanner QSS directly
        # instead of relying on fragile QLabel→ErrorBanner string replace.
        if self._variant == "success":
            bg, border_c = "#f6ffed", "#b7eb8f"
        elif self._variant == "warning":
            bg, border_c = "#fffbe6", "#ffe58f"
        elif self._variant == "error":
            bg, border_c = "#fff2f0", "#ffccc7"
        else:  # info
            bg = t.get("surface", "#fff")
            border_c = t.get("border_light", "#d9d9d9")

        self.setStyleSheet(f"""
            ErrorBanner {{
                background-color: {bg};
                border: 1px solid {border_c};
                border-radius: 8px;
                padding: 12px 16px;
                font-size: {FONT_SIZE_BODY}px;
                color: {t.get("text", "#333")};
            }}
        """)

        # Title colour
        title_colors = {
            "error": t.get("error", "#cf1322"),
            "warning": "#d48806",
            "info": t.get("primary", "#1677ff"),
        }
        self._title_label.setStyleSheet(
            f"font-weight: 700; font-size: {FONT_SIZE_BODY}px; "
            f"color: {title_colors.get(self._variant, t['text'])}; "
            f"font-family: {FONT_FAMILY};"
        )

        # Message colour
        self._message_label.setStyleSheet(
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"color: {t.get('text_secondary', t['text'])}; "
            f"font-family: {FONT_FAMILY};"
        )

        # Toggle button
        self._toggle_btn.setStyleSheet(
            f"color: {t.get('primary', '#1677ff')}; border: none; "
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"font-family: {FONT_FAMILY};"
        )

        # Retry button
        self._retry_btn.setStyleSheet(
            f"color: {t.get('primary', '#1677ff')}; "
            f"border: 1px solid {t.get('border', '#d9d9d9')}; "
            f"border-radius: 4px; padding: 4px 12px; "
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"font-family: {FONT_FAMILY};"
        )

        # Dismiss button
        self._dismiss_btn.setStyleSheet(
            f"color: {t.get('text_secondary', '#999')}; border: none; "
            f"font-size: 14px; font-family: {FONT_FAMILY};"
        )

        # Traceback
        self._traceback_edit.setStyleSheet(
            f"background-color: {t.get('background', '#fff')}; "
            f"color: {t.get('text', '#333')}; "
            f"border: 1px solid {t.get('border', '#d9d9d9')}; "
            f"border-radius: 4px; padding: 8px; "
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"font-family: {FONT_FAMILY_MONO};"
        )

    # ------------------------------------------------------------------
    # Internal — slots
    # ------------------------------------------------------------------

    def _on_toggle_traceback(self) -> None:
        """Expand or collapse the technical traceback section."""
        self._traceback_expanded = not self._traceback_expanded
        self._traceback_edit.setVisible(self._traceback_expanded)
        self._toggle_btn.setText(
            tr("▲ 收起详情", "▲ Hide details")
            if self._traceback_expanded
            else tr("▼ 技术详情", "▼ Details")
        )

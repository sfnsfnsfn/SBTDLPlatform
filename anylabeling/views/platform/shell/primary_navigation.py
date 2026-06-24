"""Primary navigation — 5-domain left sidebar.

Replaces the 8-step horizontal NavigationBar with a vertical 5-domain
navigation panel. Each domain shows an icon, label, and status indicator.
"""

from __future__ import annotations

from enum import Enum, IntEnum

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    PRIMARY_NAV_MIN_WIDTH,
    PRIMARY_NAV_WIDTH,
)
from anylabeling.views.labeling.utils.theme import get_theme


# ---------------------------------------------------------------------------
# Domain enum — 5-domain top-level navigation
# ---------------------------------------------------------------------------


class Domain(IntEnum):
    """Five-domain navigation structure (replaces 8-step pipeline)."""
    PROJECT = 0
    DATA_PREP = 1
    TRAIN = 2
    EVAL_VALIDATE = 3
    EXPORT = 4


DOMAIN_LABELS_ZH: dict[Domain, str] = {
    Domain.PROJECT: "项目",
    Domain.DATA_PREP: "数据准备",
    Domain.TRAIN: "训练",
    Domain.EVAL_VALIDATE: "评估与验证",
    Domain.EXPORT: "导出",
}

DOMAIN_LABELS_EN: dict[Domain, str] = {
    Domain.PROJECT: "Project",
    Domain.DATA_PREP: "Data Prep",
    Domain.TRAIN: "Train",
    Domain.EVAL_VALIDATE: "Eval & Validate",
    Domain.EXPORT: "Export",
}

# Unicode icon characters per domain (fallback until SVG icons)
_DOMAIN_ICONS: dict[Domain, str] = {
    Domain.PROJECT: "\U0001f4c1",       # 📁 folder
    Domain.DATA_PREP: "\U0001f50d",     # 🔍 magnifying glass
    Domain.TRAIN: "⚙️",       # ⚙️ gear
    Domain.EVAL_VALIDATE: "\U0001f4ca",  # 📊 bar chart
    Domain.EXPORT: "\U0001f4e4",        # 📤 outbox tray
}


# ---------------------------------------------------------------------------
# NavState enum
# ---------------------------------------------------------------------------


class NavState(Enum):
    """Per-domain navigation state indicator.

    Each state maps to a distinct visual treatment (icon + colour).
    Colour is never the sole differentiator.
    """
    NOT_STARTED = "not_started"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NEEDS_ATTENTION = "needs_attention"
    EXPIRED = "expired"


# Unicode indicators per state (paired with colour in the widget)
_STATE_ICONS: dict[NavState, str] = {
    NavState.NOT_STARTED: "○",      # ○
    NavState.READY: "●",             # ●
    NavState.IN_PROGRESS: "▶",       # ▶
    NavState.COMPLETED: "✓",         # ✓
    NavState.NEEDS_ATTENTION: "⚠",   # ⚠
    NavState.EXPIRED: "✗",           # ✗
}

_STATE_COLORS: dict[NavState, str] = {
    NavState.NOT_STARTED: "text_secondary",
    NavState.READY: "primary",
    NavState.IN_PROGRESS: "primary",
    NavState.COMPLETED: "success",
    NavState.NEEDS_ATTENTION: "warning",
    NavState.EXPIRED: "error",
}


# ---------------------------------------------------------------------------
# PrimaryNavigation widget
# ---------------------------------------------------------------------------


class PrimaryNavigation(QtWidgets.QWidget):
    """5-domain vertical navigation panel.

    Emits ``domain_changed(int)`` when the user clicks a domain button.
    Emits ``fold_requested(bool)`` when the fold toggle is clicked.

    Supports folding to 56 px (icon-only) for label workspace.
    """

    domain_changed = QtCore.pyqtSignal(int)  # Domain value
    fold_requested = QtCore.pyqtSignal(bool)  # True = fold

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self._current_domain: Domain = Domain.PROJECT
        self._folded = False
        self._domain_states: dict[Domain, NavState] = {
            d: NavState.NOT_STARTED for d in Domain
        }

        self._build_ui()
        self._apply_theme()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_current_domain(self, domain: Domain) -> None:
        """Highlight *domain* as the active navigation item."""
        self._current_domain = domain
        for d, btn in self._domain_buttons.items():
            self._apply_button_state(btn, d)

    def set_domain_state(self, domain: Domain, state: NavState) -> None:
        """Update the status indicator for a domain."""
        self._domain_states[domain] = state
        if domain in self._domain_state_labels:
            self._domain_state_labels[domain].setText(_STATE_ICONS[state])
            t = get_theme()
            color_key = _STATE_COLORS[state]
            self._domain_state_labels[domain].setStyleSheet(
                f"color: {t.get(color_key, t['text_secondary'])}; "
                f"font-size: {FONT_SIZE_CAPTION}px; "
                f"font-family: {FONT_FAMILY}; "
                f"font-weight: bold;"
            )

    def set_folded(self, folded: bool) -> None:
        """Fold (56 px, icon-only) or unfold (176 px, full labels)."""
        if self._folded == folded:
            return
        self._folded = folded
        target_width = (
            PRIMARY_NAV_MIN_WIDTH if folded else PRIMARY_NAV_WIDTH
        )
        self.setFixedWidth(target_width)
        for btn in self._domain_buttons.values():
            btn.setText("" if folded else btn.property("_full_label"))
        self._fold_btn.setText(
            "▶" if folded else "◀"
        )

    def is_folded(self) -> bool:
        return self._folded

    # ------------------------------------------------------------------
    # Internal — UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        # Domain buttons
        self._domain_buttons: dict[Domain, QtWidgets.QPushButton] = {}
        self._domain_state_labels: dict[Domain, QtWidgets.QLabel] = {}

        for domain in Domain:
            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(12, 0, 12, 0)

            icon_label = QtWidgets.QLabel(_DOMAIN_ICONS[domain])
            icon_label.setFixedWidth(24)
            icon_label.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignCenter
            )
            icon_label.setStyleSheet(
                f"font-size: 16px; font-family: {FONT_FAMILY};"
            )

            label = tr(DOMAIN_LABELS_ZH[domain], DOMAIN_LABELS_EN[domain])
            btn = QtWidgets.QPushButton(label)
            btn.setProperty("_full_label", label)
            btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            btn.setFlat(True)
            btn.clicked.connect(
                lambda checked, d=domain: self._on_domain_clicked(d)
            )

            state_label = QtWidgets.QLabel(_STATE_ICONS[NavState.NOT_STARTED])
            state_label.setFixedWidth(20)
            state_label.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignCenter
            )

            row.addWidget(icon_label)
            row.addWidget(btn, stretch=1)
            row.addWidget(state_label)

            row_widget = QtWidgets.QWidget()
            row_widget.setLayout(row)
            layout.addWidget(row_widget)

            self._domain_buttons[domain] = btn
            self._domain_state_labels[domain] = state_label

        # Spacer
        layout.addStretch(1)

        # Fold toggle button
        self._fold_btn = QtWidgets.QPushButton("◀")  # ◀
        self._fold_btn.setFlat(True)
        self._fold_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._fold_btn.setToolTip(
            tr("折叠导航", "Collapse navigation")
        )
        self._fold_btn.clicked.connect(self._on_fold_clicked)
        layout.addWidget(self._fold_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        self.setFixedWidth(PRIMARY_NAV_WIDTH)
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Internal — theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        t = get_theme()
        self.setStyleSheet(f"""
            PrimaryNavigation {{
                background-color: {t["surface"]};
                border-right: 1px solid {t["border"]};
            }}
        """)
        self._fold_btn.setStyleSheet(f"""
            QPushButton {{
                color: {t["text_secondary"]};
                border: none;
                background: transparent;
                font-size: 12px;
                padding: 4px 8px;
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                color: {t["text"]};
            }}
        """)
        for domain, btn in self._domain_buttons.items():
            self._apply_button_state(btn, domain)

    def _apply_button_state(
        self, btn: QtWidgets.QPushButton, domain: Domain
    ) -> None:
        t = get_theme()
        is_current = domain == self._current_domain

        if is_current:
            bg = t.get("selection", t["primary"])
            fg = t.get("selection_text", "#ffffff")
        else:
            bg = "transparent"
            fg = t["text"]

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: none;
                border-radius: 6px;
                padding: 10px 12px;
                text-align: left;
                font-size: {FONT_SIZE_BODY}px;
                font-weight: {"600" if is_current else "400"};
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                background-color: {t["highlight"] + "22" if not is_current else bg};
                color: {fg if is_current else t["text"]};
            }}
        """)

    # ------------------------------------------------------------------
    # Internal — slots
    # ------------------------------------------------------------------

    def _on_domain_clicked(self, domain: Domain) -> None:
        self.set_current_domain(domain)
        self.domain_changed.emit(domain.value)

    def _on_fold_clicked(self) -> None:
        self.set_folded(not self._folded)
        self.fold_requested.emit(self._folded)

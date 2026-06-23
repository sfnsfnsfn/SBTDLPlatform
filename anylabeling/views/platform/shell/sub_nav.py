"""Sub-navigation — data-prep domain 4-step inline stepper.

Only visible within the DATA_PREP domain. Displays::

    导入数据 → 任务与标签 → 标注 → 数据集构建
    资产 17,888 | 已标注 12,310 | 待复核 420 | 当前任务：实例分割 v3
"""

from __future__ import annotations

from enum import IntEnum

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.shell.primary_navigation import NavState
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
)
from anylabeling.views.labeling.utils.theme import get_theme


# ---------------------------------------------------------------------------
# SubStep enum
# ---------------------------------------------------------------------------


class SubStep(IntEnum):
    """Four-step data preparation sub-navigation."""
    IMPORT = 0
    TASK = 1
    LABEL = 2
    DATASET_BUILD = 3


SUBSTEP_LABELS_ZH: dict[SubStep, str] = {
    SubStep.IMPORT: "导入数据",
    SubStep.TASK: "任务与标签",
    SubStep.LABEL: "标注",
    SubStep.DATASET_BUILD: "数据集构建",
}

SUBSTEP_LABELS_EN: dict[SubStep, str] = {
    SubStep.IMPORT: "Import Data",
    SubStep.TASK: "Task & Labels",
    SubStep.LABEL: "Label",
    SubStep.DATASET_BUILD: "Dataset Build",
}

# State icons (matching PrimaryNav NavState)
_STATE_ICONS: dict[NavState, str] = {
    NavState.NOT_STARTED: "○",
    NavState.READY: "●",
    NavState.IN_PROGRESS: "▶",
    NavState.COMPLETED: "✓",
    NavState.NEEDS_ATTENTION: "⚠",
    NavState.EXPIRED: "✗",
}

_STATE_COLORS: dict[NavState, str] = {
    NavState.NOT_STARTED: "text_secondary",
    NavState.READY: "primary",
    NavState.IN_PROGRESS: "primary",
    NavState.COMPLETED: "success",
    NavState.NEEDS_ATTENTION: "warning",
    NavState.EXPIRED: "error",
}

_SUBSTEP_COUNT = len(SubStep)


# ---------------------------------------------------------------------------
# SubNav widget
# ---------------------------------------------------------------------------


class SubNav(QtWidgets.QWidget):
    """Data-prep inline sub-navigation with 4 steps + summary bar.

    Emits ``step_changed(int)`` when a step is clicked.
    """

    step_changed = QtCore.pyqtSignal(int)  # SubStep value

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self._current_step: SubStep = SubStep.IMPORT
        self._step_states: dict[SubStep, NavState] = {
            s: NavState.NOT_STARTED for s in SubStep
        }
        self._summary: str = ""

        self._build_ui()
        self._apply_theme()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_current_step(self, step: SubStep) -> None:
        """Highlight *step* as the active sub-step."""
        self._current_step = step
        for s, btn in self._step_buttons.items():
            self._apply_button_state(btn, s)

    def set_step_state(self, step: SubStep, state: NavState) -> None:
        """Update the state indicator for a sub-step."""
        self._step_states[step] = state
        if step in self._step_state_labels:
            self._step_state_labels[step].setText(_STATE_ICONS[state])
            t = get_theme()
            color_key = _STATE_COLORS[state]
            self._step_state_labels[step].setStyleSheet(
                f"color: {t.get(color_key, t['text_secondary'])}; "
                f"font-size: {FONT_SIZE_CAPTION}px; "
                f"font-family: {FONT_FAMILY}; "
                f"font-weight: bold;"
            )

    def set_summary(self, text: str) -> None:
        """Set the statistics summary line."""
        self._summary = text
        self._summary_label.setText(text)
        self._summary_label.setVisible(bool(text))

    # ------------------------------------------------------------------
    # Internal — UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QtWidgets.QVBoxLayout()
        outer.setContentsMargins(20, 6, 16, 6)
        outer.setSpacing(4)

        # Step row
        step_row = QtWidgets.QHBoxLayout()
        step_row.setContentsMargins(0, 0, 0, 0)
        step_row.setSpacing(4)

        self._step_buttons: dict[SubStep, QtWidgets.QPushButton] = {}
        self._step_state_labels: dict[SubStep, QtWidgets.QLabel] = {}

        for i, step in enumerate(SubStep):
            if i > 0:
                arrow = QtWidgets.QLabel("→")
                t = get_theme()
                arrow.setStyleSheet(
                    f"color: {t['text_secondary']}; "
                    f"font-size: {FONT_SIZE_BODY}px; "
                    f"font-family: {FONT_FAMILY};"
                )
                step_row.addWidget(arrow)

            state_icon = QtWidgets.QLabel(
                _STATE_ICONS[NavState.NOT_STARTED]
            )
            state_icon.setFixedWidth(16)
            state_icon.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignCenter
            )
            step_row.addWidget(state_icon)

            btn = QtWidgets.QPushButton(
                tr(SUBSTEP_LABELS_ZH[step], SUBSTEP_LABELS_EN[step])
            )
            btn.setFlat(True)
            btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda checked, s=step: self._on_step_clicked(s)
            )
            step_row.addWidget(btn)

            self._step_buttons[step] = btn
            self._step_state_labels[step] = state_icon

        step_row.addStretch(1)
        outer.addLayout(step_row)

        # Summary row
        self._summary_label = QtWidgets.QLabel()
        self._summary_label.setVisible(False)
        outer.addWidget(self._summary_label)

        self.setLayout(outer)

    # ------------------------------------------------------------------
    # Internal — theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        t = get_theme()
        self.setStyleSheet(f"""
            SubNav {{
                background-color: {t["surface"]};
                border-bottom: 1px solid {t["border"]};
            }}
        """)
        self._summary_label.setStyleSheet(
            f"color: {t['text_secondary']}; "
            f"font-size: {FONT_SIZE_CAPTION}px; "
            f"font-family: {FONT_FAMILY};"
        )
        for step, btn in self._step_buttons.items():
            self._apply_button_state(btn, step)

    def _apply_button_state(
        self, btn: QtWidgets.QPushButton, step: SubStep
    ) -> None:
        t = get_theme()
        is_current = step == self._current_step

        fg = t["primary"] if is_current else t["text_secondary"]
        fw = "600" if is_current else "400"

        btn.setStyleSheet(f"""
            QPushButton {{
                color: {fg};
                border: none;
                background: transparent;
                font-size: {FONT_SIZE_BODY}px;
                font-weight: {fw};
                font-family: {FONT_FAMILY};
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {t["text"]};
                background-color: {t["highlight"]}22;
            }}
        """)

    # ------------------------------------------------------------------
    # Internal — slots
    # ------------------------------------------------------------------

    def _on_step_clicked(self, step: SubStep) -> None:
        self.set_current_step(step)
        self.step_changed.emit(step.value)

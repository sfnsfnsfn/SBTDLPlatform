"""Navigation bar — DEPRECATED.

Use ``anylabeling.views.platform.shell`` (PrimaryNavigation + Domain)
instead of the 8-step horizontal NavigationBar.

The PipelineStep enum and step_label() helper remain in active use
by WorkbenchWindow for its internal QStackedWidget page indexing.
"""

from enum import IntEnum

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtGui import QFont

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    get_primary_button_style,
    get_secondary_button_style,
)
from anylabeling.views.labeling.utils.theme import get_theme


# ---------------------------------------------------------------------------
# PipelineStep enum — 8-step pipeline
# ---------------------------------------------------------------------------

class PipelineStep(IntEnum):
    """Eight-step vision algorithm pipeline."""
    PROJECT = 0       # 项目管理 / Project Home
    IMPORT = 1        # 导入 / Import
    CONFIG = 2        # 配置 / Configure
    LABEL = 3         # 标注 / Label
    PREPROCESS = 4    # 预处理 / Preprocess
    TRAIN = 5         # 训练 / Train
    EVALUATE = 6      # 评估 / Evaluate
    EXPORT = 7        # 导出 / Export
    MODELS = 8        # 模型库 / Model Library


STEP_LABELS_EN: dict[PipelineStep, str] = {
    PipelineStep.PROJECT: "Project",
    PipelineStep.IMPORT: "Import",
    PipelineStep.CONFIG: "Configure",
    PipelineStep.LABEL: "Label",
    PipelineStep.PREPROCESS: "Preprocess",
    PipelineStep.TRAIN: "Train",
    PipelineStep.EVALUATE: "Evaluate",
    PipelineStep.EXPORT: "Export",
    PipelineStep.MODELS: "Models",
}

STEP_LABELS_ZH: dict[PipelineStep, str] = {
    PipelineStep.PROJECT: "项目",
    PipelineStep.IMPORT: "导入",
    PipelineStep.CONFIG: "配置",
    PipelineStep.LABEL: "标注",
    PipelineStep.PREPROCESS: "预处理",
    PipelineStep.TRAIN: "训练",
    PipelineStep.EVALUATE: "评估",
    PipelineStep.EXPORT: "导出",
    PipelineStep.MODELS: "模型库",
}

_STEP_COUNT = len(PipelineStep)


def step_label(step: int | PipelineStep) -> str:
    """Return the localized label for a navigation step."""
    if isinstance(step, PipelineStep):
        return tr(STEP_LABELS_ZH.get(step, "?"), STEP_LABELS_EN.get(step, "?"))
    # Handle raw int for backward compat
    try:
        ps = PipelineStep(step)
        return tr(STEP_LABELS_ZH.get(ps, "?"), STEP_LABELS_EN.get(ps, "?"))
    except ValueError:
        return "?"


# ---------------------------------------------------------------------------
# Backward-compatible deprecated aliases
# ---------------------------------------------------------------------------
# These int constants map to the semantically corresponding PipelineStep values.
# They are kept so existing imports do not break immediately.
# New code should use PipelineStep directly.

DATA = PipelineStep.PROJECT.value     # was 0, still 0 (now PROJECT)
LABEL = PipelineStep.LABEL.value      # was 1, now 3
TRAIN = PipelineStep.TRAIN.value      # was 2, now 5
EVALUATE = PipelineStep.EVALUATE.value  # was 3, now 6
INFER = PipelineStep.PREPROCESS.value  # was 4, now 4 (closest match: PREPROCESS)
EXPORT = PipelineStep.EXPORT.value    # was 5, now 7

# Backward-compatible STEP_LABELS alias (old code imports STEP_LABELS directly)
STEP_LABELS = {
    PipelineStep.PROJECT.value: tr(STEP_LABELS_ZH[PipelineStep.PROJECT], STEP_LABELS_EN[PipelineStep.PROJECT]),
    PipelineStep.IMPORT.value: tr(STEP_LABELS_ZH[PipelineStep.IMPORT], STEP_LABELS_EN[PipelineStep.IMPORT]),
    PipelineStep.CONFIG.value: tr(STEP_LABELS_ZH[PipelineStep.CONFIG], STEP_LABELS_EN[PipelineStep.CONFIG]),
    PipelineStep.LABEL.value: tr(STEP_LABELS_ZH[PipelineStep.LABEL], STEP_LABELS_EN[PipelineStep.LABEL]),
    PipelineStep.PREPROCESS.value: tr(STEP_LABELS_ZH[PipelineStep.PREPROCESS], STEP_LABELS_EN[PipelineStep.PREPROCESS]),
    PipelineStep.TRAIN.value: tr(STEP_LABELS_ZH[PipelineStep.TRAIN], STEP_LABELS_EN[PipelineStep.TRAIN]),
    PipelineStep.EVALUATE.value: tr(STEP_LABELS_ZH[PipelineStep.EVALUATE], STEP_LABELS_EN[PipelineStep.EVALUATE]),
    PipelineStep.EXPORT.value: tr(STEP_LABELS_ZH[PipelineStep.EXPORT], STEP_LABELS_EN[PipelineStep.EXPORT]),
    PipelineStep.MODELS.value: tr(STEP_LABELS_ZH[PipelineStep.MODELS], STEP_LABELS_EN[PipelineStep.MODELS]),
}


# ---------------------------------------------------------------------------
# NavigationBar widget
# ---------------------------------------------------------------------------

class NavigationBar(QtWidgets.QWidget):
    """DEPRECATED: 8-step flow navigation.

    Replaced by ``PrimaryNavigation`` (5-domain vertical nav) in
    ``anylabeling.views.platform.shell``. This class is kept for
    backward-compatible access only.

    Emits ``page_changed(int)`` when a step button is clicked.
    Uses the translation system for button labels.
    """

    page_changed = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        self._buttons: dict[int, QtWidgets.QPushButton] = {}
        self._active_btn_style = get_primary_button_style(min_height=32)
        self._inactive_btn_style = get_secondary_button_style(min_height=32)
        self._current_step: int = PipelineStep.PROJECT.value

        for step in PipelineStep:
            idx = step.value
            btn = QtWidgets.QPushButton(step_label(step))
            btn.setFont(QFont(FONT_FAMILY, FONT_SIZE_BODY))
            btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(32)
            btn.clicked.connect(lambda checked, i=idx: self._on_clicked(i))
            btn.setEnabled(True)
            layout.addWidget(btn)
            self._buttons[idx] = btn

            if idx < _STEP_COUNT - 1:
                arrow = QtWidgets.QLabel("→")
                arrow.setStyleSheet(
                    f"color: {get_theme()['text_secondary']}; font-size: 14px;"
                )
                layout.addWidget(arrow)

        self.set_project_open(False)
        self._buttons[PipelineStep.PROJECT.value].setEnabled(True)
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_current_step(self, step: int | PipelineStep) -> None:
        """Set the currently active step (0-7 or PipelineStep)."""
        idx = step.value if isinstance(step, PipelineStep) else step
        self._current_step = idx
        for _idx, btn in self._buttons.items():
            btn.setStyleSheet(
                self._active_btn_style if _idx == idx
                else self._inactive_btn_style
            )

    def current_step(self) -> int:
        """Return the currently active step index."""
        return self._current_step

    def set_project_open(self, open_: bool) -> None:
        """Enable/disable step buttons based on whether a project is open."""
        self._project_open = open_
        t = get_theme()
        disabled_style = f"""
            QPushButton:disabled {{
                background-color: {t["surface"]};
                color: {t["text_secondary"]};
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-family: {FONT_FAMILY};
            }}
        """
        for idx, btn in self._buttons.items():
            if idx == PipelineStep.PROJECT.value:
                btn.setEnabled(True)
            else:
                btn.setEnabled(open_)
                if not open_:
                    btn.setStyleSheet(disabled_style)

    def refresh_labels(self) -> None:
        """Refresh all button labels (call after locale change)."""
        for idx, btn in self._buttons.items():
            try:
                btn.setText(step_label(PipelineStep(idx)))
            except ValueError:
                btn.setText(step_label(idx))

    @property
    def page_count(self) -> int:
        """Number of pipeline steps."""
        return _STEP_COUNT

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_clicked(self, index: int) -> None:
        self.set_current_step(index)
        self.page_changed.emit(index)

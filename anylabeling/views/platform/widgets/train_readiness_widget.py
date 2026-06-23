"""TrainReadinessWidget— pre-training readiness checklist.

Shows a vertical checklist with pass/fail/warning icons and a
"Start Training" button that enables only when all blocking checks
pass.
"""

from __future__ import annotations

import logging

from PyQt6 import QtCore, QtWidgets

from anylabeling.platform.domain.training_readiness import (
    CheckResult,
    TrainReadinessReport,
)
from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    get_heading_label_style,
    get_primary_button_style,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)


class TrainReadinessWidget(QtWidgets.QWidget):
    """Vertical checklist showing pre-training readiness.

    Each check shows:
    - Green tick if passed
    - Red cross if failed (blocking)
    - Yellow warning if failed (non-blocking)

    The "Start Training" button is enabled only when all
    blocking checks pass.

    Signals:
        start_requested(): Emitted when user clicks start.
        fix_requested(check_name: str): Emitted when user clicks fix.
    """

    start_requested = QtCore.pyqtSignal()
    fix_requested = QtCore.pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QtWidgets.QLabel(
            tr("训练就绪检查", "Training Readiness Check")
        )
        header.setStyleSheet(get_heading_label_style())
        layout.addWidget(header)

        self._checks_layout = QtWidgets.QVBoxLayout()
        self._checks_layout.setSpacing(4)
        layout.addLayout(self._checks_layout)

        self._warnings_layout = QtWidgets.QVBoxLayout()
        self._warnings_layout.setSpacing(4)
        layout.addLayout(self._warnings_layout)

        layout.addStretch()

        self._start_btn = QtWidgets.QPushButton(
            tr("开始训练", "Start Training")
        )
        self._start_btn.setEnabled(False)
        self._start_btn.setMinimumHeight(36)
        self._start_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._start_btn.setStyleSheet(
            get_primary_button_style(min_height=36)
        )
        self._start_btn.clicked.connect(self.start_requested.emit)
        layout.addWidget(self._start_btn)

    # ------------------------------------------------------------------
    # i18n rendering helpers
    # ------------------------------------------------------------------

    def _render_check_text(
        self, check: CheckResult
    ) -> tuple[str, str]:
        """Render check name and detail with i18n via tr()."""
        _CHECK_NAME_DISPLAY: dict[str, str] = {
            "assets_exist": tr("图像资产", "Image Assets"),
            "annotations_coverage": tr(
                "标注覆盖率", "Annotation Coverage"
            ),
            "dataset_build": tr("数据集构建", "Dataset Build"),
            "model_compatible": tr(
                "模型兼容性", "Model Compatibility"
            ),
            "disk_space": tr("磁盘空间", "Disk Space"),
        }
        display_name = _CHECK_NAME_DISPLAY.get(
            check.name, check.name
        )
        if check.name == "dataset_build":
            display_detail = (
                tr("数据集构建已完成", "Dataset build complete")
                if check.passed
                else tr("缺少数据集构建", "Missing dataset build")
            )
        elif check.name == "model_compatible":
            display_detail = tr(
                "模型兼容性由训练适配器在启动时验证",
                "Model compatibility validated by training"
                " adapter at startup",
            )
        elif check.name == "disk_space":
            if not check.passed and not check.blocking:
                display_detail = tr(
                    "无法检测磁盘空间", "Cannot detect disk space"
                )
            else:
                display_detail = check.detail
        else:
            display_detail = check.detail
        return display_name, display_detail

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_report(self, report: TrainReadinessReport) -> None:
        """Display a TrainReadinessReport.

        Args:
            report: TrainReadinessReport with checks and warnings.
        """
        self._clear_contents()

        t = get_theme()
        success_color = t.get('success', '#2e7d32')
        error_color = t.get('error', '#c62828')
        warning_color = '#f57f17'

        blocking_ok = True

        for check in report.checks:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(6)

            if check.passed:
                icon = "✓"
                color = success_color
            elif check.blocking:
                icon = "✗"
                color = error_color
                blocking_ok = False
            else:
                icon = "⚠"
                color = warning_color

            icon_label = QtWidgets.QLabel(icon)
            icon_label.setStyleSheet(
                f'color: {color}; font-weight: bold; font-size: 16px;'
                f'font-family: {FONT_FAMILY};'
            )
            icon_label.setFixedWidth(24)
            row.addWidget(icon_label)

            display_name, display_detail = self._render_check_text(
                check
            )
            text = (
                display_name + chr(10) + display_detail
                if display_detail
                else display_name
            )
            detail_label = QtWidgets.QLabel(text)
            detail_label.setWordWrap(True)
            detail_label.setStyleSheet(
                f'font-size: {FONT_SIZE_BODY}px;'
                f"color: {t['text']};"
                f'font-family: {FONT_FAMILY};'
            )
            row.addWidget(detail_label, 1)

            if not check.passed and check.detail:
                fix_btn = QtWidgets.QPushButton(tr("修复", "Fix"))
                fix_btn.setFixedWidth(60)
                fix_btn.setStyleSheet(
                    f'font-size: {FONT_SIZE_CAPTION}px;'
                    f'font-family: {FONT_FAMILY};'
                    f'padding: 2px 8px;'
                )
                fix_btn.clicked.connect(
                    lambda checked, n=check.name: self.fix_requested.emit(n)
                )
                row.addWidget(fix_btn)

            self._checks_layout.addLayout(row)

        for warning in report.warnings:
            warn_label = QtWidgets.QLabel(f"⚠ {warning}")
            warn_label.setStyleSheet(
                f'color: {warning_color};'
                f'font-size: {FONT_SIZE_BODY}px;'
                f'font-family: {FONT_FAMILY};'
            )
            warn_label.setWordWrap(True)
            self._warnings_layout.addWidget(warn_label)

        self._start_btn.setEnabled(blocking_ok and report.ready)

    def clear(self) -> None:
        """Clear all checks and reset button state."""
        self._clear_contents()
        self._start_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _clear_contents(self) -> None:
        """Remove all check rows and warnings."""
        for layout in (self._checks_layout, self._warnings_layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    nested = item.layout()
                    while nested.count():
                        sub = nested.takeAt(0)
                        if sub.widget():
                            sub.widget().deleteLater()


__all__ = ["TrainReadinessWidget"]

"""New Project dialog — lightweight: name + description + location + optional template."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtGui import QFont

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_HEADING,
    FONT_SIZE_BODY,
    get_primary_button_style,
    get_secondary_button_style,
    get_combo_style,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Quick-start template presets (optional)
# ---------------------------------------------------------------------------

_TEMPLATE_PRESETS: dict[str, dict] = {
    "classification": {
        "display_zh": "分类",
        "display_en": "Classification",
        "family": "classification",
    },
    "detection": {
        "display_zh": "目标检测",
        "display_en": "Object Detection",
        "family": "detection_hbb",
    },
    "obb": {
        "display_zh": "旋转目标检测 (OBB)",
        "display_en": "Oriented BBox (OBB)",
        "family": "detection_obb",
    },
    "instance_seg": {
        "display_zh": "实例分割",
        "display_en": "Instance Segmentation",
        "family": "instance_segmentation",
    },
    "anomaly": {
        "display_zh": "异常检测",
        "display_en": "Anomaly Detection",
        "family": "anomaly",
    },
    "ocr": {
        "display_zh": "OCR",
        "display_en": "OCR",
        "family": "ocr",
    },
    "later": {
        "display_zh": "稍后配置",
        "display_en": "Configure Later",
        "family": None,
    },
}

_TEMPLATE_KEYS = list(_TEMPLATE_PRESETS.keys())


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


class NewProjectDialog(QtWidgets.QDialog):
    """Modal dialog that collects project name, description, parent directory,
    and an optional quick-start template before project creation.

    Usage::

        dialog = NewProjectDialog(parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, parent_dir, description, template_key = dialog.get_result()
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("新建项目", "New Project"))
        self.setMinimumSize(480, 340)
        self.setModal(True)

        # Internal state
        self._parent_dir: str = os.path.expanduser("~")
        self._current_template_key: str = _TEMPLATE_KEYS[0]

        # Build UI
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get_result(self) -> tuple[str, str, str, str | None] | None:
        """Return ``(name, parent_dir, description, template_key_or_none)``
        if accepted, else None.

        ``template_key_or_none`` is None when "Configure Later" is selected.
        """
        if self.result() != QtWidgets.QDialog.DialogCode.Accepted:
            return None

        name = self._name_edit.text().strip()
        parent_dir = self._parent_dir
        description = self._desc_edit.toPlainText().strip()
        template_key = self._current_template_key

        if template_key == "later":
            template_key = None

        return name, parent_dir, description, template_key

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # -- Project name --
        layout.addWidget(self._make_section_label(tr("项目名称", "Project Name")))
        self._name_edit = QtWidgets.QLineEdit()
        self._name_edit.setPlaceholderText(
            tr("输入项目名称", "Enter project name")
        )
        self._name_edit.setMinimumHeight(32)
        layout.addWidget(self._name_edit)

        # -- Description --
        layout.addWidget(self._make_section_label(tr("项目描述", "Description")))
        self._desc_edit = QtWidgets.QTextEdit()
        self._desc_edit.setPlaceholderText(
            tr("可选：描述项目的用途和内容", "Optional: describe the project purpose and content")
        )
        self._desc_edit.setMaximumHeight(60)
        self._desc_edit.setMinimumHeight(48)
        layout.addWidget(self._desc_edit)

        # -- Parent directory --
        layout.addWidget(self._make_section_label(tr("项目位置", "Project Location")))
        dir_row = QtWidgets.QHBoxLayout()
        dir_row.setSpacing(8)
        self._dir_edit = QtWidgets.QLineEdit(self._parent_dir)
        self._dir_edit.setReadOnly(True)
        self._dir_edit.setMinimumHeight(32)
        dir_row.addWidget(self._dir_edit)

        browse_btn = QtWidgets.QPushButton(tr("浏览...", "Browse..."))
        browse_btn.setMinimumHeight(32)
        browse_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._on_browse)
        browse_btn.setStyleSheet(get_secondary_button_style(min_height=32))
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # -- Quick-start template (optional) --
        layout.addWidget(self._make_section_label(
            tr("快速模板（可选）", "Quick Template (Optional)")
        ))
        template_group = QtWidgets.QButtonGroup(self)
        template_row = QtWidgets.QHBoxLayout()
        template_row.setSpacing(8)

        for i, key in enumerate(_TEMPLATE_KEYS):
            preset = _TEMPLATE_PRESETS[key]
            radio = QtWidgets.QRadioButton(
                tr(preset["display_zh"], preset["display_en"])
            )
            radio.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            if i == 0:
                radio.setChecked(True)
            template_group.addButton(radio, i)
            template_row.addWidget(radio)

        template_group.idClicked.connect(self._on_template_changed)
        layout.addLayout(template_row)

        # -- Buttons --
        layout.addSpacing(4)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QtWidgets.QPushButton(tr("取消", "Cancel"))
        cancel_btn.setMinimumHeight(36)
        cancel_btn.setMinimumWidth(90)
        cancel_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(get_secondary_button_style(min_width=90, min_height=36))
        btn_row.addWidget(cancel_btn)

        self._create_btn = QtWidgets.QPushButton(tr("创建项目", "Create Project"))
        self._create_btn.setMinimumHeight(36)
        self._create_btn.setMinimumWidth(110)
        self._create_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._create_btn.clicked.connect(self._on_create)
        self._create_btn.setStyleSheet(get_primary_button_style(min_width=110, min_height=36))
        btn_row.addWidget(self._create_btn)

        layout.addLayout(btn_row)
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_browse(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            tr("选择父目录", "Select Parent Directory"),
            self._parent_dir,
        )
        if path:
            self._parent_dir = path
            self._dir_edit.setText(path)

    def _on_template_changed(self, idx: int):
        key = _TEMPLATE_KEYS[idx]
        self._current_template_key = key

    def _on_create(self):
        if not self._name_edit.text().strip():
            QtWidgets.QMessageBox.warning(
                self,
                tr("验证失败", "Validation"),
                tr("请输入项目名称。", "Please enter a project name."),
            )
            return

        if not self._parent_dir or not os.path.isdir(self._parent_dir):
            QtWidgets.QMessageBox.warning(
                self,
                tr("验证失败", "Validation"),
                tr("请选择有效的项目目录。", "Please select a valid project directory."),
            )
            return

        self.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_section_label(self, text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setFont(QFont(FONT_FAMILY, FONT_SIZE_HEADING, QFont.Weight.DemiBold))
        label.setStyleSheet(f"color: {get_theme()['text']};")
        return label

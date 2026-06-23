"""Project home page — create/open project, recent projects list."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtGui import QFont

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_HERO,
    FONT_SIZE_HEADING,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    get_primary_button_style,
    get_secondary_button_style,
    get_info_banner_style,
    get_list_widget_style,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)

_RECENT_PROJECTS_KEY = "platform/recent_projects"
_MAX_RECENT = 10


class ProjectHomeWidget(QtWidgets.QWidget):
    """First page of the platform pipeline — project creation and overview."""

    project_opened = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._project_path: str | None = None
        self._project_meta: dict | None = None

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QtWidgets.QLabel(tr(
            "欢迎使用视觉算法平台", "Welcome to Vision Algorithm Platform"
        ))
        title.setFont(QFont(FONT_FAMILY, FONT_SIZE_HERO, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color: {get_theme()['text']}; font-family: {FONT_FAMILY};"
        )
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel(tr(
            "创建新项目或打开已有项目以开始使用",
            "Create a new project or open an existing one to get started."
        ))
        subtitle.setStyleSheet(
            f"color: {get_theme()['text_secondary']};"
            f"font-size: {FONT_SIZE_BODY}px;"
            f"font-family: {FONT_FAMILY};"
        )
        layout.addWidget(subtitle)

        layout.addSpacing(12)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(12)

        self._btn_new = QtWidgets.QPushButton(tr("  新建项目", "  New Project"))
        self._btn_new.setMinimumHeight(40)
        self._btn_new.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._btn_new.clicked.connect(self._on_new_project)
        self._btn_new.setStyleSheet(get_primary_button_style(min_height=40))
        btn_row.addWidget(self._btn_new)

        self._btn_open = QtWidgets.QPushButton(tr("  打开项目", "  Open Project"))
        self._btn_open.setMinimumHeight(40)
        self._btn_open.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._btn_open.clicked.connect(self._on_open_project)
        self._btn_open.setStyleSheet(get_secondary_button_style(min_height=40))
        btn_row.addWidget(self._btn_open)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addSpacing(8)

        self._summary_widget = QtWidgets.QWidget()
        self._summary_widget.setVisible(False)
        summary_layout = QtWidgets.QVBoxLayout()
        summary_layout.setContentsMargins(0, 0, 0, 0)

        self._summary_label = QtWidgets.QLabel()
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet(get_info_banner_style("success"))
        summary_layout.addWidget(self._summary_label)
        self._summary_widget.setLayout(summary_layout)
        layout.addWidget(self._summary_widget)

        layout.addSpacing(8)
        recent_title = QtWidgets.QLabel(tr("最近项目", "Recent Projects"))
        recent_title.setFont(QFont(FONT_FAMILY, FONT_SIZE_HEADING, QFont.Weight.DemiBold))
        recent_title.setStyleSheet(
            f"color: {get_theme()['text']}; font-family: {FONT_FAMILY};"
        )
        layout.addWidget(recent_title)

        self._recent_list = QtWidgets.QListWidget()
        self._recent_list.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._recent_list.itemDoubleClicked.connect(self._on_recent_double_clicked)
        self._recent_list.setStyleSheet(get_list_widget_style())
        layout.addWidget(self._recent_list)

        layout.addStretch()
        self.setLayout(layout)

        self._load_recent_projects()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project(self, project_path: str) -> None:
        self._project_path = project_path
        try:
            from anylabeling.platform.infrastructure.project_file_store import (
                ProjectFileStore,
            )
            self._project_meta = ProjectFileStore.open_project(project_path)
        except Exception as exc:
            logger.warning("Failed to read project metadata: %s", exc)
            self._project_meta = {"name": Path(project_path).name}

        self._update_summary()
        self._add_recent_project(project_path)

    def project_path(self) -> str | None:
        return self._project_path

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_new_project(self):
        from anylabeling.views.platform.new_project_dialog import (
            NewProjectDialog,
        )
        from anylabeling.platform.infrastructure.project_file_store import (
            ProjectFileStore,
        )

        dialog = NewProjectDialog(self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        result = dialog.get_result()
        if result is None:
            return

        name, parent_dir, description, template_key = result

        # Build TaskSpec from template if one was selected
        task_spec = None
        if template_key is not None:
            # Import template presets inline to build a TaskSpec
            from anylabeling.platform.domain.task import TaskSpec, LabelClass
            from anylabeling.views.platform.new_project_dialog import (
                _TEMPLATE_PRESETS,
            )
            preset = _TEMPLATE_PRESETS[template_key]
            task_spec = TaskSpec(
                id=f"{template_key}_v1",
                family=preset["family"],
                labels=(LabelClass(id=0, name="object"),),
            )

        try:
            project_root = ProjectFileStore.create_project(
                parent_dir, name, task_spec, description,
            )
            self._activate_project(str(project_root))
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self,
                tr("错误", "Error"),
                tr(f"创建项目失败：{exc}", f"Failed to create project: {exc}"),
            )

    def _on_open_project(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            tr("打开平台项目", "Open Platform Project"),
            os.path.expanduser("~"),
        )
        if not path:
            return

        try:
            from anylabeling.platform.infrastructure.project_file_store import (
                ProjectFileStore,
            )
            issues = ProjectFileStore.validate_project(path)
            if issues:
                QtWidgets.QMessageBox.warning(
                    self,
                    tr("项目验证", "Project Validation"),
                    tr("项目存在以下问题：\n", "Project has the following issues:\n")
                    + "\n".join(issues),
                )
                return
            self._activate_project(path)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self,
                tr("错误", "Error"),
                tr(f"打开项目失败：{exc}", f"Failed to open project: {exc}"),
            )

    def _on_recent_double_clicked(self, item: QtWidgets.QListWidgetItem):
        path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if path and os.path.isdir(path):
            self._activate_project(path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _activate_project(self, path: str):
        self.set_project(path)
        self.project_opened.emit(path)

    def _update_summary(self):
        if not self._project_meta:
            self._summary_widget.setVisible(False)
            return

        meta = self._project_meta
        name = meta.get("name", Path(self._project_path or "").name)
        version = meta.get("version", "?")
        created = meta.get("created_at", "?")
        task_spec = meta.get("task_spec", {})
        family = task_spec.get("family", "?")

        asset_count = 0
        assets_dir = Path(self._project_path or "") / "assets"
        if assets_dir.is_dir():
            asset_count = sum(
                1 for _ in assets_dir.rglob("*")
                if _.is_file() and _.suffix.lower() in {
                    ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"
                }
            )

        text = (
            f"<b>{tr('项目：', 'Project:')}</b> {name}<br>"
            f"<b>{tr('版本：', 'Version:')}</b> {version}<br>"
            f"<b>{tr('任务类型：', 'Task Family:')}</b> {family}<br>"
            f"<b>{tr('资源数量：', 'Assets:')}</b> {asset_count}<br>"
            f"<b>{tr('创建时间：', 'Created:')}</b> {created}"
        )
        self._summary_label.setText(text)
        self._summary_widget.setVisible(True)

    def _add_recent_project(self, path: str):
        settings = QtCore.QSettings("anylabeling", "anylabeling_platform")
        recent = settings.value(_RECENT_PROJECTS_KEY, "[]")
        if isinstance(recent, str):
            try:
                recent = json.loads(recent)
            except json.JSONDecodeError:
                recent = []

        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:_MAX_RECENT]

        settings.setValue(_RECENT_PROJECTS_KEY, json.dumps(recent))
        self._load_recent_projects()

    def _load_recent_projects(self):
        self._recent_list.clear()
        settings = QtCore.QSettings("anylabeling", "anylabeling_platform")
        recent = settings.value(_RECENT_PROJECTS_KEY, "[]")
        if isinstance(recent, str):
            try:
                recent = json.loads(recent)
            except json.JSONDecodeError:
                recent = []

        for path in recent:
            if os.path.isdir(path):
                item = QtWidgets.QListWidgetItem(Path(path).name)
                item.setToolTip(path)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, path)
                self._recent_list.addItem(item)

        if self._recent_list.count() == 0:
            t = get_theme()
            placeholder = QtWidgets.QListWidgetItem(
                tr("暂无最近项目 — 点击「新建项目」开始", "No recent projects — click New Project to start")
            )
            placeholder.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            placeholder.setForeground(QtCore.Qt.GlobalColor.gray)
            placeholder.setToolTip(tr("创建您的第一个项目", "Create your first project"))
            self._recent_list.addItem(placeholder)

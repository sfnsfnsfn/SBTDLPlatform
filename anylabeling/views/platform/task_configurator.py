"""Task Configurator — STEP 3 of the pipeline: configure task type and labels.

A QWidget embedded into WorkbenchWindow's QStackedWidget.
Mirrors ``DataWorkspace`` embedding pattern with ``set_project_context()``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_HEADING,
    get_combo_style,
    get_heading_label_style,
    get_info_banner_style,
    get_input_style,
    get_list_widget_style,
    get_primary_button_style,
    get_secondary_button_style,
    get_outline_toolbar_button_style,
    get_scroll_area_style,
    get_group_box_style,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Task type definitions
# ---------------------------------------------------------------------------

_TASK_TYPES: list[tuple[str, str, str]] = [
    ("detection_hbb", tr("目标检测 (HBB)", "Detection (HBB)"),
     tr("检测水平边界框", "Detect horizontal bounding boxes")),
    ("detection_obb", tr("旋转框检测 (OBB)", "Rotation Detection (OBB)"),
     tr("检测旋转边界框", "Detect oriented bounding boxes")),
    ("instance_segmentation", tr("实例分割", "Instance Segmentation"),
     tr("像素级实例分割", "Pixel-level instance segmentation")),
    ("semantic_segmentation", tr("语义分割", "Semantic Segmentation"),
     tr("像素级语义分割", "Pixel-level semantic segmentation")),
    ("pose", tr("关键点检测", "Keypoint Detection"),
     tr("检测人体关键点", "Detect keypoints")),
    ("classification", tr("图像分类", "Image Classification"),
     tr("整图分类", "Whole-image classification")),
    ("anomaly", tr("异常检测", "Anomaly Detection"),
     tr("检测异常区域", "Detect anomalous regions")),
    ("ocr", tr("OCR 字符识别", "OCR"),
     tr("光学字符识别", "Optical character recognition")),
]

_FAMILY_INDEX: dict[str, int] = {t[0]: i for i, t in enumerate(_TASK_TYPES)}


def _smart_recommend_task(asset_count: int, group_count: int) -> str | None:
    """Return a suggested task family based on data characteristics.

    Simple heuristic: more than 10 groups suggests classification,
    fewer groups with many assets suggests detection.
    """
    if asset_count == 0:
        return None
    if group_count >= 10:
        return "classification"
    return "detection_hbb"


try:
    from PyQt6 import QtCore, QtWidgets
    from PyQt6.QtCore import pyqtSignal
    from PyQt6.QtGui import QFont

    from anylabeling.platform.domain.task import TaskSpec, LabelClass
    from anylabeling.platform.domain.import_config import ImportConfig

    class TaskConfigurator(QtWidgets.QWidget):
        """STEP 3: Task type selection, label CRUD, and annotation validation.

        Embedded in :class:`WorkbenchWindow` QStackedWidget. Receives the
        active project path via :meth:`set_project_context`.

        Signals:
            task_configured(TaskSpec): Emitted with the newly configured task.
        """

        task_configured = pyqtSignal(TaskSpec)
        back_requested = pyqtSignal()
        next_requested = pyqtSignal()

        def __init__(self, parent=None):
            super().__init__(parent)
            self._project_path: Path | None = None
            self._labels: list[LabelClass] = []
            self._next_label_id = 0
            self._dirty = False

            self._setup_ui()

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def set_project_context(self, project_path: str | Path) -> None:
            """Set the active project path and scan for assets."""
            self._project_path = Path(project_path)
            self._scan_and_update()

        # ------------------------------------------------------------------
        # UI setup
        # ------------------------------------------------------------------

        def _setup_ui(self):
            main = QtWidgets.QVBoxLayout()
            main.setContentsMargins(16, 16, 16, 16)
            main.setSpacing(10)

            # -- Section: imported image preview --
            preview_header = QtWidgets.QLabel(
                tr("已导入图片", "Imported Images")
            )
            preview_header.setStyleSheet(get_heading_label_style())
            main.addWidget(preview_header)

            self._preview_area = QtWidgets.QScrollArea()
            self._preview_area.setStyleSheet(get_scroll_area_style())
            self._preview_area.setMinimumHeight(110)
            self._preview_area.setMaximumHeight(140)
            self._preview_area.setWidgetResizable(True)
            self._preview_area.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn
            )
            self._preview_area.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )

            self._preview_container = QtWidgets.QWidget()
            self._preview_layout = QtWidgets.QHBoxLayout()
            self._preview_layout.setContentsMargins(4, 4, 4, 4)
            self._preview_layout.setSpacing(6)
            self._preview_layout.addStretch()
            self._preview_container.setLayout(self._preview_layout)
            self._preview_area.setWidget(self._preview_container)

            self._empty_preview_label = QtWidgets.QLabel(
                tr("暂无导入图片。请先通过 STEP 2 导入图片。",
                   "No images imported. Go to STEP 2 first.")
            )
            self._empty_preview_label.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignCenter
            )
            self._empty_preview_label.setStyleSheet(
                f"color: {get_theme().get('text_placeholder', '#aaa')};"
                f"font-size: {FONT_SIZE_BODY}px;"
                f"font-family: {FONT_FAMILY};"
            )
            self._preview_layout.addWidget(self._empty_preview_label)
            main.addWidget(self._preview_area)

            # -- Smart recommendation banner --
            self._recommend_banner = QtWidgets.QLabel()
            self._recommend_banner.setVisible(False)
            self._recommend_banner.setStyleSheet(get_info_banner_style("info"))
            self._recommend_banner.setWordWrap(True)
            main.addWidget(self._recommend_banner)

            # -- Task type selector --
            task_header = QtWidgets.QLabel(
                tr("任务类型", "Task Type")
            )
            task_header.setStyleSheet(get_heading_label_style())
            main.addWidget(task_header)

            task_row = QtWidgets.QHBoxLayout()
            task_row.setSpacing(8)

            self._task_combo = QtWidgets.QComboBox()
            for family, display, desc in _TASK_TYPES:
                self._task_combo.addItem(display, family)
                self._task_combo.setItemData(
                    self._task_combo.count() - 1, desc, QtCore.Qt.ItemDataRole.ToolTipRole
                )
            self._task_combo.setStyleSheet(get_combo_style())
            self._task_combo.setMinimumHeight(32)
            self._task_combo.currentIndexChanged.connect(self._on_task_changed)
            task_row.addWidget(self._task_combo, 1)

            self._task_desc_label = QtWidgets.QLabel()
            self._task_desc_label.setStyleSheet(
                f"color: {get_theme().get('text_secondary', '#888')};"
                f"font-size: {FONT_SIZE_CAPTION}px;"
                f"font-family: {FONT_FAMILY};"
            )
            task_row.addWidget(self._task_desc_label, 2)
            main.addLayout(task_row)

            # -- Label CRUD table --
            label_section = QtWidgets.QHBoxLayout()
            label_header = QtWidgets.QLabel(
                tr("标签管理", "Label Management")
            )
            label_header.setStyleSheet(get_heading_label_style())
            label_section.addWidget(label_header)
            label_section.addStretch()

            self._add_label_btn = QtWidgets.QPushButton(
                tr("+ 添加标签", "+ Add Label")
            )
            self._add_label_btn.setCursor(
                QtCore.Qt.CursorShape.PointingHandCursor
            )
            self._add_label_btn.clicked.connect(self._on_add_label)
            self._add_label_btn.setStyleSheet(
                get_outline_toolbar_button_style()
            )
            label_section.addWidget(self._add_label_btn)

            self._delete_label_btn = QtWidgets.QPushButton(
                tr("- 删除选中", "- Delete Selected")
            )
            self._delete_label_btn.setCursor(
                QtCore.Qt.CursorShape.PointingHandCursor
            )
            self._delete_label_btn.clicked.connect(self._on_delete_label)
            self._delete_label_btn.setStyleSheet(
                get_outline_toolbar_button_style()
            )
            label_section.addWidget(self._delete_label_btn)

            import_menu = QtWidgets.QMenu(self)
            import_menu.addAction(
                tr("从文件夹导入", "Import from Folders"),
                self._on_import_labels_from_folders,
            )
            import_menu.addAction(
                tr("从 JSON 导入", "Import from JSON"),
                self._on_import_labels_from_json,
            )
            self._import_label_btn = QtWidgets.QPushButton(
                tr("从...导入 ▼", "Import from... ▼")
            )
            self._import_label_btn.setCursor(
                QtCore.Qt.CursorShape.PointingHandCursor
            )
            self._import_label_btn.setMenu(import_menu)
            self._import_label_btn.setStyleSheet(
                get_outline_toolbar_button_style()
            )
            label_section.addWidget(self._import_label_btn)
            main.addLayout(label_section)

            # Label table: ID | Name | Shortcut
            self._label_table = QtWidgets.QTableWidget(0, 2)
            self._label_table.setHorizontalHeaderLabels([
                tr("ID", "ID"),
                tr("名称", "Name"),
            ])
            self._label_table.horizontalHeader().setStretchLastSection(True)
            self._label_table.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
            )
            self._label_table.setSelectionMode(
                QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
            )
            self._label_table.setStyleSheet(get_list_widget_style())
            self._label_table.setMinimumHeight(150)
            main.addWidget(self._label_table)

            # -- Validation rules (collapsible) --
            self._validation_group = QtWidgets.QGroupBox(
                tr("标注验证规则", "Annotation Validation Rules")
            )
            self._validation_group.setCheckable(True)
            self._validation_group.setChecked(False)
            self._validation_group.setStyleSheet(get_group_box_style())
            val_layout = QtWidgets.QFormLayout()

            self._min_area_sb = QtWidgets.QSpinBox()
            self._min_area_sb.setRange(0, 1000000)
            self._min_area_sb.setValue(0)
            self._min_area_sb.setSuffix(" px")
            self._min_area_sb.setStyleSheet(get_input_style())
            val_layout.addRow(
                tr("最小标注面积：", "Min Annotation Area:"),
                self._min_area_sb,
            )

            self._min_count_sb = QtWidgets.QSpinBox()
            self._min_count_sb.setRange(0, 100000)
            self._min_count_sb.setValue(0)
            self._min_count_sb.setStyleSheet(get_input_style())
            val_layout.addRow(
                tr("最少标注数：", "Min Annotation Count:"),
                self._min_count_sb,
            )

            self._validation_group.setLayout(val_layout)
            main.addWidget(self._validation_group)

            # -- Bottom navigation --
            main.addStretch()
            nav_row = QtWidgets.QHBoxLayout()
            nav_row.setSpacing(8)

            back_btn = QtWidgets.QPushButton(tr("← 返回", "← Back"))
            back_btn.setMinimumHeight(36)
            back_btn.setMinimumWidth(100)
            back_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            back_btn.clicked.connect(self.back_requested.emit)
            back_btn.setStyleSheet(
                get_secondary_button_style(min_width=100, min_height=36)
            )
            nav_row.addWidget(back_btn)

            nav_row.addStretch()

            self._next_btn = QtWidgets.QPushButton(tr("下一步 →", "Next →"))
            self._next_btn.setMinimumHeight(36)
            self._next_btn.setMinimumWidth(120)
            self._next_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            self._next_btn.clicked.connect(self._on_next)
            self._next_btn.setStyleSheet(
                get_primary_button_style(min_width=120, min_height=36)
            )
            nav_row.addWidget(self._next_btn)

            main.addLayout(nav_row)
            self.setLayout(main)

            # Initial task description
            self._update_task_description()

        # ------------------------------------------------------------------
        # Slots
        # ------------------------------------------------------------------

        def _on_task_changed(self, index: int):
            """Handle task type combo box change."""
            family = self._task_combo.currentData()
            if family and self._labels:
                reply = QtWidgets.QMessageBox.question(
                    self,
                    tr("确认切换", "Confirm Change"),
                    tr(
                        "切换任务类型将清空当前标签列表，是否继续？",
                        "Changing task type will clear current labels. Continue?",
                    ),
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.No,
                )
                if reply == QtWidgets.QMessageBox.StandardButton.No:
                    # Revert to previous selection
                    self._task_combo.blockSignals(True)
                    prev_idx = _FAMILY_INDEX.get(
                        self._task_combo.itemData(index), 0
                    )
                    self._task_combo.setCurrentIndex(prev_idx)
                    self._task_combo.blockSignals(False)
                    return
                self._clear_labels()

            self._dirty = True
            self._update_task_description()

        def _on_add_label(self):
            """Add a new label row with auto-incremented ID."""
            name, ok = QtWidgets.QInputDialog.getText(
                self,
                tr("添加标签", "Add Label"),
                tr("标签名称：", "Label Name:"),
            )
            if ok and name.strip():
                label = LabelClass(
                    id=self._next_label_id,
                    name=name.strip(),
                )
                self._labels.append(label)
                self._next_label_id += 1
                self._dirty = True
                self._refresh_label_table()

        def _on_delete_label(self):
            """Delete the selected label row."""
            row = self._label_table.currentRow()
            if row < 0 or row >= len(self._labels):
                return
            label_name = self._labels[row].name
            reply = QtWidgets.QMessageBox.question(
                self,
                tr("确认删除", "Confirm Delete"),
                tr(
                    f"确定要删除标签 '{label_name}' 吗？",
                    f"Delete label '{label_name}'?",
                ),
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                del self._labels[row]
                self._dirty = True
                self._refresh_label_table()

        def _on_import_labels_from_folders(self):
            """Scan assets/ subfolder names as label names."""
            if self._project_path is None:
                return

            assets_dir = self._project_path / "assets"
            if not assets_dir.is_dir():
                QtWidgets.QMessageBox.information(
                    self,
                    tr("无数据", "No Data"),
                    tr("请先导入图片。", "Please import images first."),
                )
                return

            # Scan subdirectories
            subdirs = [
                d.name
                for d in assets_dir.iterdir()
                if d.is_dir()
            ]

            if not subdirs:
                # Try to get labels from group_ids
                subdirs = self._scan_group_ids_from_assets(assets_dir)

            if not subdirs:
                QtWidgets.QMessageBox.information(
                    self,
                    tr("未找到", "Not Found"),
                    tr(
                        "未找到子文件夹。请先导入图片。",
                        "No sub-folders found. Please import images first.",
                    ),
                )
                return

            # Clear existing and import
            reply = QtWidgets.QMessageBox.question(
                self,
                tr("确认导入", "Confirm Import"),
                tr(
                    f"从子文件夹导入 {len(subdirs)} 个标签，将替换现有标签。继续？",
                    f"Import {len(subdirs)} labels from sub-folders. "
                    f"Existing labels will be replaced. Continue?",
                ),
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self._clear_labels()
                for name in sorted(subdirs):
                    self._labels.append(
                        LabelClass(id=self._next_label_id, name=name)
                    )
                    self._next_label_id += 1
                self._refresh_label_table()

        def _on_import_labels_from_json(self):
            """Import labels from a JSON file."""
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                tr("选择标签 JSON 文件", "Select Label JSON File"),
                "",
                "JSON Files (*.json);;" + tr("所有文件 (*.*)", "All Files (*.*)"),
            )
            if not path:
                return

            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                labels_data = data if isinstance(data, list) else data.get("labels", [])

                if not labels_data:
                    QtWidgets.QMessageBox.information(
                        self,
                        tr("无数据", "No Data"),
                        tr(
                            "JSON 文件中未找到标签定义。",
                            "No label definitions found in JSON file.",
                        ),
                    )
                    return

                # Validate and import
                new_labels: list[LabelClass] = []
                for item in labels_data:
                    if isinstance(item, dict):
                        lid = item.get("id", self._next_label_id + len(new_labels))
                        name = item.get("name", f"label_{lid}")
                        new_labels.append(LabelClass(id=lid, name=name))
                    elif isinstance(item, str):
                        new_labels.append(
                            LabelClass(
                                id=self._next_label_id + len(new_labels),
                                name=item,
                            )
                        )

                if new_labels:
                    reply = QtWidgets.QMessageBox.question(
                        self,
                        tr("确认导入", "Confirm Import"),
                        tr(
                            f"从 JSON 导入 {len(new_labels)} 个标签。继续？",
                            f"Import {len(new_labels)} labels from JSON. Continue?",
                        ),
                        QtWidgets.QMessageBox.StandardButton.Yes
                        | QtWidgets.QMessageBox.StandardButton.No,
                        QtWidgets.QMessageBox.StandardButton.No,
                    )
                    if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                        self._clear_labels()
                        self._labels = new_labels
                        self._next_label_id = max(
                            (l.id for l in self._labels), default=0
                        ) + 1
                        self._refresh_label_table()

            except (json.JSONDecodeError, OSError) as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    tr("导入失败", "Import Failed"),
                    str(e),
                )

        def _on_next(self):
            """Validate and emit task_configured signal."""
            family = self._task_combo.currentData()
            if family is None:
                return

            task_spec = TaskSpec(
                id=f"task_{self._project_path.name if self._project_path else 'unknown'}",
                family=family,
                labels=tuple(self._labels),
            )
            self.task_configured.emit(task_spec)
            self._dirty = False
            self.next_requested.emit()

        # ------------------------------------------------------------------
        # Properties
        # ------------------------------------------------------------------

        @property
        def is_modified(self) -> bool:
            """True if the configurator has unsaved changes."""
            return self._dirty

        # ------------------------------------------------------------------
        # Helpers
        # ------------------------------------------------------------------

        def _scan_and_update(self):
            """Scan assets directory and update previews/recommendations."""
            if self._project_path is None:
                return

            assets_dir = self._project_path / "assets"
            if not assets_dir.is_dir():
                self._show_empty_preview()
                return

            image_files = [
                f for f in assets_dir.iterdir()
                if f.is_file()
                and f.suffix.lower() in ImportConfig().supported_extensions
            ]

            if not image_files:
                self._show_empty_preview()
                return

            # Populate preview with first 20 thumbnails
            self._clear_preview()
            for img_path in image_files[:20]:
                w, h = self._read_image_dims(img_path)
                thumbnail_label = self._make_thumbnail_label(img_path, w, h)
                self._preview_layout.addWidget(thumbnail_label)

            # Show recommendation
            group_ids = self._scan_group_ids_from_assets(assets_dir)
            suggestion = _smart_recommend_task(
                len(image_files), len(group_ids)
            )
            if suggestion:
                display = {
                    t[0]: t[1] for t in _TASK_TYPES
                }.get(suggestion, suggestion)
                self._recommend_banner.setText(
                    tr(
                        f"基于已导入数据，推荐: {display}",
                        f"Based on imported data, recommend: {display}",
                    )
                )
                self._recommend_banner.setVisible(True)

        def _show_empty_preview(self):
            self._clear_preview()
            self._preview_layout.addWidget(self._empty_preview_label)
            self._recommend_banner.setVisible(False)

        def _clear_preview(self):
            while self._preview_layout.count():
                item = self._preview_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        def _refresh_label_table(self):
            """Rebuild the label table from self._labels."""
            self._label_table.setRowCount(0)
            for label in self._labels:
                row = self._label_table.rowCount()
                self._label_table.insertRow(row)

                id_item = QtWidgets.QTableWidgetItem(str(label.id))
                id_item.setFlags(
                    QtCore.Qt.ItemFlag.ItemIsEnabled
                    | QtCore.Qt.ItemFlag.ItemIsSelectable
                )
                self._label_table.setItem(row, 0, id_item)

                name_item = QtWidgets.QTableWidgetItem(label.name)
                self._label_table.setItem(row, 1, name_item)

        def _clear_labels(self):
            self._labels = []
            self._next_label_id = 0
            self._refresh_label_table()

        def _update_task_description(self):
            family = self._task_combo.currentData()
            if family is None:
                return
            desc_map = {t[0]: t[2] for t in _TASK_TYPES}
            desc = desc_map.get(family, "")
            self._task_desc_label.setText(desc)

        # ------------------------------------------------------------------
        # Static helpers
        # ------------------------------------------------------------------

        @staticmethod
        def _read_image_dims(file_path: Path) -> tuple[int, int]:
            """Read image dimensions quickly."""
            try:
                from anylabeling.platform.infrastructure.image_reader import ImageReader
                meta = ImageReader.metadata(str(file_path))
                if meta.width == 0:
                    return 0, 0
                return meta.width, meta.height
            except Exception:
                return 0, 0

        @staticmethod
        def _make_thumbnail_label(
            file_path: Path, width: int, height: int
        ) -> QtWidgets.QLabel:
            """Create a labeled thumbnail widget."""
            label = QtWidgets.QLabel()
            label.setFixedSize(100, 110)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(
                f"border: 1px solid {get_theme().get('border', '#ccc')};"
                f"border-radius: 4px;"
                f"background-color: {get_theme().get('background_secondary', '#f5f5f5')};"
                f"font-size: {FONT_SIZE_CAPTION}px;"
                f"color: {get_theme().get('text_secondary', '#888')};"
                f"font-family: {FONT_FAMILY};"
            )

            try:
                from anylabeling.platform.infrastructure.image_reader import ImageReader
                from PyQt6 import QtGui

                img = ImageReader.read(str(file_path), output_color="BGR")
                if img is not None:
                    h, w = img.shape[:2]
                    scale = 80 / max(w, h)
                    new_w, new_h = int(w * scale), int(h * scale)
                    resized = cv2.resize(img, (new_w, new_h))
                    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                    qimg = QtGui.QImage(
                        rgb.data, new_w, new_h, new_w * 3,
                        QtGui.QImage.Format.Format_RGB888,
                    )
                    pix = QtGui.QPixmap.fromImage(qimg)
                    label.setPixmap(pix)
            except Exception:
                pass

            label.setText(f"{file_path.name}\n{width}x{height}")
            return label

        @staticmethod
        def _scan_group_ids_from_assets(assets_dir: Path) -> set[str]:
            """Return unique group/folder names from assets directory."""
            subdirs = {
                d.name for d in assets_dir.iterdir() if d.is_dir()
            }
            if not subdirs:
                # Files directly in assets/ have no group
                return set()
            return subdirs


except ImportError:
    TaskConfigurator = None  # type: ignore


__all__ = [
    "TaskConfigurator",
    "_TASK_TYPES",
    "_FAMILY_INDEX",
    "_smart_recommend_task",
]

"""ImportWorkspace — embedded non-modal import page with precheck + execution.

Follows QWIDGET_PATTERN: signals at class level, _build_ui() pattern.
Uses ImportViewModel for state; precheck and import run in QThread workers.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from anylabeling.platform.application.import_service import (
    ImportCancelledError,
    ImportService,
)
from anylabeling.platform.domain.import_config import ImportResult, PrecheckResult
from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import FONT_FAMILY, FONT_SIZE_BODY, FONT_SIZE_CAPTION
from anylabeling.views.platform.view_models.import_vm import ImportViewModel
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)


class _PrecheckWorker(QtCore.QThread):
    """Worker thread for precheck — scans without copying."""

    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(object)  # PrecheckResult or Exception

    def __init__(self, vm: ImportViewModel, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._vm = vm

    def run(self) -> None:
        try:
            result = self._vm.start_precheck(
                progress_callback=self._on_progress
            )
            self.finished.emit(result)
        except Exception as exc:
            self.finished.emit(exc)

    def _on_progress(self, current: int, total: int) -> None:
        self.progress.emit(current, total)


class _ImportWorker(QtCore.QThread):
    """Worker thread for import — copies files with progress and cancel."""

    progress = QtCore.pyqtSignal(int, int, str)
    finished = QtCore.pyqtSignal(object)  # ImportResult or Exception

    def __init__(self, vm: ImportViewModel, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._vm = vm

    def run(self) -> None:
        try:
            result = self._vm.start_import(
                progress_callback=self._on_progress
            )
            self.finished.emit(result)
        except ImportCancelledError:
            self.finished.emit(ImportCancelledError())
        except Exception as exc:
            self.finished.emit(exc)

    def _on_progress(self, current: int, total: int, filename: str) -> None:
        self.progress.emit(current, total, filename)


class ImportWorkspace(QtWidgets.QWidget):
    """Embedded (non-modal) import page for the platform workbench.

    Lifecycle:
        1. User adds sources (files/directories)
        2. User clicks "Precheck" → scans sources, shows results
        3. User reviews problems, adjusts rules
        4. User clicks "Start Import" → copies files with progress
        5. Completion report shown (does NOT auto-navigate away)

    Signals:
        import_completed(ImportResult): Emitted when import finishes.
    """

    import_completed = QtCore.pyqtSignal(ImportResult)
    asset_repository_changed = QtCore.pyqtSignal()
    back_requested = QtCore.pyqtSignal()

    def __init__(
        self,
        import_service: ImportService,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = import_service
        self._vm = ImportViewModel(import_service)
        self._precheck_worker: _PrecheckWorker | None = None
        self._import_worker: _ImportWorker | None = None
        self._project_labels: dict[int, dict] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t = get_theme()
        main = QtWidgets.QVBoxLayout()
        main.setContentsMargins(16, 12, 16, 12)
        main.setSpacing(12)

        # ── Back button row ──
        back_row = QtWidgets.QHBoxLayout()
        self._back_btn = QtWidgets.QPushButton(
            tr("← 返回概览", "← Back to Overview")
        )
        self._back_btn.setMinimumSize(80, 28)
        self._back_btn.setFlat(True)
        self._back_btn.setStyleSheet(
            f"QPushButton {{"
            f"font-family: {FONT_FAMILY};"
            f"font-size: {FONT_SIZE_CAPTION}px;"
            f"color: {t['text_secondary']};"
            f"border: none; padding: 4px 8px;"
            f"}}"
            f"QPushButton:hover {{"
            f"color: {t['primary']};"
            f"}}"
        )
        self._back_btn.clicked.connect(self.back_requested.emit)
        back_row.addWidget(self._back_btn)
        back_row.addStretch()
        main.addLayout(back_row)

        # ── Page header ──
        header = QtWidgets.QLabel(tr("📥 导入图片", "📥 Import Images"))
        header.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: 20px;"
            f"font-weight: bold; color: {t['text']};"
        )
        main.addWidget(header)

        # ── Sources section ──
        sources_group = QtWidgets.QGroupBox(tr("数据源", "Sources"))
        sources_layout = QtWidgets.QVBoxLayout()
        sources_layout.setSpacing(6)

        btn_row = QtWidgets.QHBoxLayout()
        self._add_files_btn = QtWidgets.QPushButton(tr("添加文件…", "Add Files…"))
        self._add_files_btn.clicked.connect(self._on_add_files)
        btn_row.addWidget(self._add_files_btn)

        self._add_folder_btn = QtWidgets.QPushButton(tr("添加文件夹…", "Add Folder…"))
        self._add_folder_btn.clicked.connect(self._on_add_folder)
        btn_row.addWidget(self._add_folder_btn)

        self._clear_sources_btn = QtWidgets.QPushButton(tr("清空", "Clear"))
        self._clear_sources_btn.clicked.connect(self._on_clear_sources)
        btn_row.addWidget(self._clear_sources_btn)

        btn_row.addStretch()
        sources_layout.addLayout(btn_row)

        self._source_list = QtWidgets.QListWidget()
        self._source_list.setMaximumHeight(120)
        sources_layout.addWidget(self._source_list)

        sources_group.setLayout(sources_layout)
        main.addWidget(sources_group)

        # ── Precheck section ──
        precheck_group = QtWidgets.QGroupBox(tr("预检查", "Precheck"))
        precheck_layout = QtWidgets.QVBoxLayout()
        precheck_layout.setSpacing(6)

        precheck_btn_row = QtWidgets.QHBoxLayout()
        self._precheck_btn = QtWidgets.QPushButton(tr("开始扫描", "Start Scan"))
        self._precheck_btn.clicked.connect(self._on_precheck)
        self._precheck_btn.setEnabled(False)
        precheck_btn_row.addWidget(self._precheck_btn)
        precheck_btn_row.addStretch()
        precheck_layout.addLayout(precheck_btn_row)

        self._precheck_status = QtWidgets.QLabel(
            tr("添加数据源后点击扫描", "Add sources then click scan")
        )
        self._precheck_status.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_BODY}px;"
            f"color: {t['text_secondary']};"
        )
        precheck_layout.addWidget(self._precheck_status)

        # Problem files expandable
        self._problems_toggle = QtWidgets.QPushButton(
            tr("查看问题文件 ▸", "View problem files ▸")
        )
        self._problems_toggle.setFlat(True)
        self._problems_toggle.setVisible(False)
        self._problems_toggle.clicked.connect(self._on_toggle_problems)
        precheck_layout.addWidget(self._problems_toggle)

        self._problems_list = QtWidgets.QListWidget()
        self._problems_list.setVisible(False)
        self._problems_list.setMaximumHeight(100)
        precheck_layout.addWidget(self._problems_list)

        precheck_group.setLayout(precheck_layout)
        main.addWidget(precheck_group)

        # ── Import rules ──
        rules_group = QtWidgets.QGroupBox(tr("导入规则", "Import Rules"))
        rules_layout = QtWidgets.QVBoxLayout()
        rules_layout.setSpacing(6)

        self._dedup_check = QtWidgets.QCheckBox(
            tr("跳过重复文件 (SHA-256)", "Skip duplicates (SHA-256)")
        )
        self._dedup_check.setChecked(True)
        rules_layout.addWidget(self._dedup_check)

        self._group_check = QtWidgets.QCheckBox(
            tr("按源文件夹分组", "Group by source folder")
        )
        self._group_check.setChecked(True)
        rules_layout.addWidget(self._group_check)

        # --- Annotation format selector ---
        ann_format_row = QtWidgets.QHBoxLayout()
        ann_format_row.setSpacing(6)
        ann_format_label = QtWidgets.QLabel(
            tr("标注格式:", "Annotation Format:")
        )
        ann_format_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_BODY}px;"
            f"color: {t['text']};"
        )
        ann_format_row.addWidget(ann_format_label)

        self._ann_format_combo = QtWidgets.QComboBox()
        self._ann_format_combo.addItem(tr("无", "None"), "none")
        self._ann_format_combo.addItem(
            "X-AnyLabeling (JSON)", "xanylabel"
        )
        self._ann_format_combo.addItem("YOLO", "yolo")
        self._ann_format_combo.addItem("COCO", "coco")
        self._ann_format_combo.addItem(
            tr("Pascal VOC", "Pascal VOC"), "voc"
        )
        self._ann_format_combo.setMinimumWidth(160)
        self._ann_format_combo.currentTextChanged.connect(
            self._on_annotation_format_changed
        )
        ann_format_row.addWidget(self._ann_format_combo)
        ann_format_row.addStretch()
        rules_layout.addLayout(ann_format_row)

        # --- Annotation path input (conditionally visible) ---
        self._ann_path_row = QtWidgets.QHBoxLayout()
        self._ann_path_row.setSpacing(6)
        ann_path_label = QtWidgets.QLabel(
            tr("标注路径:", "Annotation Path:")
        )
        ann_path_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_BODY}px;"
            f"color: {t['text']};"
        )
        self._ann_path_row.addWidget(ann_path_label)

        self._ann_path_edit = QtWidgets.QLineEdit()
        self._ann_path_edit.setPlaceholderText(
            tr("标注文件所在目录或JSON路径", "Directory or JSON path for annotation files")
        )
        self._ann_path_edit.textChanged.connect(
            self._on_annotation_path_changed
        )
        self._ann_path_row.addWidget(self._ann_path_edit, stretch=1)

        self._ann_browse_btn = QtWidgets.QPushButton(
            tr("浏览…", "Browse…")
        )
        self._ann_browse_btn.setMinimumSize(80, 28)
        self._ann_browse_btn.clicked.connect(self._on_browse_annotation_path)
        self._ann_path_row.addWidget(self._ann_browse_btn)

        self._ann_path_widget = QtWidgets.QWidget()
        self._ann_path_widget.setLayout(self._ann_path_row)
        self._ann_path_widget.setVisible(False)
        rules_layout.addWidget(self._ann_path_widget)

        # --- Annotation preview panel (conditionally visible) ---
        self._ann_preview_widget = QtWidgets.QWidget()
        ann_preview_layout = QtWidgets.QVBoxLayout()
        ann_preview_layout.setSpacing(4)
        ann_preview_layout.setContentsMargins(8, 8, 8, 8)

        self._ann_preview_label = QtWidgets.QLabel("")
        self._ann_preview_label.setWordWrap(True)
        self._ann_preview_label.setStyleSheet(
            f"font-family: {FONT_FAMILY};"
            f"font-size: {FONT_SIZE_CAPTION}px;"
            f"color: {t['text']};"
            f"background-color: {t['surface']};"
            f"border: 1px solid {t['border']};"
            f"border-radius: 4px;"
            f"padding: 8px;"
        )
        self._ann_preview_label.setMaximumHeight(120)
        ann_preview_layout.addWidget(self._ann_preview_label)

        self._ann_preview_widget.setLayout(ann_preview_layout)
        self._ann_preview_widget.setVisible(False)
        rules_layout.addWidget(self._ann_preview_widget)

        rules_group.setLayout(rules_layout)
        main.addWidget(rules_group)

        # ── Progress ──
        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(True)
        main.addWidget(self._progress_bar)

        self._progress_file_label = QtWidgets.QLabel("")
        self._progress_file_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_CAPTION}px;"
            f"color: {t['text_secondary']};"
        )
        self._progress_file_label.setVisible(False)
        main.addWidget(self._progress_file_label)

        # ── Action buttons ──
        action_row = QtWidgets.QHBoxLayout()
        action_row.addStretch()

        self._cancel_btn = QtWidgets.QPushButton(tr("取消", "Cancel"))
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        action_row.addWidget(self._cancel_btn)

        self._start_import_btn = QtWidgets.QPushButton(tr("开始导入", "Start Import"))
        self._start_import_btn.setEnabled(False)
        self._start_import_btn.clicked.connect(self._on_start_import)
        action_row.addWidget(self._start_import_btn)

        main.addLayout(action_row)

        # ── Completion report ──
        self._completion_label = QtWidgets.QLabel("")
        self._completion_label.setWordWrap(True)
        self._completion_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_BODY}px;"
            f"color: {t['text']}; padding: 8px;"
            f"background-color: {t['surface']}; border-radius: 6px;"
        )
        self._completion_label.setVisible(False)
        main.addWidget(self._completion_label)

        main.addStretch()
        self.setLayout(main)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project_labels(self, labels: dict[int, dict]) -> None:
        """Set the project label mapping for annotation import.

        Args:
            labels: Mapping of label_id -> dict with at least 'name' key.
        """
        self._project_labels = labels

    # ------------------------------------------------------------------
    # Annotation format handlers (Phase 3)
    # ------------------------------------------------------------------

    def _on_annotation_format_changed(self, text: str) -> None:
        """Show/hide annotation path input when format is selected."""
        is_none = self._ann_format_combo.currentData() in (None, "none")
        self._ann_path_widget.setVisible(not is_none)
        self._ann_preview_widget.setVisible(not is_none and bool(
            self._ann_path_edit.text().strip()
        ))
        if is_none:
            self._ann_path_edit.clear()
            self._ann_preview_label.clear()

    def _on_annotation_path_changed(self, text: str) -> None:
        """Refresh annotation preview when path changes."""
        path = text.strip()
        if path and not self._is_format_none():
            self._ann_preview_widget.setVisible(True)
            self._refresh_annotation_preview(path)
        else:
            self._ann_preview_widget.setVisible(False)

    def _on_browse_annotation_path(self) -> None:
        """Browse for annotation source path."""
        fmt = self._get_annotation_format()
        if fmt == "coco":
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                tr("选择 COCO JSON 文件", "Select COCO JSON file"),
                "",
                tr("JSON 文件 (*.json);;所有文件 (*)",
                    "JSON files (*.json);;All files (*)"),
            )
        else:
            path = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                tr("选择标注文件夹", "Select annotation folder"),
            )
        if path:
            self._ann_path_edit.setText(path)

    def _refresh_annotation_preview(self, source_path: str) -> None:
        """Scan annotation source and show preview summary."""
        from pathlib import Path

        source = Path(source_path)
        fmt = self._get_annotation_format()

        if not source.exists():
            self._ann_preview_label.setText(
                tr("⚠ 路径不存在", "⚠ Path does not exist")
            )
            return

        if fmt == "coco":
            self._preview_coco_annotations(source)
        elif fmt == "yolo":
            self._preview_per_image_annotations(source, ".txt")
        elif fmt == "voc":
            self._preview_per_image_annotations(source, ".xml")

    def _preview_coco_annotations(self, source: Path) -> None:
        """Preview COCO JSON annotations."""
        import json

        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self._ann_preview_label.setText(
                tr(f"⚠ 无法读取文件: {exc}", f"⚠ Cannot read file: {exc}")
            )
            return

        images = data.get("images", [])
        annotations = data.get("annotations", [])
        categories = data.get("categories", [])

        cat_names = {c["id"]: c.get("name", str(c["id"])) for c in categories}

        # Count annotations per category
        cat_counts: dict[str, int] = {}
        for ann in annotations:
            cid = ann.get("category_id")
            if cid is not None:
                name = cat_names.get(cid, str(cid))
                cat_counts[name] = cat_counts.get(name, 0) + 1

        lines = [
            tr(
                f"📊 扫描到 {len(images)} 张图片, {len(annotations)} 个标注",
                f"📊 Found {len(images)} images, {len(annotations)} annotations",
            ),
        ]

        if cat_counts:
            lines.append(tr("类别统计:", "Categories:"))
            for name, count in sorted(
                cat_counts.items(), key=lambda x: -x[1]
            )[:10]:
                mapped = self._check_label_mapped(name)
                lines.append(
                    f"  {name}: {count}  {mapped}"
                )

        self._ann_preview_label.setText("\n".join(lines))

    def _preview_per_image_annotations(
        self, source: Path, ext: str,
    ) -> None:
        """Preview per-image annotation files (YOLO .txt or VOC .xml)."""
        ann_files = sorted(source.glob(f"*{ext}"))
        total = len(ann_files)

        if total == 0:
            self._ann_preview_label.setText(
                tr(
                    f"⚠ 未找到 {ext} 标注文件",
                    f"⚠ No {ext} annotation files found",
                )
            )
            return

        # Count class occurrences
        class_counts: dict[str, int] = {}
        errors = 0

        for ann_file in ann_files[:500]:  # Limit preview scan
            try:
                if ext == ".txt":
                    # YOLO: first field is class_id
                    for line in ann_file.read_text(
                        encoding="utf-8"
                    ).splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            cls_id = parts[0]
                            class_counts[cls_id] = (
                                class_counts.get(cls_id, 0) + 1
                            )
                elif ext == ".xml":
                    # VOC: <name> element
                    import xml.etree.ElementTree as ET
                    tree = ET.parse(ann_file)
                    for obj in tree.findall("object"):
                        name_elem = obj.find("name")
                        if name_elem is not None and name_elem.text:
                            name = name_elem.text.strip()
                            class_counts[name] = (
                                class_counts.get(name, 0) + 1
                            )
            except Exception:
                errors += 1

        lines = [
            tr(
                f"📊 扫描到 {total} 个标注文件",
                f"📊 Found {total} annotation files",
            ),
        ]

        if errors:
            lines.append(
                tr(
                    f"⚠ {errors} 个文件解析失败",
                    f"⚠ {errors} files failed to parse",
                )
            )

        if class_counts:
            lines.append(tr("类别统计:", "Categories:"))
            for name, count in sorted(
                class_counts.items(), key=lambda x: -x[1]
            )[:10]:
                mapped = self._check_label_mapped(name)
                lines.append(
                    f"  {name}: {count}  {mapped}"
                )

        self._ann_preview_label.setText("\n".join(lines))

    def _check_label_mapped(self, label_name: str) -> str:
        """Check if a label name matches any project label.

        Returns:
            A status indicator string: "✓" if matched, "⚠ 未匹配" if not.
        """
        if not self._project_labels:
            return tr("(无项目标签)", "(no project labels)")
        for label_id, label_info in self._project_labels.items():
            if label_info.get("name", "").lower() == label_name.lower():
                return tr("✓ 自动匹配", "✓ Auto-matched")
        return tr("⚠ 未匹配", "⚠ Unmatched")

    # ------------------------------------------------------------------
    # Annotation format helpers
    # ------------------------------------------------------------------

    def _is_format_none(self) -> bool:
        """Check if the annotation format selector is on 'None'."""
        return self._ann_format_combo.currentData() in (None, "none")

    def _get_annotation_format(self) -> str | None:
        """Get the selected annotation format key.

        Returns one of: None, "xanylabel", "yolo", "coco", "voc".
        """
        fmt = self._ann_format_combo.currentData()
        if fmt in (None, "none"):
            return None
        return fmt

    # ------------------------------------------------------------------
    # Source management
    # ------------------------------------------------------------------

    def _on_add_files(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            tr("选择图片文件", "Select image files"),
            "",
            tr(
                "图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp);;所有文件 (*)",
                "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp);;All files (*)",
            ),
        )
        if paths:
            self._vm.add_sources(list(paths))
            self._refresh_source_list()
            self._update_buttons()

    def _on_add_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            tr("选择图片文件夹", "Select image folder"),
        )
        if folder:
            self._vm.add_sources([folder])
            self._refresh_source_list()
            self._update_buttons()

    def _on_clear_sources(self) -> None:
        self._vm.clear_sources()
        self._refresh_source_list()
        self._update_buttons()

    def _refresh_source_list(self) -> None:
        self._source_list.clear()
        for src in self._vm.sources:
            item_text = f"{Path(src).name}  ({src})"
            self._source_list.addItem(item_text)

    def _update_buttons(self) -> None:
        has_sources = self._vm.source_count > 0
        not_busy = not self._vm.is_busy
        self._precheck_btn.setEnabled(has_sources and not_busy)
        self._start_import_btn.setEnabled(
            self._vm.can_start_import and not_busy
        )

    # ------------------------------------------------------------------
    # Precheck
    # ------------------------------------------------------------------

    def _on_precheck(self) -> None:
        if not self._vm.can_start_precheck:
            return

        self._set_ui_busy(True)
        self._precheck_status.setText(tr("正在扫描…", "Scanning…"))
        self._progress_bar.setVisible(True)
        self._progress_bar.setMaximum(0)  # indeterminate

        self._precheck_worker = _PrecheckWorker(self._vm, parent=self)
        self._precheck_worker.progress.connect(self._on_precheck_progress)
        self._precheck_worker.finished.connect(self._on_precheck_done)
        self._precheck_worker.start()

    def _on_precheck_progress(self, current: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(current)

    def _on_precheck_done(self, result: object) -> None:
        self._set_ui_busy(False)
        self._progress_bar.setVisible(False)

        if isinstance(result, Exception):
            self._precheck_status.setText(
                tr(f"扫描失败: {result}", f"Scan failed: {result}")
            )
            return

        precheck: PrecheckResult = result
        est_mb = precheck.estimated_size_bytes / 1024 / 1024
        self._precheck_status.setText(
            tr(
                f"✓ 有效: {precheck.ok_count}  "
                f"⚠ 损坏: {precheck.damaged_count}  "
                f"⚠ 不支持: {precheck.unsupported_count}  "
                f"⚠ 超大图像: {precheck.oversized_count}  "
                f"预估大小: {est_mb:.1f} MB",
                f"✓ Valid: {precheck.ok_count}  "
                f"⚠ Damaged: {precheck.damaged_count}  "
                f"⚠ Unsupported: {precheck.unsupported_count}  "
                f"⚠ Oversized: {precheck.oversized_count}  "
                f"Est. size: {est_mb:.1f} MB",
            )
        )

        # Populate problem files
        self._problems_list.clear()
        has_problems = False
        for p in precheck.damaged_files:
            self._problems_list.addItem(f"Damaged: {p}")
            has_problems = True
        for p in precheck.unsupported_files:
            self._problems_list.addItem(f"Unsupported: {p}")
            has_problems = True
        for p, w, h in precheck.oversized_files:
            self._problems_list.addItem(f"Oversized ({w}x{h}): {p}")
            has_problems = True

        self._problems_toggle.setVisible(has_problems)
        self._problems_list.setVisible(False)
        self._update_buttons()

    def _on_toggle_problems(self) -> None:
        visible = not self._problems_list.isVisible()
        self._problems_list.setVisible(visible)
        self._problems_toggle.setText(
            tr("隐藏问题文件 ▾", "Hide problem files ▾")
            if visible
            else tr("查看问题文件 ▸", "View problem files ▸")
        )

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def _on_start_import(self) -> None:
        if not self._vm.can_start_import:
            return

        self._set_ui_busy(True)
        self._completion_label.setVisible(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._cancel_btn.setVisible(True)
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setText(tr("取消", "Cancel"))
        self._start_import_btn.setEnabled(False)

        self._import_worker = _ImportWorker(self._vm, parent=self)
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._on_import_done)
        self._import_worker.start()

    def _on_import_progress(
        self, current: int, total: int, filename: str
    ) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_file_label.setText(filename)
        self._progress_file_label.setVisible(True)

    def _on_import_done(self, result: object) -> None:
        self._set_ui_busy(False)
        self._progress_bar.setVisible(False)
        self._progress_file_label.setVisible(False)
        self._cancel_btn.setVisible(False)

        if isinstance(result, ImportCancelledError):
            self._completion_label.setText(
                tr("⏹ 导入已取消", "⏹ Import cancelled")
            )
            self._completion_label.setVisible(True)
            self._update_buttons()
            return

        if isinstance(result, Exception):
            self._completion_label.setText(
                tr(f"❌ 导入失败: {result}", f"❌ Import failed: {result}")
            )
            self._completion_label.setVisible(True)
            self._update_buttons()
            return

        import_result: ImportResult = result
        self._completion_label.setText(
            tr(
                f"✓ 导入完成！\n"
                f"  已导入: {import_result.total} 张图片\n"
                f"  大图: {import_result.large_count} 张\n"
                f"  跳过(重复): {import_result.duplicate_count} 张\n"
                f"  错误: {len(import_result.errors)} 项",
                f"✓ Import complete!\n"
                f"  Imported: {import_result.total} images\n"
                f"  Large: {import_result.large_count}\n"
                f"  Skipped (duplicates): {import_result.duplicate_count}\n"
                f"  Errors: {len(import_result.errors)}",
            )
        )
        self._completion_label.setVisible(True)
        self._update_buttons()

        self.import_completed.emit(import_result)
        self.asset_repository_changed.emit()

    def _on_cancel(self) -> None:
        self._vm.cancel()
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText(tr("正在取消…", "Cancelling…"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_ui_busy(self, busy: bool) -> None:
        self._add_files_btn.setEnabled(not busy)
        self._add_folder_btn.setEnabled(not busy)
        self._clear_sources_btn.setEnabled(not busy)
        self._precheck_btn.setEnabled(not busy and self._vm.can_start_precheck)
        self._start_import_btn.setEnabled(
            not busy and self._vm.can_start_import
        )

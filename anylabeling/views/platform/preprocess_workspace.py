"""PreprocessWorkspace — tile slicing, dataset splitting, tile preview, and build history."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from anylabeling.platform.application.dataset_build_service import (
    DatasetBuildService,
)
from anylabeling.platform.domain.preprocess_config import (
    PreprocessConfig,
    validate_split_ratios,
)
from anylabeling.platform.domain.tile import TilePlan, TileRecord
from anylabeling.platform.tiling.tile_planner import TilePlanner
from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)

_EDGE_MODES = ["strict", "crop", "pad"]
_SPLIT_STRATEGIES = ["random_by_asset", "random_by_tile", "manual"]
_PREVIEW_DEBOUNCE_MS = 300


class PreprocessWorkspace(QtWidgets.QWidget):
    """Preprocess Workspace — configure tile slicing, split ratios, augmentations,
    preview tile grids, and browse build history.

    Emits ``build_requested(PreprocessConfig)`` when the user clicks Build.
    """

    build_requested = QtCore.pyqtSignal(PreprocessConfig)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._large_images: list[str] = []
        self._total_assets = 0
        self._project_path: str = ""
        self._task_family: str = "detection_hbb"
        self._preview_image_path: str = ""
        self._preview_tiles: list[TileRecord] = []
        self._label_counts: dict[str, int] = {}
        self._truncated_counts: dict[str, int] = {}
        self._preview_debounce_timer = QtCore.QTimer(self)
        self._preview_debounce_timer.setSingleShot(True)
        self._preview_debounce_timer.timeout.connect(self._update_preview)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        t = get_theme()
        main = QtWidgets.QVBoxLayout()
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(12)

        # ── Tab widget ──
        self._tab_widget = QtWidgets.QTabWidget()
        main.addWidget(self._tab_widget)

        # Tab 0: Config
        self._config_tab = QtWidgets.QWidget()
        self._setup_config_tab()
        self._tab_widget.addTab(
            self._config_tab, tr("配置", "Config")
        )

        # Tab 1: Preview
        self._preview_tab = QtWidgets.QWidget()
        self._setup_preview_tab()
        self._tab_widget.addTab(
            self._preview_tab, tr("预览", "Preview")
        )

        # Tab 2: History
        self._history_tab = QtWidgets.QWidget()
        self._setup_history_tab()
        self._tab_widget.addTab(
            self._history_tab, tr("历史", "History")
        )

        self.setLayout(main)

    # ------------------------------------------------------------------
    # Config Tab
    # ------------------------------------------------------------------

    def _setup_config_tab(self):
        t = get_theme()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        label_font = f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_BODY}px; color: {t['text']};"
        caption_font = f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_CAPTION}px; color: {t['text_secondary']};"

        # ── Large image preview ──
        preview_group = QtWidgets.QGroupBox(tr("大图预览", "Large Image Preview"))
        preview_layout = QtWidgets.QVBoxLayout()

        self._large_image_label = QtWidgets.QLabel(tr("检测到 0 张大图 (>2000px)", "Detected 0 large images (>2000px)"))
        self._large_image_label.setStyleSheet(caption_font)
        preview_layout.addWidget(self._large_image_label)

        self._thumbnail_list = QtWidgets.QListWidget()
        self._thumbnail_list.setMaximumHeight(120)
        self._thumbnail_list.setStyleSheet(
            f"border: 1px solid {t['border']}; border-radius: 4px;"
            f"background-color: {t['surface']};"
        )
        self._thumbnail_list.itemClicked.connect(self._on_thumbnail_clicked)
        preview_layout.addWidget(self._thumbnail_list)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # ── Tile config ──
        tile_group = QtWidgets.QGroupBox(tr("切片配置", "Tile Configuration"))
        tile_layout = QtWidgets.QFormLayout()

        self._tile_width_sb = QtWidgets.QSpinBox()
        self._tile_width_sb.setRange(64, 4096)
        self._tile_width_sb.setValue(1024)
        self._tile_width_sb.valueChanged.connect(self._on_tile_params_changed)
        tile_layout.addRow(tr("切片宽度:", "Tile Width:"), self._tile_width_sb)

        self._tile_height_sb = QtWidgets.QSpinBox()
        self._tile_height_sb.setRange(64, 4096)
        self._tile_height_sb.setValue(1024)
        self._tile_height_sb.valueChanged.connect(self._on_tile_params_changed)
        tile_layout.addRow(tr("切片高度:", "Tile Height:"), self._tile_height_sb)

        self._overlap_x_sb = QtWidgets.QSpinBox()
        self._overlap_x_sb.setRange(0, 2048)
        self._overlap_x_sb.setValue(256)
        self._overlap_x_sb.setSuffix(" px")
        self._overlap_x_sb.valueChanged.connect(self._on_tile_params_changed)
        tile_layout.addRow(tr("overlap_x:", "overlap_x:"), self._overlap_x_sb)

        self._overlap_y_sb = QtWidgets.QSpinBox()
        self._overlap_y_sb.setRange(0, 2048)
        self._overlap_y_sb.setValue(256)
        self._overlap_y_sb.setSuffix(" px")
        self._overlap_y_sb.valueChanged.connect(self._on_tile_params_changed)
        tile_layout.addRow(tr("overlap_y:", "overlap_y:"), self._overlap_y_sb)

        self._edge_mode_combo = QtWidgets.QComboBox()
        self._edge_mode_combo.addItems(_EDGE_MODES)
        self._edge_mode_combo.currentTextChanged.connect(self._on_tile_params_changed)
        tile_layout.addRow(tr("边缘模式:", "Edge Mode:"), self._edge_mode_combo)

        # Recommendation hint
        rec_label = QtWidgets.QLabel(tr("推荐值: 1024x1024, 重叠 256px (20%)", "Recommended: 1024x1024, overlap 256px (20%)"))
        rec_label.setStyleSheet(caption_font)
        tile_layout.addRow("", rec_label)

        # Tile preview
        self._tile_preview_label = QtWidgets.QLabel(tr("预计每张图: — 块切片", "Estimated per image: — tiles"))
        self._tile_preview_label.setStyleSheet(caption_font)
        tile_layout.addRow("", self._tile_preview_label)

        tile_group.setLayout(tile_layout)
        layout.addWidget(tile_group)

        # ── Split config ──
        split_group = QtWidgets.QGroupBox(tr("切分配置", "Split Configuration"))
        split_layout = QtWidgets.QFormLayout()

        self._split_strategy_combo = QtWidgets.QComboBox()
        self._split_strategy_combo.addItems(_SPLIT_STRATEGIES)
        split_layout.addRow(tr("策略:", "Strategy:"), self._split_strategy_combo)

        self._train_ratio_sb = QtWidgets.QDoubleSpinBox()
        self._train_ratio_sb.setRange(0.1, 1.0)
        self._train_ratio_sb.setSingleStep(0.05)
        self._train_ratio_sb.setValue(0.7)
        self._train_ratio_sb.valueChanged.connect(self._on_split_params_changed)
        split_layout.addRow(tr("训练集:", "Train:"), self._train_ratio_sb)

        self._val_ratio_sb = QtWidgets.QDoubleSpinBox()
        self._val_ratio_sb.setRange(0.0, 0.9)
        self._val_ratio_sb.setSingleStep(0.05)
        self._val_ratio_sb.setValue(0.2)
        self._val_ratio_sb.valueChanged.connect(self._on_split_params_changed)
        split_layout.addRow(tr("验证集:", "Val:"), self._val_ratio_sb)

        self._test_ratio_sb = QtWidgets.QDoubleSpinBox()
        self._test_ratio_sb.setRange(0.0, 0.9)
        self._test_ratio_sb.setSingleStep(0.05)
        self._test_ratio_sb.setValue(0.1)
        self._test_ratio_sb.valueChanged.connect(self._on_split_params_changed)
        split_layout.addRow(tr("测试集:", "Test:"), self._test_ratio_sb)

        self._seed_sb = QtWidgets.QSpinBox()
        self._seed_sb.setRange(0, 999999)
        self._seed_sb.setValue(42)
        split_layout.addRow(tr("随机种子:", "Seed:"), self._seed_sb)

        self._split_preview_label = QtWidgets.QLabel(tr("训练 — | 验证 — | 测试 —", "Train — | Val — | Test —"))
        self._split_preview_label.setStyleSheet(caption_font)
        split_layout.addRow("", self._split_preview_label)

        split_group.setLayout(split_layout)
        layout.addWidget(split_group)

        # ── Augmentation ──
        aug_group = QtWidgets.QGroupBox(tr("数据增强", "Data Augmentation"))
        aug_layout = QtWidgets.QHBoxLayout()

        self._hflip_cb = QtWidgets.QCheckBox(tr("水平翻转", "H-Flip"))
        self._hflip_cb.setEnabled(False)
        self._hflip_cb.setToolTip(tr("（规划中）", "(planned)"))
        self._hflip_cb.setChecked(True)
        aug_layout.addWidget(self._hflip_cb)

        self._vflip_cb = QtWidgets.QCheckBox(tr("垂直翻转", "V-Flip"))
        self._vflip_cb.setEnabled(False)
        self._vflip_cb.setToolTip(tr("（规划中）", "(planned)"))
        aug_layout.addWidget(self._vflip_cb)

        self._brightness_cb = QtWidgets.QCheckBox(tr("亮度", "Brightness"))
        self._brightness_cb.setEnabled(False)
        self._brightness_cb.setToolTip(tr("（规划中）", "(planned)"))
        self._brightness_cb.setChecked(True)
        aug_layout.addWidget(self._brightness_cb)

        self._rotate_cb = QtWidgets.QCheckBox(tr("旋转", "Rotate"))
        self._rotate_cb.setEnabled(False)
        self._rotate_cb.setToolTip(tr("（规划中）", "(planned)"))
        self._rotate_cb.setChecked(True)
        aug_layout.addWidget(self._rotate_cb)

        aug_layout.addStretch()
        aug_group.setLayout(aug_layout)
        layout.addWidget(aug_group)

        # ── Action buttons ──
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        self._preview_btn = QtWidgets.QPushButton(tr("预览构建", "Preview Build"))
        self._preview_btn.clicked.connect(lambda: self._tab_widget.setCurrentIndex(1))
        btn_layout.addWidget(self._preview_btn)

        self._build_btn = QtWidgets.QPushButton(tr("直接构建 →", "Build →"))
        self._build_btn.setEnabled(False)
        self._build_btn.clicked.connect(self._on_build_clicked)
        btn_layout.addWidget(self._build_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()
        self._config_tab.setLayout(layout)

    # ------------------------------------------------------------------
    # Preview Tab
    # ------------------------------------------------------------------

    def _setup_preview_tab(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar: image selector + navigation
        toolbar = QtWidgets.QHBoxLayout()

        self._preview_image_combo = QtWidgets.QComboBox()
        self._preview_image_combo.setMinimumWidth(300)
        self._preview_image_combo.currentTextChanged.connect(
            self._on_preview_image_changed
        )
        toolbar.addWidget(QtWidgets.QLabel(tr("图片:", "Image:")))
        toolbar.addWidget(self._preview_image_combo, stretch=1)

        self._preview_tile_info = QtWidgets.QLabel()
        toolbar.addWidget(self._preview_tile_info)

        layout.addLayout(toolbar)

        # Splitter: tile preview | inspector panel
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        from anylabeling.views.platform.widgets.tile_preview_widget import (
            TilePreviewWidget,
        )
        self._tile_preview_widget = TilePreviewWidget()
        self._tile_preview_widget.tile_selected.connect(self._on_tile_selected)
        splitter.addWidget(self._tile_preview_widget)

        from anylabeling.views.platform.widgets.tile_inspector_panel import (
            TileInspectorPanel,
        )
        self._tile_inspector_panel = TileInspectorPanel()
        self._tile_inspector_panel.accept_tile.connect(self._on_accept_tile)
        self._tile_inspector_panel.flag_tile.connect(self._on_flag_tile)
        splitter.addWidget(self._tile_inspector_panel)

        splitter.setSizes([600, 300])
        layout.addWidget(splitter, stretch=1)

        # Info label when no large images
        self._preview_placeholder = QtWidgets.QLabel(
            tr(
                "没有检测到大图。预览标签需要>2000px的图片。",
                "No large images detected. Preview requires images >2000px.",
            )
        )
        self._preview_placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._preview_placeholder.setVisible(False)
        layout.addWidget(self._preview_placeholder)

        self._preview_tab.setLayout(layout)

    # ------------------------------------------------------------------
    # History Tab
    # ------------------------------------------------------------------

    def _setup_history_tab(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Build history table
        self._history_table = QtWidgets.QTableWidget()
        self._history_table.setColumnCount(6)
        self._history_table.setHorizontalHeaderLabels([
            tr("构建 ID", "Build ID"),
            tr("日期", "Date"),
            tr("资源数量", "Assets"),
            tr("切片数量", "Tiles"),
            tr("状态", "Status"),
            tr("操作", "Actions"),
        ])
        self._history_table.horizontalHeader().setStretchLastSection(True)
        self._history_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._history_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._history_table.setMinimumHeight(200)
        layout.addWidget(self._history_table, stretch=1)

        # Refresh button
        refresh_layout = QtWidgets.QHBoxLayout()
        refresh_layout.addStretch()
        refresh_btn = QtWidgets.QPushButton(tr("刷新", "Refresh"))
        refresh_btn.clicked.connect(self._refresh_history)
        refresh_layout.addWidget(refresh_btn)
        layout.addLayout(refresh_layout)

        self._history_tab.setLayout(layout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project_path(self, project_path: str) -> None:
        """Set the project root path for build history."""
        self._project_path = project_path
        self._refresh_history()

    def set_task_family(self, family: str) -> None:
        """Set the task family for label splitter selection."""
        self._task_family = family

    def set_total_assets(self, count: int):
        """Set the total number of assets (large + normal images).

        Controls the Build button enabled state independently of
        large-image detection.
        """
        self._total_assets = count
        self._build_btn.setEnabled(count > 0)
        if count > 0 and not self._large_images:
            self._large_image_label.setText(tr(
                "正常图片模式 (Normal image mode)",
                "Normal image mode"
            ))
            self._tile_preview_label.setVisible(False)

    def set_large_images(self, image_paths: list[str]):
        """Set the list of large images for preview and estimation."""
        self._large_images = image_paths
        count = len(image_paths)
        if count > 0:
            self._large_image_label.setText(tr(
                f"检测到 {count} 张大图 (>2000px)",
                f"Detected {count} large images (>2000px)"
            ))
            self._tile_preview_label.setVisible(True)
        elif self._total_assets > 0:
            self._large_image_label.setText(tr(
                "正常图片模式 (Normal image mode)",
                "Normal image mode"
            ))
            self._tile_preview_label.setVisible(False)
        else:
            self._large_image_label.setText(tr(
                "检测到 0 张大图 (>2000px)",
                "Detected 0 large images (>2000px)"
            ))
            self._tile_preview_label.setVisible(False)
        self._thumbnail_list.clear()
        for p in image_paths[:20]:  # Show up to 20 thumbnails
            import os
            self._thumbnail_list.addItem(os.path.basename(p))

        # Populate preview image combo
        self._preview_image_combo.clear()
        self._preview_image_combo.addItem(
            tr("-- 选择大图预览 --", "-- Select large image to preview --")
        )
        for p in image_paths:
            self._preview_image_combo.addItem(Path(p).name, p)

        # Enable preview tab if large images exist
        preview_enabled = count > 0
        self._tab_widget.setTabEnabled(1, preview_enabled)
        if not preview_enabled:
            self._preview_placeholder.setVisible(True)

        self._build_btn.setEnabled(self._total_assets > 0)
        if self._large_images:
            self._on_tile_params_changed()

    def _validate_current_split(self) -> list[str]:
        """Validate the current split ratio settings."""
        train = self._train_ratio_sb.value()
        val = self._val_ratio_sb.value()
        test = self._test_ratio_sb.value()
        return validate_split_ratios(train, val, test)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_current_config(self) -> PreprocessConfig:
        """Build a PreprocessConfig from current UI state."""
        augs: set[str] = set()
        if self._hflip_cb.isChecked():
            augs.add("hflip")
        if self._vflip_cb.isChecked():
            augs.add("vflip")
        if self._brightness_cb.isChecked():
            augs.add("brightness")
        if self._rotate_cb.isChecked():
            augs.add("rotate")

        return PreprocessConfig(
            tile_width=self._tile_width_sb.value(),
            tile_height=self._tile_height_sb.value(),
            overlap_x=self._overlap_x_sb.value(),
            overlap_y=self._overlap_y_sb.value(),
            edge_mode=self._edge_mode_combo.currentText(),
            split_strategy=self._split_strategy_combo.currentText(),
            train_ratio=self._train_ratio_sb.value(),
            val_ratio=self._val_ratio_sb.value(),
            test_ratio=self._test_ratio_sb.value(),
            random_seed=self._seed_sb.value(),
            augmentations=frozenset(augs),
        )

    def _get_current_tile_plan(self) -> TilePlan:
        """Build a TilePlan from the current tile config UI state."""
        return TilePlan(
            tile_width=self._tile_width_sb.value(),
            tile_height=self._tile_height_sb.value(),
            overlap_x=self._overlap_x_sb.value(),
            overlap_y=self._overlap_y_sb.value(),
            edge_mode=(
                self._edge_mode_combo.currentText()
                if self._edge_mode_combo.currentText() in ("crop", "pad")
                else "crop"
            ),
            padding_value=0,
            min_object_pixels=16,
            min_visibility_ratio=0.3,
        )

    def _on_tile_params_changed(self):
        """Update tile preview estimate when parameters change."""
        if not self._large_images:
            return
        config = self._get_current_config()
        total_tiles = 0
        # Use a default estimate of 3000x2000 per image if no actual images loaded
        default_w, default_h = 3000, 2000
        for _img in self._large_images or [None]:
            total_tiles += PreprocessConfig.estimate_tiles(config, default_w, default_h)

        per_image = total_tiles // max(1, len(self._large_images)) if self._large_images else total_tiles
        self._tile_preview_label.setText(tr(
            f"预计每张图: {per_image} 块切片, 总计约 {total_tiles} 块",
            f"Estimated per image: {per_image} tiles, total ~{total_tiles} tiles"
        ))

        # Debounce preview update
        if self._preview_image_path:
            self._preview_debounce_timer.start(_PREVIEW_DEBOUNCE_MS)

    def _on_split_params_changed(self):
        """Update split ratio preview."""
        total_items = len(self._large_images) if self._large_images else 10  # use default for preview
        config = self._get_current_config()

        from anylabeling.platform.domain.split_manifest import SplitManifest
        manifest = SplitManifest(
            strategy=config.split_strategy,
            train_ratio=config.train_ratio,
            val_ratio=config.val_ratio,
            test_ratio=config.test_ratio,
            random_seed=config.random_seed,
            asset_assignments={},
        )
        train, val, test = SplitManifest.compute_split_counts(manifest, total_items)

        # Validate
        issues = validate_split_ratios(config.train_ratio, config.val_ratio, config.test_ratio)
        if issues:
            self._split_preview_label.setText(f"⚠ {issues[0]}")
        else:
            self._split_preview_label.setText(tr(
                f"预览: 训练 {train} | 验证 {val} | 测试 {test}",
                f"Preview: Train {train} | Val {val} | Test {test}"
            ))

    def _on_build_clicked(self):
        """Emit build_requested with the current config."""
        config = self._get_current_config()
        self.build_requested.emit(config)

    # ------------------------------------------------------------------
    # Preview slot handlers
    # ------------------------------------------------------------------

    def _on_thumbnail_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        """Handle thumbnail click — switch to preview tab for this image."""
        name = item.text()
        for i in range(self._preview_image_combo.count()):
            if self._preview_image_combo.itemText(i) == name:
                self._preview_image_combo.setCurrentIndex(i)
                self._tab_widget.setCurrentIndex(1)
                break

    def _on_preview_image_changed(self, text: str) -> None:
        """Handle preview image selection — load and show tile grid."""
        idx = self._preview_image_combo.currentIndex()
        if idx <= 0:  # placeholder item
            self._preview_image_path = ""
            self._preview_placeholder.setVisible(True)
            self._tile_preview_widget.setVisible(False)
            return

        path = self._preview_image_combo.currentData()
        if not path or not Path(path).exists():
            return

        self._preview_image_path = path
        self._preview_placeholder.setVisible(False)
        self._tile_preview_widget.setVisible(True)
        self._update_preview()

    def _update_preview(self) -> None:
        """Compute and render the tile preview for the current image."""
        if not self._preview_image_path:
            return

        self._tile_preview_widget.set_source_image(self._preview_image_path)

        # Get image dimensions
        from anylabeling.platform.infrastructure.image_reader import ImageReader
        meta = ImageReader.metadata(self._preview_image_path)
        if meta.width == 0:
            return
        h, w = meta.height, meta.width

        # Create a synthetic Asset for TilePlanner
        from anylabeling.platform.domain.asset import Asset
        asset = Asset(
            id=Path(self._preview_image_path).stem,
            path=self._preview_image_path,
            width=w,
            height=h,
        )

        plan = self._get_current_tile_plan()

        # Plan tiles
        try:
            tiles = TilePlanner.plan(asset, plan)
        except ValueError as exc:
            logger.warning("TilePlanner failed: %s", exc)
            return

        self._preview_tiles = tiles
        self._preview_tile_info.setText(
            tr(
                f"{len(tiles)} 块切片",
                f"{len(tiles)} tiles",
            )
        )

        # Try to load annotations for label counts
        label_counts: dict[str, int] = {}
        truncated_counts: dict[str, int] = {}
        if self._project_path:
            ann_dir = Path(self._project_path) / "annotations"
            ann_path = ann_dir / f"{asset.id}.json"
            if ann_path.exists():
                try:
                    ann_data = json.loads(
                        ann_path.read_text(encoding="utf-8")
                    )
                    objects = self._parse_annotation_objects(ann_data, w, h)
                    # For each tile, check how many objects intersect it
                    for tile in tiles:
                        tile_box = (
                            tile.x0, tile.y0,
                            tile.x0 + tile.valid_width,
                            tile.y0 + tile.valid_height,
                        )
                        label_count = 0
                        trun_count = 0
                        for obj in objects:
                            vis = self._compute_visibility(obj, tile_box)
                            if vis is not None:
                                label_count += 1
                                if vis < 0.8:
                                    trun_count += 1
                        label_counts[tile.tile_id] = label_count
                        truncated_counts[tile.tile_id] = trun_count
                except Exception:
                    logger.exception("Failed to parse annotations for preview")

        self._tile_preview_widget.set_tile_plan(plan)
        self._tile_preview_widget.set_tile_data(
            tiles, label_counts, truncated_counts
        )

    def _on_tile_selected(self, tile_id: str) -> None:
        """Handle tile click — show tile details in inspector."""
        # Find the tile record
        tile = None
        for t in self._preview_tiles:
            if t.tile_id == tile_id:
                tile = t
                break

        if tile is None:
            return

        # Load annotations for this image
        objects: list = []
        if self._project_path and self._preview_image_path:
            asset_id = Path(self._preview_image_path).stem
            ann_path = (
                Path(self._project_path) / "annotations" / f"{asset_id}.json"
            )
            if ann_path.exists():
                try:
                    from anylabeling.platform.infrastructure.image_reader import ImageReader
                    meta = ImageReader.metadata(self._preview_image_path)
                    h, w = (meta.height, meta.width) if meta.width > 0 else (0, 0)
                    ann_data = json.loads(
                        ann_path.read_text(encoding="utf-8")
                    )
                    objects = self._parse_annotation_objects(ann_data, w, h)
                except Exception:
                    logger.exception("Failed to load annotations for tile")

        img = None
        from anylabeling.platform.infrastructure.image_reader import ImageReader
        try:
            img = ImageReader.read(self._preview_image_path, output_color="BGR")
        except Exception:
            pass
        source_size = (
            (img.shape[1], img.shape[0]) if img is not None else (0, 0)
        )

        plan = self._get_current_tile_plan()
        self._tile_inspector_panel.set_tile(
            tile,
            objects,
            source_size,
            tile_plan=plan,
            task_family=self._task_family,
        )

        # Highlight tile in preview widget
        self._tile_preview_widget.highlight_tile(tile_id)

    @staticmethod
    def _parse_annotation_objects(
        ann_data: dict, img_w: int, img_h: int
    ) -> list:
        """Parse annotation JSON into AnnotationObject list (basic)."""
        from anylabeling.platform.domain.annotation import AnnotationObject

        objects: list = []
        for i, shape in enumerate(ann_data.get("shapes", [])):
            shape_type = shape.get("shape_type", "rectangle")
            geometry_type = "bbox_xyxy"
            geometry: object = shape.get("points", [])

            if shape_type == "rectangle":
                pts = shape.get("points", [])
                if len(pts) == 2:
                    x1 = min(pts[0][0], pts[1][0])
                    y1 = min(pts[0][1], pts[1][1])
                    x2 = max(pts[0][0], pts[1][0])
                    y2 = max(pts[0][1], pts[1][1])
                    geometry = (x1, y1, x2, y2)
                geometry_type = "bbox_xyxy"
            elif shape_type == "polygon":
                geometry = shape.get("points", [])
                geometry_type = "polygon"

            # Resolve label_id from label name
            label_name = shape.get("label", "")
            label_id = hash(label_name) % 80  # approximate

            objects.append(
                AnnotationObject(
                    id=shape.get("id", f"obj_{i}"),
                    label_id=label_id,
                    geometry_type=geometry_type,
                    geometry=geometry,
                    source_object_id=shape.get("id", f"obj_{i}"),
                )
            )
        return objects

    @staticmethod
    def _compute_visibility(
        obj, tile_box: tuple[int, int, int, int]
    ) -> float | None:
        """Compute visibility ratio of an object within a tile bbox."""
        tx1, ty1, tx2, ty2 = tile_box

        if obj.geometry_type == "bbox_xyxy":
            x1, y1, x2, y2 = obj.geometry
            ix1 = max(x1, tx1)
            iy1 = max(y1, ty1)
            ix2 = min(x2, tx2)
            iy2 = min(y2, ty2)
            if ix1 >= ix2 or iy1 >= iy2:
                return None
            inter = (ix2 - ix1) * (iy2 - iy1)
            orig = (x2 - x1) * (y2 - y1)
            return inter / orig if orig > 0 else 0.0
        elif obj.geometry_type in ("polygon", "obb_polygon"):
            points = obj.geometry
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            ix1 = max(x1, tx1)
            iy1 = max(y1, ty1)
            ix2 = min(x2, tx2)
            iy2 = min(y2, ty2)
            if ix1 >= ix2 or iy1 >= iy2:
                return None
            inter = (ix2 - ix1) * (iy2 - iy1)
            orig = (x2 - x1) * (y2 - y1)
            return inter / orig if orig > 0 else 0.0
        return None

    def _on_accept_tile(self, tile_id: str) -> None:
        """Handle tile accept action."""
        logger.info("Tile accepted: %s", tile_id)

    def _on_flag_tile(self, tile_id: str, reason: str) -> None:
        """Handle tile flag action."""
        logger.info("Tile flagged: %s — %s", tile_id, reason)

    # ------------------------------------------------------------------
    # History tab
    # ------------------------------------------------------------------

    def _refresh_history(self) -> None:
        """Scan dataset_builds/ directory and populate the history table."""
        self._history_table.setRowCount(0)

        if not self._project_path:
            return

        builds_dir = Path(self._project_path) / "dataset_builds"
        if not builds_dir.is_dir():
            return

        builds: list[dict] = []
        for build_dir in sorted(builds_dir.iterdir(), reverse=True):
            if not build_dir.is_dir():
                continue
            build_json = build_dir / "build.json"
            if not build_json.exists():
                continue
            try:
                data = json.loads(build_json.read_text(encoding="utf-8"))
                ready = (build_dir / "_READY").exists()
                builds.append({
                    "id": data.get("id", build_dir.name),
                    "created_at": data.get("created_at", ""),
                    "status": "ready" if ready else "failed",
                    "dir": str(build_dir),
                })
            except Exception:
                logger.exception(
                    "Failed to read build.json from %s", build_dir
                )

        self._history_table.setRowCount(len(builds))
        for row, build in enumerate(builds):
            # Build ID
            id_item = QtWidgets.QTableWidgetItem(build["id"])
            self._history_table.setItem(row, 0, id_item)

            # Date
            created = build["created_at"]
            if created:
                try:
                    from datetime import datetime as dt
                    dt_parsed = dt.fromisoformat(created)
                    created = dt_parsed.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass
            date_item = QtWidgets.QTableWidgetItem(created)
            self._history_table.setItem(row, 1, date_item)

            # Asset count — read from split manifest
            asset_count = self._count_assets_in_build(build["dir"])
            count_item = QtWidgets.QTableWidgetItem(str(asset_count))
            self._history_table.setItem(row, 2, count_item)

            # Tile count — read from tile manifest
            tile_count = self._count_tiles_in_build(build["dir"])
            tile_item = QtWidgets.QTableWidgetItem(str(tile_count))
            self._history_table.setItem(row, 3, tile_item)

            # Status
            status_text = tr("就绪", "Ready") if build["status"] == "ready" else tr("失败", "Failed")
            status_item = QtWidgets.QTableWidgetItem(status_text)
            if build["status"] == "ready":
                status_item.setForeground(
                    QtCore.Qt.GlobalColor.darkGreen
                )
            else:
                status_item.setForeground(
                    QtCore.Qt.GlobalColor.darkRed
                )
            self._history_table.setItem(row, 4, status_item)

            # Actions — buttons
            actions_widget = QtWidgets.QWidget()
            actions_layout = QtWidgets.QHBoxLayout()
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(4)

            use_btn = QtWidgets.QPushButton(tr("使用配置", "Use Config"))
            use_btn.clicked.connect(
                lambda checked, d=build["dir"]: self._use_build_config(d)
            )
            actions_layout.addWidget(use_btn)

            open_btn = QtWidgets.QPushButton(tr("打开目录", "Open Dir"))
            open_btn.clicked.connect(
                lambda checked, d=build["dir"]: self._open_build_dir(d)
            )
            actions_layout.addWidget(open_btn)

            actions_layout.addStretch()
            actions_widget.setLayout(actions_layout)
            self._history_table.setCellWidget(row, 5, actions_widget)

        self._history_table.resizeColumnsToContents()

    @staticmethod
    def _count_assets_in_build(build_dir: str) -> int:
        """Count assets from the split manifest."""
        manifest = Path(build_dir) / "split_manifest.jsonl"
        if not manifest.exists():
            return 0
        try:
            count = 0
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    count += 1
            return count
        except (OSError, json.JSONDecodeError):
            return 0

    @staticmethod
    def _count_tiles_in_build(build_dir: str) -> int:
        """Count tiles from the tile manifest."""
        manifest = Path(build_dir) / "tile_manifest.jsonl"
        if not manifest.exists():
            return 0
        try:
            count = 0
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    count += 1
            return count
        except (OSError, json.JSONDecodeError):
            return 0

    def _use_build_config(self, build_dir: str) -> None:
        """Read build.json and populate current tile/split settings."""
        build_json = Path(build_dir) / "build.json"
        if not build_json.exists():
            return
        try:
            data = json.loads(build_json.read_text(encoding="utf-8"))
            tp = data.get("tile_plan")
            if tp:
                self._tile_width_sb.setValue(tp.get("tile_width", 1024))
                self._tile_height_sb.setValue(tp.get("tile_height", 1024))
                self._overlap_x_sb.setValue(tp.get("overlap_x", 256))
                self._overlap_y_sb.setValue(tp.get("overlap_y", 256))
                edge_mode = tp.get("edge_mode", "crop")
                idx = self._edge_mode_combo.findText(edge_mode)
                if idx >= 0:
                    self._edge_mode_combo.setCurrentIndex(idx)

            strategy = data.get("split_strategy", "random_by_asset")
            idx = self._split_strategy_combo.findText(strategy)
            if idx >= 0:
                self._split_strategy_combo.setCurrentIndex(idx)

            self._seed_sb.setValue(data.get("split_seed", 42))
        except Exception:
            logger.exception("Failed to use build config from %s", build_dir)

    def _open_build_dir(self, build_dir: str) -> None:
        """Open the build directory in the system file manager."""
        path = Path(build_dir)
        if path.exists():
            QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(str(path))
            )

    # ------------------------------------------------------------------
    # Properties for testing
    # ------------------------------------------------------------------

    @property
    def tile_width(self) -> int:
        return self._tile_width_sb.value()

    @property
    def tile_height(self) -> int:
        return self._tile_height_sb.value()

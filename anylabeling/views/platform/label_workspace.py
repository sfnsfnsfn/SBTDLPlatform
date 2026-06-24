"""LabelWorkspace — platform-native labeling page with task-aware tool filtering."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from anylabeling.platform.application.asset_repository import AssetRepository
from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    get_list_widget_style,
)
from anylabeling.views.platform.widgets.asset_list_model import AssetListModel
from anylabeling.views.platform.widgets.asset_filter_bar import (
    AssetFilterBar,
    AssetFilterProxyModel,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)

# LabelingWidget action name → Canvas shape_type
_ACTION_SHAPE_TYPE_MAP: dict[str, str] = {
    "create_mode":            "polygon",
    "create_rectangle_mode":  "rectangle",
    "create_rotation_mode":   "rotation",
    "create_point_mode":      "point",
    "create_line_mode":       "line",
    "create_line_strip_mode": "linestrip",
    "create_circle_mode":     "circle",
    "create_cuboid_mode":     "cuboid",
    "create_quadrilateral_mode": "quadrilateral",
}

# Status → QStyle standard pixmap for icons (UI Finding #7 fix)
_STATUS_ICON_MAP = {
    "unannotated": QtWidgets.QStyle.StandardPixmap.SP_MessageBoxQuestion,
    "partial":     QtWidgets.QStyle.StandardPixmap.SP_ArrowForward,
    "complete":    QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton,
}


class AssetListItem(QtWidgets.QListWidgetItem):
    """List item representing an image asset with annotation status."""

    STATUS_UNANNOTATED = "unannotated"
    STATUS_PARTIAL = "partial"
    STATUS_COMPLETE = "complete"

    def __init__(self, asset_path: str, status: str = STATUS_UNANNOTATED):
        super().__init__()
        self.asset_path = asset_path
        self.annotation_status = status
        self._refresh_display()

    def _refresh_display(self):
        icon_pixmap = _STATUS_ICON_MAP.get(self.annotation_status)
        if icon_pixmap is not None:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                self.setIcon(app.style().standardIcon(icon_pixmap))
        self.setText(Path(self.asset_path).name)
        self.setData(QtCore.Qt.ItemDataRole.UserRole, self.asset_path)

    def set_status(self, status: str):
        self.annotation_status = status
        self._refresh_display()


class LabelWorkspace(QtWidgets.QWidget):
    """Platform-native labeling workspace.

    Embeds the existing LabelingWidget + Canvas unchanged, adding:
    - Asset list with annotation status
    - Task-aware tool filtering (hides incompatible shape tools)
    - Auto-save to project/annotations/
    - Inspector panel for shape attributes
    - AI toolbar for auto-labeling / batch labeling

    LabelingWidget is created once in set_project_context() and reused
    across asset switches — preserving zoom, pan, tool, and undo state.
    """

    asset_changed = QtCore.pyqtSignal(str)
    ai_predict_requested = QtCore.pyqtSignal()
    ai_batch_requested = QtCore.pyqtSignal()
    nav_fold_requested = QtCore.pyqtSignal(bool)  # True = fold

    def showEvent(self, event):
        """Emit nav fold when label workspace becomes visible."""
        super().showEvent(event)
        self.nav_fold_requested.emit(True)

    def hideEvent(self, event):
        """Emit nav unfold when label workspace is hidden."""
        super().hideEvent(event)
        self.nav_fold_requested.emit(False)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_path: str | None = None
        self._task_spec = None
        self._labeling_widget = None
        self._current_asset: str | None = None
        self._label_name_to_id: dict[str, int] = {}
        self._asset_repository: AssetRepository | None = None
        self._asset_model: AssetListModel | None = None
        self._asset_proxy: AssetFilterProxyModel | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        t = get_theme()

        # -- Left: Asset List --
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        header = QtWidgets.QLabel(tr("📁 资产列表", "📁 Assets"))
        header.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_BODY}px;"
            f"font-weight: bold; padding: 6px 8px; color: {t['text']};"
        )
        left_layout.addWidget(header)

        # -- AI Toolbar --
        ai_toolbar = QtWidgets.QWidget()
        ai_layout = QtWidgets.QHBoxLayout()
        ai_layout.setContentsMargins(4, 2, 4, 2)
        ai_layout.setSpacing(4)

        self._model_combo = QtWidgets.QComboBox()
        self._model_combo.setMinimumWidth(100)
        self._model_combo.setToolTip(tr("选择模型", "Select model"))
        self._model_combo.setEnabled(False)

        self._ai_predict_btn = QtWidgets.QPushButton(tr("AI 预标注", "AI Predict"))
        self._ai_predict_btn.setEnabled(False)
        self._ai_predict_btn.setToolTip(tr("对当前选中图片运行推理", "Run inference on selected image"))
        self._ai_predict_btn.clicked.connect(self.ai_predict_requested.emit)

        self._ai_batch_btn = QtWidgets.QPushButton(tr("批量标注", "Batch Label"))
        self._ai_batch_btn.setEnabled(False)
        self._ai_batch_btn.setToolTip(tr("对全部未标注图片运行推理", "Run inference on all unannotated images"))
        self._ai_batch_btn.clicked.connect(self.ai_batch_requested.emit)

        ai_layout.addWidget(self._model_combo)
        ai_layout.addWidget(self._ai_predict_btn)
        ai_layout.addWidget(self._ai_batch_btn)
        ai_toolbar.setLayout(ai_layout)
        left_layout.addWidget(ai_toolbar)

        # -- Filter bar (Phase 3a: shown when AssetRepository available) --
        self._filter_bar_container = QtWidgets.QWidget()
        filter_bar_layout = QtWidgets.QVBoxLayout()
        filter_bar_layout.setContentsMargins(0, 0, 0, 0)
        filter_bar_layout.setSpacing(0)

        self._search_bar = QtWidgets.QLineEdit()
        self._search_bar.setPlaceholderText(tr("搜索...", "Search..."))
        filter_bar_layout.addWidget(self._search_bar)

        # FilterBar placeholder — created when AssetRepository is available
        self._filter_bar: AssetFilterBar | None = None
        self._filter_bar_container.setLayout(filter_bar_layout)
        self._filter_bar_container.setVisible(False)
        left_layout.addWidget(self._filter_bar_container)

        # -- Asset list view (Phase 3a: QListView with virtual model) --
        self._asset_list_view = QtWidgets.QListView()
        self._asset_list_view.setStyleSheet(get_list_widget_style())
        self._asset_list_view.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        left_layout.addWidget(self._asset_list_view)

        # Legacy QListWidget (hidden when AssetRepository available)
        self._asset_list = QtWidgets.QListWidget()
        self._asset_list.setStyleSheet(get_list_widget_style())
        self._asset_list.setVisible(False)
        left_layout.addWidget(self._asset_list)

        self._progress_label = QtWidgets.QLabel()
        self._progress_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_CAPTION}px;"
            f"color: {t['text_secondary']}; padding: 4px 8px;"
        )
        left_layout.addWidget(self._progress_label)

        left.setLayout(left_layout)
        splitter.addWidget(left)

        # -- Center: Canvas container --
        self._canvas_container = QtWidgets.QWidget()
        self._canvas_layout = QtWidgets.QVBoxLayout()
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)
        placeholder = QtWidgets.QLabel(tr(
            "选择一个资产开始标注", "Select an asset to start labeling"
        ))
        placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._canvas_layout.addWidget(placeholder)
        self._canvas_container.setLayout(self._canvas_layout)
        splitter.addWidget(self._canvas_container)

        # -- Right: Inspector + Suggestion Actions --
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self._inspector = QtWidgets.QTextEdit()
        self._inspector.setReadOnly(True)
        self._inspector.setMaximumWidth(240)
        self._inspector.setMinimumWidth(140)
        self._inspector.setPlaceholderText(tr(
            "检查器\n\n选择画布上的形状\n以查看其属性",
            "Inspector\n\nSelect a shape on the\ncanvas to inspect its\nproperties."
        ))
        self._inspector.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {t['border']};
                background-color: {t['surface']};
                font-size: {FONT_SIZE_BODY}px;
                color: {t['text']};
                font-family: {FONT_FAMILY};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        right_layout.addWidget(self._inspector)

        # Phase 3b: Suggestion action buttons
        self._suggestion_panel = QtWidgets.QWidget()
        sug_layout = QtWidgets.QVBoxLayout()
        sug_layout.setContentsMargins(0, 4, 0, 0)
        sug_layout.setSpacing(2)

        self._suggestion_info_label = QtWidgets.QLabel("")
        self._suggestion_info_label.setStyleSheet(
            f"font-size: {FONT_SIZE_CAPTION}px; padding: 2px 4px;"
        )
        self._suggestion_info_label.setWordWrap(True)
        sug_layout.addWidget(self._suggestion_info_label)

        sug_btn_row = QtWidgets.QHBoxLayout()
        self._accept_btn = QtWidgets.QPushButton(tr("接受", "Accept"))
        self._reject_btn = QtWidgets.QPushButton(tr("拒绝", "Reject"))
        self._accept_btn.clicked.connect(self._on_accept_suggestion)
        self._reject_btn.clicked.connect(self._on_reject_suggestion)
        self._accept_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)
        sug_btn_row.addWidget(self._accept_btn)
        sug_btn_row.addWidget(self._reject_btn)
        sug_layout.addLayout(sug_btn_row)

        batch_btn_row = QtWidgets.QHBoxLayout()
        self._accept_all_btn = QtWidgets.QPushButton(
            tr("接受全部", "Accept All")
        )
        self._reject_all_btn = QtWidgets.QPushButton(
            tr("拒绝全部", "Reject All")
        )
        self._accept_all_btn.clicked.connect(self._on_accept_all_suggestions)
        self._reject_all_btn.clicked.connect(self._on_reject_all_suggestions)
        self._accept_all_btn.setEnabled(False)
        self._reject_all_btn.setEnabled(False)
        batch_btn_row.addWidget(self._accept_all_btn)
        batch_btn_row.addWidget(self._reject_all_btn)
        sug_layout.addLayout(batch_btn_row)

        self._suggestion_panel.setLayout(sug_layout)
        self._suggestion_panel.setVisible(False)
        right_layout.addWidget(self._suggestion_panel)
        right_layout.addStretch()

        right_panel.setLayout(right_layout)
        splitter.addWidget(right_panel)

        splitter.setSizes([200, 700, 220])
        splitter.setCollapsible(0, True)   # left panel collapsible
        splitter.setCollapsible(2, True)   # right panel collapsible
        self._splitter = splitter
        self._left_panel = left
        self._right_panel = right_panel

        # -- Toggle bar (compact button row to show/hide panels) --
        toggle_bar = QtWidgets.QHBoxLayout()
        toggle_bar.setContentsMargins(4, 2, 4, 2)
        toggle_bar.setSpacing(4)

        self._toggle_left_btn = QtWidgets.QPushButton(tr("◀ 隐藏列表", "◀ Hide List"))
        self._toggle_left_btn.setCheckable(True)
        self._toggle_left_btn.setChecked(True)
        self._toggle_left_btn.setFixedHeight(22)
        self._toggle_left_btn.clicked.connect(self._on_toggle_left)
        toggle_bar.addWidget(self._toggle_left_btn)

        toggle_bar.addStretch()

        self._toggle_right_btn = QtWidgets.QPushButton(tr("隐藏检查器 ▶", "Hide Inspector ▶"))
        self._toggle_right_btn.setCheckable(True)
        self._toggle_right_btn.setChecked(True)
        self._toggle_right_btn.setFixedHeight(22)
        self._toggle_right_btn.clicked.connect(self._on_toggle_right)
        toggle_bar.addWidget(self._toggle_right_btn)

        main = QtWidgets.QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addLayout(toggle_bar)
        main.addWidget(splitter)
        self.setLayout(main)

    def _on_toggle_left(self, checked: bool) -> None:
        self._left_panel.setVisible(checked)
        self._toggle_left_btn.setText(
            tr("◀ 隐藏列表", "◀ Hide List") if checked
            else tr("显示列表 ▶", "Show List ▶")
        )

    def _on_toggle_right(self, checked: bool) -> None:
        self._right_panel.setVisible(checked)
        self._toggle_right_btn.setText(
            tr("隐藏检查器 ▶", "Hide Inspector ▶") if checked
            else tr("◀ 显示检查器", "◀ Show Inspector")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project_context(
        self, project_path: str, task_spec,
        asset_repository: AssetRepository | None = None,
    ) -> None:
        """Initialize with project and task spec. Called by WorkbenchWindow.

        Creates the LabelingWidget once and reuses it for all assets.
        Phase 3a: Wires QListView + AssetListModel + AssetFilterBar when
        AssetRepository is available; falls back to QListWidget otherwise.
        """
        self._project_path = project_path
        self._task_spec = task_spec
        self._asset_repository = asset_repository  # Phase 3a
        self._label_name_to_id = {
            lb.name: lb.id for lb in task_spec.labels
        }

        # Phase 3a: Wire model/view if AssetRepository available
        if self._asset_repository is not None:
            self._wire_model_view()

        # Create LabelingWidget once — it persists across asset switches
        self._create_labeling_widget_once()

        # Phase 3b: check for crash recovery files before loading assets
        self._check_and_prompt_recovery()

        self._scan_assets()
        self._apply_task_tool_filter()

    def _wire_model_view(self) -> None:
        """Wire QListView with AssetListModel + AssetFilterProxyModel + AssetFilterBar.

        Hides legacy QListWidget + search bar; shows QListView + filter bar.
        """
        repo = self._asset_repository
        if repo is None:
            return

        # Create model and proxy
        self._asset_model = AssetListModel(repo, parent=self)
        self._asset_proxy = AssetFilterProxyModel(self)
        self._asset_proxy.set_repository(repo)
        self._asset_proxy.setSourceModel(self._asset_model)
        self._asset_list_view.setModel(self._asset_proxy)

        # Wire selection
        self._asset_list_view.selectionModel().currentChanged.connect(
            self._on_model_selection_changed
        )

        # Replace search bar with full filter bar
        if self._filter_bar is None:
            self._filter_bar = AssetFilterBar(repo, parent=self)
            self._filter_bar.filter_changed.connect(self._on_filter_changed)
            self._filter_bar_container.layout().addWidget(self._filter_bar)

        # Connect search input to proxy
        self._search_bar.textChanged.connect(self._proxy_set_search)

        # Show/hide widgets
        self._asset_list.setVisible(False)
        self._asset_list_view.setVisible(True)
        self._filter_bar_container.setVisible(True)

    # ------------------------------------------------------------------
    # AI Toolbar
    # ------------------------------------------------------------------

    def _update_ai_toolbar_state(self, runs: list[dict] | None = None, has_assets: bool = False):
        """Update AI toolbar enable/disable state based on available runs and assets.

        Called by the workbench after scanning for runs and assets.
        """
        # Populate model combo
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        if runs:
            for run_info in runs:
                run_id = run_info.get("id", "")
                display = run_info.get("display_name", run_id)
                self._model_combo.addItem(display, run_id)
        self._model_combo.blockSignals(False)

        has_runs = bool(runs) and self._model_combo.count() > 0
        self._model_combo.setEnabled(has_runs)

        # Enable buttons only when both runs and assets are available
        can_label = has_runs and has_assets
        self._ai_predict_btn.setEnabled(can_label)
        self._ai_batch_btn.setEnabled(can_label)

    # ------------------------------------------------------------------
    # Asset management
    # ------------------------------------------------------------------

    def _scan_assets(self):
        # Phase 3a: Model/View path when AssetRepository is available
        if self._asset_repository is not None and self._asset_model is not None:
            self._asset_list_view.setVisible(True)
            self._asset_list.setVisible(False)
            self._asset_model.refresh()
            stats = self._asset_repository.get_stats()
            annotated = stats.get("annotated", 0)
            total = stats.get("total", 0)
            self._update_progress(annotated, total)
            self._update_ai_toolbar_state(has_assets=(total > 0))
            return

        # Legacy fallback — direct filesystem scan with QListWidget
        self._asset_list_view.setVisible(False)
        self._asset_list.setVisible(True)
        self._asset_list.blockSignals(True)
        self._asset_list.clear()

        # Phase 3a: Use AssetRepository even without full model/view
        if self._asset_repository is not None:
            paths = self._asset_repository.scan_assets()
            statuses = self._asset_repository.get_annotation_statuses()
            annotated = sum(
                1 for s in statuses.values()
                if s == "complete"
            )

            status_map = {
                "complete": AssetListItem.STATUS_COMPLETE,
                "partial": AssetListItem.STATUS_PARTIAL,
            }
            for p in paths:
                stem = Path(p).stem
                raw = statuses.get(stem, "unannotated")
                status = status_map.get(raw, AssetListItem.STATUS_UNANNOTATED)
                self._asset_list.addItem(AssetListItem(p, status))

            total = len(paths)
        else:
            # Legacy fallback — direct filesystem scan
            assets_dir = (
                Path(self._project_path) / "assets"
                if self._project_path else None
            )
            if not assets_dir or not assets_dir.is_dir():
                self._asset_list.blockSignals(False)
                self._filter_bar_container.setVisible(False)
                self._update_ai_toolbar_state(has_assets=False)
                return

            from anylabeling.platform.domain.import_config import get_supported_extensions
            exts = set(get_supported_extensions())
            annotated = 0
            total = 0

            for p in sorted(assets_dir.iterdir()):
                if not p.is_file() or p.suffix.lower() not in exts:
                    continue
                total += 1

                ann_path = (
                    Path(self._project_path) / "annotations"
                    / f"{p.stem}.json"
                )
                status = AssetListItem.STATUS_UNANNOTATED
                if ann_path.exists():
                    try:
                        ann_data = json.loads(
                            ann_path.read_text(encoding="utf-8")
                        )
                        if ann_data.get("shapes"):
                            status = AssetListItem.STATUS_COMPLETE
                            annotated += 1
                    except (json.JSONDecodeError, OSError):
                        pass

                self._asset_list.addItem(AssetListItem(str(p), status))

        self._asset_list.blockSignals(False)
        # Wire QListWidget selection for legacy path
        try:
            self._asset_list.currentItemChanged.disconnect()
        except TypeError:
            pass
        self._asset_list.currentItemChanged.connect(self._on_asset_selected)
        self._update_progress(annotated, total)
        self._update_ai_toolbar_state(has_assets=(total > 0))

    # ------------------------------------------------------------------
    # Model/View handlers (Phase 3a)
    # ------------------------------------------------------------------

    def _on_model_selection_changed(
        self, current: QtCore.QModelIndex, _previous: QtCore.QModelIndex
    ) -> None:
        """Handle selection change from QListView (model/view path)."""
        if not current.isValid():
            return
        asset_path = self._asset_proxy.data(
            current, QtCore.Qt.ItemDataRole.ToolTipRole
        )
        if not asset_path or not Path(asset_path).is_file():
            return
        self._current_asset = asset_path
        if self._labeling_widget is not None:
            self._labeling_widget.load_file(asset_path)
            self._load_existing_annotations(asset_path)
            self.asset_changed.emit(asset_path)

    def _on_filter_changed(self) -> None:
        """Apply filter bar changes to the proxy model."""
        if self._filter_bar is None or self._asset_proxy is None:
            return
        self._asset_proxy.set_status_filter(self._filter_bar.status_filter)
        self._asset_proxy.set_group_filter(self._filter_bar.group_filter)
        self._asset_proxy.set_search_text(self._filter_bar.search_text)
        self._asset_proxy.set_sort_option(self._filter_bar.sort_option)

    def _proxy_set_search(self, text: str) -> None:
        """Set search text on proxy model."""
        if self._asset_proxy is not None:
            self._asset_proxy.set_search_text(text)

    def _on_search(self, text: str):
        """Legacy search — filter QListWidget items by setHidden."""
        for i in range(self._asset_list.count()):
            item = self._asset_list.item(i)
            if isinstance(item, AssetListItem):
                name = Path(item.asset_path).name.lower()
                item.setHidden(text.lower() not in name)

    def _update_progress(self, annotated: int, total: int):
        pct = (annotated / total * 100) if total > 0 else 0
        self._progress_label.setText(tr(
            f"总计: {total} | 已标注: {annotated} | 进度: {pct:.0f}%",
            f"Total: {total} | Annotated: {annotated} | Progress: {pct:.0f}%"
        ))

    # ------------------------------------------------------------------
    # Asset selection & annotation loading
    # ------------------------------------------------------------------

    def _on_asset_selected(self, current: AssetListItem, _previous):
        if current is None:
            return

        asset_path = getattr(current, "asset_path", None)
        if not asset_path or not Path(asset_path).is_file():
            return

        self._current_asset = asset_path

        # Reuse existing LabelingWidget — just load the new file
        if self._labeling_widget is not None:
            self._labeling_widget.load_file(asset_path)
            self._load_existing_annotations(asset_path)
            self.asset_changed.emit(asset_path)

    def _load_existing_annotations(self, asset_path: str):
        from anylabeling.platform.application.annotation_adapter import (
            load_annotations_for_asset,
        )
        from anylabeling.views.labeling.shape import Shape

        shape_dicts = load_annotations_for_asset(asset_path, self._project_path)
        if shape_dicts is None:
            canvas = self._labeling_widget.canvas
            canvas.shapes = []
            canvas.update()
            return

        shapes = []
        for sd in shape_dicts:
            shape = Shape(
                label=sd["label"],
                shape_type=sd["shape_type"],
                group_id=sd.get("group_id"),
                description=sd.get("description", ""),
                difficult=sd.get("difficult", False),
            )
            for px, py in sd["points"]:
                shape.add_point(QtCore.QPointF(px, py))
            shape.close()
            shapes.append(shape)

        canvas = self._labeling_widget.canvas
        canvas.shapes = shapes
        canvas.update()

    # ------------------------------------------------------------------
    # Annotation save
    # ------------------------------------------------------------------

    def _on_annotation_changed(self):
        if not self._current_asset or not self._project_path:
            return

        from anylabeling.platform.application.annotation_adapter import (
            save_annotations_for_asset,
        )

        canvas = self._labeling_widget.canvas
        save_annotations_for_asset(
            self._current_asset, canvas.shapes,
            self._project_path, self._label_name_to_id,
        )

        self._update_asset_status(self._current_asset, canvas.shapes)

    def _update_asset_status(self, asset_path: str, shapes: list):
        # Model/View path: invalidate cache to refresh status display
        if self._asset_repository is not None:
            self._asset_repository.invalidate_cache()
            # Refresh filter bar dropdowns
            if self._filter_bar is not None:
                self._filter_bar.refresh_groups()
            self._recount_progress()
            return

        # Legacy QListWidget path
        for i in range(self._asset_list.count()):
            item = self._asset_list.item(i)
            if isinstance(item, AssetListItem) and item.asset_path == asset_path:
                status = (
                    AssetListItem.STATUS_COMPLETE if shapes
                    else AssetListItem.STATUS_UNANNOTATED
                )
                item.set_status(status)
                break
        self._recount_progress()

    def _recount_progress(self):
        # Model/View path: use repository stats
        if self._asset_repository is not None:
            stats = self._asset_repository.get_stats()
            self._update_progress(
                stats.get("annotated", 0), stats.get("total", 0)
            )
            return

        # Legacy QListWidget path
        total = self._asset_list.count()
        annotated = sum(
            1 for i in range(total)
            if isinstance(self._asset_list.item(i), AssetListItem)
            and self._asset_list.item(i).annotation_status == AssetListItem.STATUS_COMPLETE
        )
        self._update_progress(annotated, total)

    # ------------------------------------------------------------------
    # LabelingWidget creation (once, reused across assets)
    # ------------------------------------------------------------------

    def _create_labeling_widget_once(self):
        """Create the LabelingWidget exactly once — NEVER destroy on asset switch.

        Previously each asset-switch called _create_labeling_widget() which
        destroyed the old widget (deleteLater) and lost zoom/pan/tool/undo state.
        Now the widget persists and only load_file() is called to change images.
        """
        from anylabeling.views.labeling.label_widget import LabelingWidget

        # Remove placeholder label if present
        while self._canvas_layout.count():
            item = self._canvas_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        labeling = LabelingWidget(parent=self, config=None, filename=None)
        labeling.set_project_context({
            "project_path": self._project_path,
            "assets_dir": str(Path(self._project_path) / "assets") if self._project_path else "",
            "annotations_dir": str(Path(self._project_path) / "annotations") if self._project_path else "",
            "label_name_to_id": self._label_name_to_id,
        })

        labeling.canvas.shape_moved.connect(self._on_annotation_changed)
        labeling.canvas.new_shape.connect(self._on_annotation_changed)
        labeling.canvas.selection_changed.connect(self._on_inspector_update)

        # Phase 3b: enable debounced auto-save and wire status signal
        labeling.enable_auto_save()
        labeling.auto_save_completed.connect(self._on_auto_save_completed)

        # Phase 3b: wire AI suggestion signals
        labeling.suggestion_accepted.connect(
            lambda _: self._update_suggestion_buttons()
        )
        labeling.suggestion_rejected.connect(
            lambda _: self._update_suggestion_buttons()
        )

        self._canvas_layout.addWidget(labeling)
        self._labeling_widget = labeling

    # ------------------------------------------------------------------
    # Task-aware tool filtering
    # ------------------------------------------------------------------

    def _apply_task_tool_filter(self):
        if self._task_spec is None:
            return
        if self._labeling_widget is None:
            return

        from anylabeling.platform.application.annotation_adapter import (
            get_allowed_shape_types,
        )

        allowed = get_allowed_shape_types(self._task_spec.family)
        actions = self._labeling_widget.actions

        for action_name, shape_type in _ACTION_SHAPE_TYPE_MAP.items():
            action = getattr(actions, action_name, None)
            if action is not None:
                action.setVisible(shape_type in allowed)

        if allowed:
            self._labeling_widget.canvas._create_mode = allowed[0]

    # ------------------------------------------------------------------
    # Inspector
    # ------------------------------------------------------------------

    def _on_inspector_update(self, selected_shapes):
        if not selected_shapes:
            self._inspector.clear()
            self._inspector.setPlaceholderText(tr(
                "检查器\n\n选择画布上的形状\n以查看其属性",
                "Inspector\n\nSelect a shape on the\ncanvas to inspect its\nproperties."
            ))
            self._suggestion_panel.setVisible(False)
            return

        shape = selected_shapes[0]
        lines = [
            f"<b>{tr('标签', 'Label')}:</b> {shape.label}",
            f"<b>{tr('类型', 'Type')}:</b> {shape.shape_type}",
            f"<b>{tr('顶点数', 'Vertices')}:</b> {len(shape.points)}",
            f"<b>{tr('困难', 'Difficult')}:</b> {getattr(shape, 'difficult', False)}",
        ]
        if getattr(shape, 'group_id', None) is not None:
            lines.append(f"<b>{tr('组ID', 'Group')}:</b> {shape.group_id}")
        if getattr(shape, 'description', ''):
            lines.append(f"<b>{tr('描述', 'Desc')}:</b> {shape.description}")

        # Phase 3b: Show suggestion info when a suggestion shape is selected
        is_suggestion = getattr(shape, "is_suggestion", False)
        if is_suggestion:
            confidence = getattr(shape, "suggestion_confidence", 0.0)
            lines.append(
                f"<b>{tr('AI建议', 'AI Suggestion')}:</b> "
                f"{confidence:.2f}"
            )
            self._suggestion_panel.setVisible(True)
            self._suggestion_info_label.setText(
                tr(
                    f"置信度: {confidence:.2f}",
                    f"Confidence: {confidence:.2f}",
                )
            )
            self._accept_btn.setEnabled(True)
            self._reject_btn.setEnabled(True)
        else:
            self._suggestion_panel.setVisible(False)
            self._accept_btn.setEnabled(False)
            self._reject_btn.setEnabled(False)

        self._inspector.setHtml("<br>".join(lines))

    # ------------------------------------------------------------------
    # Phase 3b: AI suggestion accept / reject
    # ------------------------------------------------------------------

    def _on_accept_suggestion(self) -> None:
        """Accept the currently selected suggestion."""
        widget = self._labeling_widget
        if widget is None:
            return
        selected = widget.canvas.selected_shapes
        if not selected:
            return
        shape = selected[0]
        sid = getattr(shape, "suggestion_id", None)
        if sid is None:
            return
        if widget.accept_suggestion(sid):
            self._progress_label.setText(
                tr("建议已接受", "Suggestion accepted")
            )
            # Refresh inspector
            self._suggestion_panel.setVisible(False)
            self._recount_progress()

    def _on_reject_suggestion(self) -> None:
        """Reject the currently selected suggestion."""
        widget = self._labeling_widget
        if widget is None:
            return
        selected = widget.canvas.selected_shapes
        if not selected:
            return
        shape = selected[0]
        sid = getattr(shape, "suggestion_id", None)
        if sid is None:
            return
        if widget.reject_suggestion(sid):
            self._progress_label.setText(
                tr("建议已拒绝", "Suggestion rejected")
            )
            self._inspector.clear()
            self._suggestion_panel.setVisible(False)

    def _on_accept_all_suggestions(self) -> None:
        """Accept all pending suggestions."""
        widget = self._labeling_widget
        if widget is None:
            return
        count = widget.accept_all_suggestions()
        if count > 0:
            self._progress_label.setText(
                tr(f"已接受 {count} 个建议", f"Accepted {count} suggestion(s)")
            )
            self._suggestion_panel.setVisible(False)
            self._recount_progress()
            self._update_suggestion_buttons()

    def _on_reject_all_suggestions(self) -> None:
        """Reject all pending suggestions."""
        widget = self._labeling_widget
        if widget is None:
            return
        count = widget.reject_all_suggestions()
        if count > 0:
            self._progress_label.setText(
                tr(f"已拒绝 {count} 个建议", f"Rejected {count} suggestion(s)")
            )
            self._suggestion_panel.setVisible(False)
            self._update_suggestion_buttons()

    def _update_suggestion_buttons(self) -> None:
        """Enable/disable all suggestion batch buttons based on pending count."""
        widget = self._labeling_widget
        if widget is None:
            return
        pending = widget.pending_suggestion_count()
        has_pending = pending > 0
        self._accept_all_btn.setEnabled(has_pending)
        self._reject_all_btn.setEnabled(has_pending)
        if has_pending:
            self._progress_label.setText(
                tr(
                    f"AI 建议: {pending} 个待处理",
                    f"AI Suggestions: {pending} pending",
                )
            )

    # ------------------------------------------------------------------
    # Phase 3b: Auto-save status
    # ------------------------------------------------------------------

    def _on_auto_save_completed(self, ok: bool, message: str) -> None:
        """Handle auto-save completion signal from LabelingWidget."""
        if ok:
            self._progress_label.setText(message)
        else:
            self._progress_label.setText(
                f"<span style='color:red'>{message}</span>"
            )

    def _check_and_prompt_recovery(self) -> None:
        """Scan for crash recovery files and offer to restore them.

        Called from ``set_project_context()`` before the labeling widget
        loads its first asset.
        """
        if not self._project_path:
            return

        from anylabeling.platform.application.annotation_adapter import (
            find_recovery_files,
        )
        tmp_files = find_recovery_files(self._project_path)
        if not tmp_files:
            return

        # Show a non-modal banner
        count = len(tmp_files)
        reply = QtWidgets.QMessageBox.question(
            self,
            tr("恢复未保存的更改", "Recover Unsaved Changes"),
            tr(
                f"发现 {count} 个未保存的标注文件（崩溃恢复）。\n"
                f"要恢复这些更改吗？",
                f"Found {count} unsaved annotation file(s) from a "
                f"previous crash.\nRecover these changes?",
            ),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self._recover_files(tmp_files)
        else:
            self._discard_recovery_files(tmp_files)

    def _recover_files(self, tmp_files: list) -> None:
        """Recover annotations from .tmp files: load → save → delete .tmp."""
        from pathlib import Path
        from anylabeling.platform.application.annotation_adapter import (
            recover_from_tmp,
            save_annotations_for_asset,
        )
        from anylabeling.platform.infrastructure.image_reader import ImageReader

        recovered = 0
        for tmp_path in tmp_files:
            # Derive asset path from tmp filename
            stem = tmp_path.stem.replace(".json", "")
            assets_dir = Path(self._project_path) / "assets"
            # Try common extensions
            asset_path = None
            for ext in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"):
                candidate = assets_dir / f"{stem}{ext}"
                if candidate.exists():
                    asset_path = candidate
                    break

            if asset_path is None:
                continue

            try:
                info = ImageReader.metadata(str(asset_path))
            except Exception:
                continue
            h, w = info.height, info.width

            doc = recover_from_tmp(tmp_path, w, h)
            if doc is None:
                continue

            # Convert doc to shapes and save normally
            from anylabeling.platform.application.annotation_adapter import (
                annotation_doc_to_shapes,
            )
            shapes = annotation_doc_to_shapes(doc)
            save_annotations_for_asset(
                str(asset_path),
                shapes,
                self._project_path,
                self._label_name_to_id,
            )
            # Clean up tmp
            try:
                tmp_path.unlink()
            except OSError:
                pass
            recovered += 1

        if recovered > 0:
            logger.info("Recovered %d annotation(s) from crash", recovered)
            self._scan_assets()

    def _discard_recovery_files(self, tmp_files: list) -> None:
        """Delete all .tmp recovery files."""
        for tmp_path in tmp_files:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        logger.info("Discarded %d recovery file(s)", len(tmp_files))

"""Workbench shell — wraps existing LabelingWidget as a Label Workspace page."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from anylabeling.platform.application.asset_repository import AssetRepository
from anylabeling.platform.application.dataset_build_service import DatasetBuildService
from anylabeling.platform.domain.import_config import get_supported_extensions
from anylabeling.platform.application.evaluation_service import EvaluationService
from anylabeling.platform.application.export_service import ExportService
from anylabeling.platform.application.inference_service import InferenceService
from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.application.project_session import ProjectSession
from anylabeling.platform.application.training_service import TrainingService
from anylabeling.platform.application.import_service import ImportService
from anylabeling.views.platform.data_workspace import DataWorkspace
from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
from anylabeling.views.platform.export_workspace import ExportWorkspace
from anylabeling.views.platform.i18n import tr, set_locale
from anylabeling.views.platform.label_workspace import LabelWorkspace
from anylabeling.views.platform.workspaces.import_workspace import ImportWorkspace
from anylabeling.views.platform.job_console import JobConsole
from anylabeling.views.platform.navigation_bar import (
    DATA,
    LABEL,
    TRAIN,
    EVALUATE,
    INFER,
    EXPORT,
    NavigationBar,
    PipelineStep,
    step_label,
)
from anylabeling.views.platform.project_home import ProjectHomeWidget
from anylabeling.views.platform.train_workspace import TrainWorkspace

from anylabeling.views.platform.shell import (
    AppBar,
    Domain,
    ErrorBanner,
    NavState,
    PageHeader,
    PrimaryNavigation,
    StatusBar,
    SubNav,
    SubStep,
    TaskCenterDrawer,
)

from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    get_list_widget_style,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PipelineStep → Domain mapping (Phase 2a)
# ---------------------------------------------------------------------------


def _pipeline_step_to_domain(step: PipelineStep) -> Domain:
    """Map legacy 8-step PipelineStep to new 5-domain navigation."""
    mapping: dict[PipelineStep, Domain] = {
        PipelineStep.PROJECT: Domain.PROJECT,
        PipelineStep.IMPORT: Domain.DATA_PREP,
        PipelineStep.CONFIG: Domain.DATA_PREP,
        PipelineStep.LABEL: Domain.DATA_PREP,
        PipelineStep.PREPROCESS: Domain.DATA_PREP,
        PipelineStep.TRAIN: Domain.TRAIN,
        PipelineStep.EVALUATE: Domain.EVAL_VALIDATE,
        PipelineStep.EXPORT: Domain.EXPORT,
        PipelineStep.MODELS: Domain.EXPORT,
    }
    return mapping.get(step, Domain.PROJECT)


# ---------------------------------------------------------------------------
# WorkbenchWindow
# ---------------------------------------------------------------------------


class WorkbenchWindow(QtWidgets.QMainWindow):
    """V4 MVP Platform Workbench — 8-step pipeline."""

    PAGE_COUNT = len(PipelineStep)  # 9 (now includes MODELS)

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self._config = config
        self._project_path: str | None = None
        self._job_service: JobService | None = None
        self._session = ProjectSession()
        self._asset_repository: AssetRepository | None = None
        self._model_library = None

        # Init locale from config
        if config:
            set_locale(config.get("language", "zh_CN"))

        self.setWindowTitle(tr("视觉算法平台", "Vision Algorithm Platform"))
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.resize(1920, 1080)

        self._central = QtWidgets.QWidget()
        self.setCentralWidget(self._central)

        # --- New Shell layout ---
        main_vlayout = QtWidgets.QVBoxLayout()
        main_vlayout.setContentsMargins(0, 0, 0, 0)
        main_vlayout.setSpacing(0)

        # AppBar (48 px)
        self._app_bar = AppBar()
        self._app_bar.project_selected.connect(self._on_appbar_project_selected)
        self._app_bar.task_center_toggled.connect(self._on_task_center_toggled)
        self._app_bar.models_requested.connect(self._show_model_library)
        self._app_bar.settings_requested.connect(self._on_settings_requested)
        self._app_bar.help_requested.connect(self._on_help_requested)
        main_vlayout.addWidget(self._app_bar)

        # Body: PrimaryNav | Content area
        body_h = QtWidgets.QHBoxLayout()
        body_h.setContentsMargins(0, 0, 0, 0)
        body_h.setSpacing(0)

        # PrimaryNav (176 px / 56 px folded)
        self._primary_nav = PrimaryNavigation()
        self._primary_nav.domain_changed.connect(self._on_domain_changed)
        body_h.addWidget(self._primary_nav)

        # Right content area
        right_v = QtWidgets.QVBoxLayout()
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(0)

        # PageHeader (56 px)
        self._page_header = PageHeader()
        right_v.addWidget(self._page_header)

        # ErrorBanner (conditional — shows below PageHeader on error)
        self._error_banner = ErrorBanner()
        self._error_banner.dismissed.connect(self._on_error_dismissed)
        right_v.addWidget(self._error_banner)

        # SubNav (conditional — only DATA_PREP domain)
        self._sub_nav = SubNav()
        self._sub_nav.step_changed.connect(self._on_sub_step_changed)
        self._sub_nav.setVisible(False)
        right_v.addWidget(self._sub_nav)

        # Page stack (stretch)
        self._pages = QtWidgets.QStackedWidget()
        right_v.addWidget(self._pages, stretch=1)

        # StatusBar (24 px)
        self._status_bar_widget = StatusBar()
        right_v.addWidget(self._status_bar_widget)

        body_h.addLayout(right_v, stretch=1)

        # TaskCenterDrawer (420 px — right-side slide-in panel)
        self._task_center_drawer = TaskCenterDrawer()
        self._task_center_drawer.job_cancel_requested.connect(
            self._on_job_cancel
        )
        self._task_center_drawer.job_retry_requested.connect(
            self._on_job_retry
        )
        body_h.addWidget(self._task_center_drawer)

        main_vlayout.addLayout(body_h, stretch=1)

        self._central.setLayout(main_vlayout)

        # --- Legacy widgets (removed from layout, code preserved for Phase 3) ---
        # NavigationBar, QTreeWidget explorer, QTextEdit inspector,
        # and JobConsole are no longer in the layout but their code
        # is kept below for backward-compatible access.
        self._navigation = NavigationBar()
        self._navigation.page_changed.connect(self._on_page_changed)
        self._navigation.setVisible(False)

        self._explorer = QtWidgets.QTreeWidget()
        self._explorer.setVisible(False)
        self._explorer.setStyleSheet(get_list_widget_style())

        t = get_theme()
        self._inspector = QtWidgets.QTextEdit()
        self._inspector.setReadOnly(True)
        self._inspector.setMaximumWidth(280)
        self._inspector.setMinimumWidth(160)
        self._inspector.setPlaceholderText(tr(
            "检查器\n\n选择画布上的形状以查看其属性",
            "Inspector\n\nSelect a shape on the canvas to inspect its properties."
        ))
        self._inspector.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {t["border"]};
                background-color: {t["surface"]};
                font-size: {FONT_SIZE_BODY}px;
                color: {t["text"]};
                font-family: {FONT_FAMILY};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        self._inspector.setVisible(False)

        self._job_console = JobConsole()
        self._job_console.setMaximumHeight(200)
        self._job_console.setMinimumHeight(80)
        self._job_console.setVisible(False)

        # Lazy-loading state
        self._page_loaded: dict[int, bool] = {}
        self._page_widgets: dict[int, QtWidgets.QWidget] = {}
        self._create_pages()

        self._setup_menu_bar()

        self._pages.setCurrentIndex(PipelineStep.PROJECT.value)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project(self, project_path: str) -> None:
        self._project_path = project_path
        self._project_home.set_project(project_path)

        # --- Initialize services via ProjectSession BEFORE UI updates ---
        self._session.open_project(project_path)
        self._job_service = self._session.job_service
        self._context = self._session.context  # ProjectContext (Phase E/F1)
        self._asset_repository = AssetRepository(project_path)

        self._navigation.set_project_open(True)
        self._navigation.set_current_step(PipelineStep.PROJECT)

        # --- New Shell: show project in AppBar + StatusBar ---
        project_name = Path(project_path).name
        self._app_bar.set_project(project_name)
        self._status_bar_widget.set_save_status(tr("已保存", "Saved"))
        self.setWindowTitle(tr(
            f"{project_name} — 视觉算法平台",
            f"{project_name} — Vision Algorithm Platform"
        ))

        self._build_explorer_tree(project_path)

        # Wire-up JobService to dependent widgets
        self._job_console.set_job_service(self._job_service)
        self._task_center_drawer.set_job_service(self._job_service)
        if self._context is not None and hasattr(self._task_center_drawer, 'set_job_repository'):
            self._task_center_drawer.set_job_repository(
                self._context.jobs
            )

        training_service = TrainingService(
            self._job_service, project_path,
            context=self._context,
        )
        export_service = ExportService(self._job_service, project_path)
        evaluation_service = EvaluationService(self._job_service, project_path)
        inference_service = InferenceService(self._job_service, project_path)
        self._dataset_build_service = DatasetBuildService(
            project_path, context=self._context,
        )

        # --- Load project data ---
        task_specs = self._load_task_specs(project_path)
        dataset_builds = self._load_dataset_builds(project_path)

        # --- Verify build integrity for past builds ---
        self._verify_past_build_integrity(project_path)

        # --- Import Workspace (embedded import page) ---
        self._import_workspace = ImportWorkspace(
            ImportService(project_path, context=self._context)
        )
        self._import_workspace.import_completed.connect(
            self._on_import_completed
        )
        self._import_workspace.asset_repository_changed.connect(
            self._on_asset_repository_changed
        )

        # --- Data Workspace (simplified data overview) ---
        self._data_workspace = DataWorkspace()
        if self._context is not None:
            self._data_workspace.set_context(self._context)
        asset_paths = self._asset_repository.scan_assets()  # Phase 3a: unified via AssetRepository
        self._data_workspace.set_assets(asset_paths)
        self._data_workspace.import_requested.connect(
            self._show_import_workspace
        )
        self._data_workspace.navigate_to_step.connect(
            lambda step: self._navigate_to(step)
        )

        # Populate class distribution if task specs and annotations exist
        if task_specs:
            label_names = {lb.id: lb.name for lb in task_specs[0].labels}
            class_counts = self._count_annotations_by_class(project_path, label_names)
            self._data_workspace.set_class_distribution(class_counts)

        # Replace IMPORT placeholder with the real DataWorkspace
        self._replace_page(PipelineStep.IMPORT, self._data_workspace)

        # --- Label Workspace ---
        if task_specs:
            self._label_workspace = LabelWorkspace()
            self._label_workspace.set_project_context(
                project_path, task_specs[0],
                asset_repository=self._asset_repository,  # Phase 3a
            )
            # Fold primary nav when entering label workspace
            self._label_workspace.nav_fold_requested.connect(
                self._primary_nav.set_folded
            )
            # If the page was already loaded, replace the old one
            self._replace_page(PipelineStep.LABEL, self._label_workspace)

        # --- Train Workspace (lazy, loaded on first access) ---
        # Keep reference to task_specs/dataset_builds for lazy init
        self._pending_task_specs = task_specs
        self._pending_dataset_builds = dataset_builds
        self._training_service = training_service
        self._export_service = export_service

        # --- Config Workspace ---
        if hasattr(self, "_config_workspace") and self._config_workspace is not None:
            self._config_workspace.set_project_context(project_path)
            self._replace_page(PipelineStep.CONFIG, self._config_workspace)
        self._evaluation_service = evaluation_service
        self._inference_service = inference_service

        # --- Update already-loaded lazy workspaces with project context ---
        for pkv in (
            ("_evaluate_workspace", PipelineStep.EVALUATE),
            ("_export_workspace", PipelineStep.EXPORT),
            ("_preprocess_workspace", PipelineStep.PREPROCESS),
        ):
            attr, pstep = pkv
            ws = getattr(self, attr, None)
            if ws is not None and self._page_loaded.get(pstep.value, False):
                if hasattr(ws, "set_project_context"):
                    ws.set_project_context(project_path)
                self._replace_page(pstep, ws)

        # --- Status bar ---
        project_name = Path(project_path).name
        self._status_bar_widget.set_save_status(tr("已保存", "Saved"))
        self.setWindowTitle(tr(
            f"{project_name} — 视觉算法平台",
            f"{project_name} — Vision Algorithm Platform"
        ))

        # Refresh navigation state
        self._refresh_nav_states()

        # Update AppBar task count
        jobs = self._job_service.list_jobs()
        active = sum(
            1 for j in jobs
            if j.get("state") in {"queued", "starting", "running"}
        )
        self._app_bar.set_task_count(active)
        self._status_bar_widget.set_background_tasks(active)

        # Auto-jump to IMPORT if assets are empty
        if not asset_paths:
            self._navigate_to(PipelineStep.IMPORT)

        # Update AI toolbar with available runs
        if hasattr(self, "_label_workspace") and hasattr(self, "_training_service"):
            runs_data = self._load_runs_for_ai_toolbar(project_path)
            self._label_workspace._update_ai_toolbar_state(
                runs=runs_data,
                has_assets=len(asset_paths) > 0,
            )

        logger.info("Opened project: %s", project_path)

    def add_label_workspace(self, _labeling_widget: QtWidgets.QWidget) -> None:
        """Deprecated — LabelWorkspace is now native. Kept for API compat."""
        logger.warning(
            "add_label_workspace() called but LabelWorkspace is now native."
        )

    def project_path(self) -> str | None:
        return self._project_path

    def job_service(self) -> JobService | None:
        return self._job_service

    # ------------------------------------------------------------------
    # Internal — page creation
    # ------------------------------------------------------------------

    def _create_pages(self):
        """Register 8 pages. Most are placeholders; real widgets loaded lazily."""

        # Page 0: PROJECT — ProjectHomeWidget (eager, shown immediately)
        self._project_home = ProjectHomeWidget()
        self._project_home.project_opened.connect(self.set_project)
        self._pages.addWidget(self._project_home)
        self._page_loaded[PipelineStep.PROJECT.value] = True
        self._page_widgets[PipelineStep.PROJECT.value] = self._project_home

        # Pages 1-7: placeholders (lazy-loaded on first navigation)
        for step in PipelineStep:
            if step == PipelineStep.PROJECT:
                continue
            placeholder = self._create_placeholder_page(step_label(step))
            self._pages.addWidget(placeholder)
            self._page_loaded[step.value] = False
            self._page_widgets[step.value] = placeholder

    def _load_page(self, step: PipelineStep) -> None:
        """Lazy-load the real widget for a pipeline step, replacing its placeholder."""
        if self._page_loaded.get(step.value, False):
            return

        widget: QtWidgets.QWidget | None = None

        if step == PipelineStep.IMPORT:
            if hasattr(self, "_data_workspace") and self._data_workspace is not None:
                widget = self._data_workspace
            else:
                widget = self._create_placeholder_page(tr(
                    "请先打开项目以查看数据。",
                    "Open a project first to view data."
                ))
        elif step == PipelineStep.CONFIG:
            widget = self._create_config_workspace()
        elif step == PipelineStep.LABEL:
            if hasattr(self, "_label_workspace") and self._label_workspace is not None:
                widget = self._label_workspace
            else:
                widget = self._create_placeholder_page(tr(
                    "请先配置任务标签。",
                    "Configure task labels first."
                ))
        elif step == PipelineStep.PREPROCESS:
            widget = self._create_preprocess_workspace()
        elif step == PipelineStep.TRAIN:
            widget = self._create_train_workspace()
        elif step == PipelineStep.EVALUATE:
            widget = self._create_evaluate_workspace()
        elif step == PipelineStep.EXPORT:
            widget = self._create_export_workspace()
        elif step == PipelineStep.MODELS:
            if self._model_library is not None:
                widget = self._model_library
            else:
                widget = self._create_placeholder_page(tr(
                    "请先打开项目。",
                    "Open a project first.",
                ))

        if widget is not None:
            self._replace_page(step, widget)

    def _create_train_workspace(self) -> QtWidgets.QWidget:
        """Create and wire TrainWorkspace."""
        workspace = TrainWorkspace()
        if hasattr(self, "_pending_task_specs") and hasattr(self, "_pending_dataset_builds"):
            workspace.set_project_context(
                job_service=self._job_service,
                training_service=self._training_service,
                task_specs=self._pending_task_specs,
                dataset_builds=self._pending_dataset_builds,
            )
        self._train_workspace = workspace
        return workspace

    def _create_evaluate_workspace(self) -> QtWidgets.QWidget:
        """Create and wire EvaluateWorkspace."""
        workspace = EvaluateWorkspace()
        if hasattr(self, "_training_service"):
            workspace.set_project_context(
                training_service=self._training_service
            )
            workspace.evaluate_requested.connect(self._on_evaluate_requested)
        return workspace

    def _create_export_workspace(self) -> QtWidgets.QWidget:
        """Create and wire ExportWorkspace."""
        workspace = ExportWorkspace()
        if hasattr(self, "_training_service"):
            workspace.set_project_context(
                training_service=self._training_service
            )
            # Wire provider for dynamic format checkbox generation
            try:
                from anylabeling.platform.adapters.registry import AlgorithmRegistry
                provider = AlgorithmRegistry.get_provider("ultralytics_yolo_detect")
                workspace.set_provider(provider)
            except (ImportError, AttributeError) as exc:
                logger.debug(
                    "Provider not available for export workspace: %s", exc
                )
            workspace.export_requested.connect(self._on_export_requested)
        return workspace

    def _create_config_workspace(self) -> QtWidgets.QWidget:
        """Create and wire TaskConfigurator to the CONFIG page."""
        from anylabeling.views.platform.task_configurator import (
            TaskConfigurator,
        )
        configurator = TaskConfigurator()
        if self._project_path:
            configurator.set_project_context(self._project_path)
        configurator.task_configured.connect(self._on_task_configured)
        configurator.back_requested.connect(
            lambda: self._navigate_to(PipelineStep.PROJECT))
        configurator.next_requested.connect(
            lambda: self._navigate_to(PipelineStep.LABEL))
        self._config_workspace = configurator
        return configurator

    def _on_task_configured(self, task_spec) -> None:
        """Save the configured TaskSpec via ProjectFileStore."""
        self._pending_task_specs = [task_spec]
        if self._project_path:
            try:
                from anylabeling.platform.infrastructure.project_file_store import (
                    ProjectFileStore,
                )
                ProjectFileStore.save_task_spec(self._project_path, task_spec)
            except (OSError, ImportError) as exc:
                logger.warning(
                    "Failed to persist TaskSpec for %s: %s",
                    self._project_path, exc,
                )

    def _create_preprocess_workspace(self) -> QtWidgets.QWidget:
        """Create and wire PreprocessWorkspace."""
        from anylabeling.views.platform.preprocess_workspace import (
            PreprocessWorkspace,
        )
        workspace = PreprocessWorkspace()

        # Populate with large images from project assets
        if self._project_path:
            workspace.set_project_path(self._project_path)

            # Pass task family for label splitter selection
            pending_ts = getattr(self, "_pending_task_specs", None)
            if pending_ts:
                workspace.set_task_family(pending_ts[0].family)

            assets_dir = Path(self._project_path) / "assets"
            if assets_dir.is_dir():
                # Use AssetRepository's QImageReader-based scan that
                # handles all formats including large TIFFs.
                large_images = self._asset_repository.find_large_images()
                workspace.set_large_images(large_images)

            # Set total asset count so Build button enables for normal images
            total = self._asset_repository.count_assets()
            workspace.set_total_assets(total)

        workspace.build_requested.connect(self._on_preprocess_build_requested)
        return workspace

    def _replace_page(self, step: PipelineStep, widget: QtWidgets.QWidget) -> None:
        """Replace the placeholder at the given step index with the real widget.

        Does NOT call deleteLater() on the old widget — the caller may
        hold a reference and re-insert it later (e.g. DataWorkspace and
        ImportWorkspace toggle on the IMPORT page).  Placeholder widgets
        with no remaining Python references are collected naturally by GC.
        """
        idx = step.value
        old = self._pages.widget(idx)
        if old is not None and old is not widget:
            self._pages.removeWidget(old)
        self._pages.insertWidget(idx, widget)
        self._page_widgets[idx] = widget
        self._page_loaded[idx] = True

    def _navigate_to(self, step: PipelineStep) -> None:
        """Navigate to a pipeline step, loading it lazily if needed."""
        self._load_page(step)
        self._pages.setCurrentIndex(step.value)
        self._navigation.set_current_step(step)
        # Update new Shell — map PipelineStep to Domain
        domain = _pipeline_step_to_domain(step)
        self._primary_nav.set_current_domain(domain)
        # Show/hide SubNav for DATA_PREP domain
        self._sub_nav.setVisible(domain == Domain.DATA_PREP)

    @staticmethod
    def _create_placeholder_page(name: str) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        label = QtWidgets.QLabel(tr(
            f"{name}\n\n（即将推出）", f"{name}\n\n(Coming soon)"
        ))
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"color: {get_theme()['text_secondary']}; font-size: 24px;"
            f"font-weight: bold; font-family: {FONT_FAMILY};"
        )
        layout.addWidget(label)
        widget.setLayout(layout)
        return widget

    # ------------------------------------------------------------------
    # Internal — menu bar
    # ------------------------------------------------------------------

    def _setup_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu(tr("文件(&F)", "&File"))
        file_menu.addAction(
            tr("打开项目(&O)...", "&Open Project..."),
            self._on_open_project_menu,
        )
        file_menu.addSeparator()
        exit_action = file_menu.addAction(tr("退出(&X)", "E&xit"))
        exit_action.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)

        proj_menu = menubar.addMenu(tr("项目(&P)", "&Project"))
        proj_menu.addAction(
            tr("项目主页(&H)", "Project &Home"),
            lambda: self._navigate_to(PipelineStep.PROJECT),
        )
        proj_menu.addAction(
            tr("导入(&I)", "&Import"),
            lambda: self._navigate_to(PipelineStep.IMPORT),
        )
        proj_menu.addAction(
            tr("标注工作区(&L)", "&Label Workspace"),
            lambda: self._navigate_to(PipelineStep.LABEL),
        )
        proj_menu.addAction(
            tr("训练(&T)", "&Train"),
            lambda: self._navigate_to(PipelineStep.TRAIN),
        )
        proj_menu.addAction(
            tr("导出(&E)", "E&xport"),
            lambda: self._navigate_to(PipelineStep.EXPORT),
        )

        help_menu = menubar.addMenu(tr("帮助(&H)", "&Help"))
        help_menu.addAction(tr("关于(&A)", "&About"), self._on_about)

    # ------------------------------------------------------------------
    # Internal — explorer
    # ------------------------------------------------------------------

    def _build_explorer_tree(self, project_path: str):
        self._explorer.clear()
        root = Path(project_path)

        project_item = QtWidgets.QTreeWidgetItem([root.name])
        project_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, project_path)
        project_item.setIcon(0, self.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_DirIcon
        ))
        self._explorer.addTopLevelItem(project_item)

        for entry in sorted(root.iterdir()):
            if entry.is_dir():
                child = QtWidgets.QTreeWidgetItem([entry.name])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, str(entry))
                child.setIcon(0, self.style().standardIcon(
                    QtWidgets.QStyle.StandardPixmap.SP_DirIcon
                ))
                project_item.addChild(child)

        project_item.setExpanded(True)

    def _on_explorer_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, _column: int):
        path = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if path and (Path(path) / "assets").exists():
            self._navigate_to(PipelineStep.LABEL)

    # ------------------------------------------------------------------
    # Internal — slots
    # ------------------------------------------------------------------

    def _on_page_changed(self, index: int):
        """Handle navigation bar page change (lazy-load if needed)."""
        try:
            step = PipelineStep(index)
        except ValueError:
            return
        self._load_page(step)
        self._pages.setCurrentIndex(index)

    # ------------------------------------------------------------------
    # Import workspace wiring (Phase 3)
    # ------------------------------------------------------------------

    def _show_import_workspace(self) -> None:
        """Switch the IMPORT page to show ImportWorkspace and navigate to it."""
        if hasattr(self, "_import_workspace") and self._import_workspace is not None:
            self._replace_page(PipelineStep.IMPORT, self._import_workspace)
            self._navigate_to(PipelineStep.IMPORT)

    def _on_import_completed(self, result) -> None:
        """Handle import completion: refresh caches and workspace views."""
        from anylabeling.platform.domain.import_config import ImportResult

        if self._asset_repository is not None:
            self._asset_repository.invalidate_cache()
            asset_paths = self._asset_repository.scan_assets()
            self._data_workspace.set_assets(asset_paths)

        # Refresh LabelWorkspace if loaded
        if (
            hasattr(self, "_label_workspace")
            and self._label_workspace is not None
        ):
            if hasattr(self._label_workspace, "_scan_assets"):
                self._label_workspace._scan_assets()

        # Switch back to DataWorkspace (overview)
        self._replace_page(PipelineStep.IMPORT, self._data_workspace)

        # Update status bar
        if isinstance(result, ImportResult):
            self._status_bar_widget.set_save_status(
                tr(
                    f"✓ 已导入 {result.total} 张图片",
                    f"✓ Imported {result.total} images",
                )
            )

        # Update AI toolbar
        if hasattr(self, "_label_workspace") and hasattr(self, "_training_service"):
            asset_paths = self._asset_repository.scan_assets()
            runs_data = self._load_runs_for_ai_toolbar(self._project_path)
            self._label_workspace._update_ai_toolbar_state(
                runs=runs_data,
                has_assets=len(asset_paths) > 0,
            )

    def _on_asset_repository_changed(self) -> None:
        """Handle asset_repository_changed signal from ImportWorkspace."""
        logger.debug("Asset repository change notification received")

    # ------------------------------------------------------------------
    # New Shell slots (Phase 2a)
    # ------------------------------------------------------------------

    def _on_domain_changed(self, domain_value: int) -> None:
        """Handle PrimaryNav domain change — navigate to the default
        PipelineStep for that domain."""
        try:
            domain = Domain(domain_value)
        except ValueError:
            return

        # Map domain to its default PipelineStep
        mapping: dict[Domain, PipelineStep] = {
            Domain.PROJECT: PipelineStep.PROJECT,
            Domain.DATA_PREP: PipelineStep.IMPORT,
            Domain.TRAIN: PipelineStep.TRAIN,
            Domain.EVAL_VALIDATE: PipelineStep.EVALUATE,
            Domain.EXPORT: PipelineStep.EXPORT,
        }
        step = mapping.get(domain, PipelineStep.PROJECT)
        self._navigate_to(step)

    def _on_sub_step_changed(self, sub_step_value: int) -> None:
        """Handle SubNav step change — navigate to the corresponding
        PipelineStep within DATA_PREP domain."""
        try:
            sub_step = SubStep(sub_step_value)
        except ValueError:
            return

        mapping: dict[SubStep, PipelineStep] = {
            SubStep.IMPORT: PipelineStep.IMPORT,
            SubStep.TASK: PipelineStep.CONFIG,
            SubStep.LABEL: PipelineStep.LABEL,
            SubStep.DATASET_BUILD: PipelineStep.PREPROCESS,
        }
        step = mapping.get(sub_step)
        if step is not None:
            self._navigate_to(step)

    def _on_appbar_project_selected(self, _path: str) -> None:
        """Handle AppBar project selector click — navigate to PROJECT."""
        self._navigate_to(PipelineStep.PROJECT)

    def _on_task_center_toggled(self) -> None:
        """Handle AppBar task center button — toggle drawer."""
        self._task_center_drawer.toggle()

    def _on_settings_requested(self) -> None:
        """Handle AppBar settings button."""
        logger.info("Settings requested (placeholder)")

    def _on_help_requested(self) -> None:
        """Handle AppBar help button — show About dialog."""
        self._on_about()

    def _on_open_project_menu(self):
        self._navigate_to(PipelineStep.PROJECT)

    def _on_about(self):
        QtWidgets.QMessageBox.about(
            self,
            tr("关于视觉算法平台", "About Vision Algorithm Platform"),
            tr(
                "视觉算法平台 V4 MVP\n\n"
                "X-AnyLabeling 平台工作台\n"
                "八步流水线：项目 → 导入 → 配置 → 标注 → 预处理 → 训练 → 评估 → 导出",
                "Vision Algorithm Platform V4 MVP\n\n"
                "X-AnyLabeling Platform Workbench\n"
                "8-step pipeline: Project → Import → Configure → Label → "
                "Preprocess → Train → Evaluate → Export",
            ),
        )

    # ------------------------------------------------------------------
    # TaskCenterDrawer & ErrorBanner handlers
    # ------------------------------------------------------------------

    def _on_job_cancel(self, job_id: str) -> None:
        """Cancel a running job."""
        if self._job_service is None:
            return
        try:
            self._job_service.cancel_job(job_id)
            logger.info("Job cancelled: %s", job_id)
        except Exception:
            logger.exception("Failed to cancel job %s", job_id)
            self._error_banner.show_error(
                title=tr("取消失败", "Cancel Failed"),
                what=tr(
                    f"无法取消作业 {job_id}",
                    f"Cannot cancel job {job_id}",
                ),
                impact=tr("作业继续运行", "Job continues running"),
                fix=tr("请等待作业完成后重试", "Wait for job to finish and retry"),
                traceback="",
            )

    def _on_job_retry(self, job_id: str) -> None:
        """Retry a failed job — deferred to Phase 4a."""
        logger.info("Job retry requested for %s (deferred to Phase 4)", job_id)
        self._error_banner.show_info(
            title=tr("重试", "Retry"),
            message=tr(
                f"作业 {job_id[:12]} 的重试功能将在后续版本中提供。"
                f"请手动重新配置并提交。",
                f"Retry for job {job_id[:12]} will be available in a "
                f"future version. Please reconfigure and resubmit manually.",
            ),
        )

    def _on_error_dismissed(self) -> None:
        """Handle ErrorBanner dismissed."""
        pass  # No additional cleanup needed

    def _verify_past_build_integrity(self, project_path: str) -> None:
        """Verify manifest integrity for all past builds in the project.

        Runs non-blocking (inline but fast).  If corruption is detected,
        shows an ErrorBanner.
        """
        builds_dir = Path(project_path) / "dataset_builds"
        if not builds_dir.is_dir():
            return

        corrupted_builds: list[str] = []
        for build_dir in sorted(builds_dir.iterdir()):
            if not build_dir.is_dir():
                continue
            if not (build_dir / "build.json").exists():
                continue
            try:
                report = DatasetBuildService.verify_build_integrity(build_dir)
                if not report.passed:
                    corrupted_builds.append(report.build_id)
                    logger.warning(
                        "Build integrity failed for %s: %s",
                        report.build_id,
                        report.error or ", ".join(report.corrupted_files),
                    )
            except Exception:
                logger.exception(
                    "Integrity verification failed for %s", build_dir
                )

        if corrupted_builds:
            self._error_banner.show_error(
                title=tr("构建完整性警告", "Build Integrity Warning"),
                what=tr(
                    f"{len(corrupted_builds)} 个构建的清单文件已损坏或丢失。",
                    f"{len(corrupted_builds)} build(s) have corrupted or "
                    f"missing manifest files.",
                ),
                impact=tr(
                    "这些构建的训练或评估结果可能不可靠。",
                    "Training or evaluation results from these builds "
                    "may be unreliable.",
                ),
                fix=tr(
                    "请重新构建受影响的数据集，或删除损坏的构建。",
                    "Rebuild affected datasets or remove corrupted builds.",
                ),
                traceback="\n".join(corrupted_builds[:5]),
            )

    def _refresh_nav_states(self) -> None:
        """Refresh PrimaryNavigation domain states from WorkflowState."""
        if self._session.workflow_state is None:
            return
        states = self._session.refresh_navigation_state()
        for domain_val, domain_state in states.items():
            try:
                domain = Domain(domain_val)
                nav_state = NavState(domain_state.state)
                self._primary_nav.set_domain_state(domain, nav_state)
            except (ValueError, KeyError):
                logger.warning(
                    "Invalid domain state: %s → %s",
                    domain_val,
                    domain_state,
                )

    def _show_error(
        self,
        title: str,
        what: str,
        impact: str,
        fix: str,
        traceback: str = "",
    ) -> None:
        """Show an error in the ErrorBanner (non-blocking)."""
        self._error_banner.show_error(
            title=title,
            what=what,
            impact=impact,
            fix=fix,
            traceback=traceback,
        )

    def _build_project_context(self) -> dict:
        ctx = {"project_path": self._project_path}
        if self._project_path:
            ctx["project_root"] = self._project_path
            ctx["assets_dir"] = str(Path(self._project_path) / "assets")
            ctx["annotations_dir"] = str(Path(self._project_path) / "annotations")
        return ctx

    # ------------------------------------------------------------------
    # Internal — project data loading
    # ------------------------------------------------------------------

    def _load_task_specs(self, project_path: str) -> list:
        from anylabeling.platform.domain.task import TaskSpec, LabelClass
        from anylabeling.platform.infrastructure.project_file_store import (
            ProjectFileStore,
        )

        task_specs: list = []
        try:
            meta = ProjectFileStore.open_project(project_path)
            labels_data = ProjectFileStore.open_labels(project_path)

            labels = tuple(
                LabelClass(
                    id=lb["id"],
                    name=lb["name"],
                    color=lb.get("color"),
                    supercategory=lb.get("supercategory"),
                )
                for lb in labels_data
            )

            ts_data = meta.get("task_spec", {})
            if ts_data is None:
                # "稍后配置" — task_spec is null
                logger.info("Project has no task spec (configured later)")
                return task_specs

            task_spec = TaskSpec(
                id=ts_data.get("id", "default"),
                family=ts_data.get("family", "detection_hbb"),
                labels=labels,
                annotation_schema=ts_data.get("annotation_schema", "yolo_bbox"),
                primary_metric=ts_data.get("primary_metric", "mAP50-95"),
            )
            task_specs.append(task_spec)
        except Exception:
            logger.warning(
                "Failed to load task specs from %s", project_path, exc_info=True
            )

        return task_specs

    def _load_dataset_builds(self, project_path: str) -> list:
        import json

        from anylabeling.platform.domain.dataset import DatasetBuild
        from anylabeling.platform.domain.tile import TilePlan

        builds: list = []
        builds_dir = Path(project_path) / "dataset_builds"
        if not builds_dir.exists():
            return builds

        for build_dir in sorted(builds_dir.iterdir()):
            if not build_dir.is_dir():
                continue
            build_json = build_dir / "build.json"
            if not build_json.exists():
                continue
            try:
                data = json.loads(build_json.read_text(encoding="utf-8"))
                tile_plan = None
                if data.get("tile_plan"):
                    tp = data["tile_plan"]
                    tile_plan = TilePlan(
                        tile_width=tp.get("tile_width", 1024),
                        tile_height=tp.get("tile_height", 1024),
                        overlap_x=tp.get("overlap_x", 0.2),
                        overlap_y=tp.get("overlap_y", 0.2),
                        edge_mode=tp.get("edge_mode", "strict"),
                        min_object_pixels=tp.get("min_object_pixels", 16),
                        min_visibility_ratio=tp.get("min_visibility_ratio", 0.3),
                    )
                build = DatasetBuild(
                    id=data.get("id", build_dir.name),
                    task_spec_id=data.get("task_spec_id", ""),
                    source_asset_manifest_hash=data.get("source_asset_manifest_hash", ""),
                    annotation_manifest_hash=data.get("annotation_manifest_hash", ""),
                    split_seed=data.get("split_seed", 42),
                    split_strategy=data.get("split_strategy", "random_by_asset"),
                    tile_plan=tile_plan,
                    augmentation_plan_id=data.get("augmentation_plan_id"),
                    adapter_id=data.get("adapter_id"),
                    output_path=data.get("output_path", str(build_dir)),
                )
                builds.append(build)
            except Exception:
                logger.warning(
                    "Failed to load dataset build from %s", build_dir, exc_info=True,
                )

        return builds

    # ------------------------------------------------------------------
    # Internal — signal handlers
    # ------------------------------------------------------------------

    def _on_preprocess_build_requested(self, config) -> None:
        """Handle build request from PreprocessWorkspace.

        Args:
            config: A PreprocessConfig dataclass from preprocess_config.py.
        """
        if self._job_service is None:
            logger.warning("Cannot build dataset: no JobService available")
            return
        if getattr(self, "_dataset_build_service", None) is None:
            logger.warning("Cannot build dataset: no DatasetBuildService")
            return

        try:
            task_specs = self._load_task_specs(self._project_path)
            if not task_specs:
                QtWidgets.QMessageBox.warning(
                    self,
                    tr("构建失败", "Build Failed"),
                    tr("没有可用的任务规格。", "No task specs available."),
                )
                return
            task_spec = task_specs[0]

            assets, annotations, image_sources = self._collect_build_inputs(
                self._project_path, task_spec
            )

            if not assets:
                QtWidgets.QMessageBox.warning(
                    self,
                    tr("构建失败", "Build Failed"),
                    tr("项目中没有找到资源（图片）文件。", "No asset files found in project."),
                )
                return

            if not image_sources:
                QtWidgets.QMessageBox.warning(
                    self,
                    tr("构建失败", "Build Failed"),
                    tr("无法创建图像源。请确保 assets/ 目录包含有效图片。",
                       "Cannot create image sources. Ensure assets/ contains valid images."),
                )
                return

            # Build TilePlan from PreprocessConfig
            tile_plan = None
            if config.tile_width and config.tile_height:
                from anylabeling.platform.domain.tile import TilePlan
                tile_plan = TilePlan(
                    tile_width=config.tile_width,
                    tile_height=config.tile_height,
                    overlap_x=config.overlap_x,
                    overlap_y=config.overlap_y,
                    edge_mode="crop" if config.edge_mode in ("crop", "pad") else "crop",
                    padding_value=0,
                    min_object_pixels=16,
                    min_visibility_ratio=0.3,
                )

            build = self._dataset_build_service.build(
                task_spec=task_spec,
                assets=assets,
                annotations=annotations,
                tile_plan=tile_plan,
                image_sources=image_sources,
                split_seed=config.random_seed,
                split_ratios=(
                    config.train_ratio,
                    config.val_ratio,
                    config.test_ratio,
                ),
            )

            logger.info("Dataset build completed: %s", build.id)

            # Run leakage detection
            leakage_report = None
            try:
                build_dir = Path(self._project_path) / "dataset_builds" / build.id
                leakage_report = DatasetBuildService.detect_leakage(
                    build_dir, task_spec
                )
                logger.info(
                    "Leakage report for %s: passed=%s, cross_split=%s",
                    build.id,
                    leakage_report.passed,
                    leakage_report.has_cross_split_groups,
                )
            except Exception:
                logger.exception("Leakage detection failed for build %s", build.id)

            # Display build result with leakage info
            msg_parts = [tr(
                f"数据集构建成功！\n构建 ID：{build.id}",
                f"Dataset build completed!\nBuild ID: {build.id}",
            )]
            if leakage_report is not None:
                if leakage_report.has_cross_split_groups:
                    msg_parts.append(
                        tr(
                            f"\n⚠ 检测到跨切分数据泄露: {len(leakage_report.cross_split_groups)} 个组",
                            f"\n⚠ Cross-split data leakage detected: {len(leakage_report.cross_split_groups)} groups",
                        )
                    )
                else:
                    msg_parts.append(
                        tr(
                            "\n✓ 无跨切分数据泄露",
                            "\n✓ No cross-split data leakage",
                        )
                    )
                if leakage_report.class_imbalance_warnings:
                    msg_parts.append(
                        tr(
                            f"\n⚠ {len(leakage_report.class_imbalance_warnings)} 个类别不均衡警告",
                            f"\n⚠ {len(leakage_report.class_imbalance_warnings)} class imbalance warnings",
                        )
                    )
            QtWidgets.QMessageBox.information(
                self,
                tr("构建完成", "Build Complete"),
                "".join(msg_parts),
            )

            # Refresh dataset builds list and history
            builds = self._load_dataset_builds(str(self._project_path))
            if self._page_loaded.get(PipelineStep.TRAIN.value, False):
                if hasattr(self, "_train_workspace"):
                    self._train_workspace.set_dataset_builds(builds)
            # Refresh PreprocessWorkspace history
            if self._page_loaded.get(PipelineStep.PREPROCESS.value, False):
                preprocess_ws = self._page_widgets.get(
                    PipelineStep.PREPROCESS.value
                )
                if hasattr(preprocess_ws, "_refresh_history"):
                    preprocess_ws._refresh_history()

        except Exception as exc:
            logger.exception("Dataset build failed")
            QtWidgets.QMessageBox.critical(
                self,
                tr("构建错误", "Build Error"),
                tr(f"数据集构建失败：\n{exc}", f"Dataset build failed:\n{exc}"),
            )

    def _on_dataset_build_requested(self, config: dict) -> None:
        if self._job_service is None:
            logger.warning("Cannot build dataset: no JobService available")
            return
        if getattr(self, "_dataset_build_service", None) is None:
            logger.warning("Cannot build dataset: no DatasetBuildService")
            return

        try:
            task_specs = self._load_task_specs(self._project_path)
            if not task_specs:
                QtWidgets.QMessageBox.warning(
                    self,
                    tr("构建失败", "Build Failed"),
                    tr("没有可用的任务规格。", "No task specs available."),
                )
                return
            task_spec = task_specs[0]

            assets, annotations, image_sources = self._collect_build_inputs(
                self._project_path, task_spec
            )

            if not assets:
                QtWidgets.QMessageBox.warning(
                    self,
                    tr("构建失败", "Build Failed"),
                    tr("项目中没有找到资源（图片）文件。", "No asset files found in project."),
                )
                return

            if not image_sources:
                QtWidgets.QMessageBox.warning(
                    self,
                    tr("构建失败", "Build Failed"),
                    tr("无法创建图像源。请确保 assets/ 目录包含有效图片。",
                       "Cannot create image sources. Ensure assets/ contains valid images."),
                )
                return

            tile_plan = None
            if config.get("tile_width") and config.get("tile_height"):
                from anylabeling.platform.domain.tile import TilePlan
                tile_plan = TilePlan(
                    tile_width=config["tile_width"],
                    tile_height=config["tile_height"],
                    overlap_x=config.get("overlap_x", 0),
                    overlap_y=config.get("overlap_y", 0),
                    edge_mode="crop",
                    padding_value=0,
                    min_object_pixels=16,
                    min_visibility_ratio=0.3,
                )

            build = self._dataset_build_service.build(
                task_spec=task_spec,
                assets=assets,
                annotations=annotations,
                tile_plan=tile_plan,
                image_sources=image_sources,
                split_seed=config.get("split_seed", 42),
                split_ratios=(
                    config.get("train_ratio", 0.7),
                    config.get("val_ratio", 0.2),
                    config.get("test_ratio", 0.1),
                ),
            )

            logger.info("Dataset build completed: %s", build.id)
            QtWidgets.QMessageBox.information(
                self,
                tr("构建完成", "Build Complete"),
                tr(f"数据集构建成功！\n构建 ID：{build.id}",
                   f"Dataset build completed!\nBuild ID: {build.id}"),
            )

            # Refresh dataset builds list (lazy-load train workspace if needed)
            builds = self._load_dataset_builds(str(self._project_path))
            if self._page_loaded.get(PipelineStep.TRAIN.value, False):
                self._train_workspace.set_dataset_builds(builds)

        except Exception as exc:
            logger.exception("Dataset build failed")
            QtWidgets.QMessageBox.critical(
                self,
                tr("构建错误", "Build Error"),
                tr(f"数据集构建失败：\n{exc}", f"Dataset build failed:\n{exc}"),
            )

    def _on_evaluate_requested(self, run_id: str, mode: str) -> None:
        service = getattr(self, "_evaluation_service", None)
        if service is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr("没有可用的评估服务。", "No evaluation service available."),
            )
            return

        train_ws = self._page_widgets.get(PipelineStep.TRAIN.value)
        training_service = getattr(train_ws, "training_service", None)
        if training_service is None:
            training_service = getattr(self, "_training_service", None)
        if training_service is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr("没有可用的训练服务。", "No training service available."),
            )
            return

        run = training_service.read_run_record(run_id)
        if run is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr(f"未找到运行记录：{run_id}", f"Run record not found: {run_id}"),
            )
            return

        dataset_builds = self._load_dataset_builds(str(self._project_path))
        matching_build = None
        for db in dataset_builds:
            if db.id == run.dataset_build_id:
                matching_build = db
                break
        if matching_build is None and dataset_builds:
            matching_build = dataset_builds[0]

        if matching_build is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr("没有找到用于评估的数据集构建。",
                   "No dataset build found for evaluation."),
            )
            return

        try:
            job_id = service.evaluate_tile_native(
                run=run,
                build=matching_build,
                split=mode if mode in ("train", "val", "test") else "val",
            )
            logger.info("Evaluation started: run=%s job=%s", run_id, job_id)
            self._status_bar_widget.set_save_status(
                tr(f"评估已启动：{job_id}", f"Evaluation started: {job_id}")
            )

            self._pending_eval = {
                "job_id": job_id,
                "run": run,
                "build": matching_build,
                "service": service,
            }
            if not hasattr(self, "_eval_poll_timer"):
                from PyQt6.QtCore import QTimer
                self._eval_poll_timer = QTimer(self)
                self._eval_poll_timer.timeout.connect(self._poll_eval_completion)
            self._eval_poll_timer.start(2000)
        except Exception as exc:
            logger.exception("Evaluation failed")
            QtWidgets.QMessageBox.critical(
                self,
                tr("评估错误", "Evaluation Error"),
                tr(f"评估失败：\n{exc}", f"Evaluation failed:\n{exc}"),
            )

    def _poll_eval_completion(self) -> None:
        """Poll for evaluation job completion and display metrics."""
        pending = getattr(self, "_pending_eval", None)
        if pending is None:
            if hasattr(self, "_eval_poll_timer"):
                self._eval_poll_timer.stop()
            return

        from anylabeling.platform.workers.protocol import JobState
        state = self._job_service.get_job_state(pending["job_id"])

        terminal_states = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}
        if state not in terminal_states:
            return

        if hasattr(self, "_eval_poll_timer"):
            self._eval_poll_timer.stop()

        if state == JobState.COMPLETED:
            try:
                metrics = pending["service"].parse_val_results(
                    pending["run"], pending["build"]
                )
                if metrics:
                    eval_ws = self._page_widgets.get(PipelineStep.EVALUATE.value)
                    if hasattr(eval_ws, "display_metrics"):
                        eval_ws.display_metrics(metrics)
                    self._status_bar_widget.set_save_status(
                        tr("评估完成", "Evaluation complete")
                    )
                else:
                    eval_ws = self._page_widgets.get(PipelineStep.EVALUATE.value)
                    if hasattr(eval_ws, "display_metrics"):
                        eval_ws.display_metrics(
                            {"error": "No metrics found in val output"}
                        )
            except Exception as exc:
                logger.exception("Failed to parse val results")
                eval_ws = self._page_widgets.get(PipelineStep.EVALUATE.value)
                if hasattr(eval_ws, "display_metrics"):
                    eval_ws.display_metrics({"error": str(exc)})
        else:
            eval_ws = self._page_widgets.get(PipelineStep.EVALUATE.value)
            if hasattr(eval_ws, "display_metrics"):
                eval_ws.display_metrics(
                    {"error": f"Evaluation job ended with state: {state.value}"}
                )

        self._pending_eval = None

    def _poll_infer_completion(self) -> None:
        """Poll for inference job completion and render results."""
        pending = getattr(self, "_pending_infer", None)
        if pending is None:
            if hasattr(self, "_infer_poll_timer"):
                self._infer_poll_timer.stop()
            return

        from anylabeling.platform.workers.protocol import JobState
        state = self._job_service.get_job_state(pending["job_id"])

        terminal = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}
        if state not in terminal:
            return

        if hasattr(self, "_infer_poll_timer"):
            self._infer_poll_timer.stop()

        if state == JobState.COMPLETED:
            import json
            stdout, _ = self._job_service.get_job_logs(pending["job_id"])
            try:
                detections = json.loads(stdout.strip().split("\n")[-1])
                if isinstance(detections, list):
                    train_ws = self._page_widgets.get(PipelineStep.TRAIN.value)
                    training_service = getattr(train_ws, "training_service", None)
                    run = training_service.read_run_record(pending["run"].id)
                    class_names = []
                    if run and run.config:
                        import json as _json
                        from anylabeling.platform.infrastructure.project_file_store import ProjectFileStore
                        try:
                            labels_data = ProjectFileStore.open_labels(self._project_path)
                            class_names = [lb["name"] for lb in labels_data]
                        except (OSError, _json.JSONDecodeError, KeyError) as exc:
                            logger.warning(
                                "Failed to load labels for inference display: %s",
                                exc,
                            )
                    infer_ws = getattr(self, "_infer_workspace", None)
                    if infer_ws and hasattr(infer_ws, "display_inference_result"):
                        infer_ws.display_inference_result(
                            pending["image_path"], detections, class_names,
                        )
                        # Phase 4 validation: show per-image comparison
                        if hasattr(infer_ws, "display_validation_comparison"):
                            from pathlib import Path as _Path
                            image_name = _Path(pending["image_path"]).name
                            infer_ws.display_validation_comparison(
                                image_name, detections, class_names,
                            )
            except Exception:
                logger.exception("Failed to parse inference results")

        self._pending_infer = None

    def _on_export_requested(self, config: dict) -> None:
        service = getattr(self, "_export_service", None)
        if service is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr("没有可用的导出服务。", "No export service available."),
            )
            return

        run_id = config.get("run_id")
        if not run_id:
            train_ws = self._page_widgets.get(PipelineStep.TRAIN.value)
            if hasattr(train_ws, "active_job_id"):
                run_id = train_ws.active_job_id()

        if not run_id:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr("未选择要导出的 Run。", "No Run selected for export."),
            )
            return

        train_ws = self._page_widgets.get(PipelineStep.TRAIN.value)
        training_service = getattr(train_ws, "training_service", None)
        if training_service is None:
            training_service = getattr(self, "_training_service", None)
        if training_service is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr("没有可用的训练服务。", "No training service available."),
            )
            return

        run = training_service.read_run_record(run_id)
        if run is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr(f"未找到运行记录：{run_id}", f"Run record not found: {run_id}"),
            )
            return

        export_config = {k: v for k, v in config.items() if k != "run_id"}

        try:
            job_id = service.start_export(run=run, export_config=export_config)
            logger.info("Export started: run=%s job=%s", run_id, job_id)
            self._status_bar_widget.set_save_status(
                tr(f"导出已启动：{job_id}", f"Export started: {job_id}")
            )
        except Exception as exc:
            logger.exception("Export failed")
            QtWidgets.QMessageBox.critical(
                self,
                tr("导出错误", "Export Error"),
                tr(f"导出失败：\n{exc}", f"Export failed:\n{exc}"),
            )

    def _on_infer_requested(self, config: dict) -> None:
        service = getattr(self, "_inference_service", None)
        if service is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr("没有可用的推理服务。", "No inference service available."),
            )
            return

        run_id = config.get("run_id")
        if not run_id:
            return

        train_ws = self._page_widgets.get(PipelineStep.TRAIN.value)
        training_service = getattr(train_ws, "training_service", None)
        if training_service is None:
            training_service = getattr(self, "_training_service", None)
        if training_service is None:
            return

        run = training_service.read_run_record(run_id)
        if run is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr(f"未找到运行记录：{run_id}", f"Run record not found: {run_id}"),
            )
            return

        mode = config.get("mode", "single")
        try:
            if mode == "batch":
                assets_dir = str(Path(self._project_path) / "assets")
                job_id = service.infer_batch(
                    run=run,
                    image_dir=assets_dir,
                    conf=config.get("conf", 0.25),
                    iou=config.get("iou", 0.45),
                    imgsz=config.get("imgsz", 640),
                    device=config.get("device", "cpu"),
                )
            else:
                assets_dir = Path(self._project_path) / "assets"
                images = list(assets_dir.glob("*"))
                if not images:
                    QtWidgets.QMessageBox.warning(
                        self,
                        tr("错误", "Error"),
                        tr("assets/ 目录中没有图片。",
                           "No images in assets/ directory."),
                    )
                    return
                job_id = service.infer_image(
                    run=run,
                    image_path=str(images[0]),
                    conf=config.get("conf", 0.25),
                    iou=config.get("iou", 0.45),
                    imgsz=config.get("imgsz", 640),
                    device=config.get("device", "cpu"),
                )

            logger.info("Inference started: run=%s job=%s", run_id, job_id)
            self._status_bar_widget.set_save_status(
                tr(f"推理已启动：{job_id}", f"Inference started: {job_id}")
            )

            if mode == "single":
                self._pending_infer = {
                    "job_id": job_id,
                    "mode": mode,
                    "image_path": config.get("image_path"),
                    "run": run,
                }
                if not hasattr(self, "_infer_poll_timer"):
                    from PyQt6.QtCore import QTimer
                    self._infer_poll_timer = QTimer(self)
                    self._infer_poll_timer.timeout.connect(self._poll_infer_completion)
                self._infer_poll_timer.start(2000)
        except Exception as exc:
            logger.exception("Inference failed")
            QtWidgets.QMessageBox.critical(
                self,
                tr("推理错误", "Inference Error"),
                tr(f"推理失败：\n{exc}", f"Inference failed:\n{exc}"),
            )

    # ------------------------------------------------------------------
    # Internal — asset scanning (DEPRECATED: use AssetRepository instead)
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_assets(project_path: str) -> list[str]:
        """Scan the assets directory for image files.

        Deprecated: Use AssetRepository.scan_assets() instead.
        Kept as fallback for backward compatibility.
        """
        assets_dir = Path(project_path) / "assets"
        if not assets_dir.exists():
            return []
        from anylabeling.platform.domain.import_config import get_supported_extensions
        exts = set(get_supported_extensions())
        return sorted([
            str(p) for p in assets_dir.iterdir()
            if p.is_file() and p.suffix.lower() in exts
        ])

    @staticmethod
    def _count_annotations_by_class(
        project_path: str, label_names: dict[int, str],
    ) -> dict[str, int]:
        """Count annotations grouped by class name.

        Args:
            project_path: Path to the project root.
            label_names: Mapping of label_id -> label_name.

        Returns:
            Dict of class_name -> annotation count.
        """
        import json

        ann_dir = Path(project_path) / "annotations"
        if not ann_dir.is_dir():
            return {}

        counts: dict[str, int] = {}
        for ann_file in ann_dir.glob("*.json"):
            try:
                data = json.loads(ann_file.read_text(encoding="utf-8"))
                for shape in data.get("shapes", []):
                    label = shape.get("label", "unknown")
                    counts[label] = counts.get(label, 0) + 1
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug(
                    "Skipping annotation file %s: %s", ann_file.name, exc
                )

        return dict(sorted(counts.items()))

    @staticmethod
    def _load_runs_for_ai_toolbar(project_path: str) -> list[dict]:
        """Load completed training runs for the AI toolbar model selector.

        Returns:
            List of dicts with keys 'id', 'display_name'.
        """
        import json

        runs: list[dict] = []
        runs_dir = Path(project_path) / "runs"
        if not runs_dir.is_dir():
            return runs

        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            run_json = run_dir / "run.json"
            if not run_json.exists():
                continue
            try:
                data = json.loads(run_json.read_text(encoding="utf-8"))
                if data.get("status") == "completed":
                    runs.append({
                        "id": data.get("id", run_dir.name),
                        "display_name": f"{run_dir.name} ({data.get('task_family', '')})",
                        "adapter_id": data.get("adapter_id", ""),
                    })
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug(
                    "Skipping run JSON %s: %s", run_json.name, exc
                )

        return runs

    def _collect_build_inputs(
        self, project_path: str, task_spec
    ) -> tuple[list, dict, dict]:
        """Collect assets, annotations, and image sources for dataset build."""
        from anylabeling.platform.infrastructure.image_reader import ImageReader
        import numpy as np
        from anylabeling.platform.domain.asset import Asset
        from anylabeling.platform.domain.annotation import (
            AnnotationDocument, AnnotationObject,
        )
        from anylabeling.platform.infrastructure.image_sources.file_source import (
            FileImageSource,
        )

        assets: list = []
        annotations: dict = {}
        image_sources: dict = {}

        assets_dir = Path(project_path) / "assets"
        ann_dir = Path(project_path) / "annotations"

        exts = set(get_supported_extensions())
        for p in sorted(assets_dir.iterdir()):
            if not p.is_file() or p.suffix.lower() not in exts:
                continue

            asset_id = p.stem
            try:
                info = ImageReader.metadata(str(p))
            except Exception:
                continue
            h, w = info.height, info.width

            asset = Asset(
                id=asset_id,
                path=str(p),
                width=w,
                height=h,
            )
            assets.append(asset)
            image_sources[asset_id] = FileImageSource(str(p))

            ann_path = ann_dir / f"{asset_id}.json"
            if ann_path.exists():
                try:
                    import json
                    ann_data = json.loads(ann_path.read_text(encoding="utf-8"))
                    objects = []
                    for shape in ann_data.get("shapes", []):
                        obj = AnnotationObject(
                            id=shape.get("id", f"obj_{len(objects)}"),
                            label_id=self._resolve_label_id(
                                shape.get("label", ""), task_spec
                            ),
                            geometry_type=shape.get("shape_type", "rectangle"),
                            geometry=shape.get("points", []),
                        )
                        objects.append(obj)
                    ann_doc = AnnotationDocument(
                        asset_id=asset_id,
                        image_width=w,
                        image_height=h,
                        objects=objects,
                    )
                    annotations[asset_id] = ann_doc
                except (json.JSONDecodeError, OSError, TypeError) as exc:
                    logger.debug(
                        "Skipping annotation %s: %s", ann_path.name, exc
                    )

        return assets, annotations, image_sources

    @staticmethod
    def _resolve_label_id(label_name: str, task_spec) -> int:
        """Resolve a label name to its ID from the TaskSpec."""
        for lb in task_spec.labels:
            if lb.name == label_name:
                return lb.id
        return -1

    # ------------------------------------------------------------------
    # Model Library
    # ------------------------------------------------------------------

    def _show_model_library(self):
        """Show the model library widget."""
        if self._model_library is None:
            from anylabeling.views.platform.widgets.model_library import (
                ModelLibrary,
            )
            self._model_library = ModelLibrary()
            self._model_library.model_selected.connect(
                self._on_model_selected
            )

        training_service = getattr(self, '_training_service', None)
        if training_service:
            self._model_library.set_training_service(training_service)
        self._replace_page(PipelineStep.MODELS, self._model_library)
        self._pages.setCurrentIndex(PipelineStep.MODELS.value)

    def _on_model_selected(self, run_id: str):
        """Navigate to evaluate/export with pre-selected model."""
        self._navigate_to(PipelineStep.EVALUATE)

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        # Stop polling timers
        for attr in ("_eval_poll_timer", "_infer_poll_timer"):
            timer = getattr(self, attr, None)
            if timer is not None:
                timer.stop()
        if self._job_service is not None:
            self._job_console.set_job_service(None)
            self._task_center_drawer.set_job_service(None)
            self._job_service = None
        self._session.close_project()
        super().closeEvent(event)

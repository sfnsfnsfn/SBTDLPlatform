"""Train Workspace — hyperparameter form + training progress page."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import Dict

from PyQt6 import QtCore, QtGui, QtWidgets

from anylabeling.platform.adapters.registry import AlgorithmRegistry
from anylabeling.platform.adapters.ultralytics.train_adapter import TrainRequest
from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.application.training_service import TrainingService
from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.task import TaskSpec
from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_FAMILY_MONO,
    FONT_SIZE_HERO,
    FONT_SIZE_HEADING,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_MONO,
    get_primary_button_style,
    get_danger_button_style,
    get_combo_style,
    get_scroll_area_style,
    get_log_view_style,
    get_heading_label_style,
    get_caption_label_style,
    get_status_badge_style,
    get_state_color,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2000

# ---------------------------------------------------------------------------
# i18n field label mapping — replaces _format_label() mechanical conversion
# ---------------------------------------------------------------------------

_FIELD_LABELS: dict[str, tuple[str, str]] = {
    # Basic
    "epochs":        ("训练轮数：", "Epochs:"),
    "batch":         ("批次大小：", "Batch:"),
    "imgsz":         ("图像尺寸：", "Image Size:"),
    "device":        ("设备：", "Device:"),
    "workers":       ("工作进程：", "Workers:"),
    "seed":          ("随机种子：", "Seed:"),
    # Optimizer numeric
    "lr0":           ("初始学习率：", "Initial LR:"),
    "lrf":           ("最终学习率因子：", "Final LR Factor:"),
    "momentum":      ("动量：", "Momentum:"),
    "weight_decay":  ("权重衰减：", "Weight Decay:"),
    "warmup_epochs": ("预热轮数：", "Warmup Epochs:"),
    # Optimizer bool
    "cos_lr":        ("余弦学习率调度：", "Cosine LR:"),
    "amp":           ("混合精度：", "AMP:"),
    # Augmentation
    "hsv_h":         ("HSV-H：", "HSV-H:"),
    "hsv_s":         ("HSV-S：", "HSV-S:"),
    "hsv_v":         ("HSV-V：", "HSV-V:"),
    "degrees":       ("旋转角度：", "Degrees:"),
    "translate":     ("平移：", "Translate:"),
    "scale":         ("缩放：", "Scale:"),
    "shear":         ("剪切：", "Shear:"),
    "perspective":   ("透视：", "Perspective:"),
    "fliplr":        ("水平翻转：", "Flip LR:"),
    "mosaic":        ("马赛克：", "Mosaic:"),
    "mixup":         ("混合：", "Mixup:"),
    "copy_paste":    ("复制粘贴：", "Copy-Paste:"),
    "close_mosaic":  ("关闭马赛克：", "Close Mosaic:"),
    # Loss coefficients
    "box":           ("框损失：", "Box Loss:"),
    "cls":           ("分类损失：", "Class Loss:"),
    "dfl":           ("DFL 损失：", "DFL Loss:"),
    "pose":          ("姿态损失：", "Pose Loss:"),
    "kobj":          ("关键点目标损失：", "Keypoint Obj Loss:"),
}

def _format_label(field_name: str) -> str:
    """Return an i18n label for a training hyperparameter field name."""
    labels = _FIELD_LABELS.get(field_name)
    if labels is not None:
        return tr(labels[0], labels[1])
    # Fallback for unknown fields
    return field_name.replace("_", " ").title() + ":"

_BASIC_FIELDS = ["epochs", "batch", "imgsz", "device", "workers", "seed"]
_OPTIMIZER_NUMERIC_FIELDS = [
    "lr0", "lrf", "momentum", "weight_decay", "warmup_epochs",
]
_OPTIMIZER_BOOL_FIELDS = ["cos_lr", "amp"]
_AUGMENTATION_FIELDS = [
    "hsv_h", "hsv_s", "hsv_v", "degrees", "translate", "scale",
    "shear", "perspective", "fliplr", "mosaic", "mixup", "copy_paste",
    "close_mosaic",
]
_LOSS_FIELDS = ["box", "cls", "dfl", "pose", "kobj"]

_OPTIMIZER_CHOICES = ["auto", "SGD", "Adam", "AdamW", "RMSProp"]

_MODEL_SIZE_RANGES = [
    (0, 50, "n"),       # 0-49 → nano
    (50, 201, "s"),     # 50-200 → small
    (201, 1001, "m"),   # 201-1000 → medium
    (1001, float("inf"), "l"),  # 1001+ → large
]


def _recommend_model_size(image_count: int) -> str:
    """Recommend a YOLO model size based on dataset image count.

    Returns:
        One of ``"n"`` (nano), ``"s"`` (small), ``"m"`` (medium),
        ``"l"`` (large).
    """
    for lo, hi, size in _MODEL_SIZE_RANGES:
        if lo <= image_count < hi:
            return size
    return "l"


def _format_recommendation(image_count: int, model_size: str) -> str:
    """Format a human-readable recommendation string."""
    size_names = {"n": "nano", "s": "small", "m": "medium", "l": "large"}
    display = size_names.get(model_size, model_size)
    return tr(
        f"💡 基于 {image_count} 张图片, 推荐: {model_size} ({display})",
        f"💡 Based on {image_count} images, recommend: {model_size} ({display})",
    )


def _create_params_from_schema(
    schema: dict,
) -> tuple[dict[str, QtWidgets.QWidget], dict[str, QtWidgets.QCheckBox]]:
    """Create input widgets from a JSON-Schema-like parameter description.

    Args:
        schema: Dict with ``"type": "object"`` and ``"properties"``
            containing per-parameter type/constraint/default info.

    Returns:
        A tuple of ``(inputs, bools)`` where:
        - *inputs* maps param name → QSpinBox | QDoubleSpinBox | QLineEdit
        - *bools* maps param name → QCheckBox
    """
    inputs: dict[str, QtWidgets.QWidget] = {}
    bools: dict[str, QtWidgets.QCheckBox] = {}

    properties = schema.get("properties", {})
    for name, prop in properties.items():
        ptype = prop.get("type", "number")
        default = prop.get("default")
        minimum = prop.get("minimum")
        maximum = prop.get("maximum")

        if ptype == "boolean":
            cb = QtWidgets.QCheckBox()
            if default is not None:
                cb.setChecked(bool(default))
            bools[name] = cb

        elif ptype == "integer":
            spin = QtWidgets.QSpinBox()
            spin.setMinimum(minimum if minimum is not None else -999999)
            spin.setMaximum(maximum if maximum is not None else 999999)
            if default is not None:
                spin.setValue(int(default))
            inputs[name] = spin

        elif ptype == "number":
            spin = QtWidgets.QDoubleSpinBox()
            spin.setMinimum(minimum if minimum is not None else -999999.0)
            spin.setMaximum(maximum if maximum is not None else 999999.0)
            spin.setDecimals(5)
            if default is not None:
                spin.setValue(float(default))
            inputs[name] = spin

        else:  # string or other
            edit = QtWidgets.QLineEdit()
            edit.setText(str(default) if default is not None else "")
            inputs[name] = edit

    return inputs, bools

_TRAIN_REQUEST_DEFAULTS: Dict[str, object] = {}
for _f in dataclasses.fields(TrainRequest):
    if _f.default is not dataclasses.MISSING and _f.name not in (
        "task_spec", "dataset_build",
    ):
        _TRAIN_REQUEST_DEFAULTS[_f.name] = _f.default
    elif _f.default_factory is not dataclasses.MISSING:
        _TRAIN_REQUEST_DEFAULTS[_f.name] = _f.default_factory()


class _CollapsibleGroup(QtWidgets.QGroupBox):
    """A QGroupBox that hides/shows its content widget when toggled."""

    def __init__(self, title: str, collapsed: bool = False,
                 parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(not collapsed)
        self._title = title
        self._content_widget: QtWidgets.QWidget | None = None

    def set_content(self, widget: QtWidgets.QWidget) -> None:
        self._content_widget = widget
        lay = QtWidgets.QVBoxLayout()
        lay.setContentsMargins(4, 8, 4, 4)
        lay.addWidget(widget)
        self.setLayout(lay)
        self.toggled.connect(self._on_toggled)
        # Apply initial visibility
        self._on_toggled(self.isChecked())

    def _on_toggled(self, checked: bool) -> None:
        if self._content_widget is not None:
            self._content_widget.setVisible(checked)

    def expand(self) -> None:
        self.setChecked(True)

    def collapse(self) -> None:
        self.setChecked(False)


class TrainWorkspace(QtWidgets.QWidget):
    """Train Workspace page — hyperparameter form + training progress."""

    training_started = QtCore.pyqtSignal(str)
    training_finished = QtCore.pyqtSignal(str, str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self._job_service: JobService | None = None
        self._training_service: TrainingService | None = None
        self._task_specs: list[TaskSpec] = []
        self._dataset_builds: list[DatasetBuild] = []
        self._active_job_id: str | None = None
        self._run_vm = None

        self._numeric_inputs: dict[str, QtWidgets.QWidget] = {}
        self._bool_inputs: dict[str, QtWidgets.QCheckBox] = {}
        self._dynamic_param_container: QtWidgets.QWidget | None = None
        self._current_adapter_id: str = ""

        self._setup_ui()
        self._populate_algorithm_combo()

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._poll_status)
        self._timer.setInterval(_POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project_context(
        self,
        job_service: JobService,
        training_service: TrainingService,
        task_specs: list[TaskSpec] | None = None,
        dataset_builds: list[DatasetBuild] | None = None,
    ) -> None:
        self._job_service = job_service
        self._training_service = training_service

        from anylabeling.views.platform.view_models.run_vm import RunViewModel
        self._run_vm = RunViewModel(job_service, training_service)

        if task_specs is not None:
            self._task_specs = task_specs
            self._populate_task_combo()

        if dataset_builds is not None:
            self._dataset_builds = dataset_builds
            self._populate_dataset_combo()

        self._populate_algorithm_combo()
        self._update_model_size_recommendation()

        # Run recovery check for orphaned training runs
        self._check_orphaned_runs()

        # Show readiness widget if we have required context
        if self._training_service and self._task_specs:
            self._update_readiness()

        # Timer starts only when a training job is active (lazy polling)
        self._update_button_states()

    def set_task_specs(self, task_specs: list[TaskSpec]) -> None:
        self._task_specs = task_specs
        self._populate_task_combo()

    def set_dataset_builds(self, dataset_builds: list[DatasetBuild]) -> None:
        self._dataset_builds = dataset_builds
        self._populate_dataset_combo()

    def job_service(self) -> JobService | None:
        return self._job_service

    def training_service(self) -> TrainingService | None:
        return self._training_service

    def active_job_id(self) -> str | None:
        return self._active_job_id

    # ------------------------------------------------------------------
    # Mode switching (progressive disclosure)
    # ------------------------------------------------------------------

    def _safe_collapse(self, attr_name: str) -> None:
        """Collapse a QGroupBox if it exists (safe when dynamic params replace static groups)."""
        group = getattr(self, attr_name, None)
        if group is not None:
            group.collapse()

    def _safe_expand(self, attr_name: str) -> None:
        """Expand a QGroupBox if it exists (safe when dynamic params replace static groups)."""
        group = getattr(self, attr_name, None)
        if group is not None:
            group.expand()

    def _check_orphaned_runs(self):
        """Check for orphaned training runs and show recovery prompt."""
        training_service = getattr(self, '_training_service', None)
        if training_service is None:
            return
        try:
            orphaned = training_service.find_orphaned_runs()
            if orphaned:
                run_ids = ', '.join(r.id for r in orphaned)
                self._lbl_recovery.setText(
                    tr(
                        f'检测到 {len(orphaned)} 个未完成的训练运行：'
                        f'{run_ids}。建议先恢复或丢弃这些运行。',
                        f'Found {len(orphaned)} unfinished training runs: '
                        f'{run_ids}. Consider recovering or discarding '
                        f'them first.',
                    )
                )
                self._lbl_recovery.setVisible(True)
        except Exception:
            logger.warning(
                "Failed to check for orphaned training runs",
                exc_info=True,
            )

    def _update_readiness(self):
        """Update training readiness display."""
        training_service = getattr(self, '_training_service', None)
        if training_service is None:
            return
        if not hasattr(self, '_readiness_widget'):
            return

        task_spec = (
            self._combo_task.currentData()
            if hasattr(self, '_combo_task')
            else None
        )
        build = (
            self._combo_dataset.currentData()
            if hasattr(self, '_combo_dataset')
            else None
        )

        try:
            report = training_service.validate_training_readiness(
                task_spec, build,
            )
            self._readiness_widget.set_report(report)
            self._readiness_widget.setVisible(True)
        except Exception:
            logger.warning(
                "Failed to update training readiness display",
                exc_info=True,
            )

    def _on_mode_changed(self, index: int) -> None:
        """Apply training mode: collapse/expand advanced groups and set presets."""
        mode = self._mode_combo.itemData(index)
        if mode is None:
            return

        if mode == "quick":
            self._safe_collapse("_opt_group")
            self._safe_collapse("_aug_group")
            self._safe_collapse("_loss_group")
            self._apply_mode_presets("quick")
        elif mode == "precision":
            self._safe_expand("_opt_group")
            self._safe_collapse("_aug_group")
            self._safe_collapse("_loss_group")
            self._apply_mode_presets("precision")
        else:  # custom
            self._safe_expand("_opt_group")
            self._safe_expand("_aug_group")
            self._safe_expand("_loss_group")

    def _apply_mode_presets(self, mode: str) -> None:
        """Apply predefined values based on training mode."""
        if mode == "quick":
            # Quick: fewer epochs, larger batch
            self._numeric_inputs["epochs"].setText("50")
            self._numeric_inputs["batch"].setText("16")
            self._numeric_inputs["imgsz"].setText("640")
            self._numeric_inputs["lr0"].setText("0.01")
        elif mode == "precision":
            # High precision: more epochs, moderate batch
            self._numeric_inputs["epochs"].setText("300")
            self._numeric_inputs["batch"].setText("16")
            self._numeric_inputs["imgsz"].setText("640")
            self._numeric_inputs["lr0"].setText("0.01")
            self._numeric_inputs["lrf"].setText("0.01")
            self._numeric_inputs["weight_decay"].setText("0.0005")
            self._bool_inputs.get("cos_lr", None)

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QtWidgets.QVBoxLayout()
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Header row: title + training mode selector
        header_row = QtWidgets.QHBoxLayout()
        header = QtWidgets.QLabel(tr("训练工作区", "Train Workspace"))
        header.setStyleSheet(get_heading_label_style())
        header_row.addWidget(header)
        header_row.addStretch()

        header_row.addWidget(QtWidgets.QLabel(tr("模式：", "Mode:")))
        self._mode_combo = QtWidgets.QComboBox()
        self._mode_combo.addItem(tr("快速训练", "Quick"), "quick")
        self._mode_combo.addItem(tr("高精度", "High Precision"), "precision")
        self._mode_combo.addItem(tr("自定义", "Custom"), "custom")
        self._mode_combo.setCurrentIndex(0)
        self._mode_combo.setStyleSheet(get_combo_style())
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        header_row.addWidget(self._mode_combo)
        root.addLayout(header_row)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_config_panel())
        splitter.addWidget(self._create_progress_panel())
        splitter.setSizes([480, 520])
        root.addWidget(splitter, stretch=1)

        root.addLayout(self._create_action_bar())
        self.setLayout(root)

    def _create_config_panel(self) -> QtWidgets.QWidget:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(get_scroll_area_style())

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._create_basic_group())

        # Model size recommendation label
        self._lbl_model_size_rec = QtWidgets.QLabel()
        self._lbl_model_size_rec.setStyleSheet(get_caption_label_style())
        self._lbl_model_size_rec.setToolTip(tr(
            "基于当前数据集图片数量自动推荐模型规模。",
            "Auto-recommends model size based on dataset image count.",
        ))
        layout.addWidget(self._lbl_model_size_rec)

        # Dynamic parameter container (populated on algorithm change)
        self._dynamic_param_container = QtWidgets.QWidget()
        self._dynamic_param_layout = QtWidgets.QVBoxLayout()
        self._dynamic_param_layout.setContentsMargins(0, 0, 0, 0)
        self._dynamic_param_layout.setSpacing(4)
        self._dynamic_param_container.setLayout(self._dynamic_param_layout)
        self._dynamic_param_container.setVisible(True)
        layout.addWidget(self._dynamic_param_container)

        # TrainReadinessWidget — embedded readiness checklist
        from anylabeling.views.platform.widgets.train_readiness_widget import (
            TrainReadinessWidget,
        )
        self._readiness_widget = TrainReadinessWidget()
        self._readiness_widget.setVisible(False)
        layout.addWidget(self._readiness_widget)

        # Incremental training checkbox — hidden until backend wiring complete (Phase 3)
        self._chk_resume = QtWidgets.QCheckBox(
            tr("从上次最佳权重继续训练", "Resume from last best weights")
        )
        self._chk_resume.setToolTip(tr(
            "（规划中）如果存在上次训练的最佳权重文件，将从此继续训练。",
            "(planned) If the best checkpoint exists from a previous run, training resumes from it."
        ))
        self._chk_resume.setVisible(False)
        layout.addWidget(self._chk_resume)

        layout.addStretch()

        container.setLayout(layout)
        scroll.setWidget(container)
        return scroll

    def _create_progress_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout()
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        progress_header = QtWidgets.QLabel(tr("训练进度", "Progress"))
        progress_header.setStyleSheet(get_heading_label_style())
        lay.addWidget(progress_header)

        # Training monitor graph (embedded matplotlib)
        from anylabeling.views.platform.widgets.training_monitor import TrainingMonitor
        self._training_monitor = TrainingMonitor()
        lay.addWidget(self._training_monitor, stretch=0)
        self._training_monitor.setMinimumHeight(200)
        self._training_monitor.setMaximumHeight(280)

        status_row = QtWidgets.QHBoxLayout()
        status_row.addWidget(QtWidgets.QLabel(tr("状态：", "Status:")))
        self._lbl_status = QtWidgets.QLabel(tr("空闲", "IDLE"))
        self._lbl_status.setStyleSheet(
            get_status_badge_style("idle")
        )
        status_row.addWidget(self._lbl_status)
        status_row.addStretch()
        lay.addLayout(status_row)

        self._lbl_epoch = QtWidgets.QLabel(tr("轮次：--", "Epoch: --"))
        self._lbl_epoch.setStyleSheet(
            f"font-size: {FONT_SIZE_HERO - 2}px;"
            f"font-weight: bold; color: {get_theme()['text']};"
            f"font-family: {FONT_FAMILY};"
        )
        lay.addWidget(self._lbl_epoch)

        t = get_theme()
        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {t["border"]};
                border-radius: 6px;
                text-align: center;
                height: 24px;
                background-color: {t["surface"]};
                font-family: {FONT_FAMILY};
            }}
            QProgressBar::chunk {{
                background-color: {t["primary"]};
                border-radius: 5px;
            }}
        """)
        lay.addWidget(self._progress_bar)

        self._lbl_best_metric = QtWidgets.QLabel(tr("最佳：--", "Best: --"))
        self._lbl_best_metric.setStyleSheet(
            f"font-size: {FONT_SIZE_BODY}px; color: {t['success']};"
            f"font-family: {FONT_FAMILY};"
        )
        lay.addWidget(self._lbl_best_metric)

        # Recovery suggestion (hidden by default, shown on failure)
        self._lbl_recovery = QtWidgets.QLabel()
        self._lbl_recovery.setWordWrap(True)
        self._lbl_recovery.setVisible(False)
        self._lbl_recovery.setStyleSheet(
            f"font-size: {FONT_SIZE_CAPTION}px; color: {t['text_secondary']};"
            f"font-family: {FONT_FAMILY};"
        )
        lay.addWidget(self._lbl_recovery)

        log_header = QtWidgets.QLabel(tr("日志", "Log"))
        log_header.setStyleSheet(get_heading_label_style())
        lay.addWidget(log_header)

        self._log_view = QtWidgets.QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setPlaceholderText(
            tr("训练输出将显示在这里...", "Training output will appear here...")
        )
        self._log_view.setStyleSheet(get_log_view_style())
        lay.addWidget(self._log_view, stretch=1)

        panel.setLayout(lay)
        return panel

    def _create_action_bar(self) -> QtWidgets.QLayout:
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(12)
        bar.addStretch()

        self._btn_start = QtWidgets.QPushButton(tr("开始训练", "Start Training"))
        self._btn_start.setMinimumWidth(140)
        self._btn_start.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._btn_start.setStyleSheet(get_primary_button_style(min_width=140))
        self._btn_start.clicked.connect(self._on_start)
        bar.addWidget(self._btn_start)

        self._btn_stop = QtWidgets.QPushButton(tr("停止", "Stop"))
        self._btn_stop.setMinimumWidth(100)
        self._btn_stop.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._btn_stop.setStyleSheet(get_danger_button_style(min_width=100))
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setEnabled(False)
        bar.addWidget(self._btn_stop)

        bar.addStretch()
        return bar

    # ------------------------------------------------------------------
    # Form group factories
    # ------------------------------------------------------------------

    def _create_basic_group(self) -> _CollapsibleGroup:
        group = _CollapsibleGroup(tr("基本参数", "Basic"))
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)

        self._combo_task = QtWidgets.QComboBox()
        self._combo_task.setToolTip(tr("选择任务规格", "Select the task specification"))
        form.addRow(tr("任务：", "Task:"), self._combo_task)

        self._combo_dataset = QtWidgets.QComboBox()
        self._combo_dataset.setToolTip(tr("选择数据集构建", "Select the dataset build"))
        form.addRow(tr("数据集构建：", "Dataset Build:"), self._combo_dataset)

        self._combo_algorithm = QtWidgets.QComboBox()
        self._combo_algorithm.setToolTip(tr("训练算法", "Training algorithm"))
        form.addRow(tr("算法：", "Algorithm:"), self._combo_algorithm)

        self._edit_base_model = QtWidgets.QLineEdit()
        self._edit_base_model.setPlaceholderText(
            tr(".pt 模型文件路径", "Path to .pt model file")
        )
        self._edit_base_model.setToolTip(
            tr("用于开始训练的本地 .pt 模型文件",
               "Local .pt model file to start training from")
        )
        form.addRow(tr("基础模型：", "Base Model:"), self._edit_base_model)

        for field_name in _BASIC_FIELDS:
            default_value = _TRAIN_REQUEST_DEFAULTS.get(field_name, "")
            label = _format_label(field_name)
            edit = QtWidgets.QLineEdit()
            edit.setText(str(default_value))
            edit.setToolTip(f"Training hyperparameter: {field_name}")
            self._numeric_inputs[field_name] = edit
            form.addRow(label, edit)

        widget.setLayout(form)
        group.set_content(widget)
        return group

    def _create_optimizer_group(self) -> _CollapsibleGroup:
        group = _CollapsibleGroup(tr("优化器", "Optimizer"), collapsed=True)
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)

        self._combo_optimizer = QtWidgets.QComboBox()
        self._combo_optimizer.addItems(_OPTIMIZER_CHOICES)
        self._combo_optimizer.setCurrentText(
            str(_TRAIN_REQUEST_DEFAULTS.get("optimizer", "auto"))
        )
        form.addRow(tr("优化器：", "Optimizer:"), self._combo_optimizer)

        for field_name in _OPTIMIZER_NUMERIC_FIELDS:
            default_value = _TRAIN_REQUEST_DEFAULTS.get(field_name, "")
            label = _format_label(field_name)
            edit = QtWidgets.QLineEdit()
            edit.setText(str(default_value))
            edit.setToolTip(f"Optimizer hyperparameter: {field_name}")
            self._numeric_inputs[field_name] = edit
            form.addRow(label, edit)

        for field_name in _OPTIMIZER_BOOL_FIELDS:
            default_value = bool(_TRAIN_REQUEST_DEFAULTS.get(field_name, False))
            label = _format_label(field_name)
            cb = QtWidgets.QCheckBox()
            cb.setChecked(default_value)
            self._bool_inputs[field_name] = cb
            form.addRow(label, cb)

        widget.setLayout(form)
        group.set_content(widget)
        return group

    def _create_augmentation_group(self) -> _CollapsibleGroup:
        group = _CollapsibleGroup(tr("数据增强", "Augmentation"), collapsed=True)
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)

        for field_name in _AUGMENTATION_FIELDS:
            default_value = _TRAIN_REQUEST_DEFAULTS.get(field_name, "")
            label = _format_label(field_name)
            edit = QtWidgets.QLineEdit()
            edit.setText(str(default_value))
            edit.setToolTip(f"Augmentation hyperparameter: {field_name}")
            self._numeric_inputs[field_name] = edit
            form.addRow(label, edit)

        widget.setLayout(form)
        group.set_content(widget)
        return group

    def _create_loss_group(self) -> _CollapsibleGroup:
        group = _CollapsibleGroup(tr("损失函数", "Loss"), collapsed=True)
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)

        for field_name in _LOSS_FIELDS:
            default_value = _TRAIN_REQUEST_DEFAULTS.get(field_name, "")
            label = _format_label(field_name)
            edit = QtWidgets.QLineEdit()
            edit.setText(str(default_value))
            edit.setToolTip(f"Loss coefficient: {field_name}")
            self._numeric_inputs[field_name] = edit
            form.addRow(label, edit)

        widget.setLayout(form)
        group.set_content(widget)
        return group

    # ------------------------------------------------------------------
    # Combo population
    # ------------------------------------------------------------------

    def _populate_task_combo(self) -> None:
        self._combo_task.clear()
        for ts in self._task_specs:
            self._combo_task.addItem(f"{ts.id} ({ts.family})", ts)
        # Connect task change → filter algorithms by family
        try:
            self._combo_task.currentIndexChanged.disconnect(
                self._on_task_changed
            )
        except TypeError:
            pass
        self._combo_task.currentIndexChanged.connect(self._on_task_changed)

    def _on_task_changed(self, index: int) -> None:
        """When task is selected, filter algorithms by task family."""
        if index < 0:
            return
        ts = self._combo_task.itemData(index)
        if ts is not None:
            self._populate_algorithm_combo_for_family(ts.family)

    def _populate_dataset_combo(self) -> None:
        self._combo_dataset.clear()
        for db in self._dataset_builds:
            self._combo_dataset.addItem(db.id, db)
        # Connect dataset change → update model size recommendation
        try:
            self._combo_dataset.currentIndexChanged.disconnect(
                self._on_dataset_changed
            )
        except TypeError:
            pass
        self._combo_dataset.currentIndexChanged.connect(
            self._on_dataset_changed
        )

    def _on_dataset_changed(self, index: int) -> None:
        """When dataset is selected, update model size recommendation."""
        if index < 0:
            return
        self._update_model_size_recommendation()

    def _populate_algorithm_combo(self) -> None:
        """Populate algorithm combo from all registered trainable algorithms."""
        self._combo_algorithm.clear()
        for cap in AlgorithmRegistry.list_all():
            if cap.supports_training:
                self._combo_algorithm.addItem(cap.display_name, cap.adapter_id)
        # Connect algorithm change signal (once)
        try:
            self._combo_algorithm.currentIndexChanged.disconnect(
                self._on_algorithm_changed
            )
        except TypeError:
            pass
        self._combo_algorithm.currentIndexChanged.connect(
            self._on_algorithm_changed
        )

    def _populate_algorithm_combo_for_family(self, family: str) -> None:
        """Populate algorithm combo filtered by task family."""
        self._combo_algorithm.clear()
        caps = AlgorithmRegistry.for_task(family)
        trainable = [c for c in caps if c.supports_training]
        for cap in trainable:
            self._combo_algorithm.addItem(cap.display_name, cap.adapter_id)

    def _on_algorithm_changed(self, index: int) -> None:
        """When algorithm selection changes, regenerate the param panel."""
        if index < 0:
            return
        adapter_id = self._combo_algorithm.itemData(index)
        if not adapter_id or adapter_id == self._current_adapter_id:
            return
        self._current_adapter_id = adapter_id
        self._regenerate_param_panel(adapter_id)

    def _regenerate_param_panel(self, adapter_id: str) -> None:
        """Clear dynamic param widgets and refill from provider schema.

        Preserves basic parameter entries (epochs, batch, imgsz, …) that are
        created by ``_create_basic_group`` and must survive algorithm switches.
        """
        if self._dynamic_param_layout is None:
            return

        # Save basic field references before clearing
        _BASIC_KEYS = {"epochs", "batch", "imgsz", "device", "workers", "seed"}
        saved_numeric = {k: v for k, v in self._numeric_inputs.items() if k in _BASIC_KEYS}
        saved_bool = {k: v for k, v in self._bool_inputs.items() if k in _BASIC_KEYS}

        # Clear dynamic layout widgets
        while self._dynamic_param_layout.count():
            item = self._dynamic_param_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._numeric_inputs.clear()
        self._bool_inputs.clear()

        # Restore basic fields
        self._numeric_inputs.update(saved_numeric)
        self._bool_inputs.update(saved_bool)

        # Resolve provider and get schema
        try:
            provider = AlgorithmRegistry.get_provider(adapter_id)
        except KeyError:
            return

        if provider.train_adapter is None:
            return

        schema = provider.train_adapter.train_param_schema()
        inputs, bools = _create_params_from_schema(schema)

        # Layout the dynamic params in a form
        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)

        # Sort: top-level params first, then nested
        param_order = list(schema.get("properties", {}).keys())
        for name in param_order:
            if name in inputs:
                label = _format_label(name)
                form.addRow(label, inputs[name])
                self._numeric_inputs[name] = inputs[name]
            elif name in bools:
                label = _format_label(name)
                form.addRow(label, bools[name])
                self._bool_inputs[name] = bools[name]

        dyn_widget = QtWidgets.QWidget()
        dyn_widget.setLayout(form)
        self._dynamic_param_layout.addWidget(dyn_widget)

    def _update_model_size_recommendation(self) -> None:
        """Update the recommendation label based on selected dataset."""
        db = self._combo_dataset.currentData()
        if db is None:
            self._lbl_model_size_rec.setText("")
            return

        # Try to count images from dataset build
        image_count = self._count_dataset_images(db)
        if image_count is None or image_count == 0:
            self._lbl_model_size_rec.setText("")
            return

        size = _recommend_model_size(image_count)
        self._lbl_model_size_rec.setText(
            _format_recommendation(image_count, size)
        )

    def _count_dataset_images(self, db: DatasetBuild) -> int | None:
        """Count images in a DatasetBuild, returns None if unknown."""
        if db.output_path:
            data_path = Path(db.output_path)
            if data_path.exists():
                # Look for images in train/val subdirs
                count = 0
                for sub in ["train", "val", "test"]:
                    images_dir = data_path / sub / "images"
                    if images_dir.exists():
                        count += len([
                            f for f in images_dir.iterdir()
                            if f.suffix.lower() in
                            (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")
                        ])
                return count if count > 0 else None
        return None

    # ------------------------------------------------------------------
    # Field extraction → TrainRequest
    # ------------------------------------------------------------------

    def _get_widget_value(self, widget: QtWidgets.QWidget):
        """Extract value from a form widget regardless of its concrete type."""
        if isinstance(widget, QtWidgets.QSpinBox):
            return widget.value()
        elif isinstance(widget, QtWidgets.QDoubleSpinBox):
            return widget.value()
        elif isinstance(widget, QtWidgets.QLineEdit):
            text = widget.text().strip()
            if not text:
                return None
            try:
                return int(text)
            except ValueError:
                try:
                    return float(text)
                except ValueError:
                    return text
        elif isinstance(widget, QtWidgets.QCheckBox):
            return widget.isChecked()
        return None

    def _build_train_request(self) -> TrainRequest | None:
        task_spec = self._combo_task.currentData()
        if task_spec is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("验证", "Validation"),
                tr("请选择任务。", "Please select a Task."),
            )
            return None

        dataset_build = self._combo_dataset.currentData()
        if dataset_build is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("验证", "Validation"),
                tr("请选择数据集构建。", "Please select a Dataset Build."),
            )
            return None

        base_model = self._edit_base_model.text().strip()
        if not base_model:
            QtWidgets.QMessageBox.warning(
                self,
                tr("验证", "Validation"),
                tr("请指定基础模型路径。", "Please specify a Base Model path."),
            )
            return None

        kwargs: dict = {
            "task_spec": task_spec,
            "dataset_build": dataset_build,
            "base_model": base_model,
        }

        for field_name, widget in self._numeric_inputs.items():
            val = self._get_widget_value(widget)
            if val is None:
                default_val = _TRAIN_REQUEST_DEFAULTS.get(field_name)
                if default_val is not None:
                    kwargs[field_name] = default_val
                continue
            kwargs[field_name] = val

        # Preserve optimizer combo if still present
        if hasattr(self, "_combo_optimizer"):
            kwargs["optimizer"] = self._combo_optimizer.currentText()

        for field_name, cb in self._bool_inputs.items():
            kwargs[field_name] = cb.isChecked()

        # Incremental training (resume)
        kwargs["resume"] = self._chk_resume.isChecked()

        return TrainRequest(**kwargs)

    # ------------------------------------------------------------------
    # Start / Stop handlers
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        request = self._build_train_request()
        if request is None:
            return

        if self._run_vm is None:
            QtWidgets.QMessageBox.warning(
                self,
                tr("错误", "Error"),
                tr("未设置项目上下文。", "No project context set."),
            )
            return

        try:
            job_id = self._run_vm.start_training(request)
        except Exception as exc:
            logger.exception("Failed to start training")
            QtWidgets.QMessageBox.critical(
                self,
                tr("错误", "Error"),
                tr(f"启动训练失败：\n{exc}", f"Failed to start training:\n{exc}"),
            )
            return

        self._active_job_id = job_id
        self._timer.start()  # Start polling only when job is active

        # Connect training monitor to active job
        if self._training_service is not None:
            runs_root = str(self._training_service.project_root / "runs")
            self._training_monitor.set_active_job(job_id, runs_root)

        self.training_started.emit(job_id)

        self._lbl_status.setText(tr("启动中", "STARTING"))
        self._lbl_status.setStyleSheet(get_status_badge_style("starting"))
        self._lbl_epoch.setText(tr("轮次：--", "Epoch: --"))
        self._progress_bar.setValue(0)
        self._lbl_best_metric.setText(tr("最佳：--", "Best: --"))
        self._log_view.clear()
        self._log_view.append(f"Training job started: {job_id}")

        self._update_button_states()

    def _on_stop(self) -> None:
        if not self._active_job_id or self._run_vm is None:
            return

        try:
            self._run_vm.stop_training(self._active_job_id)
            self._log_view.append(
                tr("停止信号已发送 — 等待优雅关闭...",
                   "Stop signal sent — waiting for graceful shutdown...")
            )
            self._training_monitor.clear_active_job()
        except Exception as exc:
            logger.exception("Failed to stop training")
            QtWidgets.QMessageBox.critical(
                self,
                tr("错误", "Error"),
                tr(f"停止训练失败：\n{exc}", f"Failed to stop training:\n{exc}"),
            )

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _poll_status(self) -> None:
        if not self._active_job_id or self._run_vm is None:
            return
        if self._training_service is None:
            return

        try:
            status = self._run_vm.get_status(self._active_job_id)
        except Exception:
            logger.warning(
                "Poll failed for job %s", self._active_job_id, exc_info=True
            )
            self._lbl_status.setText(tr("轮询错误", "POLL ERROR"))
            self._lbl_status.setStyleSheet(get_status_badge_style("failed"))
            return

        state: str = status.get("state", "unknown")
        epoch: int = status.get("epoch", 0)
        best_metric: dict | None = status.get("best_metric")

        self._lbl_status.setText(state.upper())
        self._lbl_status.setStyleSheet(get_status_badge_style(state))

        epochs_input = self._numeric_inputs.get("epochs")
        total_epochs = 0
        if epochs_input is not None:
            try:
                if isinstance(epochs_input, QtWidgets.QSpinBox):
                    total_epochs = epochs_input.value()
                elif isinstance(epochs_input, QtWidgets.QLineEdit):
                    total_epochs = int(epochs_input.text().strip())
            except (ValueError, TypeError):
                total_epochs = 0

        if total_epochs > 0:
            self._lbl_epoch.setText(f"Epoch: {epoch}/{total_epochs}")
            self._progress_bar.setMaximum(total_epochs)
            self._progress_bar.setValue(min(epoch, total_epochs))
        else:
            self._lbl_epoch.setText(f"Epoch: {epoch}")

        if best_metric is not None:
            name = best_metric.get("name", "")
            value = best_metric.get("value", 0.0)
            self._lbl_best_metric.setText(f"Best: {name}={value:.4f}")

        self._update_logs()

        if state in ("completed", "failed", "cancelled"):
            # Show recovery suggestions on failure
            if state == "failed":
                self._lbl_recovery.setText(tr(
                    "建议：检查日志中的错误信息 → 验证数据集路径 → 确认 GPU/显存充足 → 调整 batch size 或 imgsz 后重试",
                    "Suggestions: Check error in logs → Verify dataset path → Ensure GPU/VRAM available → Try reducing batch size or imgsz"
                ))
                self._lbl_recovery.setVisible(True)
            elif state == "completed":
                self._lbl_recovery.setText(tr(
                    "训练完成！你可以在「评估」页查看指标，或在「导出」页导出模型。",
                    "Training complete! View metrics in Evaluate page, or export the model in Export page."
                ))
                self._lbl_recovery.setVisible(True)

            # C8: Parse training results and update Run record on completion
            if state == "completed" and self._training_service is not None:
                try:
                    updated_run = self._training_service.parse_and_update_run(
                        self._active_job_id
                    )
                    if updated_run is not None and updated_run.best_metric:
                        bm = updated_run.best_metric
                        self._lbl_best_metric.setText(
                            f"Best: {bm.get('name', '')}={bm.get('value', 0):.4f}"
                        )
                except Exception:
                    logger.warning(
                        "Failed to parse training results for %s",
                        self._active_job_id, exc_info=True
                    )

            self._timer.stop()  # Stop polling on terminal state
            self._training_monitor.clear_active_job()
            self.training_finished.emit(self._active_job_id, state)
            self._update_button_states()

    def _update_logs(self) -> None:
        if not self._active_job_id or self._job_service is None:
            return

        try:
            stdout, stderr = self._job_service.get_job_logs(self._active_job_id)
        except Exception:
            logger.warning(
                "Failed to fetch logs for job %s", self._active_job_id,
                exc_info=True,
            )
            self._log_view.setPlainText(
                tr("⚠ 错误：获取训练日志失败",
                   "⚠ Error: Failed to fetch training logs from job service.")
            )
            return

        parts: list[str] = []
        if stdout:
            lines = stdout.splitlines()
            parts.extend(lines[-60:])
        if stderr:
            parts.append("--- stderr ---")
            lines = stderr.splitlines()
            parts.extend(lines[-20:])

        new_text = "\n".join(parts)
        if new_text and new_text != self._log_view.toPlainText():
            self._log_view.setPlainText(new_text)
            sb = self._log_view.verticalScrollBar()
            if sb is not None:
                sb.setValue(sb.maximum())

    def _update_button_states(self) -> None:
        is_running = False
        if self._active_job_id and self._run_vm is not None:
            try:
                status = self._run_vm.get_status(self._active_job_id)
                state = status.get("state", "")
                is_running = state in ("queued", "starting", "running")
            except Exception:
                logger.warning(
                    "Failed to poll job status for button state update",
                    exc_info=True,
                )
                return

        has_context = self._job_service is not None
        self._btn_start.setEnabled(has_context and not is_running)
        self._btn_stop.setEnabled(is_running)

    def closeEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        if self._timer.isActive():
            self._timer.stop()
        super().closeEvent(event)


def _coerce_value(field_name: str, text: str) -> int | float | str:
    default_val = _TRAIN_REQUEST_DEFAULTS.get(field_name)
    if default_val is not None:
        if isinstance(default_val, bool):
            return text.lower() in ("true", "1", "yes")
        if isinstance(default_val, int):
            return int(text)
        if isinstance(default_val, float):
            return float(text)
        return text
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


__all__ = [
    "TrainWorkspace",
    "_recommend_model_size",
    "_format_recommendation",
    "_create_params_from_schema",
]

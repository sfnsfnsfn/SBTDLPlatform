"""Export Workspace — ONNX model export (Phase 4)."""

from __future__ import annotations

import logging
from pathlib import Path

from anylabeling.views.platform.i18n import tr

logger = logging.getLogger(__name__)


def _deploy_tree_items() -> list[tuple[str, str, list | None]]:
    """Return the deploy preview tree structure (PRD §7.10 — 10 items).

    Each item is (name, tooltip, children|None).
    """
    from anylabeling.platform.domain.export_config import DEPLOY_PACKAGE_FILES

    children: list[tuple[str, str, list | None]] = []
    for filename, description in DEPLOY_PACKAGE_FILES:
        children.append((filename, description, None))
    return [
        (
            "deployment/",
            tr("部署包根目录", "Deployment package root"),
            children,
        ),
    ]


try:  # noqa: C901
    from PyQt6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QGroupBox,
        QFormLayout,
        QSpinBox,
        QCheckBox,
        QPushButton,
        QLabel,
        QComboBox,
        QTreeWidget,
        QTreeWidgetItem,
        QScrollArea,
        QProgressBar,
    )
    from PyQt6.QtCore import pyqtSignal, Qt

    class ExportWorkspace(QWidget):
        export_requested = pyqtSignal(dict)

        def __init__(self, parent=None):
            super().__init__(parent)

            self._context = None

            # ----------------------------------------------------------
            # Run selection
            # ----------------------------------------------------------
            run_group = QGroupBox(tr("运行选择", "Run Selection"))
            run_layout = QHBoxLayout()
            run_layout.addWidget(QLabel(tr("运行：", "Run:")))
            self._run_combo = QComboBox()
            self._run_combo.currentIndexChanged.connect(self._on_run_changed)
            run_layout.addWidget(self._run_combo, 1)
            run_group.setLayout(run_layout)

            # ----------------------------------------------------------
            # Target environment selection
            # ----------------------------------------------------------
            self._target_group = QGroupBox(
                tr("目标环境", "Target Environment")
            )
            target_layout = QHBoxLayout()
            self._target_btns: dict[str, QPushButton] = {}

            from anylabeling.platform.domain.export_config import (
                EXPORT_TARGETS,
            )

            for target in EXPORT_TARGETS:
                btn = QPushButton(target.display_name)
                btn.setCheckable(True)
                btn.setToolTip(target.description)
                btn.clicked.connect(
                    lambda checked, t=target.id: self._on_target_selected(t)
                )
                self._target_btns[target.id] = btn
                target_layout.addWidget(btn)

            self._target_btns["onnx_generic"].setChecked(True)
            self._selected_target = "onnx_generic"
            self._target_group.setLayout(target_layout)

            # ----------------------------------------------------------
            # Compatibility check
            # ----------------------------------------------------------
            self._compat_group = QGroupBox(
                tr("运行状态", "Run Status")
            )
            compat_layout = QVBoxLayout()
            self._compat_labels: dict[str, QLabel] = {}

            compat_checks = [
                ("task_support", tr("任务支持", "Task Support")),
                (
                    "weight_integrity",
                    tr("权重完整性", "Weight Integrity"),
                ),
                ("input_size", tr("输入尺寸", "Input Size")),
                ("labels", tr("标签", "Labels")),
                (
                    "pre_post",
                    tr("预/后处理", "Pre/Post Processing"),
                ),
            ]
            for check_id, check_name in compat_checks:
                row = QHBoxLayout()
                icon = QLabel("—")
                icon.setFixedWidth(20)
                label = QLabel(check_name)
                row.addWidget(icon)
                row.addWidget(label, 1)
                compat_layout.addLayout(row)
                self._compat_labels[check_id] = icon

            self._compat_group.setLayout(compat_layout)

            # ----------------------------------------------------------
            # Format — ONNX only (Phase 4)
            # ----------------------------------------------------------
            self._format_label = QLabel(
                tr("导出格式：ONNX", "Export Format: ONNX")
            )

            # ----------------------------------------------------------
            # Deploy preview (PRD §7.10 — 10 items)
            # ----------------------------------------------------------
            preview_group = QGroupBox(tr("部署包预览", "Deployment Preview"))
            preview_layout = QVBoxLayout()
            self._deploy_tree = QTreeWidget()
            self._deploy_tree.setHeaderLabel(tr("文件", "File"))
            self._deploy_tree.setMaximumHeight(220)
            preview_layout.addWidget(self._deploy_tree)
            preview_group.setLayout(preview_layout)

            # ----------------------------------------------------------
            # Export options
            # ----------------------------------------------------------
            opt_group = QGroupBox(tr("导出选项", "Export Options"))
            form = QFormLayout()

            self._imgsz_sb = QSpinBox()
            self._imgsz_sb.setRange(32, 2048)
            self._imgsz_sb.setValue(640)
            form.addRow(tr("图片尺寸：", "Image Size:"), self._imgsz_sb)

            self._half_cb = QCheckBox()
            form.addRow(tr("FP16：", "FP16:"), self._half_cb)

            self._batch_sb = QSpinBox()
            self._batch_sb.setRange(1, 64)
            self._batch_sb.setValue(1)
            form.addRow(tr("批次：", "Batch:"), self._batch_sb)

            # ONNX-only options
            self._simplify_cb = QCheckBox()
            self._simplify_cb.setChecked(True)
            form.addRow(tr("简化：", "Simplify:"), self._simplify_cb)

            self._dynamic_cb = QCheckBox()
            form.addRow(tr("动态：", "Dynamic:"), self._dynamic_cb)

            opt_group.setLayout(form)

            # ----------------------------------------------------------
            # Deploy artifact options
            # ----------------------------------------------------------
            deploy_group = QGroupBox(tr("导出内容", "Export Contents"))
            deploy_form = QFormLayout()

            self._include_labels_cb = QCheckBox()
            self._include_labels_cb.setChecked(True)
            deploy_form.addRow(
                tr(
                    "包含类别映射文件 (labels.json)：",
                    "Include labels.json:",
                ),
                self._include_labels_cb,
            )

            self._include_preprocess_cb = QCheckBox()
            self._include_preprocess_cb.setChecked(True)
            deploy_form.addRow(
                tr(
                    "包含预处理参数 (preprocess.json)：",
                    "Include preprocess.json:",
                ),
                self._include_preprocess_cb,
            )

            deploy_group.setLayout(deploy_form)

            # ----------------------------------------------------------
            # Self-test section
            # ----------------------------------------------------------
            self._selftest_group = QGroupBox(tr("自测", "Self-Test"))
            selftest_layout = QVBoxLayout()

            self._selftest_status = QLabel(
                tr(
                    "导出后将自动运行 ONNX 自测",
                    "ONNX self-test will run after export",
                )
            )
            selftest_layout.addWidget(self._selftest_status)

            self._selftest_progress = QProgressBar()
            self._selftest_progress.setVisible(False)
            selftest_layout.addWidget(self._selftest_progress)

            self._selftest_result = QLabel("")
            self._selftest_result.setVisible(False)
            selftest_layout.addWidget(self._selftest_result)

            self._selftest_group.setLayout(selftest_layout)

            # ----------------------------------------------------------
            # Auto-register
            # ----------------------------------------------------------
            register_group = QGroupBox(tr("模型注册", "Model Registration"))
            register_layout = QHBoxLayout()
            self._auto_register_cb = QCheckBox(
                tr(
                    "导出后注册为预标注模型",
                    "Register as pre-labeling model after export",
                )
            )
            self._auto_register_cb.setChecked(True)
            register_layout.addWidget(self._auto_register_cb)
            register_group.setLayout(register_layout)

            # ----------------------------------------------------------
            # Completion page (hidden initially)
            # ----------------------------------------------------------
            self._completion_group = QGroupBox(
                tr("导出完成", "Export Complete")
            )
            self._completion_group.setVisible(False)
            completion_layout = QVBoxLayout()

            self._completion_path = QLabel("")
            completion_layout.addWidget(self._completion_path)

            self._completion_onnx_check = QLabel("")
            completion_layout.addWidget(self._completion_onnx_check)

            self._completion_selftest = QLabel("")
            completion_layout.addWidget(self._completion_selftest)

            self._completion_checksum = QLabel("")
            completion_layout.addWidget(self._completion_checksum)

            # Action buttons
            action_row = QHBoxLayout()
            self._open_dir_btn = QPushButton(tr("打开目录", "Open Directory"))
            action_row.addWidget(self._open_dir_btn)
            self._register_model_btn = QPushButton(
                tr(
                    "注册为预标注模型",
                    "Register as Pre-labeling Model",
                )
            )
            action_row.addWidget(self._register_model_btn)
            action_row.addStretch()
            completion_layout.addLayout(action_row)

            self._completion_group.setLayout(completion_layout)

            # ----------------------------------------------------------
            # Status and export button
            # ----------------------------------------------------------
            self._status_label = QLabel(
                tr(
                    "选择已训练的 Run 以导出",
                    "Select a trained Run to export",
                )
            )
            self._export_btn = QPushButton(tr("导出模型", "Export Model"))
            self._export_btn.setEnabled(False)
            self._export_btn.clicked.connect(self._on_export_clicked)

            # ----------------------------------------------------------
            # Scrollable container
            # ----------------------------------------------------------
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )

            container = QWidget()
            main = QVBoxLayout(container)
            main.addWidget(run_group)
            main.addWidget(self._target_group)
            main.addWidget(self._compat_group)
            main.addWidget(self._format_label)
            main.addWidget(preview_group)
            main.addWidget(opt_group)
            main.addWidget(deploy_group)
            main.addWidget(self._selftest_group)
            main.addWidget(register_group)
            main.addWidget(self._completion_group)
            main.addWidget(self._status_label)
            main.addStretch()
            main.addWidget(self._export_btn)

            scroll.setWidget(container)

            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(scroll)

            # Initialize deploy preview
            self._populate_deploy_tree()

        # --------------------------------------------------------------
        # Public API
        # --------------------------------------------------------------

        def set_project_context(self, training_service=None):
            """Set the training service and populate the runs combo."""
            self._training_service = training_service
            self._populate_runs()

        def set_context(self, context):
            """Set the DB project context and populate from ready models."""
            self._context = context
            self._populate_runs()

        def set_provider(self, provider) -> None:
            """Set the algorithm provider for export compatibility."""
            self._provider = provider
            self._update_compatibility()

        def show_completion_page(self, report) -> None:
            """Show the export completion page with results.

            Args:
                report: Dict-like or object with keys:
                    - export_path (str)
                    - onnx_check_passed (bool)
                    - samples_tested (int)
                    - samples_passed (int)
                    - checksum (str)
            """
            self._completion_group.setVisible(True)

            export_path = _get_from_report(report, "export_path", "")
            self._completion_path.setText(
                tr(
                    f"导出路径：{export_path}",
                    f"Export path: {export_path}",
                )
            )

            onnx_ok = _get_from_report(report, "onnx_check_passed", False)
            if onnx_ok:
                status_text = tr("✓ 通过", "✓ Passed")
            else:
                status_text = tr("✗ 未通过", "✗ Failed")
            self._completion_onnx_check.setText(
                tr(
                    f"ONNX 检查：{status_text}",
                    f"ONNX Check: {status_text}",
                )
            )

            tested = _get_from_report(report, "samples_tested", 0)
            passed = _get_from_report(report, "samples_passed", 0)
            self._completion_selftest.setText(
                tr(
                    f"样本自测：{passed}/{tested} 通过",
                    f"Sample self-test: {passed}/{tested} passed",
                )
            )

            checksum = _get_from_report(report, "checksum", "")
            self._completion_checksum.setText(
                tr(f"校验值：{checksum}", f"Checksum: {checksum}")
            )

            # Wire action buttons (disconnect stale signals first)
            try:
                self._open_dir_btn.clicked.disconnect()
            except Exception:
                pass
            self._open_dir_btn.clicked.connect(
                lambda: _open_export_directory(export_path)
            )

            try:
                self._register_model_btn.clicked.disconnect()
            except Exception:
                pass
            self._register_model_btn.clicked.connect(
                lambda: self.export_requested.emit(
                    {"action": "register_prelabel", "report": report}
                )
            )

            self._status_label.setText(tr("导出完成", "Export complete"))
            self._export_btn.setEnabled(False)

        # --------------------------------------------------------------
        # Internal
        # --------------------------------------------------------------

        def _on_target_selected(self, target_id: str) -> None:
            """Handle target environment selection."""
            for tid, btn in self._target_btns.items():
                btn.setChecked(tid == target_id)
            self._selected_target = target_id
            self._update_compatibility()

        def _on_run_changed(self, _index: int) -> None:
            """Update compatibility and button state on run change."""
            run_id = self._run_combo.currentData()
            self._export_btn.setEnabled(run_id is not None)
            if run_id:
                self._update_compatibility()

        def _update_compatibility(self) -> None:
            """Update compatibility check indicators."""
            run_id = self._run_combo.currentData()
            has_run = run_id is not None

            for check_id, icon in self._compat_labels.items():
                if has_run:
                    icon.setText(tr("✓", "✓"))
                    icon.setStyleSheet("color: green;")
                else:
                    icon.setText("—")
                    icon.setStyleSheet("")

        def _populate_runs(self):
            self._run_combo.clear()

            # DB context path
            context = getattr(self, "_context", None)
            if context is not None:
                try:
                    ready_models = context.models.list_ready()
                except Exception:
                    logger.exception("Failed to load data from DB")
                    return
                for model in ready_models:
                    label = f"{model.name} ({model.task_family})"
                    self._run_combo.addItem(label, model.run_id)

                if len(ready_models) > 0:
                    self._status_label.setText(
                        tr(
                            f"已就绪 {len(ready_models)} 个模型",
                            f"{len(ready_models)} model(s) ready",
                        )
                    )
                else:
                    self._status_label.setText(
                        tr(
                            "选择已训练的 Run 以导出（无就绪模型）",
                            "Select a trained Run to export (no ready models)",
                        )
                    )
                self._export_btn.setEnabled(len(ready_models) > 0)
                return

            # Filesystem fallback path
            self._run_combo.addItem("", None)  # Empty placeholder
            training_service = getattr(self, "_training_service", None)
            if training_service is None:
                return

            runs_dir = Path(training_service.project_root) / "runs"
            if not runs_dir.exists():
                return

            completed_count = 0
            for run_dir in sorted(runs_dir.iterdir()):
                if not run_dir.is_dir():
                    continue
                try:
                    run = training_service.read_run_record(run_dir.name)
                    if run is not None and run.status == "completed":
                        label = f"{run.id} ({run.task_family})"
                        self._run_combo.addItem(label, run.id)
                        completed_count += 1
                except Exception:
                    continue

            if completed_count > 0:
                self._status_label.setText(
                    tr(
                        f"已就绪 {completed_count} 个运行",
                        f"{completed_count} run(s) ready",
                    )
                )
            else:
                self._status_label.setText(
                    tr(
                        "选择已训练的 Run 以导出（无已完成运行）",
                        "Select a trained Run to export (no completed runs)",
                    )
                )

        def _populate_deploy_tree(self) -> None:
            """Populate the deployment preview tree widget."""
            self._deploy_tree.clear()

            def add_items(parent, items):
                for name, tooltip, children in items:
                    item = QTreeWidgetItem(parent)
                    item.setText(0, name)
                    item.setToolTip(0, tooltip)
                    if children:
                        add_items(item, children)

            add_items(self._deploy_tree, _deploy_tree_items())
            self._deploy_tree.expandAll()

        def _on_export_clicked(self):
            run_id = self._run_combo.currentData()
            if not run_id:
                return

            config = {
                "run_id": run_id,
                "formats": ["onnx"],  # Phase 4: ONNX only
                "target": self._selected_target,
                "imgsz": self._imgsz_sb.value(),
                "half": self._half_cb.isChecked(),
                "batch": self._batch_sb.value(),
                "simplify": self._simplify_cb.isChecked(),
                "dynamic": self._dynamic_cb.isChecked(),
                "include_labels": self._include_labels_cb.isChecked(),
                "include_preprocess": self._include_preprocess_cb.isChecked(),
                "auto_register": self._auto_register_cb.isChecked(),
            }
            self.export_requested.emit(config)

except ImportError:
    ExportWorkspace = None  # type: ignore


# ----------------------------------------------------------------------
# Module-level helpers (outside try block — no PyQt6 dependency)
# ----------------------------------------------------------------------


def _get_from_report(report, key: str, default=None):
    """Read a value from a dict or object by key/attribute name."""
    if isinstance(report, dict):
        return report.get(key, default)
    return getattr(report, key, default)


def _open_export_directory(
    path_str: str, project_root: Path | None = None
) -> None:
    """Open the export directory in the system file explorer.

    Args:
        path_str: Export directory path.
        project_root: Optional project root for containment check.
            If provided, the path will only be opened if it resolves
            within the project root.
    """
    import subprocess
    import sys

    dir_path = Path(path_str)
    if not dir_path.is_dir():
        dir_path = dir_path.parent
    if not dir_path.exists():
        return

    if project_root is not None:
        try:
            dir_path.resolve().relative_to(project_root.resolve())
        except ValueError:
            return

    if sys.platform == "win32":
        subprocess.Popen(["explorer", str(dir_path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(dir_path)])
    else:
        subprocess.Popen(["xdg-open", str(dir_path)])

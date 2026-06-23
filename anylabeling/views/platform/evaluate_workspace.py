"""Evaluate Workspace — run selection, evaluation trigger, metrics visualization.

Phase 3 additions:
    - Confusion matrix heatmap rendered to QPixmap
    - Per-class analysis QTableWidget
    - Multi-run comparison view (Run A vs Run B)
    - Misclassification review panel (FP / FN / low-confidence / confused)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from anylabeling.views.platform.i18n import tr

_NO_METRIC_TEXT = tr("未生成", "Not generated")

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure

    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtCore import pyqtSignal

    from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget


    # ------------------------------------------------------------------
    # Helper: render confusion matrix to QPixmap
    # ------------------------------------------------------------------

    def _render_confusion_matrix_pixmap(
        matrix: np.ndarray | None,
        class_names: list[str],
        figsize: tuple[float, float] = (5.0, 4.0),
        dpi: int = 100,
    ) -> QtGui.QPixmap | None:
        """Render a confusion matrix heatmap to a QPixmap.

        Args:
            matrix: NxN confusion matrix, or None.
            class_names: Ordered class labels.
            figsize: Matplotlib figure size in inches.
            dpi: Dots per inch.

        Returns:
            QPixmap or None (if the matrix is empty/invalid).
        """
        if matrix is None or not isinstance(matrix, np.ndarray):
            return None
        if matrix.ndim != 2 or matrix.size == 0:
            return None

        fig = Figure(figsize=figsize, dpi=dpi)
        fig.set_layout_engine("tight")
        ax = fig.add_subplot(111)

        im = ax.imshow(matrix, cmap="Blues", aspect="auto")
        n = matrix.shape[0]
        for i in range(n):
            for j in range(n):
                val = matrix[i, j]
                text_color = "white" if val > matrix.max() / 2 else "black"
                ax.text(j, i, str(int(val)), ha="center", va="center",
                        color=text_color, fontsize=8)

        if class_names:
            ax.set_xticks(range(n))
            ax.set_yticks(range(n))
            ax.set_xticklabels(class_names, rotation=45, ha="right", fontsize=8)
            ax.set_yticklabels(class_names, fontsize=8)
        ax.set_xlabel(tr("预测类别", "Predicted"), fontsize=10)
        ax.set_ylabel(tr("真实类别", "True"), fontsize=10)
        ax.set_title(tr("混淆矩阵", "Confusion Matrix"), fontsize=12)
        fig.colorbar(im, ax=ax, shrink=0.8)

        # Render to QPixmap via an in-memory buffer
        canvas = FigureCanvasQTAgg(fig)
        canvas.draw()
        width, height = canvas.get_width_height()
        pixmap = QtGui.QPixmap(width, height)
        pixmap.fill(QtGui.QColor("white"))
        from PyQt6.QtGui import QPainter
        painter = QPainter(pixmap)
        canvas.render(painter)
        painter.end()

        plt.close(fig)
        return pixmap


    # ------------------------------------------------------------------
    # Helper: delta comparison
    # ------------------------------------------------------------------

    def _compute_delta(a: float, b: float) -> str:
        """Format a percentage-change string comparing *a* (current) to *b* (previous).

        Returns something like ``"↑ +2.1%"`` or ``"↓ -0.5%"``.
        """
        if b == 0:
            return "N/A"
        diff_pct = ((a - b) / abs(b)) * 100.0
        if diff_pct >= 0:
            return f"↑ +{diff_pct:.1f}%"
        else:
            return f"↓ {diff_pct:.1f}%"


    # ------------------------------------------------------------------
    # EvaluateWorkspace — full class
    # ------------------------------------------------------------------

    class EvaluateWorkspace(QtWidgets.QWidget):
        evaluate_requested = pyqtSignal(str, str)

        def __init__(self, parent=None):
            super().__init__(parent)

            self._training_service = None
            self._all_runs: list = []

            # --- EvalReportWidget + MisclassGallery (Phase 4) ---
            from anylabeling.views.platform.widgets.eval_report_widget import (
                EvalReportWidget,
            )
            from anylabeling.views.platform.widgets.misclass_gallery import (
                MisclassGallery,
            )
            self._eval_report = EvalReportWidget()
            self._misclass_gallery = MisclassGallery()
            self._misclass_gallery.setVisible(False)

            # Connect signals
            self._eval_report.view_misclass_requested.connect(
                self._show_misclass_gallery,
            )

            # --- Run selection ---
            run_group = QtWidgets.QGroupBox(tr("运行选择", "Run Selection"))
            run_layout = QtWidgets.QHBoxLayout()
            run_layout.addWidget(QtWidgets.QLabel(tr("运行：", "Run:")))
            self._run_combo = QtWidgets.QComboBox()
            run_layout.addWidget(self._run_combo, 1)
            run_group.setLayout(run_layout)

            # --- Buttons ---
            btn_layout = QtWidgets.QHBoxLayout()
            self._evaluate_btn = QtWidgets.QPushButton(tr("开始评估", "Start Evaluation"))
            self._evaluate_btn.setEnabled(False)
            self._evaluate_btn.clicked.connect(self._on_evaluate_clicked)
            btn_layout.addWidget(self._evaluate_btn)
            btn_layout.addStretch()

            # --- Display: tab widget ---
            self._display_tabs = QtWidgets.QTabWidget()

            # Tab 0: Summary text
            self._summary_text = QtWidgets.QTextEdit()
            self._summary_text.setReadOnly(True)
            self._display_tabs.addTab(self._summary_text, tr("摘要", "Summary"))

            # Tab 1: Confusion matrix as pixmap label
            cm_tab = QtWidgets.QWidget()
            cm_layout = QtWidgets.QVBoxLayout()
            cm_layout.setContentsMargins(4, 4, 4, 4)
            self._lbl_confusion_matrix = QtWidgets.QLabel()
            self._lbl_confusion_matrix.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignCenter
            )
            self._lbl_confusion_matrix.setMinimumSize(400, 300)
            cm_scroll = QtWidgets.QScrollArea()
            cm_scroll.setWidgetResizable(True)
            cm_scroll.setWidget(self._lbl_confusion_matrix)
            cm_layout.addWidget(cm_scroll)
            cm_tab.setLayout(cm_layout)
            self._display_tabs.addTab(cm_tab, tr("混淆矩阵", "Confusion Matrix"))

            # Tab 2: Charts (existing MetricsPlotWidget)
            self._metrics_plot = MetricsPlotWidget()
            self._display_tabs.addTab(self._metrics_plot, tr("图表", "Charts"))

            # Tab 3: Per-class analysis table
            class_tab = QtWidgets.QWidget()
            class_layout = QtWidgets.QVBoxLayout()
            class_layout.setContentsMargins(4, 4, 4, 4)
            self._per_class_table = QtWidgets.QTableWidget()
            self._per_class_table.setColumnCount(5)
            self._per_class_table.setHorizontalHeaderLabels([
                tr("类别", "Class"),
                "Precision",
                "Recall",
                "mAP50",
                "mAP50:95",
            ])
            self._per_class_table.horizontalHeader().setStretchLastSection(True)
            self._per_class_table.setAlternatingRowColors(True)
            class_layout.addWidget(self._per_class_table)
            class_tab.setLayout(class_layout)
            self._display_tabs.addTab(class_tab, tr("逐类分析", "Per-Class"))

            # --- Multi-run comparison ---
            compare_group = QtWidgets.QGroupBox(tr("多 Run 对比", "Run Comparison"))
            compare_layout = QtWidgets.QHBoxLayout()
            compare_layout.addWidget(QtWidgets.QLabel(tr("Run A：", "Run A:")))
            self._compare_run_a = QtWidgets.QComboBox()
            compare_layout.addWidget(self._compare_run_a, 1)
            compare_layout.addWidget(QtWidgets.QLabel(tr("Run B：", "Run B:")))
            self._compare_run_b = QtWidgets.QComboBox()
            compare_layout.addWidget(self._compare_run_b, 1)
            compare_group.setLayout(compare_layout)

            self._lbl_compare_summary = QtWidgets.QLabel(
                tr("选择两个 Run 以对比指标。", "Select two runs to compare metrics.")
            )
            self._lbl_compare_summary.setWordWrap(True)

            # --- Misclassification review panel ---
            self._misclass_tabs = QtWidgets.QTabWidget()
            self._fp_list = QtWidgets.QListWidget()
            self._misclass_tabs.addTab(
                self._fp_list, tr("FP 误检", "FP Misdetections")
            )
            self._fn_list = QtWidgets.QListWidget()
            self._misclass_tabs.addTab(
                self._fn_list, tr("FN 漏检", "FN Missed")
            )
            self._low_conf_list = QtWidgets.QListWidget()
            self._misclass_tabs.addTab(
                self._low_conf_list, tr("低置信度", "Low Confidence")
            )

            # Assemble main layout
            main = QtWidgets.QVBoxLayout()
            main.addWidget(run_group)
            main.addLayout(btn_layout)
            main.addWidget(self._display_tabs, stretch=1)
            main.addWidget(compare_group)
            main.addWidget(self._lbl_compare_summary)
            main.addWidget(self._misclass_tabs, stretch=0)
            self._misclass_tabs.setMaximumHeight(200)

            # Phase 4: add EvalReportWidget and MisclassGallery
            main.addWidget(self._eval_report, stretch=1)
            main.addWidget(self._misclass_gallery, stretch=0)
            self._misclass_gallery.setMaximumHeight(220)
            self.setLayout(main)

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def set_project_context(self, training_service=None):
            """Set the training service and populate the runs combo."""
            self._training_service = training_service
            self._populate_runs()

        def display_metrics(self, metrics: dict) -> None:
            """Display parsed evaluation metrics."""
            self._last_metrics = metrics
            lines = [
                f"mAP@50:      {_NO_METRIC_TEXT if (v := metrics.get('mAP50')) is None else f'{v:.4f}'}",
                f"mAP@50-95:   {_NO_METRIC_TEXT if (v := metrics.get('mAP50_95')) is None else f'{v:.4f}'}",
                f"Precision:   {_NO_METRIC_TEXT if (v := metrics.get('precision')) is None else f'{v:.4f}'}",
                f"Recall:      {_NO_METRIC_TEXT if (v := metrics.get('recall')) is None else f'{v:.4f}'}",
            ]
            self._summary_text.setPlainText("\n".join(lines))

            ap_per_class = metrics.get("ap_per_class", {})
            class_names = metrics.get("class_names", [])
            confusion_matrix = metrics.get("confusion_matrix")

            # Confusion matrix as QPixmap
            pixmap = _render_confusion_matrix_pixmap(
                confusion_matrix, class_names,
            )
            if pixmap and not pixmap.isNull():
                self._lbl_confusion_matrix.setPixmap(pixmap)
            else:
                self._lbl_confusion_matrix.setText(
                    tr("无数据", "No Data")
                )

            # Per-class table
            self._populate_per_class_table(ap_per_class, class_names)

            # Charts
            if confusion_matrix is not None and len(class_names) > 0:
                self._metrics_plot.plot_confusion_matrix(confusion_matrix, class_names)
            if ap_per_class:
                self._metrics_plot.plot_per_class_ap(ap_per_class, class_names)
                self._metrics_plot.plot_f1_curve(ap_per_class, class_names)

            # Phase 4: delegate to EvalReportWidget with key mapping
            report_metrics: dict = {}
            if metrics.get("mAP50") is not None:
                report_metrics["metrics/mAP50(B)"] = metrics["mAP50"]
            if metrics.get("mAP50_95") is not None:
                report_metrics["metrics/mAP50-95(B)"] = metrics["mAP50_95"]
            if metrics.get("precision") is not None:
                report_metrics["metrics/precision(B)"] = metrics["precision"]
            if metrics.get("recall") is not None:
                report_metrics["metrics/recall(B)"] = metrics["recall"]
            precision = metrics.get("precision")
            recall = metrics.get("recall")
            if (
                precision is not None
                and recall is not None
                and (precision + recall) > 0
            ):
                f1 = 2 * precision * recall / (precision + recall)
                report_metrics["metrics/f1(B)"] = f1
            class_names = metrics.get("class_names", [])
            if class_names:
                per_class = []
                for key_str, ap_val in metrics.get("ap_per_class", {}).items():
                    idx = int(key_str)
                    per_class.append({
                        "name": class_names[idx] if idx < len(class_names) else f"c{idx}",
                        "mAP50": ap_val,
                        "instances": -1,
                    })
                report_metrics["per_class"] = per_class
            cm = metrics.get("confusion_matrix")
            if cm is not None:
                report_metrics["confusion_matrix"] = cm
            self._eval_report.display_metrics(report_metrics)

        def _show_misclass_gallery(self):
            """Show misclassification gallery panel.

            Populates the gallery with FP/FN sample data from the last
            displayed metrics, then toggles visibility.
            """
            samples: list[dict] = []
            stored = getattr(self, "_last_metrics", {}) or {}

            fp_samples = stored.get("fp_samples", [])
            for s in fp_samples:
                samples.append({**s, "type": "fp"})

            fn_samples = stored.get("fn_samples", [])
            for s in fn_samples:
                samples.append({**s, "type": "fn"})

            if samples:
                self._misclass_gallery.set_samples(samples)
            elif stored:
                self._misclass_gallery.set_samples([])

            self._misclass_gallery.setVisible(
                not self._misclass_gallery.isVisible()
            )

        def clear_metrics(self) -> None:
            """Clear all displayed metrics."""
            self._summary_text.clear()
            self._metrics_plot.clear_all()
            self._lbl_confusion_matrix.clear()
            self._per_class_table.setRowCount(0)

        def display_comparison(
            self, metrics_a: dict, metrics_b: dict,
            run_a_id: str = "", run_b_id: str = "",
        ) -> None:
            """Display side-by-side comparison of two runs."""
            lines = []
            if run_a_id:
                lines.append(f"Run A: {run_a_id}")
            if run_b_id:
                lines.append(f"Run B: {run_b_id}")
            lines.append("=" * 40)

            for key, label in [
                ("mAP50", "mAP@50"),
                ("mAP50_95", "mAP@50-95"),
                ("precision", "Precision"),
                ("recall", "Recall"),
            ]:
                a_val = metrics_a.get(key, 0)
                b_val = metrics_b.get(key, 0)
                delta = _compute_delta(a_val, b_val)
                lines.append(
                    f"{label}:  A={a_val:.4f}  B={b_val:.4f}  Δ={delta}"
                )

            self._lbl_compare_summary.setText("\n".join(lines))

        # ------------------------------------------------------------------
        # Per-class table
        # ------------------------------------------------------------------

        def _populate_per_class_table(
            self,
            ap_per_class: dict[str, float],
            class_names: list[str],
        ) -> None:
            """Fill the QTableWidget with per-class metrics."""
            self._per_class_table.setRowCount(0)
            if not ap_per_class:
                return

            items = sorted(ap_per_class.items(), key=lambda x: x[1], reverse=True)
            self._per_class_table.setRowCount(len(items))

            for row, (idx_str, ap_val) in enumerate(items):
                idx = int(idx_str)
                name = (
                    class_names[idx]
                    if idx < len(class_names)
                    else f"class_{idx}"
                )
                self._per_class_table.setItem(
                    row, 0, QtWidgets.QTableWidgetItem(name)
                )
                self._per_class_table.setItem(
                    row, 1, QtWidgets.QTableWidgetItem("—")
                )
                self._per_class_table.setItem(
                    row, 2, QtWidgets.QTableWidgetItem("—")
                )
                self._per_class_table.setItem(
                    row, 3, QtWidgets.QTableWidgetItem(f"{ap_val:.4f}")
                )
                self._per_class_table.setItem(
                    row, 4, QtWidgets.QTableWidgetItem(f"{ap_val:.4f}")
                )

        # ------------------------------------------------------------------
        # Internal
        # ------------------------------------------------------------------

        def _populate_runs(self):
            self._run_combo.clear()
            self._all_runs = []
            training_service = getattr(self, "_training_service", None)
            if training_service is None:
                self._evaluate_btn.setEnabled(False)
                self._evaluate_btn.setText(
                    tr("评估（无训练服务）", "Evaluate (no training service)")
                )
                return

            runs_dir = Path(training_service.project_root) / "runs"
            if not runs_dir.exists():
                self._evaluate_btn.setEnabled(False)
                return

            run_count = 0
            for run_dir in sorted(runs_dir.iterdir()):
                if not run_dir.is_dir():
                    continue
                run_json = run_dir / "run.json"
                if not run_json.exists():
                    continue
                try:
                    run = training_service.read_run_record(run_dir.name)
                    if run is not None:
                        label = f"{run.id} ({run.task_family}) [{run.status}]"
                        self._run_combo.addItem(label, run.id)
                        self._all_runs.append(run)
                        run_count += 1
                except Exception:
                    continue

            self._evaluate_btn.setEnabled(run_count > 0)
            if run_count == 0:
                self._evaluate_btn.setText(
                    tr("评估（无可用运行）", "Evaluate (no runs available)")
                )

            # Also populate comparison combos
            self._populate_comparison_combos()

        def _populate_comparison_combos(self) -> None:
            """Populate Run A and Run B combos for comparison."""
            self._compare_run_a.clear()
            self._compare_run_b.clear()
            self._compare_run_a.addItem(tr("— 选择 —", "— Select —"), None)
            self._compare_run_b.addItem(tr("— 选择 —", "— Select —"), None)
            for run in self._all_runs:
                label = f"{run.id} ({run.task_family}) [{run.status}]"
                self._compare_run_a.addItem(label, run.id)
                self._compare_run_b.addItem(label, run.id)
            self._compare_run_b.addItem(
                tr("— 不对比 —", "— Don't compare —"), ""
            )

        def _on_evaluate_clicked(self):
            run_id = self._run_combo.currentData()
            if run_id:
                self.clear_metrics()
                self._summary_text.setPlainText(tr("评估中...", "Evaluating..."))
                self.evaluate_requested.emit(run_id, "val")

except ImportError:
    EvaluateWorkspace = None  # type: ignore


__all__ = [
    "EvaluateWorkspace",
    "_render_confusion_matrix_pixmap",
    "_compute_delta",
]

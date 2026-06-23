"""Matplotlib-based metrics visualization widget for the platform workbench.

Provides three tabbed plots:
    - Confusion matrix (heatmap)
    - Per-class AP (horizontal bar chart)
    - F1/Summary table
"""

from __future__ import annotations

import numpy as np

from anylabeling.views.platform.i18n import tr

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

    class MetricsPlotWidget(QWidget):
        """Tabbed widget for evaluation metrics visualization."""

        def __init__(self, parent=None):
            super().__init__(parent)

            self._tab_widget = QTabWidget()

            # Tab 0: Confusion Matrix
            self._cm_canvas = FigureCanvasQTAgg(Figure(figsize=(5, 4.5), dpi=100))
            self._cm_canvas.figure.set_layout_engine("tight")
            self._tab_widget.addTab(self._cm_canvas, tr("混淆矩阵", "Confusion Matrix"))

            # Tab 1: Per-Class AP
            self._ap_canvas = FigureCanvasQTAgg(Figure(figsize=(5, 4.5), dpi=100))
            self._ap_canvas.figure.set_layout_engine("tight")
            self._tab_widget.addTab(self._ap_canvas, tr("每类 AP", "Per-Class AP"))

            # Tab 2: Summary
            self._f1_canvas = FigureCanvasQTAgg(Figure(figsize=(5, 4.5), dpi=100))
            self._f1_canvas.figure.set_layout_engine("tight")
            self._tab_widget.addTab(self._f1_canvas, tr("指标摘要", "Summary"))

            layout = QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._tab_widget)
            self.setLayout(layout)

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def plot_confusion_matrix(
            self,
            matrix: np.ndarray | None,
            class_names: list[str],
        ) -> None:
            """Plot a confusion matrix heatmap."""
            ax = self._cm_canvas.figure.gca()
            ax.clear()

            if matrix is None or matrix.size == 0 or len(class_names) == 0:
                ax.text(0.5, 0.5, tr("无数据", "No Data"),
                        ha="center", va="center", transform=ax.transAxes,
                        fontsize=14, color="gray")
                self._cm_canvas.draw()
                return

            im = ax.imshow(matrix, cmap="Blues", aspect="auto")
            n_classes = matrix.shape[0]
            for i in range(n_classes):
                for j in range(n_classes):
                    val = matrix[i, j]
                    text_color = "white" if val > matrix.max() / 2 else "black"
                    ax.text(j, i, str(int(val)), ha="center", va="center",
                            color=text_color, fontsize=8)

            ax.set_xticks(range(n_classes))
            ax.set_yticks(range(n_classes))
            ax.set_xticklabels(class_names, rotation=45, ha="right", fontsize=8)
            ax.set_yticklabels(class_names, fontsize=8)
            ax.set_xlabel(tr("预测类别", "Predicted"), fontsize=10)
            ax.set_ylabel(tr("真实类别", "True"), fontsize=10)
            ax.set_title(tr("混淆矩阵", "Confusion Matrix"), fontsize=12)
            self._cm_canvas.figure.colorbar(im, ax=ax, shrink=0.8)
            self._cm_canvas.draw()

        def plot_per_class_ap(
            self,
            ap_per_class: dict[str, float],
            class_names: list[str],
        ) -> None:
            """Plot per-class AP as a horizontal bar chart."""
            ax = self._ap_canvas.figure.gca()
            ax.clear()

            if not ap_per_class:
                ax.text(0.5, 0.5, tr("无数据", "No Data"),
                        ha="center", va="center", transform=ax.transAxes,
                        fontsize=14, color="gray")
                self._ap_canvas.draw()
                return

            items = sorted(ap_per_class.items(), key=lambda x: x[1], reverse=True)
            names = []
            values = []
            for idx_str, ap_val in items:
                idx = int(idx_str)
                name = class_names[idx] if idx < len(class_names) else f"class_{idx}"
                names.append(name)
                values.append(ap_val)

            y_pos = range(len(names))
            colors = ["#1890ff" if v >= 0.7 else "#faad14" if v >= 0.5 else "#ff4d4f"
                      for v in values]
            bars = ax.barh(y_pos, values, color=colors, edgecolor="white")
            for bar, val in zip(bars, values):
                ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                        f"{val:.3f}", va="center", fontsize=9)

            ax.set_yticks(y_pos)
            ax.set_yticklabels(names, fontsize=9)
            ax.invert_yaxis()
            ax.set_xlabel("AP", fontsize=10)
            ax.set_title(tr("每类平均精度 (AP)", "Per-Class Average Precision"), fontsize=12)
            ax.set_xlim(0, max(values) * 1.15 if values else 1.0)
            self._ap_canvas.draw()

        def plot_f1_curve(
            self,
            ap_per_class: dict[str, float],
            class_names: list[str],
        ) -> None:
            """Display a metrics summary table."""
            ax = self._f1_canvas.figure.gca()
            ax.clear()
            ax.axis("off")

            if not ap_per_class:
                ax.text(0.5, 0.5, tr("无数据", "No Data"),
                        ha="center", va="center", transform=ax.transAxes,
                        fontsize=14, color="gray")
                self._f1_canvas.draw()
                return

            lines = [tr("指标摘要", "Metrics Summary"), "=" * 40]
            for idx_str, ap_val in sorted(ap_per_class.items(), key=lambda x: x[1], reverse=True):
                idx = int(idx_str)
                name = class_names[idx] if idx < len(class_names) else f"class_{idx}"
                lines.append(f"  {name:<20s}  AP: {ap_val:.3f}")

            text = "\n".join(lines)
            ax.text(0.5, 0.5, text, ha="center", va="center",
                    transform=ax.transAxes, fontsize=10, fontfamily="monospace")
            self._f1_canvas.draw()

        def clear_all(self) -> None:
            """Clear all plots."""
            for canvas in [self._cm_canvas, self._ap_canvas, self._f1_canvas]:
                canvas.figure.gca().clear()
                canvas.draw()

except ImportError:
    MetricsPlotWidget = None  # type: ignore

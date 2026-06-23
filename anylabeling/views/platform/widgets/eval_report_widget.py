"""Tabbed evaluation report widget.

Composes MetricsPlotWidget for confusion-matrix / per-class-AP / F1-curve
tabs.  Emits ``view_misclass_requested`` when the user clicks the
View Misclassifications button.
"""

from __future__ import annotations

import logging

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import FONT_FAMILY, FONT_SIZE_BODY

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QLabel,
        QPushButton,
        QHeaderView,
    )
    from PyQt6.QtCore import pyqtSignal, Qt

    from anylabeling.views.platform.widgets.metrics_plot import (
        MetricsPlotWidget,
    )

    class EvalReportWidget(QWidget):
        """Rich evaluation report with tabs: Overview, Per-Class,
        Confusion Matrix, PR Curve."""

        view_misclass_requested = pyqtSignal()

        def __init__(self, parent=None):
            super().__init__(parent)
            self._build_ui()

        # ------------------------------------------------------------------
        # UI construction
        # ------------------------------------------------------------------

        def _build_ui(self):
            layout = QVBoxLayout(self)

            # --- Tabs ---
            self._tabs = QTabWidget()

            # Tab 1: Overview
            self._overview_tab = QWidget()
            self._overview_layout = QVBoxLayout(self._overview_tab)

            # KPI cards row
            kpi_row = QHBoxLayout()
            self._kpi_labels: dict[str, QLabel] = {}
            for metric in [
                "mAP@0.5",
                "mAP@0.5:0.95",
                "Precision",
                "Recall",
                "F1",
            ]:
                card = QVBoxLayout()
                value_label = QLabel("—")
                value_label.setStyleSheet(
                    f"font-size: 24px; font-weight: bold;"
                    f"font-family: {FONT_FAMILY};"
                )
                value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                name_label = QLabel(metric)
                name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                name_label.setStyleSheet(
                    f"font-size: {FONT_SIZE_BODY}px; color: gray;"
                    f"font-family: {FONT_FAMILY};"
                )
                card.addWidget(value_label)
                card.addWidget(name_label)
                kpi_row.addLayout(card)
                self._kpi_labels[metric] = value_label
            self._overview_layout.addLayout(kpi_row)

            # Conclusion area
            self._conclusion_label = QLabel("")
            self._conclusion_label.setWordWrap(True)
            self._conclusion_label.setStyleSheet(
                f"font-family: {FONT_FAMILY};"
            )
            self._overview_layout.addWidget(self._conclusion_label)

            # View misclassifications button
            self._misclass_btn = QPushButton(
                tr("查看误判样本", "View Misclassifications")
            )
            self._misclass_btn.clicked.connect(
                self.view_misclass_requested.emit
            )
            self._misclass_btn.setVisible(False)
            self._overview_layout.addWidget(self._misclass_btn)

            self._overview_layout.addStretch()
            self._tabs.addTab(
                self._overview_tab, tr("概览", "Overview")
            )

            # Tab 2: Per-Class metrics table
            self._perclass_tab = QWidget()
            perclass_layout = QVBoxLayout(self._perclass_tab)
            self._perclass_table = QTableWidget()
            self._perclass_table.setColumnCount(5)
            self._perclass_table.setHorizontalHeaderLabels(
                [
                    tr("类别", "Class"),
                    tr("实例数", "Instances"),
                    "Precision",
                    "Recall",
                    "mAP@0.5",
                ]
            )
            self._perclass_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch
            )
            self._perclass_table.setSortingEnabled(True)
            perclass_layout.addWidget(self._perclass_table)
            self._tabs.addTab(
                self._perclass_tab, tr("按类别", "Per-Class")
            )

            # Tab 3: Charts
            self._metrics_plot = MetricsPlotWidget()
            self._tabs.addTab(self._metrics_plot, tr("图表", "Charts"))

            layout.addWidget(self._tabs)

        # ------------------------------------------------------------------
        # public API
        # ------------------------------------------------------------------

        def display_metrics(self, metrics: dict) -> None:
            """Display evaluation metrics.

            Args:
                metrics: Dict with keys from Ultralytics val output.
            """
            kpi_data = {
                "mAP@0.5": metrics.get("metrics/mAP50(B)", 0),
                "mAP@0.5:0.95": metrics.get("metrics/mAP50-95(B)", 0),
                "Precision": metrics.get("metrics/precision(B)", 0),
                "Recall": metrics.get("metrics/recall(B)", 0),
                "F1": metrics.get("metrics/f1(B)", 0),
            }
            self._update_kpis(kpi_data)

            mAP = kpi_data.get("mAP@0.5:0.95", 0)
            self._update_conclusion(mAP)

            per_class = metrics.get("per_class", [])
            self._update_per_class_table(per_class)

            self._update_charts(metrics, per_class)

            has_misclass = (
                metrics.get("fp_count", 0) > 0
                or metrics.get("fn_count", 0) > 0
            )
            self._misclass_btn.setVisible(has_misclass)

        # ------------------------------------------------------------------
        # private helpers
        # ------------------------------------------------------------------

        def _update_kpis(self, kpi_data: dict[str, float]) -> None:
            """Set KPI label values from parsed metric data."""
            for metric, value in kpi_data.items():
                if metric in self._kpi_labels:
                    if isinstance(value, (int, float)):
                        self._kpi_labels[metric].setText(
                            f"{value:.4f}"
                        )
                    else:
                        self._kpi_labels[metric].setText(str(value))

        def _update_conclusion(self, mAP: float) -> None:
            """Generate conclusion text based on mAP@0.5:0.95 score."""
            conclusions = []
            if isinstance(mAP, (int, float)):
                if mAP < 0.3:
                    conclusions.append(
                        tr(
                            "模型性能较低，建议检查数据质量和标注一致性",
                            "Low model performance — check data quality"
                            " and annotation consistency",
                        )
                    )
                elif mAP < 0.6:
                    conclusions.append(
                        tr(
                            "模型性能中等，可考虑增加训练数据或调整超参数",
                            "Moderate performance — consider adding"
                            " training data or tuning hyperparameters",
                        )
                    )
                else:
                    conclusions.append(
                        tr("模型性能良好", "Good model performance")
                    )
            self._conclusion_label.setText("\n".join(conclusions))

        def _update_per_class_table(
            self, per_class: list[dict]
        ) -> None:
            """Populate the per-class metrics table."""
            self._perclass_table.setRowCount(len(per_class))
            for i, cls_data in enumerate(per_class):
                self._perclass_table.setItem(
                    i, 0,
                    QTableWidgetItem(
                        cls_data.get("name", f"class_{i}")
                    ),
                )
                self._perclass_table.setItem(
                    i, 1,
                    QTableWidgetItem(
                        str(cls_data.get("instances", "-"))
                    ),
                )
                for j, key in enumerate(
                    ["precision", "recall", "mAP50"]
                ):
                    val = cls_data.get(key, 0)
                    item_text = (
                        f"{val:.4f}"
                        if isinstance(val, float)
                        else str(val)
                    )
                    self._perclass_table.setItem(
                        i, j + 2, QTableWidgetItem(item_text)
                    )

        def _update_charts(
            self,
            metrics: dict,
            per_class: list[dict],
        ) -> None:
            """Update confusion matrix and per-class AP charts."""
            cm = metrics.get("confusion_matrix")
            class_names = [
                c.get("name", f"c{i}")
                for i, c in enumerate(per_class)
            ]
            if cm and class_names:
                self._metrics_plot.plot_confusion_matrix(
                    cm, class_names
                )

            ap_per_class: dict[str, float] = {
                str(i): float(c.get("mAP50", 0))
                for i, c in enumerate(per_class)
            }
            if ap_per_class and class_names:
                self._metrics_plot.plot_per_class_ap(
                    ap_per_class, class_names
                )

        def clear(self):
            """Clear all displayed metrics."""
            for label in self._kpi_labels.values():
                label.setText("—")
            self._conclusion_label.setText("")
            self._conclusion_label.setStyleSheet(
                f"font-family: {FONT_FAMILY};"
            )
            self._perclass_table.setRowCount(0)
            self._metrics_plot.clear_all()
            self._misclass_btn.setVisible(False)

        def show_error(self, message: str):
            """Show error state."""
            self.clear()
            self._conclusion_label.setText(message)
            self._conclusion_label.setStyleSheet(
                f"color: red; font-family: {FONT_FAMILY};"
            )

except ImportError:
    EvalReportWidget = None  # type: ignore

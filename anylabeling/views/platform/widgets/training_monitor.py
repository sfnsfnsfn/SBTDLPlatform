"""TrainingMonitor — embedded matplotlib canvas for real-time training metrics.

Reads ``results.csv`` from the active training run and renders Loss / mAP
curves updated via a QTimer every 2 seconds.  The timer is only active
when a job is assigned via :meth:`set_active_job`.
"""
from __future__ import annotations

import csv
from pathlib import Path

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_BODY,
    get_heading_label_style,
)

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure

    from PyQt6 import QtCore, QtWidgets

    class TrainingMonitor(QtWidgets.QWidget):
        """Live training metrics graph with matplotlib embedded."""

        _POLL_MS = 2000  # refresh every 2 seconds

        def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
            super().__init__(parent)

            self._active_job_id: str | None = None
            self._runs_root: str = ""
            self._csv_path: str = ""

            self._setup_ui()

            self._timer = QtCore.QTimer(self)
            self._timer.timeout.connect(self._refresh)
            self._timer.setInterval(self._POLL_MS)

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def set_active_job(self, job_id: str, runs_root: str) -> None:
            """Start monitoring the given training job."""
            self._active_job_id = job_id
            self._runs_root = runs_root
            self._csv_path = str(
                Path(runs_root) / job_id / "train" / "results.csv"
            )
            self._status_label.setText(
                tr(f"监控中: {job_id}", f"Monitoring: {job_id}")
            )
            self._timer.start()

        def clear_active_job(self) -> None:
            """Stop monitoring and clear the display."""
            self._timer.stop()
            self._active_job_id = None
            self._runs_root = ""
            self._csv_path = ""
            self._status_label.setText(
                tr("空闲", "IDLE")
            )
            self._clear_plots()

        # ------------------------------------------------------------------
        # UI Setup
        # ------------------------------------------------------------------

        def _setup_ui(self) -> None:
            layout = QtWidgets.QVBoxLayout()
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(4)

            # Header
            header = QtWidgets.QLabel(tr("训练监控", "Training Monitor"))
            header.setStyleSheet(get_heading_label_style())
            layout.addWidget(header)

            # Status label
            self._status_label = QtWidgets.QLabel(tr("空闲", "IDLE"))
            self._status_label.setStyleSheet(
                f"font-size: {FONT_SIZE_CAPTION}px; color: gray;"
                f"font-family: {FONT_FAMILY};"
            )
            layout.addWidget(self._status_label)

            # Matplotlib canvas
            self._fig = Figure(figsize=(5, 3), dpi=100)
            self._fig.set_layout_engine("tight")
            self._canvas = FigureCanvasQTAgg(self._fig)
            layout.addWidget(self._canvas, stretch=1)

            self.setLayout(layout)

        # ------------------------------------------------------------------
        # Refresh cycle
        # ------------------------------------------------------------------

        def _refresh(self) -> None:
            """Read results.csv and update plots."""
            if not self._csv_path or not Path(self._csv_path).exists():
                return

            metrics = self._parse_results_csv()
            if not metrics:
                return

            self._draw_plots(metrics)

        def _parse_results_csv(self) -> dict[str, list[float]]:
            """Parse results.csv into column → list[value]."""
            columns: dict[str, list[float]] = {}
            try:
                with Path(self._csv_path).open(
                    "r", encoding="utf-8", newline=""
                ) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        for col_name, value_str in row.items():
                            col_name = col_name.strip()
                            if col_name == "epoch":
                                continue
                            try:
                                val = float(value_str.strip())
                            except (ValueError, TypeError):
                                continue
                            columns.setdefault(col_name, []).append(val)
            except (OSError, UnicodeDecodeError):
                pass
            return columns

        def _draw_plots(self, metrics: dict[str, list[float]]) -> None:
            """Draw loss and mAP curves on the figure."""
            self._fig.clear()

            # Sort columns: loss first, then mAP
            loss_cols = sorted(
                [k for k in metrics if "loss" in k.lower()],
                key=lambda k: k.lower(),
            )
            map_cols = sorted(
                [k for k in metrics if "map" in k.lower()],
                key=lambda k: k.lower(),
            )

            n_plots = (1 if loss_cols else 0) + (1 if map_cols else 0)
            if n_plots == 0:
                # No recognized columns — show the first couple
                non_epoch = [k for k in metrics if k != "epoch"]
                if non_epoch:
                    ax = self._fig.add_subplot(111)
                    for col in non_epoch[:4]:
                        ax.plot(metrics[col], label=col, linewidth=1)
                    ax.legend(fontsize=7)
                    ax.set_title(tr("训练指标", "Training Metrics"), fontsize=10)
                self._canvas.draw()
                return

            plot_idx = 1
            if loss_cols:
                ax = self._fig.add_subplot(n_plots, 1, plot_idx)
                for col in loss_cols:
                    ax.plot(metrics[col], label=col, linewidth=1)
                ax.legend(fontsize=7)
                ax.set_ylabel(tr("Loss", "Loss"), fontsize=9)
                ax.set_title(tr("训练 Loss 曲线", "Training Loss"), fontsize=10)
                ax.grid(True, alpha=0.3)
                plot_idx += 1

            if map_cols:
                ax = self._fig.add_subplot(n_plots, 1, plot_idx)
                for col in map_cols:
                    ax.plot(metrics[col], label=col, linewidth=1)
                ax.legend(fontsize=7)
                ax.set_xlabel(tr("轮次", "Epoch"), fontsize=9)
                ax.set_ylabel("mAP", fontsize=9)
                ax.set_title(tr("mAP 曲线", "mAP Curve"), fontsize=10)
                ax.grid(True, alpha=0.3)

            self._canvas.draw()

        def _clear_plots(self) -> None:
            """Clear all plot axes."""
            self._fig.clear()
            self._canvas.draw()

        def closeEvent(self, event: QtCore.QEvent) -> None:
            if self._timer.isActive():
                self._timer.stop()
            super().closeEvent(event)

except ImportError:
    TrainingMonitor = None  # type: ignore


__all__ = ["TrainingMonitor"]

"""UltralyticsRunParser — parses Ultralytics training output into Run metrics.

Architecture constraints:
    - No PyQt6 imports.
    - No ultralytics imports (operates on CSV/YAML output files).
    - Compatible with csv/stdlib only.
"""

from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path
from typing import Any

from anylabeling.platform.domain.run import MetricPoint

logger = logging.getLogger(__name__)


class UltralyticsRunParser:
    """Parse Ultralytics YOLO training output into platform Run records.

    Ultralytics writes training results to these files inside the run
    output directory::

        train/
          results.csv   — per-epoch metrics
          args.yaml     — the training configuration used
          weights/
            best.pt     — best checkpoint weights
            last.pt     — last epoch weights
    """

    # ------------------------------------------------------------------
    # results.csv
    # ------------------------------------------------------------------

    def parse_results_csv(
        self,
        results_path: str | Path,
    ) -> list[MetricPoint]:
        """Parse an Ultralytics ``results.csv`` into a list of MetricPoint.

        The CSV has a header row with column names like::

            epoch, train/box_loss, train/cls_loss, ...,
            metrics/precision(B), metrics/recall(B),
            metrics/mAP50(B), metrics/mAP50-95(B), ...

        Each data row represents one epoch.  Every numeric column is
        emitted as a separate MetricPoint with ``step`` set to the epoch
        number (1-indexed).

        Args:
            results_path: Path to the ``results.csv`` file.

        Returns:
            List of MetricPoint.  Returns an empty list if the file does
            not exist or contains no data rows.
        """
        path = Path(results_path)
        if not path.exists():
            return []

        metrics: list[MetricPoint] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    epoch = int(row.get("epoch", "0"))
                except (ValueError, TypeError):
                    epoch = 0

                for col_name, value_str in row.items():
                    if col_name.strip() == "epoch":
                        continue
                    try:
                        value = float(value_str.strip())
                    except (ValueError, TypeError):
                        continue
                    metrics.append(
                        MetricPoint(
                            name=col_name.strip(),
                            value=value,
                            step=epoch,
                        )
                    )

        return metrics

    # ------------------------------------------------------------------
    # args.yaml
    # ------------------------------------------------------------------

    def parse_args_yaml(self, args_path: str | Path) -> dict[str, Any]:
        """Parse an Ultralytics ``args.yaml`` into a config dict.

        ``args.yaml`` is a simple YAML file with ``key: value`` pairs
        recording all training arguments.  Falls back to returning an
        empty dict if ``yaml`` is not importable or the file is missing.

        Args:
            args_path: Path to the ``args.yaml`` file.

        Returns:
            Dict of training argument key → value.
        """
        path = Path(args_path)
        if not path.exists():
            return {}

        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML not available, args.yaml parsing skipped")
            return {}

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
        return {}

    # ------------------------------------------------------------------
    # best epoch
    # ------------------------------------------------------------------

    def find_best_epoch(
        self,
        metrics: list[MetricPoint],
    ) -> dict[str, Any] | None:
        """Find the best epoch by the primary metric (mAP50-95 or accuracy).

        Searches for metrics in priority order: ``metrics/mAP50-95(B)``
        (detection), ``metrics/accuracy_top1`` (classification), or
        ``val/loss`` as a fallback.  Once a candidate metric is found,
        lower-priority candidates are not considered — this prevents a
        numerically-smaller loss value from overwriting a higher-priority
        mAP selection.

        Returns:
            A dict with keys ``epoch`` and ``metric`` (the best metric
            name and value), or ``None`` if no relevant metrics were found.
        """
        # Priority order for "best" metric
        candidates = [
            "metrics/mAP50-95(B)",
            "metrics/accuracy_top1",
            "metrics/accuracy_top5",
            "val/loss",
        ]

        # Group metrics by name so we can search candidates in priority order
        by_name: dict[str, list[MetricPoint]] = {}
        for mp in metrics:
            if mp.name not in candidates:
                continue
            by_name.setdefault(mp.name, []).append(mp)

        for candidate_name in candidates:
            points = by_name.get(candidate_name)
            if not points:
                continue
            # Higher is better for map/accuracy; lower is better for loss
            if candidate_name == "val/loss":
                best_mp = min(points, key=lambda m: m.value)
            else:
                best_mp = max(points, key=lambda m: m.value)
            return {
                "epoch": best_mp.step,
                "metric": best_mp.name,
                "value": best_mp.value,
            }

        return None

    # ------------------------------------------------------------------
    # weight file paths
    # ------------------------------------------------------------------

    def get_best_weight_path(self, output_dir: str | Path) -> str | None:
        """Return the absolute path to ``best.pt`` if it exists.

        Ultralytics saves the best checkpoint at::

            <output_dir>/train/weights/best.pt

        Returns:
            Absolute path string, or ``None`` if the file does not exist.
        """
        path = Path(output_dir) / "train" / "weights" / "best.pt"
        if path.exists():
            return str(path.absolute())
        return None

    def get_last_weight_path(self, output_dir: str | Path) -> str | None:
        """Return the absolute path to ``last.pt`` if it exists.

        Ultralytics saves the last checkpoint at::

            <output_dir>/train/weights/last.pt

        Returns:
            Absolute path string, or ``None`` if the file does not exist.
        """
        path = Path(output_dir) / "train" / "weights" / "last.pt"
        if path.exists():
            return str(path.absolute())
        return None

    # ------------------------------------------------------------------
    # val output parsing
    # ------------------------------------------------------------------

    def parse_val_per_class_metrics(
        self,
        metrics_path: str | Path,
    ) -> dict | None:
        """Parse per-class metrics JSON saved by the val worker.

        Expected JSON structure::

            {
                "ap_per_class": {"0": 0.852, "1": 0.731, ...},
                "class_names": ["cat", "dog", ...],
                "mAP50": 0.842,
                "mAP50_95": 0.651,
                "precision": 0.88,
                "recall": 0.79,
            }

        Returns:
            Dict or None if file missing or invalid.
        """
        import json

        path = Path(metrics_path)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "ap_per_class" not in data and "mAP50_95" not in data:
                return None
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def parse_val_confusion_matrix(
        self,
        matrix_path: str | Path,
    ):
        """Load a confusion matrix from a .npy file saved by the val worker.

        Returns:
            numpy.ndarray or None if file missing or invalid.
        """
        import numpy as np

        path = Path(matrix_path)
        if not path.exists():
            return None

        try:
            matrix = np.load(str(path))
            if not isinstance(matrix, np.ndarray) or matrix.ndim != 2:
                return None
            return matrix
        except (ValueError, OSError):
            return None


__all__ = [
    "UltralyticsRunParser",
]

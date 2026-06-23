"""Adapter that converts a DatasetBuild to Ultralytics YOLO data.yaml format.

This is the bridge between the platform's DatasetBuild and
Ultralytics' ``model.train(data=...)`` parameter.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.task import TaskSpec


class UltralyticsDatasetAdapter:
    """Adapts a platform DatasetBuild to Ultralytics YOLO data.yaml format."""

    # ------------------------------------------------------------------
    # adapt
    # ------------------------------------------------------------------

    def adapt(self, build: DatasetBuild, task_spec: TaskSpec) -> dict:
        """Convert DatasetBuild to YOLO data.yaml dict.

        Returns dict with keys: path, train, val, test, nc, names

        The DatasetBuild output_path contains:
            images/train/, images/val/, images/test/
            labels/train/, labels/val/, labels/test/

        Generated data.yaml:
            path: <absolute path to build output>
            train: images/train
            val: images/val
            test: images/test  (if exists)
            nc: <number of classes>
            names: {0: "class1", 1: "class2", ...}
        """
        build_dir = Path(build.output_path)

        data = {
            "path": str(build_dir.absolute()),
            "train": "images/train",
            "val": "images/val",
        }

        # Add test if exists
        test_dir = build_dir / "images" / "test"
        if test_dir.exists():
            data["test"] = "images/test"

        # Class count and names from TaskSpec
        labels = task_spec.labels
        data["nc"] = len(labels)
        data["names"] = {i: label.name for i, label in enumerate(labels)}

        return data

    # ------------------------------------------------------------------
    # write_data_yaml
    # ------------------------------------------------------------------

    def write_data_yaml(self, build: DatasetBuild, task_spec: TaskSpec) -> Path:
        """Write data.yaml to the build directory. Returns path to written file."""
        data = self.adapt(build, task_spec)
        yaml_path = Path(build.output_path) / "data.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        return yaml_path

    # ------------------------------------------------------------------
    # get_data_path
    # ------------------------------------------------------------------

    def get_data_path(self, build: DatasetBuild) -> str:
        """Return the absolute path to data.yaml for use with YOLO model.train()."""
        yaml_path = Path(build.output_path) / "data.yaml"
        return str(yaml_path.absolute())


__all__ = [
    "UltralyticsDatasetAdapter",
]

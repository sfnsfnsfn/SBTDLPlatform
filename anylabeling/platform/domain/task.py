from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class LabelClass:
    """A single label class definition within a task specification."""

    id: int
    name: str
    color: str | None = None
    supercategory: str | None = None


@dataclass(frozen=True)
class TaskSpec:
    """Platform-wide task specification defining the vision task family, labels,
    annotation schema and primary evaluation metric.

    This is the immutable contract that downstream DatasetBuild, Run, and
    Evaluation all reference.  Coordinates are always L0 image coordinates.
    """

    id: str
    family: Literal[
        "classification",
        "detection_hbb",
        "detection_obb",
        "instance_segmentation",
        "pose",
        "semantic_segmentation",
        "anomaly",
        "ocr",
    ]
    labels: tuple[LabelClass, ...] = ()
    annotation_schema: str = "xanylabeling_json"
    primary_metric: str = "mAP50-95"
    version: int = 1


__all__ = [
    "LabelClass",
    "TaskSpec",
]

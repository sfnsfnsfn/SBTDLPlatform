from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class MetricPoint:
    """A single named metric value at a given training step / epoch."""

    name: str
    value: float
    step: int


@dataclass
class Run:
    """A training run record that captures the full provenance chain:

    adapter, task, dataset build, base model, configuration, environment,
    status, collected metrics and the best metric achieved.
    """

    id: str
    adapter_id: str = ""
    task_family: str = ""
    dataset_build_id: str = ""
    base_model: str = ""
    base_model_sha256: str = ""
    config: dict = field(default_factory=dict)
    environment: dict = field(default_factory=dict)
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = "queued"
    metrics: list[MetricPoint] = field(default_factory=list)
    best_metric: dict | None = None
    output_dir: str | None = None


__all__ = [
    "MetricPoint",
    "Run",
]

from __future__ import annotations

from enum import Enum


class WorkflowStage(str, Enum):
    """Named stages in the model training pipeline."""

    DATA_PREP = "data_prep"
    TRAINING = "training"
    EVALUATION = "evaluation"
    EXPORT = "export"


class WorkflowStepStatus(str, Enum):
    """Possible states for a workflow stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


__all__ = [
    "WorkflowStage",
    "WorkflowStepStatus",
]

from __future__ import annotations

from typing import Protocol, runtime_checkable

from anylabeling.platform.domain.records import (
    AnnotationSummaryRecord,
    AssetRecord,
    DatasetBuildRecord,
    EvaluationRecord,
    JobRecord,
    ModelRecord,
    RunRecord,
)
from anylabeling.platform.domain.workflow_status import WorkflowStepStatus


@runtime_checkable
class AssetRepositoryPort(Protocol):
    """Repository contract for asset records."""

    def upsert(self, record: AssetRecord) -> AssetRecord:
        """Insert or update an asset record. Returns the persisted record."""
        ...

    def get(self, asset_id: str) -> AssetRecord | None:
        """Retrieve an asset record by ID, or None if not found."""
        ...

    def list(
        self, offset: int = 0, limit: int | None = None
    ) -> list[AssetRecord]:
        """List asset records with pagination."""
        ...

    def stats(self) -> dict:
        """Return aggregate statistics about assets."""
        ...

    def mark_deleted(self, asset_id: str) -> None:
        """Soft-delete (mark deleted) an asset record."""
        ...


@runtime_checkable
class AnnotationRepositoryPort(Protocol):
    """Repository contract for annotation summaries."""

    def upsert_summary(
        self, record: AnnotationSummaryRecord
    ) -> AnnotationSummaryRecord:
        """Insert or update an annotation summary. Returns the persisted record."""
        ...

    def get_by_asset(self, asset_id: str) -> AnnotationSummaryRecord | None:
        """Retrieve annotation summary for an asset, or None."""
        ...

    def count_annotated(self) -> int:
        """Return the number of assets with annotation summaries."""
        ...

    def label_histogram(self) -> dict[str, int]:
        """Return a dict mapping label name to object count across all annotations."""
        ...


@runtime_checkable
class DatasetBuildRepositoryPort(Protocol):
    """Repository contract for dataset build records."""

    def create(self, record: DatasetBuildRecord) -> DatasetBuildRecord:
        """Create a new dataset build record. Returns the persisted record."""
        ...

    def mark_running(self, build_id: str) -> None:
        """Transition build status to running."""
        ...

    def mark_completed(self, build_id: str) -> None:
        """Transition build status to completed."""
        ...

    def mark_failed(self, build_id: str, error_message: str) -> None:
        """Transition build status to failed."""
        ...

    def list_completed(self) -> list[DatasetBuildRecord]:
        """Return all completed dataset build records."""
        ...

    def get_latest_completed(self) -> DatasetBuildRecord | None:
        """Return the most recently completed build, or None."""
        ...


@runtime_checkable
class RunRepositoryPort(Protocol):
    """Repository contract for training run records."""

    def create(self, record: RunRecord) -> RunRecord:
        """Create a new run record. Returns the persisted record."""
        ...

    def mark_running(self, run_id: str) -> None:
        """Transition run status to running."""
        ...

    def mark_completed(self, run_id: str) -> None:
        """Transition run status to completed."""
        ...

    def mark_failed(self, run_id: str, error_message: str) -> None:
        """Transition run status to failed."""
        ...

    def list_completed(self) -> list[RunRecord]:
        """Return all completed run records."""
        ...

    def get(self, run_id: str) -> RunRecord | None:
        """Retrieve a run record by ID, or None."""
        ...


@runtime_checkable
class JobRepositoryPort(Protocol):
    """Repository contract for background job records."""

    def create(self, record: JobRecord) -> JobRecord:
        """Create a new job record. Returns the persisted record."""
        ...

    def update_progress(self, job_id: str, progress: float) -> None:
        """Update the progress percentage of a job."""
        ...

    def mark_completed(self, job_id: str) -> None:
        """Transition job state to completed."""
        ...

    def mark_failed(self, job_id: str, error_message: str) -> None:
        """Transition job state to failed."""
        ...

    def list_active(self) -> list[JobRecord]:
        """Return all active (non-terminal) job records."""
        ...

    def get(self, job_id: str) -> JobRecord | None:
        """Retrieve a job record by ID, or None."""
        ...


@runtime_checkable
class ModelRepositoryPort(Protocol):
    """Repository contract for trained model records."""

    def upsert(self, record: ModelRecord) -> ModelRecord:
        """Insert or update a model record. Returns the persisted record."""
        ...

    def list_ready(self) -> list[ModelRecord]:
        """Return all models marked as ready for inference."""
        ...

    def get_by_run(self, run_id: str) -> ModelRecord | None:
        """Retrieve a model record associated with a run, or None."""
        ...


@runtime_checkable
class EvaluationRepositoryPort(Protocol):
    """Repository contract for evaluation records."""

    def create(self, record: EvaluationRecord) -> EvaluationRecord:
        """Create a new evaluation record. Returns the persisted record."""
        ...

    def mark_completed(self, evaluation_id: str) -> None:
        """Transition evaluation status to completed."""
        ...

    def list_by_run(self, run_id: str) -> list[EvaluationRecord]:
        """Return all evaluation records for a given run."""
        ...


@runtime_checkable
class WorkflowQueryPort(Protocol):
    """Query interface for workflow pipeline stage statuses."""

    def data_prep_status(self) -> WorkflowStepStatus:
        """Return the current status of the data preparation stage."""
        ...

    def train_status(self) -> WorkflowStepStatus:
        """Return the current status of the training stage."""
        ...

    def eval_status(self) -> WorkflowStepStatus:
        """Return the current status of the evaluation stage."""
        ...

    def export_status(self) -> WorkflowStepStatus:
        """Return the current status of the export stage."""
        ...

    def next_action(self) -> str | None:
        """Return a description of the next recommended action, or None."""
        ...


__all__ = [
    "AssetRepositoryPort",
    "AnnotationRepositoryPort",
    "DatasetBuildRepositoryPort",
    "RunRepositoryPort",
    "JobRepositoryPort",
    "ModelRepositoryPort",
    "EvaluationRepositoryPort",
    "WorkflowQueryPort",
]

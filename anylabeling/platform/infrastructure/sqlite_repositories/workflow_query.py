"""SQLite-backed implementation of WorkflowQueryPort for pipeline stage queries.

Aggregates across the assets, annotation_summaries, dataset_builds, runs,
and models tables to derive the current state of each ML pipeline stage.

This is a read-only query object -- it does not create or manage any tables.
"""

from __future__ import annotations

from anylabeling.platform.domain.workflow_status import WorkflowStepStatus
from anylabeling.platform.infrastructure.project_db import ProjectDb


class SQLiteWorkflowQuery:
    """Queries the project database for workflow pipeline stage statuses.

    Each ``*_status()`` method inspects the relevant tables and returns a
    :class:`WorkflowStepStatus` value.  The ``next_action()`` method provides
    a human-readable description of the most pressing next step.

    Args:
        db: An open :class:`ProjectDb` instance.
    """

    def __init__(self, db: ProjectDb) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Stage queries
    # ------------------------------------------------------------------

    def data_prep_status(self) -> WorkflowStepStatus:
        """Derive data-preparation stage status from assets and annotations.

        - ``PENDING`` -- no active assets exist.
        - ``RUNNING`` -- assets exist but none have annotations yet.
        - ``COMPLETED`` -- at least one asset has annotations.
        """
        active = self._db.query_one(
            "SELECT COUNT(*) AS cnt FROM assets "
            "WHERE status = 'active' AND deleted_at IS NULL"
        )
        active_count = active["cnt"] if active else 0

        annotated = self._db.query_one(
            "SELECT COUNT(*) AS cnt FROM annotation_summaries "
            "WHERE object_count > 0 AND status = 'active'"
        )
        annotated_count = annotated["cnt"] if annotated else 0

        if active_count == 0:
            return WorkflowStepStatus.PENDING
        if annotated_count == 0:
            return WorkflowStepStatus.RUNNING
        return WorkflowStepStatus.COMPLETED

    def train_status(self) -> WorkflowStepStatus:
        """Derive training stage status from dataset builds.

        - ``COMPLETED`` -- at least one dataset build completed.
        - ``BLOCKED`` -- no builds completed; a build failed, **or** data
          preparation is not yet complete (prerequisite not met).
        - ``PENDING`` -- no builds attempted yet and prerequisites are satisfied.
        """
        completed = self._db.query_one(
            "SELECT COUNT(*) AS cnt FROM dataset_builds "
            "WHERE status = 'completed' AND deleted_at IS NULL"
        )
        if completed and completed["cnt"] > 0:
            return WorkflowStepStatus.COMPLETED

        failed = self._db.query_one(
            "SELECT COUNT(*) AS cnt FROM dataset_builds "
            "WHERE status = 'failed' AND deleted_at IS NULL"
        )
        if failed and failed["cnt"] > 0:
            return WorkflowStepStatus.BLOCKED

        if self.data_prep_status() != WorkflowStepStatus.COMPLETED:
            return WorkflowStepStatus.BLOCKED

        return WorkflowStepStatus.PENDING

    def eval_status(self) -> WorkflowStepStatus:
        """Derive evaluation stage status from completed training runs.

        - ``COMPLETED`` -- at least one training run completed.
        - ``BLOCKED`` -- no runs completed; training prerequisite not met.
        - ``PENDING`` -- no runs yet and prerequisites are satisfied.
        """
        completed = self._db.query_one(
            "SELECT COUNT(*) AS cnt FROM runs WHERE status = 'completed'"
        )
        if completed and completed["cnt"] > 0:
            return WorkflowStepStatus.COMPLETED

        if self.train_status() != WorkflowStepStatus.COMPLETED:
            return WorkflowStepStatus.BLOCKED

        return WorkflowStepStatus.PENDING

    def export_status(self) -> WorkflowStepStatus:
        """Derive export stage status from ready models.

        - ``COMPLETED`` -- at least one model is marked ready for export.
        - ``BLOCKED`` -- no ready model; evaluation prerequisite not met.
        - ``PENDING`` -- no ready model yet but prerequisites are satisfied.
        """
        ready = self._db.query_one(
            "SELECT COUNT(*) AS cnt FROM models WHERE ready = 1"
        )
        if ready and ready["cnt"] > 0:
            return WorkflowStepStatus.COMPLETED

        if self.eval_status() != WorkflowStepStatus.COMPLETED:
            return WorkflowStepStatus.BLOCKED

        return WorkflowStepStatus.PENDING

    # ------------------------------------------------------------------
    # Next action
    # ------------------------------------------------------------------

    def next_action(self) -> str | None:
        """Return a human-readable description of the next recommended action.

        Walks the pipeline stages in order and returns guidance for the first
        stage that is not yet completed.  Returns ``None`` when every stage
        reports ``COMPLETED``.
        """
        data_prep = self.data_prep_status()
        train = self.train_status()
        eval_st = self.eval_status()
        export = self.export_status()

        # All stages complete -- nothing to do
        if (
            data_prep is WorkflowStepStatus.COMPLETED
            and train is WorkflowStepStatus.COMPLETED
            and eval_st is WorkflowStepStatus.COMPLETED
            and export is WorkflowStepStatus.COMPLETED
        ):
            return None

        # Data preparation
        if data_prep is WorkflowStepStatus.PENDING:
            return "Import assets to begin data preparation"
        if data_prep is WorkflowStepStatus.RUNNING:
            return "Annotate imported assets to complete data preparation"

        # Training
        if train is WorkflowStepStatus.PENDING:
            return "Build a dataset and start a training run"
        if train is WorkflowStepStatus.BLOCKED:
            if self.data_prep_status() != WorkflowStepStatus.COMPLETED:
                return (
                    "Complete data preparation (import and annotate assets) "
                    "before training"
                )
            return "Fix the failed dataset build before training"

        # Evaluation
        if eval_st is WorkflowStepStatus.PENDING:
            return "Run evaluation on the completed training run"
        if eval_st is WorkflowStepStatus.BLOCKED:
            return "Complete training before evaluation"

        # Export
        if export is WorkflowStepStatus.PENDING:
            return "Export the trained model for inference"
        if export is WorkflowStepStatus.BLOCKED:
            return "Complete evaluation before exporting"

        return None

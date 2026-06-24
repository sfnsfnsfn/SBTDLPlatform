"""WorkflowState — compute per-domain navigation state from project data.

Inspects the project filesystem to determine the ``NavState`` for each
of the 5 domains (Project, Data Prep, Train, Eval & Validate, Export).

Architecture constraints:
    - No PyQt6 imports (safe for worker processes).
    - No Ultralytics imports.
    - All paths are pathlib.Path.
    - All file I/O is UTF-8.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

# Domain values (mirrors primary_navigation.Domain)
_DOMAIN_PROJECT = 0
_DOMAIN_DATA_PREP = 1
_DOMAIN_TRAIN = 2
_DOMAIN_EVAL_VALIDATE = 3
_DOMAIN_EXPORT = 4

# NavState values (mirrors primary_navigation.NavState)
_STATE_NOT_STARTED = "not_started"
_STATE_READY = "ready"
_STATE_IN_PROGRESS = "in_progress"
_STATE_COMPLETED = "completed"
_STATE_NEEDS_ATTENTION = "needs_attention"
_STATE_EXPIRED = "expired"

logger = logging.getLogger(__name__)

MAX_RUNS = 1000


# ---------------------------------------------------------------------------
# DomainState — immutable value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainState:
    """Computed navigation state for a single domain.

    Attributes:
        domain: The Domain enum value (int).
        state: The NavState value (str).
        reason: Human-readable explanation of why this state was assigned.
        prerequisites: What must be completed before this domain becomes
            READY (empty list if the domain is already READY or COMPLETED).
    """

    domain: int
    state: str
    reason: str
    prerequisites: list[str]


# ---------------------------------------------------------------------------
# WorkflowState service
# ---------------------------------------------------------------------------


class WorkflowState:
    """Compute per-domain navigation state from project filesystem data.

    Usage::

        ws = WorkflowState(project_root)
        states = ws.refresh()
        for domain_val, domain_state in states.items():
            print(domain_state.state, domain_state.reason)
    """

    def __init__(self, project_root: str | Path, workflow_query=None) -> None:
        self._project_root = Path(project_root)
        self._workflow_query = workflow_query

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def workflow_query(self):
        return self._workflow_query

    def refresh(self) -> dict[int, DomainState]:
        """Recompute state for all 5 domains.

        Returns:
            Dict mapping ``Domain.value`` → ``DomainState``.
        """
        return {
            _DOMAIN_PROJECT: self._check_project(),
            _DOMAIN_DATA_PREP: self._check_data_prep(),
            _DOMAIN_TRAIN: self._check_train(),
            _DOMAIN_EVAL_VALIDATE: self._check_eval_validate(),
            _DOMAIN_EXPORT: self._check_export(),
        }

    def get_domain_state(self, domain: int) -> DomainState:
        """Get state for a single domain without recomputing all."""
        check_methods = {
            _DOMAIN_PROJECT: self._check_project,
            _DOMAIN_DATA_PREP: self._check_data_prep,
            _DOMAIN_TRAIN: self._check_train,
            _DOMAIN_EVAL_VALIDATE: self._check_eval_validate,
            _DOMAIN_EXPORT: self._check_export,
        }
        check_fn = check_methods.get(domain)
        if check_fn is None:
            return DomainState(
                domain=domain,
                state=_STATE_NOT_STARTED,
                reason=f"Unknown domain: {domain}",
                prerequisites=[],
            )
        return check_fn()

    # ------------------------------------------------------------------
    # Per-domain state checks
    # ------------------------------------------------------------------

    def _check_project(self) -> DomainState:
        """PROJECT domain is always READY."""
        return DomainState(
            domain=_DOMAIN_PROJECT,
            state=_STATE_READY,
            reason="Project is open",
            prerequisites=[],
        )

    def _check_data_prep(self) -> DomainState:
        """DATA_PREP: checks assets via DB or filesystem."""
        if self._workflow_query is not None:
            return self._check_data_prep_from_db()
        assets_dir = self._project_root / "assets"
        if not assets_dir.is_dir():
            return DomainState(
                domain=_DOMAIN_DATA_PREP,
                state=_STATE_NOT_STARTED,
                reason="No assets directory found",
                prerequisites=[
                    "Import images or open an image folder"
                ],
            )

        _image_exts = {
            ".jpg", ".jpeg", ".png", ".bmp",
            ".tif", ".tiff", ".webp",
        }
        try:
            asset_files = [
                f for f in assets_dir.iterdir()
                if f.is_file() and f.suffix.lower() in _image_exts
            ]
        except OSError:
            logger.exception("Failed to list assets directory")
            return DomainState(
                domain=_DOMAIN_DATA_PREP,
                state=_STATE_NEEDS_ATTENTION,
                reason="Cannot read assets directory",
                prerequisites=[
                    "Check project directory permissions"
                ],
            )

        if not asset_files:
            return DomainState(
                domain=_DOMAIN_DATA_PREP,
                state=_STATE_NOT_STARTED,
                reason="No image files in assets/",
                prerequisites=[
                    "Import images to the assets directory"
                ],
            )

        labels_file = self._project_root / "labels.json"
        has_labels = labels_file.is_file()

        annotations_dir = self._project_root / "annotations"
        try:
            has_annotations = (
                annotations_dir.is_dir()
                and any(annotations_dir.iterdir())
            )
        except OSError:
            has_annotations = False

        builds_dir = self._project_root / "dataset_builds"
        try:
            has_builds = (
                builds_dir.is_dir() and any(builds_dir.iterdir())
            )
        except OSError:
            has_builds = False

        if has_builds:
            return DomainState(
                domain=_DOMAIN_DATA_PREP,
                state=_STATE_COMPLETED,
                reason="Dataset build exists",
                prerequisites=[],
            )

        if has_annotations and has_labels:
            return DomainState(
                domain=_DOMAIN_DATA_PREP,
                state=_STATE_IN_PROGRESS,
                reason="Task configured and annotations present — "
                "dataset build pending",
                prerequisites=[
                    "Run dataset build to proceed to training"
                ],
            )

        if has_labels:
            return DomainState(
                domain=_DOMAIN_DATA_PREP,
                state=_STATE_IN_PROGRESS,
                reason="Task configured — annotation pending",
                prerequisites=[
                    "Annotate images before dataset build"
                ],
            )

        return DomainState(
            domain=_DOMAIN_DATA_PREP,
            state=_STATE_READY,
            reason=f"{len(asset_files)} assets imported — "
            "configure task and labels",
            prerequisites=[
                "Configure task type and label classes"
            ],
        )

    def _check_train(self) -> DomainState:
        """TRAIN: checks builds/runs via DB or filesystem."""
        if self._workflow_query is not None:
            return self._check_train_from_db()
        builds_dir = self._project_root / "dataset_builds"
        try:
            has_builds = (
                builds_dir.is_dir() and any(builds_dir.iterdir())
            )
        except OSError:
            has_builds = False

        if not has_builds:
            return DomainState(
                domain=_DOMAIN_TRAIN,
                state=_STATE_NOT_STARTED,
                reason="No dataset builds — complete Data Prep first",
                prerequisites=[
                    "Import images",
                    "Configure task and labels",
                    "Annotate images",
                    "Run dataset build",
                ],
            )

        runs = self._list_runs()
        if not runs:
            return DomainState(
                domain=_DOMAIN_TRAIN,
                state=_STATE_READY,
                reason="Dataset build exists — ready to train",
                prerequisites=[],
            )

        latest = runs[0]
        status = latest.get("status", "")

        if status == "completed":
            return DomainState(
                domain=_DOMAIN_TRAIN,
                state=_STATE_COMPLETED,
                reason=f"Training run {latest['id']} completed",
                prerequisites=[],
            )
        if status == "running":
            return DomainState(
                domain=_DOMAIN_TRAIN,
                state=_STATE_IN_PROGRESS,
                reason=f"Training run {latest['id']} in progress",
                prerequisites=[],
            )
        if status in {"cancelled", "cancelling"}:
            return DomainState(
                domain=_DOMAIN_TRAIN,
                state=_STATE_NEEDS_ATTENTION,
                reason=f"Training run {latest['id']} was cancelled",
                prerequisites=[],
            )
        if status == "failed":
            has_completed = any(
                r.get("status") == "completed" for r in runs
            )
            if has_completed:
                return DomainState(
                    domain=_DOMAIN_TRAIN,
                    state=_STATE_COMPLETED,
                    reason="At least one training run completed",
                    prerequisites=[],
                )
            return DomainState(
                domain=_DOMAIN_TRAIN,
                state=_STATE_NEEDS_ATTENTION,
                reason=f"Training run {latest['id']} failed — "
                "check logs and retry",
                prerequisites=[],
            )

        return DomainState(
            domain=_DOMAIN_TRAIN,
            state=_STATE_READY,
            reason="Ready to train",
            prerequisites=[],
        )

    def _check_eval_validate(self) -> DomainState:
        """EVAL_VALIDATE: checks runs/evaluations via DB or filesystem."""
        if self._workflow_query is not None:
            return self._check_eval_validate_from_db()
        runs = self._list_runs()
        completed_runs = [
            r for r in runs if r.get("status") == "completed"
        ]

        if not completed_runs:
            return DomainState(
                domain=_DOMAIN_EVAL_VALIDATE,
                state=_STATE_NOT_STARTED,
                reason="No completed training runs — "
                "train a model first",
                prerequisites=[
                    "Complete at least one training run",
                ],
            )

        evals_dir = self._project_root / "evaluations"
        try:
            has_evaluations = (
                evals_dir.is_dir() and any(evals_dir.iterdir())
            )
        except OSError:
            has_evaluations = False

        if has_evaluations:
            return DomainState(
                domain=_DOMAIN_EVAL_VALIDATE,
                state=_STATE_COMPLETED,
                reason="Evaluation results available",
                prerequisites=[],
            )

        return DomainState(
            domain=_DOMAIN_EVAL_VALIDATE,
            state=_STATE_READY,
            reason=f"{len(completed_runs)} completed run(s) — "
            "ready to evaluate",
            prerequisites=[],
        )

    def _check_export(self) -> DomainState:
        """EXPORT: checks models via DB or filesystem."""
        if self._workflow_query is not None:
            return self._check_export_from_db()
        models_dir = self._project_root / "models"
        if not models_dir.is_dir():
            return DomainState(
                domain=_DOMAIN_EXPORT,
                state=_STATE_NOT_STARTED,
                reason="No models directory — "
                "train and evaluate a model first",
                prerequisites=[
                    "Complete at least one training run",
                    "Evaluate the model",
                ],
            )

        try:
            exported = []
            for item in models_dir.iterdir():
                if item.is_dir():
                    ready_marker = item / "_READY"
                    model_json = item / "model.json"
                    if ready_marker.is_file() or model_json.is_file():
                        exported.append(item.name)
        except OSError:
            logger.exception("Failed to list models directory")
            return DomainState(
                domain=_DOMAIN_EXPORT,
                state=_STATE_NEEDS_ATTENTION,
                reason="Cannot read models directory",
                prerequisites=[
                    "Check project directory permissions"
                ],
            )

        if exported:
            return DomainState(
                domain=_DOMAIN_EXPORT,
                state=_STATE_READY,
                reason=f"{len(exported)} model(s) available for export",
                prerequisites=[],
            )

        return DomainState(
            domain=_DOMAIN_EXPORT,
            state=_STATE_NOT_STARTED,
            reason="No exported models — "
            "train a model before export",
            prerequisites=[
                "Complete at least one training run",
            ],
        )

    # ------------------------------------------------------------------
    # DB-backed state checks (used when workflow_query is available)
    # ------------------------------------------------------------------

    def _check_data_prep_from_db(self) -> DomainState:
        from anylabeling.platform.domain.workflow_status import WorkflowStepStatus
        status = self._workflow_query.data_prep_status()
        if status is WorkflowStepStatus.COMPLETED:
            return DomainState(domain=_DOMAIN_DATA_PREP, state=_STATE_COMPLETED,
                reason="Data preparation complete", prerequisites=[])
        if status is WorkflowStepStatus.RUNNING:
            return DomainState(domain=_DOMAIN_DATA_PREP, state=_STATE_IN_PROGRESS,
                reason="Annotation in progress",
                prerequisites=["Annotate imported assets"])
        return DomainState(domain=_DOMAIN_DATA_PREP, state=_STATE_NOT_STARTED,
            reason="Import images to begin data preparation",
            prerequisites=["Import images or open an image folder"])

    def _check_train_from_db(self) -> DomainState:
        from anylabeling.platform.domain.workflow_status import WorkflowStepStatus
        status = self._workflow_query.train_status()
        if status is WorkflowStepStatus.COMPLETED:
            return DomainState(domain=_DOMAIN_TRAIN, state=_STATE_COMPLETED,
                reason="Training completed", prerequisites=[])
        if status is WorkflowStepStatus.BLOCKED:
            return DomainState(domain=_DOMAIN_TRAIN, state=_STATE_NEEDS_ATTENTION,
                reason="Training blocked", prerequisites=["Fix dataset build issues"])
        if status is WorkflowStepStatus.RUNNING:
            return DomainState(domain=_DOMAIN_TRAIN, state=_STATE_IN_PROGRESS,
                reason="Training in progress", prerequisites=[])
        return DomainState(domain=_DOMAIN_TRAIN, state=_STATE_READY,
            reason="Ready to train", prerequisites=[])

    def _check_eval_validate_from_db(self) -> DomainState:
        from anylabeling.platform.domain.workflow_status import WorkflowStepStatus
        status = self._workflow_query.eval_status()
        if status is WorkflowStepStatus.COMPLETED:
            return DomainState(domain=_DOMAIN_EVAL_VALIDATE, state=_STATE_COMPLETED,
                reason="Evaluation completed", prerequisites=[])
        if status is WorkflowStepStatus.BLOCKED:
            return DomainState(domain=_DOMAIN_EVAL_VALIDATE, state=_STATE_NOT_STARTED,
                reason="Complete training before evaluation",
                prerequisites=["Complete at least one training run"])
        return DomainState(domain=_DOMAIN_EVAL_VALIDATE, state=_STATE_READY,
            reason="Ready to evaluate", prerequisites=[])

    def _check_export_from_db(self) -> DomainState:
        from anylabeling.platform.domain.workflow_status import WorkflowStepStatus
        status = self._workflow_query.export_status()
        if status is WorkflowStepStatus.COMPLETED:
            return DomainState(domain=_DOMAIN_EXPORT, state=_STATE_READY,
                reason="Model(s) available for export", prerequisites=[])
        if status is WorkflowStepStatus.BLOCKED:
            return DomainState(domain=_DOMAIN_EXPORT, state=_STATE_NOT_STARTED,
                reason="Complete evaluation before exporting",
                prerequisites=["Complete evaluation"])
        return DomainState(domain=_DOMAIN_EXPORT, state=_STATE_NOT_STARTED,
            reason="Train a model before export",
            prerequisites=["Complete at least one training run"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _list_runs(self) -> list[dict]:
        """List training runs ordered by most-recent first.

        Returns:
            List of run dicts with at least ``id`` and ``status`` keys.
            Empty list if runs/ does not exist or is unreadable.
        """
        runs_dir = self._project_root / "runs"
        if not runs_dir.is_dir():
            return []

        runs: list[dict] = []
        try:
            for run_dir in sorted(
                runs_dir.iterdir(),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:MAX_RUNS]:
                if not run_dir.is_dir():
                    continue
                run_json = run_dir / "run.json"
                if not run_json.is_file():
                    continue
                try:
                    data = json.loads(
                        run_json.read_text(encoding="utf-8")
                    )
                    runs.append({
                        "id": data.get("id", run_dir.name),
                        "status": data.get("status", "unknown"),
                    })
                except (json.JSONDecodeError, OSError):
                    logger.warning(
                        "Skipping unreadable run.json: %s", run_json
                    )
        except OSError:
            logger.exception("Failed to list runs directory")
            return []

        return runs


__all__ = [
    "DomainState",
    "WorkflowState",
]

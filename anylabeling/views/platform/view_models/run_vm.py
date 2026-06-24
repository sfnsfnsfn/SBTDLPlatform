"""RunViewModel — ViewModel for training run state.

Provides a clean API for the TrainWorkspace UI to start/stop training
and poll for training progress without directly accessing services.
"""

from __future__ import annotations

import logging

from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.application.training_service import TrainingService
from anylabeling.platform.adapters.ultralytics.train_adapter import TrainRequest

logger = logging.getLogger(__name__)


class RunViewModel:
    """ViewModel for training run state.

    Encapsulates JobService and TrainingService behind a simple API that
    the TrainWorkspace UI binds to.  No PyQt6 or Ultralytics imports.

    Usage::

        vm = RunViewModel(job_service, training_service)
        job_id = vm.start_training(request)
        status = vm.get_status(job_id)
        vm.stop_training(job_id)
    """

    def __init__(
        self,
        job_service: JobService,
        training_service: TrainingService,
    ) -> None:
        self._job_service = job_service
        self._training_service = training_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_training(self, request: TrainRequest) -> str:
        """Start training, return job_id.

        Delegates to TrainingService.start_training() which creates the
        Run record, builds the train command, and launches the subprocess
        via JobService.
        """
        return self._training_service.start_training(request)

    def stop_training(self, job_id: str) -> None:
        """Stop training by cancelling the job.

        Delegates to JobService.cancel_job() which writes the stop.flag
        and waits for graceful shutdown.
        """
        self._job_service.cancel_job(job_id)

    def get_status(self, job_id: str) -> dict:
        """Get current training status.

        Returns a dict with keys:
            state (str): One of queued/starting/running/completed/failed/cancelled.
            epoch (int): Current epoch number (0 if not available).
            best_metric (dict | None): Best metric seen so far, e.g.
                {"name": "mAP50", "value": 0.74}.

        If *job_id* is not found, returns ``{"state": "unknown", "epoch": 0,
        "best_metric": None}``.
        """
        try:
            state = self._job_service.get_job_state(job_id)
        except FileNotFoundError:
            return {"state": "unknown", "epoch": 0, "best_metric": None}

        result: dict = {
            "state": state.value,
            "epoch": 0,
            "best_metric": None,
        }

        # Extract epoch and best metric from job events
        try:
            events = self._job_service.get_job_events(job_id)
            for event in events:
                if event.type == "progress":
                    result["epoch"] = event.payload.get("epoch", result["epoch"])
                elif event.type == "metric":
                    name = event.payload.get("name", "")
                    value = event.payload.get("value", 0.0)
                    current = result["best_metric"]
                    if current is None or value > current.get("value", -float("inf")):
                        result["best_metric"] = {
                            "name": name,
                            "value": value,
                            "step": event.payload.get("step", 0),
                        }
        except Exception:
            logger.warning(
                "Failed to parse job events for %s", job_id, exc_info=True
            )
            result["parse_error"] = True

        return result

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def job_service(self) -> JobService:
        """The underlying JobService instance."""
        return self._job_service

    @property
    def training_service(self) -> TrainingService:
        """The underlying TrainingService instance."""
        return self._training_service


__all__ = ["RunViewModel"]

"""InferenceService — run model inference via JobService subprocess.

Architecture constraints:
    - No PyQt6 imports.
    - Uses adapters as bridge to algorithm implementations.
    - Uses domain prediction models (UnifiedPrediction, PredictionObject).
"""

from __future__ import annotations

from pathlib import Path

from anylabeling.platform.adapters.registry import AlgorithmRegistry
from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.domain.run import Run
from anylabeling.platform.workers.protocol import JobRequest


class InferenceService:
    """Application service for running model inference on images.

    Launches inference as a subprocess job via :class:`JobService`.
    Supports both single-image and batch inference.
    """

    def __init__(
        self,
        job_service: JobService,
        project_root: str | Path,
    ) -> None:
        self._job_service = job_service
        self._project_root = Path(project_root)

    # ------------------------------------------------------------------
    # provider resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _get_provider(run: Run):
        """Resolve the :class:`AlgorithmProvider` for *run*."""
        if run.adapter_id:
            try:
                return AlgorithmRegistry.get_provider(run.adapter_id)
            except KeyError:
                pass
        import anylabeling.platform.adapters.ultralytics  # noqa: F401
        return AlgorithmRegistry.get_provider("ultralytics_yolo_detect")

    # ------------------------------------------------------------------
    # inference
    # ------------------------------------------------------------------

    def infer_image(
        self,
        run: Run,
        image_path: str,
        conf: float = 0.25,
        iou: float = 0.45,
        imgsz: int = 640,
        device: str = "cpu",
    ) -> str:
        """Run inference on a single image. Returns job_id."""
        provider = self._get_provider(run)
        model_path = self._resolve_best_pt(run)

        inference_adapter = provider.inference_adapter
        if inference_adapter is None:
            raise ValueError(
                f"Algorithm '{provider.id}' does not support inference."
            )
        command = inference_adapter.get_infer_command(
            model_path, image_path, is_batch=False,
            conf=conf, iou=iou, imgsz=imgsz, device=device,
        )

        job_request = JobRequest(
            job_kind="inference",
            params={
                "run_id": run.id,
                "image_path": image_path,
                "task_family": run.task_family,
            },
        )
        return self._job_service.create_job(job_request, command)

    def infer_batch(
        self,
        run: Run,
        image_dir: str,
        conf: float = 0.25,
        iou: float = 0.45,
        imgsz: int = 640,
        device: str = "cpu",
    ) -> str:
        """Run inference on all images in a directory. Returns job_id."""
        provider = self._get_provider(run)
        model_path = self._resolve_best_pt(run)

        inference_adapter = provider.inference_adapter
        if inference_adapter is None:
            raise ValueError(
                f"Algorithm '{provider.id}' does not support inference."
            )
        command = inference_adapter.get_infer_command(
            model_path, image_dir, is_batch=True,
            conf=conf, iou=iou, imgsz=imgsz, device=device,
        )

        job_request = JobRequest(
            job_kind="inference",
            params={
                "run_id": run.id,
                "image_dir": image_dir,
                "task_family": run.task_family,
            },
        )
        return self._job_service.create_job(job_request, command)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_best_pt(run: Run) -> str:
        """Resolve the best.pt path via the provider's run_parser."""
        try:
            provider = InferenceService._get_provider(run)
        except KeyError:
            raise FileNotFoundError(
                f"best.pt not found for run {run.id}. "
                f"No algorithm provider registered."
            )
        run_parser = provider.run_parser
        if run_parser is not None:
            path = run_parser.get_best_weight_path(run.output_dir or "")
            if path:
                return path
        raise FileNotFoundError(
            f"best.pt not found for run {run.id}. "
            f"Ensure training completed successfully."
        )

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def job_service(self) -> JobService:
        return self._job_service


__all__ = ["InferenceService"]

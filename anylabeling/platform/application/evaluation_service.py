"""EvaluationService — orchestrates YOLO validation lifecycle via JobService.

Architecture constraints:
    - No PyQt6 imports (safe for worker processes).
    - No Ultralytics imports (uses adapters as the bridge).
    - All paths are pathlib.Path.
    - All file I/O is UTF-8.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from anylabeling.platform.adapters.registry import AlgorithmRegistry
from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.run import Run
from anylabeling.platform.workers.protocol import JobRequest


class EvaluationService:
    """Application service for evaluation lifecycle management.

    Runs ``YOLO(model).val()`` via a subprocess for tile-native validation.

    Usage::

        from anylabeling.platform.application.evaluation_service import EvaluationService
        service = EvaluationService(job_service, project_root="/data/project")
        job_id = service.evaluate_tile_native(run, build, split="val")
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
        """Resolve the :class:`AlgorithmProvider` for *run*.

        Uses ``run.adapter_id`` if set; otherwise falls back to
        ``"ultralytics_yolo_detect"`` for backward compatibility.
        Ensures the Ultralytics provider package is imported so the
        registry is populated.
        """
        if run.adapter_id:
            try:
                return AlgorithmRegistry.get_provider(run.adapter_id)
            except KeyError:
                pass
        # Ensure the Ultralytics provider is registered.
        import anylabeling.platform.adapters.ultralytics  # noqa: F401
        return AlgorithmRegistry.get_provider("ultralytics_yolo_detect")

    # ------------------------------------------------------------------
    # evaluate_tile_native
    # ------------------------------------------------------------------

    def evaluate_tile_native(
        self,
        run: Run,
        build: DatasetBuild,
        split: str = "val",
        device: str = "0",
        batch: int = 16,
        imgsz: int = 640,
    ) -> str:
        """Run model validation on a trained model. Returns job_id.

        Steps:
            1. Get model path (best.pt from run output_dir) via provider.
            2. Get data.yaml from DatasetBuild via provider.
            3. Build val kwargs via provider's val adapter.
            4. Create JobService job via provider's val command builder.

        Args:
            run: The training Run record (requires ``output_dir`` with best.pt).
            build: The DatasetBuild used for training.
            split: Dataset split to evaluate on ("train", "val", "test").
            device: CUDA device string (e.g. "0", "cpu").
            batch: Batch size for validation.
            imgsz: Input image size.

        Returns:
            The job_id string for tracking.

        Raises:
            ValueError: If run.output_dir is empty or best.pt is not found.
        """
        provider = self._get_provider(run)

        # 1. Get model path
        model_path = self._resolve_best_pt(run)
        if model_path is None:
            raise ValueError(
                f"No best.pt found for run {run.id}. "
                f"Ensure training completed successfully."
            )

        # 2. Get data.yaml path
        dataset_adapter = provider.dataset_adapter
        if dataset_adapter is None:
            raise ValueError(
                f"Algorithm '{provider.id}' has no dataset adapter."
            )
        data_yaml = dataset_adapter.get_data_path(build)

        # 3. Build val kwargs
        val_adapter = provider.val_adapter
        if val_adapter is None:
            raise ValueError(
                f"Algorithm '{provider.id}' has no val adapter."
            )
        run_output_dir = run.output_dir or ""
        val_kwargs = val_adapter.build_val_kwargs(
            model_path=model_path,
            data_path=data_yaml,
            split=split,
            device=device,
            batch=batch,
            imgsz=imgsz,
            output_dir=run_output_dir,
        )

        # 4. Build worker command
        command = val_adapter.get_val_command(model_path, val_kwargs)

        # 5. Create and start job
        job_request = JobRequest(
            job_kind="evaluation",
            params={
                "run_id": run.id,
                "val_kwargs": val_kwargs,
            },
        )
        return self._job_service.create_job(job_request, command)

    # ------------------------------------------------------------------
    # result parsing
    # ------------------------------------------------------------------

    def parse_val_results(
        self,
        run: Run,
        build: DatasetBuild,
    ) -> dict | None:
        """Parse validation results after a val job completes.

        Reads ``per_class_metrics.json`` and ``confusion_matrix.npy`` from
        the val output directory and returns a combined dict.

        Args:
            run: The training Run record (requires ``output_dir``).
            build: The DatasetBuild for class name resolution.

        Returns:
            Dict with keys: ``mAP50``, ``mAP50_95``, ``precision``,
            ``recall``, ``ap_per_class``, ``class_names``,
            ``confusion_matrix`` (numpy array or None), or None if no
            files found.
        """
        if not run.output_dir:
            return None

        provider = self._get_provider(run)
        run_parser = provider.run_parser
        if run_parser is None:
            return None

        metrics = run_parser.parse_val_results(run.output_dir)

        # Confusion matrix — not yet covered by RunParser ABC; fall back
        # to the inner adapter.
        confusion_matrix = None
        try:
            from anylabeling.platform.adapters.ultralytics.run_parser import (
                UltralyticsRunParser,
            )

            val_dir = Path(run.output_dir) / "val"
            confusion_matrix = UltralyticsRunParser().parse_val_confusion_matrix(
                str(val_dir / "confusion_matrix.npy")
            )
        except Exception:
            confusion_matrix = None

        if metrics is None and confusion_matrix is None:
            return None

        result: dict = metrics or {}
        result["confusion_matrix"] = confusion_matrix
        return result

    # ------------------------------------------------------------------
    # best.pt resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_best_pt(run: Run) -> str | None:
        """Resolve the best.pt path from a Run.

        Uses the registered algorithm provider's ``run_parser`` to locate
        the file in the algorithm-specific output directory structure.

        Args:
            run: The training Run record.

        Returns:
            Absolute path to best.pt, or None if not found.
        """
        if not run.output_dir:
            return None
        try:
            provider = EvaluationService._get_provider(run)
        except KeyError:
            return None
        run_parser = provider.run_parser
        if run_parser is None:
            return None
        return run_parser.get_best_weight_path(run.output_dir)

    # ------------------------------------------------------------------
    # command building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_val_command(
        model_path: str,
        kwargs: dict,
    ) -> list[str]:
        """Build the subprocess command list for YOLO validation.

        The worker script runs ``model.val(**kwargs)`` and saves:
        - ``per_class_metrics.json`` — AP per class, mAP, precision, recall
        - ``confusion_matrix.npy`` — raw confusion matrix as numpy array

        Args:
            model_path: Path to the .pt model file.
            kwargs: Validation kwargs dict from ``UltralyticsValAdapter``.

        Returns:
            Command list suitable for ``subprocess.Popen``.
        """
        kwargs_json = json.dumps(kwargs, ensure_ascii=False)

        script = (
            "import json, sys, os\n"
            "import numpy as np\n"
            "from ultralytics import YOLO\n"
            f"kwargs = json.loads({json.dumps(kwargs_json)})\n"
            f"model = YOLO({json.dumps(model_path)})\n"
            "results = model.val(**kwargs)\n"
            "# --- save per-class metrics ---\n"
            "per_class = {}\n"
            "try:\n"
            "    if hasattr(results, 'box') and results.box is not None:\n"
            "        box = results.box\n"
            "        per_class['mAP50'] = float(getattr(box, 'map50', 0))\n"
            "        per_class['mAP50_95'] = float(getattr(box, 'map', 0))\n"
            "        rd = getattr(results, 'results_dict', {})\n"
            "        per_class['precision'] = float(rd.get('metrics/precision(B)', 0))\n"
            "        per_class['recall'] = float(rd.get('metrics/recall(B)', 0))\n"
            "        ap_dict = {}\n"
            "        if hasattr(box, 'ap') and box.ap is not None:\n"
            "            ap_flat = box.ap.flatten().tolist() if hasattr(box.ap, 'flatten') else [float(x) for x in box.ap]\n"
            "            for i, ap_val in enumerate(ap_flat):\n"
            "                ap_dict[str(i)] = float(ap_val)\n"
            "        per_class['ap_per_class'] = ap_dict\n"
            "        if hasattr(model, 'names') and model.names:\n"
            "            per_class['class_names'] = [str(model.names.get(i, f'class_{i}')) for i in range(len(model.names))]\n"
            "        else:\n"
            "            per_class['class_names'] = [f'class_{i}' for i in range(len(ap_dict))]\n"
            "except Exception as e:\n"
            "    per_class['error'] = str(e)\n"
            "# --- save confusion matrix ---\n"
            "try:\n"
            "    if hasattr(results, 'confusion_matrix') and results.confusion_matrix is not None:\n"
            "        cm = results.confusion_matrix\n"
            "        if hasattr(cm, 'matrix'):\n"
            "            out_dir = os.path.join(kwargs.get('project', '.'), kwargs.get('name', 'val'))\n"
            "            os.makedirs(out_dir, exist_ok=True)\n"
            "            np.save(os.path.join(out_dir, 'confusion_matrix.npy'), cm.matrix)\n"
            "except Exception:\n"
            "    pass\n"
            "# --- write per_class_metrics.json ---\n"
            "out_dir = os.path.join(kwargs.get('project', '.'), kwargs.get('name', 'val'))\n"
            "os.makedirs(out_dir, exist_ok=True)\n"
            "with open(os.path.join(out_dir, 'per_class_metrics.json'), 'w', encoding='utf-8') as f:\n"
            "    json.dump(per_class, f, ensure_ascii=False)\n"
            "print(json.dumps({'status': 'ok', 'output_dir': out_dir}, ensure_ascii=False))\n"
        )

        return [sys.executable, "-c", script]

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def project_root(self) -> Path:
        """The project root directory."""
        return self._project_root

    @property
    def job_service(self) -> JobService:
        """The underlying JobService instance."""
        return self._job_service


__all__ = [
    "EvaluationService",
]

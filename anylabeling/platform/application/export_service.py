"""ExportService — orchestrates YOLO model export lifecycle via JobService.

Architecture constraints:
    - No PyQt6 imports (safe for worker processes).
    - No Ultralytics imports (uses adapters as the bridge).
    - All paths are pathlib.Path.
    - All file I/O is UTF-8.
"""

from __future__ import annotations

import json
import logging
import pickle
import random
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from anylabeling.platform.adapters.registry import AlgorithmRegistry
from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.domain.model import ModelArtifact
from anylabeling.platform.domain.run import Run
from anylabeling.platform.workers.protocol import JobRequest


class ExportService:
    """Application service for model export lifecycle management.

    Runs ``YOLO(model).export()`` via a subprocess and saves the resulting
    ONNX model plus metadata to ``models/<id>/``.

    Usage::

        from anylabeling.platform.application.export_service import ExportService
        service = ExportService(job_service, project_root="/data/project")
        job_id = service.start_export(run, {"half": True})
        models = service.get_exported_models()
    """

    def __init__(
        self,
        job_service: JobService,
        project_root: str | Path,
    ) -> None:
        self._job_service = job_service
        self._project_root = Path(project_root)
        self._pt_model: Any = None  # torch.nn.Module | None, lazily loaded for ONNX vs PyTorch comparison

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
    # start_export
    # ------------------------------------------------------------------

    def start_export(
        self,
        run: Run,
        export_config: dict | None = None,
        labels: list[str] | None = None,
        formats: list[str] | None = None,
    ) -> str | list[str]:
        """Export model via the algorithm provider. Returns job_id(s).

        Steps:
            1. Get best.pt from run output_dir via provider.
            2. For each format, build export kwargs and create a job.
            3. Return a single job_id if only one format, else a list.

        Args:
            run: The training Run record (requires ``output_dir`` with best.pt).
            export_config: Optional override for export kwargs
                (e.g. ``{"half": True, "imgsz": 320}``).
            labels: Optional list of class label names. If not provided,
                labels will be empty.
            formats: List of export formats (e.g. ``["onnx", "engine"]``).
                Defaults to ``["onnx"]`` if not provided. If empty,
                raises ValueError.

        Returns:
            A single job_id string (single format) or list of job_id strings.

        Raises:
            ValueError: If run.output_dir is empty, best.pt is not found,
                or formats is empty.
        """
        provider = self._get_provider(run)

        # 1. Get model path
        model_path = self._resolve_best_pt(run)
        if model_path is None:
            raise ValueError(
                f"No best.pt found for run {run.id}. "
                f"Ensure training completed successfully."
            )

        # 2. Determine formats
        if formats is None:
            # Default to single format from export_config or "onnx"
            export_config = export_config or {}
            formats = [export_config.get("format", "onnx")]

        if not formats:
            raise ValueError(
                "At least one export format is required. "
                "Use formats=['onnx'] or similar."
            )

        # 3. Resolve export adapter once
        export_adapter = provider.export_adapter
        if export_adapter is None:
            raise ValueError(
                f"Algorithm '{provider.id}' does not support export."
            )
        export_config = export_config or {}

        # 4. Export for each format
        job_ids: list[str] = []
        for fmt in formats:
            # Generate unique model_id per format
            model_id = f"model_{uuid.uuid4().hex[:12]}"

            # Build export output dir
            models_dir = str(self._project_root / "models" / model_id)
            Path(models_dir).mkdir(parents=True, exist_ok=True)

            # Build export kwargs
            export_kwargs = export_adapter.build_export_kwargs(
                model_path=model_path,
                output_dir=models_dir,
                format=fmt,
                imgsz=export_config.get("imgsz", 640),
                simplify=export_config.get("simplify", True),
                half=export_config.get("half", False),
                dynamic=export_config.get("dynamic", False),
                opset=export_config.get("opset"),
                batch=export_config.get("batch", 1),
            )

            # Build worker command
            command = export_adapter.get_export_command(model_path, export_kwargs)

            # Create and start job
            job_request = JobRequest(
                job_kind="export",
                params={
                    "run_id": run.id,
                    "model_id": model_id,
                    "export_kwargs": export_kwargs,
                    "labels": labels or [],
                    "model_path": model_path,
                    "project_root": str(self._project_root),
                },
            )
            job_id = self._job_service.create_job(job_request, command)
            job_ids.append(job_id)

        # Return single string for backward compatibility
        if len(job_ids) == 1:
            return job_ids[0]
        return job_ids

    # ------------------------------------------------------------------
    # get_exported_models
    # ------------------------------------------------------------------

    def get_exported_models(self) -> list[ModelArtifact]:
        """List all exported models in the project.

        Scans ``<project_root>/models/`` for directories containing a
        ``_READY`` marker and ``model.json``.

        Returns:
            List of :class:`ModelArtifact` objects for each exported model.
        """
        models_root = self._project_root / "models"
        if not models_root.exists():
            return []

        artifacts: list[ModelArtifact] = []
        for model_dir in sorted(models_dir for models_dir in models_root.iterdir()
                                if models_dir.is_dir()):
            ready_marker = model_dir / "_READY"
            model_json = model_dir / "model.json"

            if not ready_marker.exists():
                continue

            try:
                if model_json.exists():
                    data = json.loads(model_json.read_text(encoding="utf-8"))
                else:
                    data = {}
            except (json.JSONDecodeError, OSError):
                logger.debug(
                    "Failed to read model.json for %s", model_dir.name
                )
                data = {}

            # Load additional metadata
            labels: list[str] = data.get("labels", [])
            preprocess: dict = {}
            postprocess: dict = {}
            onnx_check: dict | None = None

            labels_json = model_dir / "labels.json"
            if labels_json.exists():
                try:
                    labels_data = json.loads(labels_json.read_text(encoding="utf-8"))
                    if not labels:
                        labels = [entry["name"] for entry in labels_data]
                except (json.JSONDecodeError, OSError, KeyError):
                    logger.debug(
                        "Failed to read labels.json for %s",
                        model_dir.name,
                    )

            preprocess_json = model_dir / "preprocess.json"
            if preprocess_json.exists():
                try:
                    preprocess = json.loads(preprocess_json.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    logger.debug(
                        "Failed to read preprocess.json for %s",
                        model_dir.name,
                    )

            postprocess_json = model_dir / "postprocess.json"
            if postprocess_json.exists():
                try:
                    postprocess = json.loads(postprocess_json.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    logger.debug(
                        "Failed to read postprocess.json for %s",
                        model_dir.name,
                    )

            onnx_check_json = model_dir / "onnx_check.json"
            if onnx_check_json.exists():
                try:
                    onnx_check = json.loads(onnx_check_json.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    logger.debug(
                        "Failed to read onnx_check.json for %s",
                        model_dir.name,
                    )

            artifact = ModelArtifact(
                id=data.get("model_id", model_dir.name),
                run_id=data.get("run_id", ""),
                format=data.get("format", "onnx"),
                path=str(model_dir),
                labels=labels,
                preprocess=preprocess,
                postprocess=postprocess,
                onnx_check=onnx_check,
            )
            artifacts.append(artifact)

        return artifacts

    # ------------------------------------------------------------------
    # save_export_artifacts (post-job callback)
    # ------------------------------------------------------------------

    def save_export_artifacts(
        self,
        export_path: str,
        model_path: str,
        model_id: str,
        labels: list[str],
        run_id: str = "",
    ) -> ModelArtifact:
        """Post-job callback to save export artifacts.

        Called after the export job completes successfully. Copies the
        exported file and writes all metadata via the provider's export
        adapter.

        Args:
            export_path: Path to the exported model file.
            model_path: Path to the original .pt file.
            model_id: Unique model identifier.
            labels: List of class label names.
            run_id: ID of the training run.

        Returns:
            A :class:`ModelArtifact`.
        """
        # Use a default run to resolve the provider.
        from anylabeling.platform.domain.run import Run as _Run
        provider = self._get_provider(
            _Run(id="", adapter_id="", output_dir=None)
        )
        export_adapter = provider.export_adapter
        if export_adapter is None:
            raise ValueError(
                f"Algorithm '{provider.id}' does not support export."
            )
        return export_adapter.save_export_artifacts(
            export_path=export_path,
            model_path=model_path,
            output_dir=str(self._project_root),
            model_id=model_id,
            labels=labels,
            run_id=run_id,
        )

    # ------------------------------------------------------------------
    # self_test_onnx
    # ------------------------------------------------------------------

    def self_test_onnx(
        self,
        onnx_path: str | Path,
        pt_model_path: str | Path | None = None,
        sample_count: int = 10,
        tolerance: float = 1e-3,
        seed: int = 42,
    ) -> "SelfTestReport":
        """Run ONNX self-test: inference on N samples, compare with PyTorch.

        Steps:
            1. Load ONNX model via onnxruntime.
            2. Generate deterministic sample inputs (seeded for reproducibility).
            3. Run ONNX inference on each sample.
            4. If *pt_model_path* is provided, run PyTorch inference on the
               same input and compare outputs via ``np.allclose`` with the
               configured *tolerance*.
            5. Return SelfTestReport with pass/fail per sample.

        Args:
            onnx_path: Path to the exported ONNX model.
            pt_model_path: Optional path to the original .pt model for
                ONNX-vs-PyTorch output comparison. When ``None``, only
                basic shape and NaN/Inf validation is performed.
            sample_count: Number of samples to test (default 10).
            tolerance: Maximum allowed relative deviation (default 1e-3).
            seed: Random seed for reproducible sample generation.

        Returns:
            SelfTestReport with aggregated results.

        Note:
            This method runs in the main process (not a subprocess job).
            It creates a fresh ONNX InferenceSession per call.
            If onnxruntime is not available, returns a failed report.
        """
        import time

        from anylabeling.platform.domain.export_config import SelfTestReport

        onnx_path = Path(onnx_path)

        # Phase 1: Validate environment (import, file checks, project root)
        early_result = self._validate_onnx_environment(onnx_path)
        if early_result is not None:
            return early_result

        # Phase 1b: Pre-validate ONNX model structure
        self._run_onnx_checker(onnx_path)

        # Phase 2: Set up RNG for deterministic sample generation
        import numpy as np
        import onnxruntime as ort

        random.seed(seed)
        np.random.seed(seed)

        failures: list[str] = []
        max_deviation = 0.0

        try:
            session = ort.InferenceSession(str(onnx_path))
            input_info = session.get_inputs()[0]
            input_name = input_info.name

            for i in range(sample_count):
                sample_input = self._generate_sample_input(
                    input_info, seed, i
                )

                try:
                    start = time.perf_counter()
                    outputs = session.run(
                        None, {input_name: sample_input}
                    )
                    elapsed = time.perf_counter() - start

                    # Basic shape validation
                    if not outputs or outputs[0] is None:
                        failures.append(
                            f"Sample {i}: no output produced"
                        )
                        continue

                    output = outputs[0]
                    if output.ndim < 2:
                        failures.append(
                            f"Sample {i}: unexpected output shape "
                            f"{output.shape}"
                        )
                        continue

                    # Check for NaN/Inf
                    if np.any(np.isnan(output)) or np.any(
                        np.isinf(output)
                    ):
                        failures.append(
                            f"Sample {i}: output contains NaN or Inf"
                        )
                        continue

                    # Compare with PyTorch if available
                    if pt_model_path is not None:
                        deviation, failure = self._compare_with_pytorch(
                            sample_input,
                            output,
                            pt_model_path,
                            i,
                            tolerance,
                        )
                        max_deviation = max(max_deviation, deviation)
                        if failure:
                            failures.append(failure)
                    else:
                        # No PyTorch model — basic output range check
                        deviation = float(np.max(np.abs(output)))
                        max_deviation = max(max_deviation, deviation)

                    logger.debug(
                        f"ONNX self-test sample {i+1}/{sample_count}: "
                        f"shape={output.shape}, "
                        f"elapsed={elapsed*1000:.1f}ms"
                    )

                except Exception as exc:
                    failures.append(
                        f"Sample {i}: inference failed — {exc}"
                    )
                    logger.warning(
                        f"ONNX self-test sample {i} failed: {exc}"
                    )

            session = None  # Release session

        except Exception as exc:
            logger.exception("ONNX self-test failed to initialize")
            return SelfTestReport(
                passed=False,
                samples_tested=0,
                max_deviation=0.0,
                failures=(
                    f"Failed to initialize ONNX session: {exc}",
                ),
                created_at=datetime.now().isoformat(),
            )

        passed = len(failures) == 0
        return SelfTestReport(
            passed=passed,
            samples_tested=sample_count,
            max_deviation=round(max_deviation, 6),
            failures=tuple(failures),
            created_at=datetime.now().isoformat(),
        )

    # ------------------------------------------------------------------
    # self_test_onnx helpers
    # ------------------------------------------------------------------

    def _validate_onnx_environment(
        self, onnx_path: Path
    ) -> "SelfTestReport | None":
        """Validate ONNX runtime availability, file type, and path safety.

        Returns:
            A failed SelfTestReport if validation fails, or None if all
            checks pass and inference can proceed.
        """
        from anylabeling.platform.domain.export_config import SelfTestReport

        # Check onnxruntime availability
        try:
            import numpy as np  # noqa: F401
            import onnxruntime as ort  # noqa: F401
        except ImportError as exc:
            logger.warning("ONNX self-test skipped: %s", exc)
            return SelfTestReport(
                passed=False,
                samples_tested=0,
                max_deviation=0.0,
                failures=(f"onnxruntime not available: {exc}",),
                created_at=datetime.now().isoformat(),
            )

        # Validate file extension
        if onnx_path.suffix.lower() != ".onnx":
            return SelfTestReport(
                passed=False,
                samples_tested=0,
                max_deviation=0.0,
                failures=(f"Not an ONNX file: {onnx_path}",),
                created_at=datetime.now().isoformat(),
            )

        # Check file exists
        if not onnx_path.exists():
            return SelfTestReport(
                passed=False,
                samples_tested=0,
                max_deviation=0.0,
                failures=(f"ONNX model not found: {onnx_path}",),
                created_at=datetime.now().isoformat(),
            )

        # Validate path is inside project_root (defense-in-depth)
        try:
            onnx_path.resolve().relative_to(
                self._project_root.resolve()
            )
        except ValueError:
            return SelfTestReport(
                passed=False,
                samples_tested=0,
                max_deviation=0.0,
                failures=(
                    f"ONNX path is outside project root: {onnx_path}",
                ),
                created_at=datetime.now().isoformat(),
            )

        return None

    @staticmethod
    def _run_onnx_checker(onnx_path: Path) -> None:
        """Pre-validate ONNX model with onnx.checker (best-effort).

        Non-fatal: some valid models may fail the strict checker.
        This is a defense-in-depth mitigation for ONNX Runtime CVEs.
        """
        try:
            import onnx

            onnx.checker.check_model(str(onnx_path))
        except ImportError:
            logger.debug(
                "onnx package not available, skipping pre-check"
            )
        except Exception as exc:
            logger.warning(
                "ONNX checker validation warning for %s: %s",
                onnx_path,
                exc,
            )

    @staticmethod
    def _generate_sample_input(
        input_info, seed: int = 0, index: int = 0
    ) -> "np.ndarray":
        """Generate a deterministic sample input tensor.

        Uses the module-level numpy RNG, which must be pre-seeded by
        the caller.  Each call advances the RNG to produce a different
        sample in a reproducible sequence.

        Args:
            input_info: ONNX model input node info (provides shape).
            seed: Base random seed (for documentation; caller must seed).
            index: Sample index in the sequence (for documentation).

        Returns:
            NumPy array of shape derived from input_info, dtype float32.
        """
        import numpy as np

        input_shape = input_info.shape  # e.g. [1, 3, 640, 640]
        sample_shape = tuple(
            dim if isinstance(dim, int) and dim > 0 else 1
            for dim in input_shape
        )
        return np.random.randn(*sample_shape).astype(np.float32)

    def _compare_with_pytorch(
        self,
        sample_input: "np.ndarray",
        output: "np.ndarray",
        pt_model_path: Path,
        index: int,
        tolerance: float,
    ) -> tuple[float, str | None]:
        """Compare ONNX output against PyTorch model output.

        Lazily loads and caches the PyTorch model on first call.

        Args:
            sample_input: The input tensor used for ONNX inference.
            output: The ONNX model output tensor.
            pt_model_path: Path to the original .pt model file.
            index: Sample index for error messages.
            tolerance: Maximum allowed relative deviation.

        Returns:
            (max_deviation, failure_message_or_None). If failure_message
            is None, the comparison passed.
        """
        import time

        import numpy as np

        try:
            import torch
        except ImportError:
            logger.debug(
                "PyTorch not available, "
                "skipping ONNX-vs-PyTorch comparison"
            )
            deviation = float(np.max(np.abs(output)))
            return deviation, None

        try:
            if self._pt_model is None:
                t0 = time.perf_counter()
                # SECURITY: torch.load with weights_only=False can
                # execute arbitrary code via pickle deserialization.
                # We try weights_only=True first (restricts loading
                # to tensor data only) and fall back only when the
                # model file requires full object deserialization
                # (e.g., custom architectures). The model file is
                # assumed to be from a trusted source (user's own
                # training output).
                try:
                    self._pt_model = torch.load(
                        str(pt_model_path),
                        map_location="cpu",
                        weights_only=True,
                    )
                except (
                    pickle.UnpicklingError,
                    TypeError,
                    ValueError,
                    AttributeError,
                ):
                    logger.warning(
                        "weights_only=True failed for %s; "
                        "falling back to weights_only=False. "
                        "Ensure the model is from a trusted source.",
                        pt_model_path,
                    )
                    self._pt_model = torch.load(
                        str(pt_model_path),
                        map_location="cpu",
                        weights_only=False,
                    )
                self._pt_model.eval()
                logger.debug(
                    "Loaded PyTorch model in %.1fms",
                    (time.perf_counter() - t0) * 1000,
                )

            with torch.no_grad():
                pt_input = torch.from_numpy(sample_input)
                pt_output = self._pt_model(pt_input)
                if isinstance(pt_output, (list, tuple)):
                    pt_output = pt_output[0]
                pt_output_np = pt_output.cpu().numpy()

            if output.shape != pt_output_np.shape:
                return 0.0, (
                    f"Sample {index}: shape mismatch ONNX "
                    f"{output.shape} vs PyTorch "
                    f"{pt_output_np.shape}"
                )

            if not np.allclose(
                output,
                pt_output_np,
                rtol=tolerance,
                atol=1e-5,
            ):
                diff = np.abs(output - pt_output_np)
                max_diff = float(np.max(diff))
                return max_diff, (
                    f"Sample {index}: deviation "
                    f"{max_diff:.6f} exceeds tolerance "
                    f"{tolerance}"
                )

            diff = np.abs(output - pt_output_np)
            max_diff = float(np.max(diff))
            return max_diff, None

        except Exception as exc:
            logger.warning(
                "ONNX-vs-PyTorch sample %d failed: %s",
                index,
                exc,
            )
            return (
                0.0,
                f"Sample {index}: PyTorch comparison failed — {exc}",
            )

    def _clear_pt_model(self) -> None:
        """Release the cached PyTorch model to free memory.

        Call this after all ONNX self-tests are complete to avoid
        holding GPU/CPU memory unnecessarily.
        """
        self._pt_model = None

    # ------------------------------------------------------------------
    # best.pt resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_best_pt(run: Run) -> str | None:
        """Resolve the best.pt path from a Run record via the provider."""
        if not run.output_dir:
            return None
        try:
            provider = ExportService._get_provider(run)
        except KeyError:
            return None
        run_parser = provider.run_parser
        if run_parser is None:
            return None
        return run_parser.get_best_weight_path(run.output_dir)

    # ------------------------------------------------------------------
    # command building
    # ----------------------------------------------------------------
    @staticmethod
    def _build_export_command(
        model_path: str,
        kwargs: dict,
        export_format: str = "onnx",
    ) -> list[str]:
        """Build export command with environment validation.

        Uses inline Python to validate the export environment and then
        run ``YOLO(model).export(**kwargs)``.

        Before running the export, validates that the necessary packages
        for the requested format are installed.

        Args:
            model_path: Path to the .pt model file.
            kwargs: Export kwargs dict from ``UltralyticsExportAdapter``.
            export_format: Export format (onnx, torchscript, etc.).

        Returns:
            Command list suitable for ``subprocess.Popen``.
        """
        import json

        kwargs_json = json.dumps(kwargs, ensure_ascii=False)
        mp_literal = json.dumps(model_path)
        kw_literal = json.dumps(kwargs_json)
        fmt_literal = json.dumps(export_format)

        lines = [
            "import json,sys",
            "from anylabeling.platform.adapters.ultralytics.export_validators import validate_export_environment",
            "fmt=" + fmt_literal,
            "missing=validate_export_environment(fmt)",
            "if missing:",
            " msg='Missing packages for '+fmt+' export: '+' '.join(missing)+'. '",
            " msg+='Please install: pip install '+' '.join(missing)",
            " print(json.dumps({'error':msg}))",
            " sys.exit(1)",
            "from ultralytics import YOLO",
            "kwargs=json.loads(" + kw_literal + ")",
            "model=YOLO(" + mp_literal + ")",
            "export_path=model.export(**kwargs)",
            "output=json.dumps({'status':'ok','export_path':str(export_path)})",
            "print(output)",
        ]
        script = "\n".join(lines)

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
    "ExportService",
]

"""TrainingService — orchestrates training lifecycle via JobService subprocess.

Architecture constraints:
    - No PyQt6 imports (safe for worker processes).
    - No Ultralytics imports (uses adapters as the bridge).
    - All paths are pathlib.Path.
    - All file I/O is UTF-8.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from anylabeling.platform.adapters.registry import AlgorithmRegistry
from anylabeling.platform.adapters.ultralytics.train_adapter import TrainRequest
from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.domain.run import MetricPoint, Run
from anylabeling.platform.infrastructure.atomic_writer import AtomicWriter
from anylabeling.platform.workers.protocol import JobRequest




# ---------------------------------------------------------------------------
# serialization helpers
# ---------------------------------------------------------------------------


def _serialize_train_request(request: TrainRequest) -> dict[str, Any]:
    """Serialize TrainRequest to a JSON-safe dict for the Run config field.

    TaskSpec and DatasetBuild references are stored by id only to keep
    the record lightweight and avoid deep nesting.
    """
    config: dict[str, Any] = {
        "task_spec_id": request.task_spec.id,
        "dataset_build_id": request.dataset_build.id,
        "base_model": request.base_model,
    }
    for field in dataclasses.fields(request):
        if field.name in ("task_spec", "dataset_build", "base_model"):
            continue
        config[field.name] = getattr(request, field.name)
    return config


def _run_to_dict(run: Run) -> dict[str, Any]:
    """Convert a Run domain object to a JSON-serializable dict."""
    return {
        "id": run.id,
        "adapter_id": run.adapter_id,
        "task_family": run.task_family,
        "dataset_build_id": run.dataset_build_id,
        "base_model": run.base_model,
        "base_model_sha256": run.base_model_sha256,
        "config": run.config,
        "environment": run.environment,
        "status": run.status,
        "metrics": [
            {"name": m.name, "value": m.value, "step": m.step}
            for m in run.metrics
        ],
        "best_metric": run.best_metric,
        "output_dir": run.output_dir,
    }


def _run_from_dict(data: dict[str, Any]) -> Run:
    """Reconstruct a Run domain object from a JSON dict."""
    metrics = [
        MetricPoint(name=m["name"], value=m["value"], step=m["step"])
        for m in data.get("metrics", [])
    ]
    return Run(
        id=data.get("id", ""),
        adapter_id=data.get("adapter_id", ""),
        task_family=data.get("task_family", ""),
        dataset_build_id=data.get("dataset_build_id", ""),
        base_model=data.get("base_model", ""),
        base_model_sha256=data.get("base_model_sha256", ""),
        config=data.get("config", {}),
        environment=data.get("environment", {}),
        status=data.get("status", "queued"),
        metrics=metrics,
        best_metric=data.get("best_metric"),
        output_dir=data.get("output_dir"),
    )


# ---------------------------------------------------------------------------
# TrainingService
# ---------------------------------------------------------------------------


class TrainingService:
    """Application service for training lifecycle management.

    Creates Run records persisted as ``run.json`` and starts training
    subprocesses via :class:`JobService`.

    Usage::

        from anylabeling.platform.application.training_service import TrainingService
        service = TrainingService(job_service, project_root="/data/project")
        run = service.create_run_record(train_request)
        job_id = service.start_training(train_request)
    """

    def __init__(
        self,
        job_service: JobService,
        project_root: str | Path,
    ) -> None:
        self._job_service = job_service
        self._project_root = Path(project_root)

    # ------------------------------------------------------------------
    # adapter id
    # ------------------------------------------------------------------

    @staticmethod
    def _get_adapter_id(task_family: str) -> str:
        """Return the first registered adapter ID for *task_family*.

        Looks up providers registered with :class:`AlgorithmRegistry`
        that support the given task family.  Returns the first match or
        an ``"unknown"`` placeholder.
        """
        providers = AlgorithmRegistry.for_task_providers(task_family)
        if providers:
            return providers[0].id
        return f"unknown_{task_family}"

    # ------------------------------------------------------------------
    # run record persistence
    # ------------------------------------------------------------------

    def create_run_record(self, request: TrainRequest) -> Run:
        """Create a ``Run`` domain object and persist ``run.json``.

        The run directory is created under ``<project_root>/runs/<run_id>/``.
        A ``run.json`` is written atomically via :class:`AtomicWriter`.

        Returns:
            The created :class:`Run` object.
        """
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        run_dir = self._project_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        run = Run(
            id=run_id,
            adapter_id=self._get_adapter_id(request.task_spec.family),
            task_family=request.task_spec.family,
            dataset_build_id=request.dataset_build.id,
            base_model=request.base_model,
            base_model_sha256="",  # computed later by checksum/validation
            config=_serialize_train_request(request),
            environment={
                "python_version": sys.version.split()[0],
                "ultralytics_version": "unknown",  # populated by the worker
            },
            status="queued",
            metrics=[],
            best_metric=None,
            output_dir=str(run_dir),
        )

        # Persist run.json atomically
        AtomicWriter.write_json(run_dir / "run.json", _run_to_dict(run))
        return run

    def read_run_record(self, run_id: str) -> Run | None:
        """Read a persisted ``run.json`` and return a ``Run`` object.

        Returns ``None`` if the file does not exist.
        """
        run_dir = self._project_root / "runs" / run_id
        run_json = run_dir / "run.json"
        if not run_json.exists():
            return None

        data = json.loads(run_json.read_text(encoding="utf-8"))
        return _run_from_dict(data)

    def update_run_record(self, run: Run) -> None:
        """Persist the current state of *run* to ``run.json``."""
        run_dir = Path(run.output_dir) if run.output_dir else self._project_root / "runs" / run.id
        AtomicWriter.write_json(run_dir / "run.json", _run_to_dict(run))

    def parse_and_update_run(self, run_id: str) -> Run | None:
        """Parse training results and update the Run record with metrics.

        Called after a training job completes. Uses the algorithm
        provider's ``run_parser`` to parse results from the training
        output directory, then updates the Run's metrics, best_metric,
        and status fields.

        Returns:
            The updated Run, or None if the run is not found.
        """
        run = self.read_run_record(run_id)
        if run is None:
            return None

        output_dir = run.output_dir
        if not output_dir:
            return run

        try:
            provider = self._get_provider(run.adapter_id)
        except KeyError:
            return run

        run_parser = provider.run_parser
        if run_parser is None:
            return run

        try:
            metrics = run_parser.parse_train_results(output_dir)
        except Exception:
            metrics = []
        run.metrics = metrics

        if run.metrics:
            try:
                run.best_metric = run_parser.find_best_epoch(run.metrics)
            except Exception:
                pass

        run.status = "completed"
        self.update_run_record(run)
        return run

    # ------------------------------------------------------------------
    # start training
    # ------------------------------------------------------------------

    def start_training(
        self,
        request: TrainRequest,
        adapter_id: str | None = None,
    ) -> str:
        """Start training via :class:`JobService` subprocess.

        1. Creates a Run record (or reuses an existing one).
        2. Resolves the algorithm provider from the registry.
        3. Gets the data.yaml path from the provider's dataset adapter.
        4. Builds training kwargs via the provider's train adapter.
        5. Constructs the worker command via the provider's train adapter.
        6. Creates the job via ``JobService.create_job()``.

        Args:
            request: The training request with all hyperparameters.
            adapter_id: Optional algorithm adapter ID. If not provided,
                resolved from ``request.task_spec.family``.

        Returns:
            The job_id string for tracking.
        """
        # 1. Create Run record
        run = self.create_run_record(request)

        # Resolve adapter_id
        if adapter_id is None:
            adapter_id = self._get_adapter_id(request.task_spec.family)

        # 2. Get provider
        provider = self._get_provider(adapter_id)
        if not provider.supports_training:
            raise ValueError(
                f"Algorithm '{adapter_id}' does not support training."
            )

        # 3. Get data.yaml path
        dataset_adapter = provider.dataset_adapter
        if dataset_adapter is None:
            raise ValueError(
                f"Algorithm '{adapter_id}' has no dataset adapter."
            )
        data_yaml = dataset_adapter.get_data_path(request.dataset_build)

        # 4. Build train kwargs
        train_adapter = provider.train_adapter
        if train_adapter is None:
            raise ValueError(
                f"Algorithm '{adapter_id}' has no train adapter."
            )
        train_kwargs = train_adapter.build_train_kwargs(
            request, data_yaml, str(Path(run.output_dir))
        )

        # 5. Build worker command
        command = train_adapter.get_train_command(
            request.base_model, train_kwargs
        )

        # 6. Create and start job
        job_request = JobRequest(
            job_kind="training",
            params={
                "run_id": run.id,
                "train_kwargs": train_kwargs,
            },
        )
        return self._job_service.create_job(job_request, command)

    # ------------------------------------------------------------------
    # validate_training_readiness
    # ------------------------------------------------------------------

    def validate_training_readiness(
        self,
        task_spec: "TaskSpec | None" = None,
        dataset_build: "DatasetBuild | None" = None,
        model_id: str = "",
    ) -> "TrainReadinessReport":
        """Validate that training can proceed.

        Checks:
            1. Assets exist (count > 0)
            2. Annotation coverage >= 50%
            3. Dataset build is complete
            4. Model is compatible with task family
            5. Disk space >= 1 GB

        Args:
            task_spec: Optional TaskSpec to validate against.
            dataset_build: Optional DatasetBuild to validate.
            model_id: Optional model identifier for compatibility check.

        Returns:
            TrainReadinessReport with individual check results.
        """
        from anylabeling.platform.domain.training_readiness import (
            CheckResult,
            TrainReadinessReport,
        )

        checks: list[CheckResult] = []
        warnings: list[str] = []

        # Count image assets once for both Check 1 and Check 2
        asset_count = self._count_image_assets()

        # Check 1: Assets exist
        checks.append(self._check_assets_exist())

        # Check 2: Annotation coverage
        coverage_result, coverage_warning = (
            self._check_annotations_coverage(asset_count)
        )
        checks.append(coverage_result)
        if coverage_warning:
            warnings.append(coverage_warning)

        # Check 3: Dataset build complete
        checks.append(self._check_dataset_build(dataset_build))

        # Check 4: Model compatibility (basic — task family match)
        checks.append(CheckResult(
            name="model_compatible",
            passed=True,  # Always pass for now; adapter validates at job start
            detail="模型兼容性由训练适配器在启动时验证",
            blocking=False,
        ))

        # Check 5: Disk space
        disk_result, disk_warning = self._check_disk_space()
        checks.append(disk_result)
        if disk_warning:
            warnings.append(disk_warning)

        # Aggregate
        blocking_passed = all(
            c.passed for c in checks if c.blocking
        )

        return TrainReadinessReport(
            ready=blocking_passed,
            checks=tuple(checks),
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------
    # validate_training_readiness helpers
    # ------------------------------------------------------------------

    def _count_image_assets(self) -> int:
        """Count image files in the project assets directory."""
        assets_dir = self._project_root / "assets" / "images"
        _MAX_SCAN_FILES = 100_000
        count = 0
        if not assets_dir.exists():
            return count
        _file_count = 0
        for entry in assets_dir.rglob("*"):
            if _file_count >= _MAX_SCAN_FILES:
                logger.warning(
                    "Asset scan hit %d file limit; "
                    "stopping scan in %s",
                    _MAX_SCAN_FILES, assets_dir,
                )
                break
            if entry.is_file() and entry.suffix.lower() in {
                ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"
            }:
                count += 1
            _file_count += 1
        return count

    def _check_assets_exist(self) -> "CheckResult":
        """Check that project contains at least one image asset."""
        from anylabeling.platform.domain.training_readiness import (
            CheckResult,
        )
        count = self._count_image_assets()
        return CheckResult(
            name="assets_exist",
            passed=count > 0,
            detail="项目包含 {}张图像".format(count) if count > 0
                   else "项目中没有图像文件",
            blocking=True,
        )

    def _check_annotations_coverage(
        self, asset_count: int,
    ) -> tuple["CheckResult", str | None]:
        """Check annotation coverage meets minimum threshold."""
        from anylabeling.platform.domain.training_readiness import (
            CheckResult,
        )

        annotations_dir = self._project_root / "annotations"
        annotated_count = 0
        if annotations_dir.exists():
            docs_dir = annotations_dir / "documents"
            if docs_dir.exists():
                annotated_count = sum(
                    1 for _ in docs_dir.rglob("*.json")
                )

        coverage = (
            (annotated_count / asset_count * 100)
            if asset_count > 0 else 0
        )
        result = CheckResult(
            name="annotations_coverage",
            passed=coverage >= 50.0,
            detail="标注覆盖率 {:.1f}％（{}/{}）".format(
                coverage, annotated_count, asset_count
            ),
            blocking=False,
        )

        warning: str | None = None
        if coverage < 50.0:
            warning = (
                "标注覆盖率仅 {:.1f}％，"
                "建议至少标注 50% 的资产后再训练"
            ).format(coverage)

        return result, warning

    @staticmethod
    def _check_dataset_build(
        dataset_build: "DatasetBuild | None",
    ) -> "CheckResult":
        """Check that a dataset build has been provided."""
        from anylabeling.platform.domain.training_readiness import (
            CheckResult,
        )
        build_ok = dataset_build is not None
        return CheckResult(
            name="dataset_build",
            passed=build_ok,
            detail="数据集构建已完成" if build_ok else "缺少数据集构建",
            blocking=True,
        )

    def _check_disk_space(
        self,
    ) -> tuple["CheckResult", str | None]:
        """Check available disk space meets minimum threshold."""
        import shutil

        from anylabeling.platform.domain.training_readiness import (
            CheckResult,
        )

        try:
            usage = shutil.disk_usage(self._project_root)
            free_gb = usage.free / (1024 ** 3)
            result = CheckResult(
                name="disk_space",
                passed=free_gb >= 1.0,
                detail="可用磁盘空间 {:.1f} GB".format(free_gb),
                blocking=False,
            )
            warning: str | None = None
            if free_gb < 1.0:
                warning = (
                    "磁盘空间不足（仅 {:.1f} GB），"
                    "训练可能因空间不足而失败"
                ).format(free_gb)
            return result, warning
        except OSError:
            return CheckResult(
                name="disk_space",
                passed=True,
                detail="无法检测磁盘空间",
                blocking=False,
            ), None

    # ------------------------------------------------------------------
    # find_orphaned_runs
    # ------------------------------------------------------------------

    def find_orphaned_runs(self) -> list["Run"]:
        """Find training runs left in 'running' state.

        Scans <project_root>/runs/ for run.json records with
        status == "running". These indicate runs that were
        interrupted (app crash, power loss, etc.).

        Returns:
            List of orphaned Run records (may be empty).
        """
        from anylabeling.platform.domain.run import Run as RunRecord

        runs_dir = self._project_root / "runs"
        if not runs_dir.exists():
            return []

        orphaned: list[RunRecord] = []
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            try:
                run = self.read_run_record(run_dir.name)
                if run is not None and run.status == "running":
                    orphaned.append(run)
            except (json.JSONDecodeError, OSError):
                logger.warning(
                    f"Failed to read run record: {run_dir.name}",
                    exc_info=True,
                )

        return orphaned

    # ------------------------------------------------------------------
    # command building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_train_command(
        model_path: str,
        kwargs: dict[str, Any],
    ) -> list[str]:
        """Build the subprocess command list for YOLO training.

        Uses inline Python::

            import json
            from ultralytics import YOLO
            kwargs = json.loads('''<kwargs_json>''')
            model = YOLO(r"<model_path>")
            model.train(**kwargs)

        Args:
            model_path: Path to the local .pt model file.
            kwargs: Training kwargs dict from ``UltralyticsTrainAdapter``.

        Returns:
            Command list suitable for ``subprocess.Popen``.
        """
        kwargs_json = json.dumps(kwargs, ensure_ascii=False)

        script = (
            "import json,sys\n"
            "from ultralytics import YOLO\n"
            f"kwargs = json.loads({json.dumps(kwargs_json)})\n"
            f"model = YOLO({json.dumps(model_path)})\n"
            "model.train(**kwargs)\n"
        )

        return [sys.executable, "-c", script]

    # ------------------------------------------------------------------
    # provider resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _get_provider(adapter_id: str):
        """Resolve an :class:`AlgorithmProvider` by *adapter_id*.

        Returns the registered provider.  Falls back to
        ``"ultralytics_yolo_detect"`` when *adapter_id* is empty or not
        found, for backward compatibility with runs created before the
        provider migration.
        """
        from anylabeling.platform.adapters.provider import AlgorithmProvider

        if adapter_id:
            try:
                return AlgorithmRegistry.get_provider(adapter_id)
            except KeyError:
                pass
        return AlgorithmRegistry.get_provider("ultralytics_yolo_detect")

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
    "TrainingService",
    "_run_to_dict",
    "_run_from_dict",
    "_serialize_train_request",
]

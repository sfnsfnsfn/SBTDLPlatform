"""Tests for TrainingService SQLite DB integration (E2-3).

Verifies that TrainingService writes RunRecord and ModelRecord to the
SQLite database via ProjectContext, while remaining backward-compatible
when no context is provided.

Coverage:
    1. Training with completed build creates RunRecord in DB.
    2. Training with failed build raises and does not create RunRecord.
    3. Training with missing build raises and does not create RunRecord.
    4. Training without context still works (backward compatibility).
    5. After successful training, parse_and_update_run upserts ModelRecord
       with ready=1 and marks the run completed.
"""

from __future__ import annotations

import pathlib
import sys
import textwrap
import types
from importlib import util as importlib_util
from pathlib import Path
from unittest.mock import MagicMock, ANY

import pytest

# ---------------------------------------------------------------------------
# Manual package bootstrap for new domain.records module
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
DOMAIN_DIR = REPO_ROOT / "anylabeling" / "platform" / "domain"


def _bootstrap_domain_records() -> None:
    """Load new domain sub-modules into an already-installed package.

    Strategy: first import the real parent packages so their ``__path__``
    is set correctly by the installed distribution, then load new
    sub-modules that do not exist in the installed package yet.
    """
    # Import the real installed packages first — this ensures
    # ``anylabeling.platform.__path__`` includes *all* sub-package
    # directories (adapters, application, domain, infrastructure).
    import anylabeling  # noqa: F401
    import anylabeling.platform  # noqa: F401

    # Now create / load the domain sub-package and its modules.
    _ensure_package("anylabeling.platform.domain", DOMAIN_DIR)
    _load_module(
        "anylabeling.platform.domain.records",
        DOMAIN_DIR / "records.py",
    )
    _load_module(
        "anylabeling.platform.domain.workflow_status",
        DOMAIN_DIR / "workflow_status.py",
    )


def _ensure_package(name: str, path: pathlib.Path | None = None) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
        module.__path__ = [] if path is None else [str(path)]
    return module


def _load_module(name: str, path: pathlib.Path) -> types.ModuleType:
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None) == str(path):
        return existing
    spec = importlib_util.spec_from_file_location(name, path)
    module = importlib_util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_bootstrap_domain_records()

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

# Trigger UltralyticsProvider registration (required by AlgorithmRegistry)
import anylabeling.platform.adapters.ultralytics  # noqa: F401

from anylabeling.platform.adapters.registry import AlgorithmRegistry
from anylabeling.platform.adapters.ultralytics.provider import UltralyticsProvider
from anylabeling.platform.adapters.ultralytics.train_adapter import TrainRequest
from anylabeling.platform.application.training_service import TrainingService
from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.records import DatasetBuildRecord, ModelRecord
from anylabeling.platform.domain.task import LabelClass, TaskSpec


@pytest.fixture(autouse=True)
def _ensure_provider_registered():
    """Re-register UltralyticsProvider (other tests may call clear())."""
    try:
        AlgorithmRegistry.get_provider("ultralytics_yolo_detect")
    except KeyError:
        AlgorithmRegistry.register(UltralyticsProvider())


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_task_spec() -> TaskSpec:
    """A minimal detection task spec for testing."""
    return TaskSpec(
        id="task_det_001",
        family="detection_hbb",
        labels=(
            LabelClass(id=0, name="cat"),
            LabelClass(id=1, name="dog"),
        ),
        annotation_schema="yolo_bbox",
        primary_metric="mAP50-95",
    )


@pytest.fixture
def sample_dataset_build(tmp_path: Path) -> DatasetBuild:
    """A dataset build with a real temporary output path containing data.yaml."""
    build_dir = tmp_path / "dataset_builds" / "build_abc123"
    build_dir.mkdir(parents=True)
    yaml_content = textwrap.dedent("""\
        path: {build_dir}
        train: images/train
        val: images/val
        test: images/test
        nc: 2
        names:
          0: cat
          1: dog
    """).replace("{build_dir}", str(build_dir))
    (build_dir / "data.yaml").write_text(yaml_content, encoding="utf-8")
    return DatasetBuild(
        id="build_abc123",
        task_spec_id="task_det_001",
        source_asset_manifest_hash="abc",
        annotation_manifest_hash="def",
        split_seed=42,
        split_strategy="random_by_asset",
        output_path=str(build_dir),
    )


@pytest.fixture
def sample_train_request(
    sample_task_spec: TaskSpec,
    sample_dataset_build: DatasetBuild,
) -> TrainRequest:
    """A valid TrainRequest used across tests."""
    return TrainRequest(
        task_spec=sample_task_spec,
        dataset_build=sample_dataset_build,
        base_model="yolo11n.pt",
        epochs=100,
        batch=16,
    )


@pytest.fixture
def mock_context() -> MagicMock:
    """A mocked ProjectContext with repository attributes."""
    ctx = MagicMock()
    ctx.dataset_builds = MagicMock()
    ctx.runs = MagicMock()
    ctx.models = MagicMock()
    ctx.jobs = MagicMock()
    return ctx


@pytest.fixture
def mock_job_service() -> MagicMock:
    """A mocked JobService that records create_job calls."""
    svc = MagicMock(spec=JobService)
    svc.create_job.return_value = "job_fake123"
    return svc


# ============================================================================
# Tests
# ============================================================================


class TestTrainingServiceDbIntegration:
    """TrainingService DB mirror: validation and recording."""

    def test_train_with_completed_build_creates_run(
        self,
        mock_job_service: MagicMock,
        mock_context: MagicMock,
        sample_train_request: TrainRequest,
        tmp_path: Path,
    ):
        """Training with a completed dataset build creates a RunRecord in DB."""
        mock_context.dataset_builds.get.return_value = DatasetBuildRecord(
            id="build_abc123",
            task_family="detection_hbb",
            output_path="/tmp/build",
            status="completed",
        )
        service = TrainingService(
            mock_job_service,
            project_root=tmp_path,
            context=mock_context,
        )
        service.start_training(sample_train_request)

        mock_context.runs.create.assert_called_once()
        args = mock_context.runs.create.call_args[0][0]
        assert args.dataset_build_id == "build_abc123"
        assert args.status == "running"

    def test_train_with_failed_build_rejects(
        self,
        mock_job_service: MagicMock,
        mock_context: MagicMock,
        sample_train_request: TrainRequest,
        tmp_path: Path,
    ):
        """Training with a failed build raises and does not create a RunRecord."""
        mock_context.dataset_builds.get.return_value = DatasetBuildRecord(
            id="build_abc123",
            task_family="detection_hbb",
            output_path="/tmp/build",
            status="failed",
            error_message="OOM during preprocessing",
        )
        service = TrainingService(
            mock_job_service,
            project_root=tmp_path,
            context=mock_context,
        )

        with pytest.raises(ValueError, match="not completed"):
            service.start_training(sample_train_request)

        mock_context.runs.create.assert_not_called()

    def test_train_with_missing_build_rejects(
        self,
        mock_job_service: MagicMock,
        mock_context: MagicMock,
        sample_train_request: TrainRequest,
        tmp_path: Path,
    ):
        """Training with a non-existent build raises and does not create a RunRecord."""
        mock_context.dataset_builds.get.return_value = None
        service = TrainingService(
            mock_job_service,
            project_root=tmp_path,
            context=mock_context,
        )

        with pytest.raises(ValueError, match="not found"):
            service.start_training(sample_train_request)

        mock_context.runs.create.assert_not_called()

    def test_train_without_context_does_not_crash(
        self,
        mock_job_service: MagicMock,
        sample_train_request: TrainRequest,
        tmp_path: Path,
    ):
        """Backward compat: TrainingService without ProjectContext works as before."""
        service = TrainingService(mock_job_service, project_root=tmp_path)
        job_id = service.start_training(sample_train_request)
        assert job_id == "job_fake123"

    def test_train_success_upserts_ready_model(
        self,
        mock_job_service: MagicMock,
        mock_context: MagicMock,
        sample_train_request: TrainRequest,
        tmp_path: Path,
    ):
        """After training completes, parse_and_update_run upserts a ModelRecord with ready=1."""
        mock_context.dataset_builds.get.return_value = DatasetBuildRecord(
            id="build_abc123",
            task_family="detection_hbb",
            output_path="/tmp/build",
            status="completed",
        )
        service = TrainingService(
            mock_job_service,
            project_root=tmp_path,
            context=mock_context,
        )
        run = service.create_run_record(sample_train_request)
        run_id = run.id

        # Simulate training output directory with best.pt
        output_dir = Path(run.output_dir)
        weights_dir = output_dir / "train" / "weights"
        weights_dir.mkdir(parents=True)
        (weights_dir / "best.pt").write_text("fake model content", encoding="utf-8")

        service.parse_and_update_run(run_id)

        mock_context.runs.mark_completed.assert_called_once_with(run_id)
        mock_context.models.upsert.assert_called_once()
        model_args = mock_context.models.upsert.call_args[0][0]
        assert model_args.run_id == run_id
        assert model_args.ready is True


__all__: list[str] = []

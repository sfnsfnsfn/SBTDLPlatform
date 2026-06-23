"""Tests for TrainingService, UltralyticsRunParser, and run record persistence.

Coverage:
    1. create_run_record persists run.json
    2. create_run_record sets status=queued with correct fields
    3. read_run_record roundtrips correctly
    4. update_run_record persists changes
    5. RunParser parse_results_csv from CSV content
    6. RunParser find_best_epoch selects correct epoch
    7. RunParser get_best_weight_path / get_last_weight_path
    8. RunParser parse_args_yaml
    9. TrainingService._build_train_command structure
    10. _run_to_dict / _run_from_dict roundtrip
    11. _serialize_train_request excludes domain objects
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Trigger UltralyticsProvider registration (required by AlgorithmRegistry)
import anylabeling.platform.adapters.ultralytics  # noqa: F401

from anylabeling.platform.adapters.registry import AlgorithmRegistry
from anylabeling.platform.adapters.ultralytics.provider import UltralyticsProvider
from anylabeling.platform.adapters.ultralytics.run_parser import (
    UltralyticsRunParser,
)
from anylabeling.platform.adapters.ultralytics.train_adapter import (
    TrainRequest,
)
from anylabeling.platform.application.training_service import (
    TrainingService,
    _run_from_dict,
    _run_to_dict,
    _serialize_train_request,
)
from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.run import MetricPoint, Run
from anylabeling.platform.domain.task import (
    LabelClass,
    TaskSpec,
)
from anylabeling.platform.workers.protocol import JobRequest


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
def mock_job_service() -> MagicMock:
    """A mocked JobService that records create_job calls."""
    svc = MagicMock(spec=JobService)
    svc.create_job.return_value = "job_fake123"
    return svc


@pytest.fixture
def training_service(
    mock_job_service: MagicMock,
    tmp_path: Path,
) -> TrainingService:
    """TrainingService with mocked JobService and temp project root."""
    return TrainingService(mock_job_service, project_root=tmp_path)


# ============================================================================
# 1. create_run_record persistence
# ============================================================================


class TestCreateRunRecord:
    """Test that create_run_record creates correct run.json on disk."""

    def test_create_run_record_persists_run_json(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """create_run_record should write run.json to the run directory."""
        run = training_service.create_run_record(sample_train_request)

        assert run.output_dir is not None
        run_json_path = Path(run.output_dir) / "run.json"
        assert run_json_path.exists()

        data = json.loads(run_json_path.read_text(encoding="utf-8"))
        assert data["id"] == run.id
        assert data["status"] == "queued"
        assert data["task_family"] == "detection_hbb"
        assert data["base_model"] == "yolo11n.pt"

    def test_create_run_record_sets_status_queued(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """A freshly created run record must have status='queued'."""
        run = training_service.create_run_record(sample_train_request)
        assert run.status == "queued"

    def test_create_run_record_generates_unique_ids(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """Each call to create_run_record must produce a unique run id."""
        run1 = training_service.create_run_record(sample_train_request)
        run2 = training_service.create_run_record(sample_train_request)
        assert run1.id != run2.id
        assert run1.id.startswith("run_")

    def test_create_run_record_adapter_id(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """adapter_id must match the task family mapping."""
        run = training_service.create_run_record(sample_train_request)
        assert run.adapter_id == "ultralytics_yolo_detect"

    def test_create_run_record_config_contains_hyperparams(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """The config dict should contain non-domain fields from the request."""
        run = training_service.create_run_record(sample_train_request)
        assert run.config["epochs"] == 100
        assert run.config["batch"] == 16
        assert run.config["task_spec_id"] == "task_det_001"
        assert run.config["dataset_build_id"] == "build_abc123"

    def test_create_run_record_environment_populated(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """The environment dict should contain python_version."""
        run = training_service.create_run_record(sample_train_request)
        assert "python_version" in run.environment
        assert "ultralytics_version" in run.environment

    def test_create_run_record_run_dir_created(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """The run directory must be created under project_root/runs/."""
        run = training_service.create_run_record(sample_train_request)
        run_dir = Path(run.output_dir)
        assert run_dir.exists()
        assert run_dir.parent.name == "runs"

    def test_dataset_build_id_preserved(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """The dataset_build_id in the Run must match the request."""
        run = training_service.create_run_record(sample_train_request)
        assert run.dataset_build_id == "build_abc123"


# ============================================================================
# 2. read_run_record and roundtrip
# ============================================================================


class TestReadUpdateRunRecord:
    """Test read_run_record and update_run_record."""

    def test_read_run_record_returns_none_for_missing(
        self,
        training_service: TrainingService,
    ):
        """read_run_record must return None for a non-existent run."""
        result = training_service.read_run_record("nonexistent_run")
        assert result is None

    def test_read_run_record_roundtrips(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """create → read must return an equivalent Run."""
        created = training_service.create_run_record(sample_train_request)
        read_back = training_service.read_run_record(created.id)
        assert read_back is not None
        assert read_back.id == created.id
        assert read_back.status == created.status
        assert read_back.task_family == created.task_family
        assert read_back.config == created.config

    def test_update_run_record_persists_changes(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """update_run_record must write the new state to disk."""
        run = training_service.create_run_record(sample_train_request)
        run.status = "running"
        training_service.update_run_record(run)

        read_back = training_service.read_run_record(run.id)
        assert read_back is not None
        assert read_back.status == "running"

    def test_update_run_record_metrics(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """Metrics in the Run should survive an update roundtrip."""
        run = training_service.create_run_record(sample_train_request)
        run.metrics.append(MetricPoint(name="mAP50", value=0.85, step=10))
        run.best_metric = {"epoch": 10, "metric": "mAP50", "value": 0.85}
        training_service.update_run_record(run)

        read_back = training_service.read_run_record(run.id)
        assert read_back is not None
        assert len(read_back.metrics) == 1
        assert read_back.metrics[0].name == "mAP50"
        assert read_back.metrics[0].value == 0.85
        assert read_back.best_metric == {"epoch": 10, "metric": "mAP50", "value": 0.85}


# ============================================================================
# 3. RunParser — parse_results_csv
# ============================================================================


class TestRunParserParseResultsCsv:
    """Test UltralyticsRunParser.parse_results_csv."""

    @pytest.fixture
    def parser(self) -> UltralyticsRunParser:
        return UltralyticsRunParser()

    def test_parse_results_csv_basic(self, parser: UltralyticsRunParser, tmp_path: Path):
        """Parse a minimal results.csv with two epochs."""
        csv_content = textwrap.dedent("""\
            epoch,train/box_loss,train/cls_loss,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B)
            1,1.5,1.2,0.6,0.5,0.55,0.40
            2,1.3,1.0,0.7,0.6,0.65,0.50
        """)
        csv_path = tmp_path / "results.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        metrics = parser.parse_results_csv(csv_path)
        assert len(metrics) == 12  # 6 metric cols x 2 epochs

        # Check epoch 2 metrics exist
        epoch2_metrics = [m for m in metrics if m.step == 2]
        assert len(epoch2_metrics) == 6

    def test_parse_results_csv_empty_file(
        self, parser: UltralyticsRunParser, tmp_path: Path
    ):
        """An empty file should return an empty list."""
        csv_path = tmp_path / "results.csv"
        csv_path.write_text("epoch\n", encoding="utf-8")
        metrics = parser.parse_results_csv(csv_path)
        assert metrics == []

    def test_parse_results_csv_missing_file(
        self, parser: UltralyticsRunParser,
    ):
        """A non-existent file should return an empty list (no exception)."""
        metrics = parser.parse_results_csv("/nonexistent/path/results.csv")
        assert metrics == []

    def test_parse_results_csv_preserves_metric_names(
        self, parser: UltralyticsRunParser, tmp_path: Path
    ):
        """MetricPoint.name must contain the original column header."""
        csv_content = textwrap.dedent("""\
            epoch,metrics/mAP50-95(B)
            1,0.75
        """)
        csv_path = tmp_path / "results.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        metrics = parser.parse_results_csv(csv_path)
        assert len(metrics) == 1
        assert metrics[0].name == "metrics/mAP50-95(B)"
        assert metrics[0].value == 0.75
        assert metrics[0].step == 1

    def test_parse_results_csv_skips_non_numeric(
        self, parser: UltralyticsRunParser, tmp_path: Path
    ):
        """Non-numeric column values should be skipped gracefully."""
        csv_content = textwrap.dedent("""\
            epoch,metrics/mAP50-95(B),notes
            1,0.75,N/A
        """)
        csv_path = tmp_path / "results.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        metrics = parser.parse_results_csv(csv_path)
        assert len(metrics) == 1
        assert metrics[0].name == "metrics/mAP50-95(B)"


# ============================================================================
# 4. RunParser — find_best_epoch
# ============================================================================


class TestRunParserFindBestEpoch:
    """Test UltralyticsRunParser.find_best_epoch."""

    @pytest.fixture
    def parser(self) -> UltralyticsRunParser:
        return UltralyticsRunParser()

    def test_find_best_epoch_by_map50_95(
        self, parser: UltralyticsRunParser
    ):
        """The best epoch should be the one with the highest mAP50-95."""
        metrics = [
            MetricPoint(name="metrics/mAP50-95(B)", value=0.40, step=1),
            MetricPoint(name="metrics/mAP50-95(B)", value=0.55, step=2),
            MetricPoint(name="metrics/mAP50-95(B)", value=0.50, step=3),
        ]
        result = parser.find_best_epoch(metrics)
        assert result is not None
        assert result["epoch"] == 2
        assert result["value"] == 0.55
        assert result["metric"] == "metrics/mAP50-95(B)"

    def test_find_best_epoch_by_accuracy(
        self, parser: UltralyticsRunParser
    ):
        """When map50-95 is absent, fall back to accuracy_top1."""
        metrics = [
            MetricPoint(name="metrics/accuracy_top1", value=0.88, step=1),
            MetricPoint(name="metrics/accuracy_top1", value=0.92, step=2),
            MetricPoint(name="metrics/accuracy_top1", value=0.90, step=3),
        ]
        result = parser.find_best_epoch(metrics)
        assert result is not None
        assert result["epoch"] == 2
        assert result["value"] == 0.92

    def test_find_best_epoch_val_loss_lower_is_better(
        self, parser: UltralyticsRunParser
    ):
        """When using val/loss, the epoch with the LOWEST loss is best."""
        metrics = [
            MetricPoint(name="val/loss", value=0.50, step=1),
            MetricPoint(name="val/loss", value=0.30, step=2),
            MetricPoint(name="val/loss", value=0.40, step=3),
        ]
        result = parser.find_best_epoch(metrics)
        assert result is not None
        assert result["epoch"] == 2
        assert result["value"] == 0.30

    def test_find_best_epoch_empty_returns_none(
        self, parser: UltralyticsRunParser
    ):
        """An empty metric list should return None."""
        result = parser.find_best_epoch([])
        assert result is None

    def test_find_best_epoch_unknown_metric_returns_none(
        self, parser: UltralyticsRunParser
    ):
        """Metrics not in the candidate list should yield None."""
        metrics = [
            MetricPoint(name="custom/metric", value=0.99, step=1),
        ]
        result = parser.find_best_epoch(metrics)
        assert result is None

    def test_find_best_epoch_map_priority_over_loss(
        self, parser: UltralyticsRunParser
    ):
        """mAP50-95 should be preferred over val/loss when both are present."""
        metrics = [
            MetricPoint(name="metrics/mAP50-95(B)", value=0.40, step=3),
            MetricPoint(name="val/loss", value=0.10, step=5),
        ]
        result = parser.find_best_epoch(metrics)
        assert result is not None
        assert result["metric"] == "metrics/mAP50-95(B)"  # higher priority
        assert result["epoch"] == 3


# ============================================================================
# 5. RunParser — weight paths
# ============================================================================


class TestRunParserWeightPaths:
    """Test weight path resolution."""

    @pytest.fixture
    def parser(self) -> UltralyticsRunParser:
        return UltralyticsRunParser()

    def test_get_best_weight_path_exists(
        self, parser: UltralyticsRunParser, tmp_path: Path
    ):
        """Should return the path when best.pt exists."""
        weights_dir = tmp_path / "train" / "weights"
        weights_dir.mkdir(parents=True)
        (weights_dir / "best.pt").write_text("fake", encoding="utf-8")

        result = parser.get_best_weight_path(str(tmp_path))
        assert result is not None
        assert result.endswith("best.pt")
        assert Path(result).exists()

    def test_get_best_weight_path_missing(
        self, parser: UltralyticsRunParser, tmp_path: Path
    ):
        """Should return None when best.pt does not exist."""
        result = parser.get_best_weight_path(str(tmp_path))
        assert result is None

    def test_get_last_weight_path_exists(
        self, parser: UltralyticsRunParser, tmp_path: Path
    ):
        """Should return the path when last.pt exists."""
        weights_dir = tmp_path / "train" / "weights"
        weights_dir.mkdir(parents=True)
        (weights_dir / "last.pt").write_text("fake", encoding="utf-8")

        result = parser.get_last_weight_path(str(tmp_path))
        assert result is not None
        assert result.endswith("last.pt")

    def test_get_last_weight_path_missing(
        self, parser: UltralyticsRunParser, tmp_path: Path
    ):
        """Should return None when last.pt does not exist."""
        result = parser.get_last_weight_path(str(tmp_path))
        assert result is None


# ============================================================================
# 6. RunParser — parse_args_yaml
# ============================================================================


class TestRunParserParseArgsYaml:
    """Test UltralyticsRunParser.parse_args_yaml."""

    @pytest.fixture
    def parser(self) -> UltralyticsRunParser:
        return UltralyticsRunParser()

    def test_parse_args_yaml_returns_dict(
        self, parser: UltralyticsRunParser, tmp_path: Path
    ):
        """Should parse a valid YAML file into a dict."""
        yaml_content = textwrap.dedent("""\
            epochs: 100
            batch: 16
            imgsz: 640
            model: yolo11n.pt
        """)
        args_path = tmp_path / "args.yaml"
        args_path.write_text(yaml_content, encoding="utf-8")

        result = parser.parse_args_yaml(args_path)
        assert isinstance(result, dict)
        assert result["epochs"] == 100
        assert result["batch"] == 16

    def test_parse_args_yaml_missing_file(
        self, parser: UltralyticsRunParser,
    ):
        """A missing file should return an empty dict."""
        result = parser.parse_args_yaml("/nonexistent/args.yaml")
        assert result == {}


# ============================================================================
# 7. TrainingService._build_train_command
# ============================================================================


class TestBuildTrainCommand:
    """Test the _build_train_command static method."""

    def test_command_is_list_of_strings(self):
        """The returned command must be a list of strings."""
        cmd = TrainingService._build_train_command("yolo11n.pt", {"epochs": 10})
        assert isinstance(cmd, list)
        for part in cmd:
            assert isinstance(part, str)

    def test_command_starts_with_python_executable(self):
        """The first element should be sys.executable."""
        cmd = TrainingService._build_train_command("yolo11n.pt", {"epochs": 10})
        assert cmd[0] == __import__("sys").executable
        assert cmd[1] == "-c"

    def test_command_script_contains_model_path(self):
        """The inline script must contain the model path."""
        cmd = TrainingService._build_train_command(
            "yolo11n.pt", {"epochs": 10}
        )
        script = cmd[2]
        assert "yolo11n.pt" in script

    def test_command_script_contains_kwargs(self):
        """The inline script must serialize kwargs as JSON."""
        cmd = TrainingService._build_train_command(
            "yolo11n.pt", {"epochs": 10, "batch": 8}
        )
        script = cmd[2]
        assert "epochs" in script
        assert "10" in script

    def test_command_script_uses_yolo_train(self):
        """The inline script must call model.train(**kwargs)."""
        cmd = TrainingService._build_train_command(
            "yolo11n.pt", {"epochs": 10}
        )
        script = cmd[2]
        assert "model.train(**kwargs)" in script
        assert "from ultralytics import YOLO" in script


# ============================================================================
# 8. start_training integration
# ============================================================================


# ============================================================================
# 9. Source binding audit — dataset_build_id on Run records
# ============================================================================


class TestSourceBinding:
    """Verify that Run records carry immutable dataset_build_id binding."""

    def test_run_stores_dataset_build_id_on_creation(self):
        """Run.dataset_build_id is stored when the Run is created."""
        run = Run(
            id="run-001",
            dataset_build_id="build-abc",
            task_family="detection_hbb",
        )
        assert run.dataset_build_id == "build-abc"
        assert run.id == "run-001"

    def test_train_request_stores_build_id(self):
        """TrainRequest retains the dataset_build.id it was constructed with."""
        from anylabeling.platform.domain.dataset import DatasetBuild
        from anylabeling.platform.domain.task import LabelClass, TaskSpec

        task = TaskSpec(
            id="task-001",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="defect"),),
        )
        build = DatasetBuild(
            id="build-xyz",
            task_spec_id=task.id,
            source_asset_manifest_hash="abc123",
            annotation_manifest_hash="def456",
            split_seed=42,
            split_strategy="random_by_asset",
            output_path="/tmp/builds/build-xyz",
        )
        req = TrainRequest(task_spec=task, dataset_build=build)
        assert req.dataset_build.id == "build-xyz"

    def test_run_default_dataset_build_id_empty(self):
        """Run created without explicit dataset_build_id defaults to ''."""
        run = Run(id="run-empty")
        assert run.dataset_build_id == ""


class TestStartTraining:
    """Test the start_training orchestration method."""

    def test_start_training_returns_job_id(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """start_training should return the job_id from JobService."""
        job_id = training_service.start_training(sample_train_request)
        assert job_id == "job_fake123"

    def test_start_training_calls_create_job_once(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """start_training should call JobService.create_job exactly once."""
        training_service.start_training(sample_train_request)
        assert training_service._job_service.create_job.call_count == 1

    def test_start_training_job_kind_is_training(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """The JobRequest should have job_kind='training'."""
        training_service.start_training(sample_train_request)
        call_args = training_service._job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert job_request.job_kind == "training"

    def test_start_training_job_params_contain_run_id(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """The JobRequest params must contain the run_id."""
        training_service.start_training(sample_train_request)
        call_args = training_service._job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert "run_id" in job_request.params
        assert "train_kwargs" in job_request.params

    def test_start_training_train_kwargs_contain_data(
        self,
        training_service: TrainingService,
        sample_train_request: TrainRequest,
    ):
        """The train_kwargs passed to the job must contain the data path."""
        training_service.start_training(sample_train_request)
        call_args = training_service._job_service.create_job.call_args
        assert call_args is not None
        job_request, _ = call_args[0]
        assert "data" in job_request.params["train_kwargs"]


# ============================================================================
# 9. run_to_dict / run_from_dict roundtrip
# ============================================================================


class TestRunSerialization:
    """Test _run_to_dict and _run_from_dict."""

    def test_run_to_dict_includes_all_fields(self):
        """Serialized dict should contain all Run fields."""
        run = Run(
            id="run_abc",
            status="queued",
            metrics=[
                MetricPoint(name="loss", value=0.5, step=1),
            ],
        )
        data = _run_to_dict(run)
        assert data["id"] == "run_abc"
        assert data["status"] == "queued"
        assert len(data["metrics"]) == 1

    def test_run_from_dict_reconstructs_correctly(self):
        """Run reconstructed from dict should match."""
        original = Run(
            id="run_xyz",
            adapter_id="ultralytics_yolo_detect",
            task_family="detection_hbb",
            dataset_build_id="build_001",
            base_model="yolo11n.pt",
            status="completed",
            best_metric={"epoch": 5, "value": 0.85},
        )
        data = _run_to_dict(original)
        reconstructed = _run_from_dict(data)
        assert reconstructed.id == original.id
        assert reconstructed.adapter_id == original.adapter_id
        assert reconstructed.status == original.status
        assert reconstructed.best_metric == original.best_metric

    def test_run_to_dict_empty_metrics(self):
        """Serialized dict should handle empty metrics list."""
        run = Run(id="run_empty")
        data = _run_to_dict(run)
        assert data["metrics"] == []


# ============================================================================
# 10. _serialize_train_request
# ============================================================================


class TestSerializeTrainRequest:
    """Test the _serialize_train_request helper."""

    def test_serialize_excludes_domain_objects(
        self,
        sample_train_request: TrainRequest,
    ):
        """Domain objects should be replaced by their IDs."""
        config = _serialize_train_request(sample_train_request)
        assert "task_spec" not in config
        assert "dataset_build" not in config
        assert config["task_spec_id"] == "task_det_001"
        assert config["dataset_build_id"] == "build_abc123"

    def test_serialize_includes_all_hyperparams(
        self,
        sample_train_request: TrainRequest,
    ):
        """All hyperparameter fields should be in the config dict."""
        config = _serialize_train_request(sample_train_request)
        assert "epochs" in config
        assert "batch" in config
        assert "imgsz" in config
        assert "lr0" in config
        assert "optimizer" in config


# ============================================================================
# 11. adapter_id mapping for all task families
# ============================================================================


class TestAdapterIdMapping:
    """Test _get_adapter_id for known and unknown task families.

    Resolution is driven by :class:`AlgorithmRegistry` providers.
    Currently only ``detection_hbb`` has a registered
    :class:`UltralyticsProvider`.
    """

    @pytest.mark.parametrize(
        "family,expected",
        [
            ("detection_hbb", "ultralytics_yolo_detect"),
        ],
    )
    def test_registered_families_map_correctly(
        self,
        family: str,
        expected: str,
    ):
        """A task family with a registered provider should resolve correctly."""
        result = TrainingService._get_adapter_id(family)
        assert result == expected

    @pytest.mark.parametrize(
        "family",
        [
            "classification",
            "detection_obb",
            "instance_segmentation",
            "pose",
        ],
    )
    def test_unregistered_families_return_unknown_placeholder(
        self, family: str
    ):
        """Families without registered providers return an unknown placeholder."""
        result = TrainingService._get_adapter_id(family)
        assert result.startswith("unknown_")
        assert family in result

    def test_unknown_family_returns_unknown(self):
        """An unrecognized task family should return an 'unknown' placeholder."""
        result = TrainingService._get_adapter_id("unknown_family_xyz")
        assert "unknown" in result


__all__: list[str] = []

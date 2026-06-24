"""Contract tests for platform Record DTOs and Repository Protocols.

Verifies:
  1. All 7 Record dataclasses are frozen and instantiable.
  2. All 8 Repository Protocols are importable and runtime_checkable.
  3. Round-trip serialization through dataclasses.asdict().
  4. workflow_status.py enums have expected values.
  5. AnnotationCodec migrated to ports/__init__.py.
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys
import types
from importlib import util as importlib_util
from typing import Protocol

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PLATFORM_DIR = REPO_ROOT / "anylabeling" / "platform"
DOMAIN_DIR = PLATFORM_DIR / "domain"
APPLICATION_DIR = PLATFORM_DIR / "application"
PORTS_DIR = APPLICATION_DIR / "ports"


def _ensure_package(name: str, path: pathlib.Path | None = None) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [] if path is None else [str(path)]
    return module


def _load_module(name: str, path: pathlib.Path) -> types.ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        if getattr(existing, "__file__", None) == str(path):
            return existing
        del sys.modules[name]
    spec = importlib_util.spec_from_file_location(name, str(path))
    module = importlib_util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bootstrap() -> None:
    """Ensure all packages and modules are importable without pip-installing."""
    _ensure_package("anylabeling")
    _ensure_package("anylabeling.platform", PLATFORM_DIR)
    _ensure_package("anylabeling.platform.domain", DOMAIN_DIR)
    _ensure_package("anylabeling.platform.application", APPLICATION_DIR)

    # Clear old ports.py module if it was previously loaded as a file module
    old = sys.modules.get("anylabeling.platform.application.ports")
    if old is not None and not hasattr(old, "__path__"):
        del sys.modules["anylabeling.platform.application.ports"]

    _ensure_package("anylabeling.platform.application.ports", PORTS_DIR)

    # Load domain dependencies first (needed by AnnotationCodec in ports/__init__)
    _load_module("anylabeling.platform.domain.annotation", DOMAIN_DIR / "annotation.py")

    # Load new domain modules
    _load_module("anylabeling.platform.domain.records", DOMAIN_DIR / "records.py")
    _load_module("anylabeling.platform.domain.workflow_status", DOMAIN_DIR / "workflow_status.py")

    # Load ports package
    _load_module("anylabeling.platform.application.ports", PORTS_DIR / "__init__.py")
    _load_module("anylabeling.platform.application.ports.repositories", PORTS_DIR / "repositories.py")


_bootstrap()

# ---------------------------------------------------------------------------
# Imports after bootstrap
# ---------------------------------------------------------------------------

from anylabeling.platform.domain.records import (
    AnnotationSummaryRecord,
    AssetRecord,
    DatasetBuildRecord,
    EvaluationRecord,
    JobRecord,
    ModelRecord,
    RunRecord,
)
from anylabeling.platform.domain.workflow_status import (
    WorkflowStage,
    WorkflowStepStatus,
)
from anylabeling.platform.application.ports import AnnotationCodec
from anylabeling.platform.application.ports.repositories import (
    AnnotationRepositoryPort,
    AssetRepositoryPort,
    DatasetBuildRepositoryPort,
    EvaluationRepositoryPort,
    JobRepositoryPort,
    ModelRepositoryPort,
    RunRepositoryPort,
    WorkflowQueryPort,
)


# ---------------------------------------------------------------------------
# Record class listing for parametrized tests
# ---------------------------------------------------------------------------

RECORD_CLASSES = [
    AssetRecord,
    AnnotationSummaryRecord,
    DatasetBuildRecord,
    RunRecord,
    JobRecord,
    ModelRecord,
    EvaluationRecord,
]

PROTOCOL_CLASSES = [
    AssetRepositoryPort,
    AnnotationRepositoryPort,
    DatasetBuildRepositoryPort,
    RunRepositoryPort,
    JobRepositoryPort,
    ModelRepositoryPort,
    EvaluationRepositoryPort,
    WorkflowQueryPort,
]

HAS_PROTOCOL = True
try:
    HAS_PROTOCOL
except NameError:
    HAS_PROTOCOL = False


# ===========================================================================
# 1. Record frozen & instantiation tests
# ===========================================================================


class TestRecordsAreFrozen:
    """All 7 Record dataclasses must be frozen (immutable)."""

    @pytest.mark.parametrize("cls", RECORD_CLASSES, ids=lambda c: c.__name__)
    def test_is_dataclass(self, cls: type) -> None:
        assert dataclasses.is_dataclass(cls), f"{cls.__name__} is not a dataclass"

    @pytest.mark.parametrize("cls", RECORD_CLASSES, ids=lambda c: c.__name__)
    def test_is_frozen(self, cls: type) -> None:
        assert cls.__dataclass_params__.frozen is True

    @pytest.mark.parametrize("cls", RECORD_CLASSES, ids=lambda c: c.__name__)
    def test_frozen_instance_error(self, cls: type) -> None:
        fields = dataclasses.fields(cls)
        kwargs: dict[str, object] = {}
        for f in fields:
            if f.type in ("str", str):
                kwargs[f.name] = "test"
            elif f.type in ("int", int):
                kwargs[f.name] = 0
            elif f.type in ("float", float):
                kwargs[f.name] = 0.0
            elif f.type in ("bool", bool):
                kwargs[f.name] = False
            else:
                kwargs[f.name] = "test"
        instance = cls(**kwargs)
        target = next((f.name for f in fields if f.type in ("str", str)), fields[0].name)
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, target, "mutated")


class TestAssetRecord:
    def test_minimal(self) -> None:
        r = AssetRecord(id="a1", rel_path="img/001.jpg", width=1920, height=1080)
        assert r.id == "a1"
        assert r.rel_path == "img/001.jpg"
        assert r.width == 1920
        assert r.height == 1080
        assert r.sha256 is None
        assert r.channels is None
        assert r.ext is None
        assert r.size_bytes == 0
        assert r.group_name is None
        assert r.is_large is False
        assert r.status == "active"
        assert r.source_kind is None
        assert r.created_at is None
        assert r.updated_at is None
        assert r.deleted_at is None

    def test_full(self) -> None:
        r = AssetRecord(
            id="a1",
            rel_path="img/001.jpg",
            sha256="abc123def456",
            width=1920,
            height=1080,
            channels=3,
            ext=".jpg",
            size_bytes=102400,
            group_name="batch_1",
            is_large=False,
            status="active",
            source_kind="import",
            source_version="v4.0",
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-02T00:00:00",
        )
        assert r.sha256 == "abc123def456"
        assert r.channels == 3
        assert r.ext == ".jpg"
        assert r.size_bytes == 102400
        assert r.group_name == "batch_1"
        assert r.source_kind == "import"
        assert r.created_at == "2025-01-01T00:00:00"


class TestAnnotationSummaryRecord:
    def test_minimal(self) -> None:
        r = AnnotationSummaryRecord(
            asset_id="a1", rel_path="ann/001.json", format="xanylabeling_json"
        )
        assert r.asset_id == "a1"
        assert r.rel_path == "ann/001.json"
        assert r.format == "xanylabeling_json"
        assert r.object_count == 0
        assert r.label_histogram_json is None
        assert r.checksum is None
        assert r.status == "active"
        assert r.updated_at is None

    def test_full(self) -> None:
        r = AnnotationSummaryRecord(
            asset_id="a1",
            rel_path="ann/001.json",
            format="coco_json",
            object_count=5,
            label_histogram_json='{"defect": 3, "scratch": 2}',
            checksum="def456",
            status="complete",
            updated_at="2025-01-02T00:00:00",
        )
        assert r.object_count == 5
        assert r.checksum == "def456"
        assert r.label_histogram_json == '{"defect": 3, "scratch": 2}'


class TestDatasetBuildRecord:
    def test_minimal(self) -> None:
        r = DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1"
        )
        assert r.id == "b1"
        assert r.task_family == "detection_hbb"
        assert r.status == "pending"
        assert r.split_strategy == ""
        assert r.error_message is None
        assert r.created_at is None
        assert r.completed_at is None

    def test_full(self) -> None:
        r = DatasetBuildRecord(
            id="b1",
            task_family="detection_hbb",
            output_path="builds/b1",
            split_strategy="random_by_asset",
            split_seed=42,
            split_ratios_json='{"train": 0.8, "val": 0.2}',
            tile_plan_json='{"tile_width": 1024, "tile_height": 1024}',
            preprocess_config_json='{"mean": [0, 0, 0], "std": [1, 1, 1]}',
            manifest_hash="hash123",
            status="completed",
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-02T00:00:00",
            completed_at="2025-01-02T01:00:00",
        )
        assert r.split_strategy == "random_by_asset"
        assert r.split_seed == 42
        assert r.manifest_hash == "hash123"
        assert r.tile_plan_json is not None


class TestRunRecord:
    def test_minimal(self) -> None:
        r = RunRecord(
            id="r1",
            dataset_build_id="b1",
            adapter_id="ultralytics.v1",
            task_family="detection_hbb",
        )
        assert r.status == "pending"
        assert r.config_json is None
        assert r.metrics_json is None
        assert r.best_model_path is None
        assert r.log_path is None
        assert r.started_at is None
        assert r.finished_at is None
        assert r.error_message is None

    def test_full(self) -> None:
        r = RunRecord(
            id="r1",
            dataset_build_id="b1",
            adapter_id="ultralytics.v1",
            task_family="detection_hbb",
            status="completed",
            config_json='{"epochs": 100, "imgsz": 640}',
            metrics_json='{"map50": 0.85, "map50_95": 0.62}',
            best_model_path="models/best.onnx",
            log_path="logs/r1.log",
            started_at="2025-01-01T00:00:00",
            finished_at="2025-01-02T00:00:00",
            updated_at="2025-01-02T00:00:00",
        )
        assert r.metrics_json == '{"map50": 0.85, "map50_95": 0.62}'
        assert r.best_model_path == "models/best.onnx"


class TestJobRecord:
    def test_minimal(self) -> None:
        r = JobRecord(id="j1", kind="training", state="pending")
        assert r.progress == 0.0
        assert r.entity_type is None
        assert r.entity_id is None
        assert r.payload_json is None
        assert r.log_path is None
        assert r.created_at is None
        assert r.finished_at is None
        assert r.error_message is None

    def test_full(self) -> None:
        r = JobRecord(
            id="j1",
            kind="training",
            state="running",
            progress=0.5,
            entity_type="run",
            entity_id="r1",
            payload_json='{"epochs": 100}',
            log_path="logs/j1.log",
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-02T00:00:00",
            finished_at="2025-01-03T00:00:00",
        )
        assert r.progress == 0.5
        assert r.entity_id == "r1"
        assert r.payload_json == '{"epochs": 100}'


class TestModelRecord:
    def test_minimal(self) -> None:
        r = ModelRecord(
            id="m1",
            run_id="r1",
            name="yolo11s",
            format="onnx",
            path="models/best.onnx",
            task_family="detection_hbb",
        )
        assert r.ready is False
        assert r.metrics_json is None
        assert r.created_at is None
        assert r.updated_at is None

    def test_full(self) -> None:
        r = ModelRecord(
            id="m1",
            run_id="r1",
            name="yolo11s",
            format="onnx",
            path="models/best.onnx",
            task_family="detection_hbb",
            metrics_json='{"map50": 0.85}',
            ready=True,
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-02T00:00:00",
        )
        assert r.ready is True
        assert r.metrics_json == '{"map50": 0.85}'


class TestEvaluationRecord:
    def test_minimal(self) -> None:
        r = EvaluationRecord(id="e1", run_id="r1", dataset_build_id="b1")
        assert r.status == "pending"
        assert r.metrics_json is None
        assert r.report_path is None
        assert r.created_at is None
        assert r.completed_at is None
        assert r.error_message is None

    def test_full(self) -> None:
        r = EvaluationRecord(
            id="e1",
            run_id="r1",
            dataset_build_id="b1",
            status="completed",
            metrics_json='{"map50": 0.85}',
            report_path="reports/e1.html",
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-02T00:00:00",
            completed_at="2025-01-02T01:00:00",
        )
        assert r.metrics_json == '{"map50": 0.85}'
        assert r.report_path == "reports/e1.html"


# ===========================================================================
# 2. Protocol contract tests
# ===========================================================================


class TestRepositoryProtocols:
    """All 8 Repository Protocols must be Protocols and runtime_checkable."""

    @pytest.mark.parametrize("cls", PROTOCOL_CLASSES, ids=lambda c: c.__name__)
    def test_is_protocol(self, cls: type) -> None:
        assert issubclass(cls, Protocol), f"{cls.__name__} is not a Protocol"

    @pytest.mark.parametrize("cls", PROTOCOL_CLASSES, ids=lambda c: c.__name__)
    def test_is_runtime_checkable(self, cls: type) -> None:
        assert getattr(cls, "_is_runtime_protocol", False) is True


class TestAnnotationCodecProtocol:
    def test_is_protocol(self) -> None:
        assert issubclass(AnnotationCodec, Protocol)

    def test_is_runtime_checkable(self) -> None:
        assert AnnotationCodec._is_runtime_protocol is True

    def test_has_required_methods(self) -> None:
        assert hasattr(AnnotationCodec, "load_annotations")
        assert hasattr(AnnotationCodec, "save_annotations")
        assert hasattr(AnnotationCodec, "validate_annotations")


# ===========================================================================
# 3. Workflow enum tests
# ===========================================================================


class TestWorkflowStage:
    def test_values(self) -> None:
        assert WorkflowStage.DATA_PREP.value == "data_prep"
        assert WorkflowStage.TRAINING.value == "training"
        assert WorkflowStage.EVALUATION.value == "evaluation"
        assert WorkflowStage.EXPORT.value == "export"

    def test_is_str_enum(self) -> None:
        assert issubclass(WorkflowStage, str)


class TestWorkflowStepStatus:
    def test_values(self) -> None:
        assert WorkflowStepStatus.PENDING.value == "pending"
        assert WorkflowStepStatus.RUNNING.value == "running"
        assert WorkflowStepStatus.COMPLETED.value == "completed"
        assert WorkflowStepStatus.FAILED.value == "failed"
        assert WorkflowStepStatus.SKIPPED.value == "skipped"
        assert WorkflowStepStatus.BLOCKED.value == "blocked"

    def test_is_str_enum(self) -> None:
        assert issubclass(WorkflowStepStatus, str)


# ===========================================================================
# 4. Serialization round-trip tests
# ===========================================================================


class TestRecordSerialization:
    """Every Record dataclass must round-trip through dataclasses.asdict()."""

    def _roundtrip(self, instance: object) -> dict:
        d = dataclasses.asdict(instance)
        cls = type(instance)
        reconstructed = cls(**d)
        d2 = dataclasses.asdict(reconstructed)
        assert d == d2, f"{cls.__name__} serialization round-trip mismatch"
        return d

    def test_asset_record(self) -> None:
        r = AssetRecord(id="a1", rel_path="img/001.jpg", width=1920, height=1080)
        self._roundtrip(r)

    def test_asset_record_full(self) -> None:
        r = AssetRecord(
            id="a2",
            rel_path="img/002.tif",
            sha256="abc",
            width=32000,
            height=32000,
            channels=1,
            ext=".tif",
            size_bytes=999999,
            group_name="g1",
            is_large=True,
            status="active",
            source_kind="scan",
            source_version="v1",
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-02T00:00:00",
        )
        self._roundtrip(r)

    def test_annotation_summary_record(self) -> None:
        r = AnnotationSummaryRecord(
            asset_id="a1", rel_path="ann/001.json", format="xanylabeling_json"
        )
        self._roundtrip(r)

    def test_annotation_summary_record_full(self) -> None:
        r = AnnotationSummaryRecord(
            asset_id="a1",
            rel_path="ann/001.json",
            format="coco_json",
            object_count=5,
            label_histogram_json='{"a": 3}',
            checksum="chk",
            status="complete",
            updated_at="2025-01-02T00:00:00",
        )
        self._roundtrip(r)

    def test_dataset_build_record(self) -> None:
        r = DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1"
        )
        self._roundtrip(r)

    def test_dataset_build_record_full(self) -> None:
        r = DatasetBuildRecord(
            id="b1",
            task_family="segmentation",
            output_path="builds/b1",
            split_strategy="random",
            split_seed=42,
            split_ratios_json='{"train":0.8}',
            tile_plan_json="{}",
            preprocess_config_json="{}",
            manifest_hash="mh",
            status="completed",
            created_at="now",
            updated_at="now",
            completed_at="now",
            error_message=None,
        )
        self._roundtrip(r)

    def test_run_record(self) -> None:
        r = RunRecord(
            id="r1",
            dataset_build_id="b1",
            adapter_id="ultra.v1",
            task_family="detection_hbb",
        )
        self._roundtrip(r)

    def test_run_record_full(self) -> None:
        r = RunRecord(
            id="r1",
            dataset_build_id="b1",
            adapter_id="ultra.v1",
            task_family="detection_hbb",
            status="completed",
            config_json="{}",
            metrics_json="{}",
            best_model_path="best.onnx",
            log_path="log.txt",
            started_at="now",
            finished_at="now",
            updated_at="now",
        )
        self._roundtrip(r)

    def test_job_record(self) -> None:
        r = JobRecord(id="j1", kind="training", state="pending")
        self._roundtrip(r)

    def test_job_record_full(self) -> None:
        r = JobRecord(
            id="j1",
            kind="training",
            state="running",
            progress=0.5,
            entity_type="run",
            entity_id="r1",
            payload_json="{}",
            log_path="log.txt",
            created_at="now",
            updated_at="now",
            finished_at="now",
        )
        self._roundtrip(r)

    def test_model_record(self) -> None:
        r = ModelRecord(
            id="m1",
            run_id="r1",
            name="yolo11s",
            format="onnx",
            path="models/best.onnx",
            task_family="detection_hbb",
        )
        self._roundtrip(r)

    def test_model_record_full(self) -> None:
        r = ModelRecord(
            id="m1",
            run_id="r1",
            name="yolo11s",
            format="onnx",
            path="models/best.onnx",
            task_family="detection_hbb",
            metrics_json="{}",
            ready=True,
            created_at="now",
            updated_at="now",
        )
        self._roundtrip(r)

    def test_evaluation_record(self) -> None:
        r = EvaluationRecord(id="e1", run_id="r1", dataset_build_id="b1")
        self._roundtrip(r)

    def test_evaluation_record_full(self) -> None:
        r = EvaluationRecord(
            id="e1",
            run_id="r1",
            dataset_build_id="b1",
            status="completed",
            metrics_json="{}",
            report_path="report.html",
            created_at="now",
            updated_at="now",
            completed_at="now",
        )
        self._roundtrip(r)

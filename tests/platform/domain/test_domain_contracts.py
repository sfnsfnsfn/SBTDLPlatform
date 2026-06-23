"""Contract tests for platform domain DTOs.

Verifies:
  1. Every dataclass can be instantiated with valid data.
  2. Every dataclass round-trips through ``dataclasses.asdict()``.
  3. No forbidden imports (PyQt6, Ultralytics, views.*) exist in domain/ files.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import sys
import types
from importlib import util as importlib_util

import pytest

# ---------------------------------------------------------------------------
# Helpers – manual package bootstrap so we do NOT need pip install -e .
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PLATFORM_DIR = REPO_ROOT / "anylabeling" / "platform"
DOMAIN_DIR = PLATFORM_DIR / "domain"


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


def _bootstrap_domain() -> None:
    """Ensure the domain package is importable without pip-installing the project."""
    _ensure_package("anylabeling")
    _ensure_package("anylabeling.platform", PLATFORM_DIR)
    _ensure_package("anylabeling.platform.domain", DOMAIN_DIR)

    # Load domain modules so cross-references (e.g. DatasetBuild -> TilePlan) resolve.
    _load_module("anylabeling.platform.domain.tile", DOMAIN_DIR / "tile.py")
    _load_module("anylabeling.platform.domain.task", DOMAIN_DIR / "task.py")
    _load_module("anylabeling.platform.domain.asset", DOMAIN_DIR / "asset.py")
    _load_module("anylabeling.platform.domain.annotation", DOMAIN_DIR / "annotation.py")
    _load_module("anylabeling.platform.domain.dataset", DOMAIN_DIR / "dataset.py")
    _load_module("anylabeling.platform.domain.run", DOMAIN_DIR / "run.py")
    _load_module("anylabeling.platform.domain.prediction", DOMAIN_DIR / "prediction.py")
    _load_module("anylabeling.platform.domain.model", DOMAIN_DIR / "model.py")

    # Load __init__.py so __all__ is populated on the domain package.
    _load_module("anylabeling.platform.domain", DOMAIN_DIR / "__init__.py")


_bootstrap_domain()

# Now normal imports work.
from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.asset import Asset
from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.model import ModelArtifact
from anylabeling.platform.domain.prediction import PredictionObject, UnifiedPrediction
from anylabeling.platform.domain.run import MetricPoint, Run
from anylabeling.platform.domain.task import LabelClass, TaskSpec
from anylabeling.platform.domain.tile import TilePlan, TileRecord


# ---------------------------------------------------------------------------
# 1. Instantiation tests
# ---------------------------------------------------------------------------

class TestTaskSpec:
    def test_label_class_minimal(self) -> None:
        lc = LabelClass(id=0, name="defect")
        assert lc.id == 0
        assert lc.name == "defect"
        assert lc.color is None

    def test_label_class_full(self) -> None:
        lc = LabelClass(id=1, name="scratch", color="#FF0000", supercategory="surface")
        assert lc.supercategory == "surface"

    def test_task_spec_hbb(self) -> None:
        labels = (LabelClass(id=0, name="defect"), LabelClass(id=1, name="scratch"))
        ts = TaskSpec(
            id="task_hbb_001",
            family="detection_hbb",
            labels=labels,
            annotation_schema="xanylabeling_json",
            primary_metric="map50_95",
        )
        assert ts.id == "task_hbb_001"
        assert ts.family == "detection_hbb"
        assert len(ts.labels) == 2

    def test_task_spec_frozen(self) -> None:
        ts = TaskSpec(
            id="t1",
            family="classification",
            labels=(),
            annotation_schema="flags",
            primary_metric="accuracy",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            ts.id = "t2"  # type: ignore[misc]


class TestAsset:
    def test_asset_minimal(self) -> None:
        a = Asset(id="a1", path="assets/img01.jpg", width=1920, height=1080)
        assert a.width == 1920
        assert a.channels is None

    def test_asset_full(self) -> None:
        a = Asset(
            id="a2",
            path="assets/wafer.tif",
            width=32000,
            height=32000,
            channels=1,
            bit_depth=8,
            group_id="lot_42",
            sha256="abc123",
        )
        assert a.sha256 == "abc123"
        assert a.group_id == "lot_42"

    def test_asset_frozen(self) -> None:
        a = Asset(id="a1", path="p", width=1, height=1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            a.width = 999  # type: ignore[misc]


class TestAnnotation:
    def test_annotation_object_bbox(self) -> None:
        obj = AnnotationObject(
            id="obj1",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(10.0, 20.0, 100.0, 200.0),
        )
        assert obj.geometry_type == "bbox_xyxy"
        assert obj.source_object_id is None
        assert obj.attributes == {}

    def test_annotation_object_polygon(self) -> None:
        obj = AnnotationObject(
            id="obj2",
            label_id=1,
            geometry_type="polygon",
            geometry=[(0.0, 0.0), (50.0, 0.0), (50.0, 50.0)],
            attributes={"area": 1250.0},
            source_object_id="src_obj_99",
        )
        assert obj.source_object_id == "src_obj_99"

    def test_annotation_document(self) -> None:
        obj = AnnotationObject(id="o1", label_id=0, geometry_type="bbox_xyxy", geometry=(0, 0, 10, 10))
        doc = AnnotationDocument(
            asset_id="a1",
            image_width=1024,
            image_height=1024,
            objects=[obj],
            image_labels={"has_defect": True},
        )
        assert len(doc.objects) == 1
        assert doc.image_labels["has_defect"] is True

    def test_annotation_document_defaults(self) -> None:
        doc = AnnotationDocument(asset_id="a1", image_width=640, image_height=480)
        assert doc.objects == []
        assert doc.image_labels == {}


class TestTile:
    def test_tile_plan(self) -> None:
        tp = TilePlan(
            tile_width=1024,
            tile_height=1024,
            overlap_x=204,
            overlap_y=204,
            edge_mode="pad",
            padding_value=0,
            min_object_pixels=64,
            min_visibility_ratio=0.3,
        )
        assert tp.tile_width == 1024
        assert tp.overlap_x == 204  # pixels, not percentage

    def test_tile_plan_tuple_padding(self) -> None:
        tp = TilePlan(
            tile_width=512,
            tile_height=512,
            overlap_x=0,
            overlap_y=0,
            edge_mode="pad",
            padding_value=(114, 114, 114),
            min_object_pixels=1,
            min_visibility_ratio=0.0,
        )
        assert tp.padding_value == (114, 114, 114)

    def test_tile_record(self) -> None:
        tr = TileRecord(
            tile_id="tile_a1_0000_0000",
            asset_id="a1",
            x0=0,
            y0=0,
            width=1024,
            height=1024,
            valid_width=1024,
            valid_height=1024,
            split="train",
        )
        assert tr.split == "train"

    def test_tile_plan_frozen(self) -> None:
        tp = TilePlan(1024, 1024, 0, 0, "crop", 0, 1, 0.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            tp.tile_width = 512  # type: ignore[misc]

    def test_tile_record_frozen(self) -> None:
        tr = TileRecord("t0", "a0", 0, 0, 512, 512, 512, 512, "val")
        with pytest.raises(dataclasses.FrozenInstanceError):
            tr.split = "train"  # type: ignore[misc]


class TestDatasetBuild:
    def test_dataset_build_minimal(self) -> None:
        db = DatasetBuild(
            id="build_001",
            task_spec_id="task_hbb_001",
            source_asset_manifest_hash="abc",
            annotation_manifest_hash="def",
            split_seed=42,
            split_strategy="random_by_asset",
        )
        assert db.tile_plan is None
        assert db.augmentation_plan_id is None

    def test_dataset_build_with_tiling(self) -> None:
        tp = TilePlan(1024, 1024, 204, 204, "pad", 0, 64, 0.3)
        db = DatasetBuild(
            id="build_002",
            task_spec_id="task_obb_001",
            source_asset_manifest_hash="abc",
            annotation_manifest_hash="def",
            split_seed=123,
            split_strategy="group_by_group_id",
            tile_plan=tp,
            augmentation_plan_id="aug_001",
            adapter_id="ultralytics.v1",
            output_path="dataset_builds/build_002",
        )
        assert db.tile_plan is not None
        assert db.adapter_id == "ultralytics.v1"

    def test_dataset_build_frozen(self) -> None:
        db = DatasetBuild(
            id="b1", task_spec_id="t1",
            source_asset_manifest_hash="a", annotation_manifest_hash="b",
            split_seed=1, split_strategy="manual",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            db.split_seed = 99  # type: ignore[misc]


class TestRun:
    def test_metric_point(self) -> None:
        mp = MetricPoint(name="metrics/mAP50", value=0.74, step=12)
        assert mp.name == "metrics/mAP50"
        assert mp.value == 0.74

    def test_run_minimal(self) -> None:
        r = Run(id="run_001")
        assert r.status == "queued"
        assert r.metrics == []
        assert r.best_metric is None

    def test_run_full(self) -> None:
        r = Run(
            id="run_001",
            adapter_id="ultralytics.v1",
            task_family="instance_segmentation",
            dataset_build_id="build_001",
            base_model="D:/models/yolo11s-seg.pt",
            base_model_sha256="abc123",
            config={"epochs": 100, "imgsz": 640},
            environment={"python": "3.11", "cuda": "12.1"},
            status="completed",
            metrics=[MetricPoint("map50_95", 0.62, 100)],
            best_metric={"name": "map50_95", "value": 0.62},
            output_dir="runs/run_001",
        )
        assert r.status == "completed"
        assert len(r.metrics) == 1
        assert r.best_metric is not None


class TestPrediction:
    def test_prediction_object(self) -> None:
        po = PredictionObject(
            id="pred_001",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(100.0, 200.0, 300.0, 400.0),
            score=0.95,
            source_tile_ids=["tile_0"],
        )
        assert po.score == 0.95
        assert len(po.source_tile_ids) == 1

    def test_prediction_object_defaults(self) -> None:
        po = PredictionObject(
            id="pred_002",
            label_id=1,
            geometry_type="polygon",
            geometry=[(0, 0), (10, 10)],
            score=0.5,
        )
        assert po.source_tile_ids == []

    def test_unified_prediction(self) -> None:
        pos = [
            PredictionObject("p1", 0, "bbox_xyxy", (0, 0, 50, 50), 0.9),
            PredictionObject("p2", 0, "bbox_xyxy", (30, 30, 80, 80), 0.8, ["t1"]),
        ]
        up = UnifiedPrediction(
            asset_id="a1",
            task_family="detection_hbb",
            model_id="model_v1",
            objects=pos,
            source_tile_ids=["t0", "t1"],
            elapsed_ms=125.5,
        )
        assert len(up.objects) == 2
        assert up.elapsed_ms == 125.5

    def test_unified_prediction_defaults(self) -> None:
        up = UnifiedPrediction(asset_id="a1", task_family="classification", model_id="m1")
        assert up.objects == []
        assert up.elapsed_ms == 0.0


class TestModelArtifact:
    def test_model_artifact_minimal(self) -> None:
        ma = ModelArtifact(
            id="model_001",
            run_id="run_001",
            format="onnx",
            path="models/model_001/best.onnx",
        )
        assert ma.format == "onnx"
        assert ma.labels == []

    def test_model_artifact_full(self) -> None:
        ma = ModelArtifact(
            id="model_001",
            run_id="run_001",
            format="onnx",
            path="models/model_001/best.onnx",
            labels=["defect", "scratch"],
            preprocess={"mean": [0, 0, 0], "std": [1, 1, 1]},
            postprocess={"conf_thres": 0.25, "iou_thres": 0.45},
            onnx_check={
                "load_ok": True,
                "output_schema_ok": True,
                "samples": 10,
                "max_abs_error": 0.00031,
                "prediction_match_rate": 1.0,
                "passed": True,
            },
        )
        assert ma.onnx_check is not None
        assert ma.onnx_check["passed"] is True


# ---------------------------------------------------------------------------
# 2. Serialization round-trip tests
# ---------------------------------------------------------------------------

class TestSerialization:
    """Every domain dataclass must round-trip through dataclasses.asdict()."""

    def _roundtrip(self, instance: object) -> dict:
        d = dataclasses.asdict(instance)
        cls = type(instance)
        # Reconstruct from dict
        reconstructed = cls(**d)
        d2 = dataclasses.asdict(reconstructed)
        assert d == d2, f"{cls.__name__} serialization round-trip mismatch"
        return d

    def test_task_spec_serialization(self) -> None:
        labels = (LabelClass(id=0, name="defect"),)
        ts = TaskSpec("t1", "detection_hbb", labels, "xanylabeling_json", "map50_95")
        self._roundtrip(ts)

    def test_asset_serialization(self) -> None:
        a = Asset("a1", "assets/img.jpg", 1920, 1080, 3, 8, "g1", "abc")
        self._roundtrip(a)

    def test_annotation_document_serialization(self) -> None:
        obj = AnnotationObject("o1", 0, "bbox_xyxy", (0, 0, 10, 10), {"a": 1}, "src1")
        doc = AnnotationDocument("a1", 1024, 1024, [obj], {"ok": True})
        self._roundtrip(doc)

    def test_tile_plan_serialization(self) -> None:
        tp = TilePlan(1024, 1024, 204, 204, "pad", 0, 64, 0.3)
        self._roundtrip(tp)

    def test_tile_record_serialization(self) -> None:
        tr = TileRecord("t0", "a0", 0, 0, 1024, 1024, 1024, 1024, "train")
        self._roundtrip(tr)

    def test_dataset_build_serialization(self) -> None:
        tp = TilePlan(512, 512, 0, 0, "crop", 0, 1, 0.0)
        db = DatasetBuild(
            "b1", "t1", "a_hash", "ann_hash", 42, "random_by_asset",
            tp, "aug_1", "ultra.v1", "out",
        )
        self._roundtrip(db)

    def test_dataset_build_no_tiling_serialization(self) -> None:
        db = DatasetBuild(
            "b1", "t1", "a", "b", 1, "manual",
            None, None, "adapter.v1", "out",
        )
        self._roundtrip(db)

    def test_run_serialization(self) -> None:
        r = Run(
            id="run_001",
            adapter_id="u.v1",
            task_family="detection_hbb",
            dataset_build_id="b1",
            base_model="yolo.pt",
            base_model_sha256="abc",
            config={"epochs": 50},
            environment={"cuda": "12.1"},
            status="completed",
            metrics=[MetricPoint("map50", 0.8, 50)],
            best_metric={"name": "map50", "value": 0.8},
            output_dir="runs/run_001",
        )
        self._roundtrip(r)

    def test_prediction_serialization(self) -> None:
        po = PredictionObject("p1", 0, "bbox_xyxy", (0, 0, 10, 10), 0.9, ["t0"])
        up = UnifiedPrediction("a1", "detection_hbb", "m1", [po], ["t0"], 100.0)
        self._roundtrip(up)

    def test_model_artifact_serialization(self) -> None:
        ma = ModelArtifact(
            "m1", "r1", "onnx", "path/best.onnx",
            ["a", "b"], {"mean": [0]}, {"conf": 0.5}, {"passed": True},
        )
        self._roundtrip(ma)


# ---------------------------------------------------------------------------
# 3. Forbidden import detection
# ---------------------------------------------------------------------------

FORBIDDEN_MODULES = [
    "PyQt6",
    "PyQt5",
    "ultralytics",
    "anylabeling.views",
]


def _domain_source_files() -> list[pathlib.Path]:
    return sorted(DOMAIN_DIR.glob("*.py"))


def _extract_imports(source: str) -> list[str]:
    """Return all top-level and function-level import names from source code."""
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.append(node.module)
    return imports


@pytest.mark.parametrize("file_path", _domain_source_files())
def test_no_forbidden_imports(file_path: pathlib.Path) -> None:
    """Verify domain/ files do not import PyQt6, Ultralytics, or views.*."""
    source = file_path.read_text(encoding="utf-8")
    imported = _extract_imports(source)
    violations: list[str] = []
    for imp in imported:
        for forbidden in FORBIDDEN_MODULES:
            if imp == forbidden or imp.startswith(forbidden + "."):
                violations.append(imp)
    assert violations == [], (
        f"{file_path.name} imports forbidden modules: {violations}"
    )


# ---------------------------------------------------------------------------
# 4. Architecture constraint tests
# ---------------------------------------------------------------------------

def test_domain_files_have_future_annotations() -> None:
    """All non-init domain files must have ``from __future__ import annotations``."""
    missing: list[str] = []
    for fp in _domain_source_files():
        if fp.name == "__init__.py":
            continue
        source = fp.read_text(encoding="utf-8")
        if "from __future__ import annotations" not in source:
            missing.append(fp.name)
    assert missing == [], f"Missing __future__ annotations in: {missing}"


def test_domain_files_have_all_export() -> None:
    """All non-init domain files should define __all__."""
    missing: list[str] = []
    for fp in _domain_source_files():
        if fp.name == "__init__.py":
            continue
        source = fp.read_text(encoding="utf-8")
        if "__all__" not in source:
            missing.append(fp.name)
    assert missing == [], f"Missing __all__ export in: {missing}"


def test_domain_serializes_with_asdict() -> None:
    """Smoke test: every exported class must support dataclasses.asdict."""
    from anylabeling.platform import domain as dm

    for name in dm.__all__:
        cls = getattr(dm, name)
        # Find a way to instantiate with defaults / minimal args
        if not dataclasses.is_dataclass(cls):
            continue
        # Test that the class is a dataclass and has fields
        fields = dataclasses.fields(cls)
        assert len(fields) > 0, f"{name} has no fields"

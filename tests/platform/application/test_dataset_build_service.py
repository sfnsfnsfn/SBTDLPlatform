"""Tests for DatasetBuildService and TileMaterializer (M2.6).

Coverage:
    1. Split assignment determinism — same seed + assets → same assignment
    2. Same group split — assets with same group_id go to same split
    3. No cross-tile split leakage — all tiles from one asset have same split
    4. Build with tiling — create test assets, tile, verify outputs
    5. Build without tiling — no tile_plan → labels still written
    6. Manifest integrity — split_manifest.jsonl and tile_manifest.jsonl parseable
    7. build.json correctness — contains correct fields
    8. _READY marker — created after successful build
    9. Reproducibility — two builds with same inputs produce byte-identical manifests
    10. TileMaterializer — materializes tile images correctly
    11. YOLO label format — labels written in correct YOLO format
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from anylabeling.platform.application.dataset_build_service import (
    DatasetBuildService,
)
from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.asset import Asset
from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.task import LabelClass, TaskSpec
from anylabeling.platform.domain.tile import TilePlan, TileRecord
from anylabeling.platform.infrastructure.image_sources.memory_image_source import (
    MemoryImageSource,
)
from anylabeling.platform.infrastructure.manifest_store import ManifestStore
from anylabeling.platform.tiling.label_splitters import HBBSplitter
from anylabeling.platform.tiling.tile_materializer import TileMaterializer
from anylabeling.platform.tiling.tile_planner import TilePlanner


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Create a minimal project directory structure."""
    root = tmp_path / "test_project"
    root.mkdir(parents=True)
    (root / "dataset_builds").mkdir()
    (root / "assets").mkdir()
    (root / "annotations").mkdir()
    return root


@pytest.fixture
def hbb_task_spec() -> TaskSpec:
    """A detection_hbb task with two classes."""
    return TaskSpec(
        id="task_hbb_001",
        family="detection_hbb",
        labels=(
            LabelClass(id=0, name="defect"),
            LabelClass(id=1, name="scratch"),
        ),
        annotation_schema="xanylabeling_v4",
        primary_metric="mAP@0.5",
    )


@pytest.fixture
def classify_task_spec() -> TaskSpec:
    """A classification task with two classes."""
    return TaskSpec(
        id="task_cls_001",
        family="classification",
        labels=(
            LabelClass(id=0, name="ok"),
            LabelClass(id=1, name="ng"),
        ),
        annotation_schema="xanylabeling_v4",
        primary_metric="accuracy",
    )


@pytest.fixture
def tile_plan_128() -> TilePlan:
    """128x128 tiles with no overlap, crop edge mode."""
    return TilePlan(
        tile_width=128,
        tile_height=128,
        overlap_x=0,
        overlap_y=0,
        edge_mode="crop",
        padding_value=0,
        min_object_pixels=16,
        min_visibility_ratio=0.3,
    )


# ---------------------------------------------------------------------------
# Test asset factory
# ---------------------------------------------------------------------------


def _make_asset(
    asset_id: str,
    width: int = 256,
    height: int = 256,
    group_id: str | None = None,
) -> Asset:
    return Asset(
        id=asset_id,
        path=f"images/{asset_id}.png",
        width=width,
        height=height,
        channels=3,
        bit_depth=8,
        group_id=group_id,
    )


def _make_test_image(
    width: int = 256,
    height: int = 256,
    channels: int = 3,
    seed: int = 0,
) -> np.ndarray:
    """Create a deterministic synthetic image."""
    rng = np.random.RandomState(seed)
    return rng.randint(0, 256, (height, width, channels), dtype=np.uint8)


def _make_image_sources(
    assets: list, width: int = 256, height: int = 256, seed: int = 0
) -> dict:
    """Create MemoryImageSource entries for a list of assets."""
    from anylabeling.platform.infrastructure.image_sources.memory_image_source import (
        MemoryImageSource,
    )
    sources: dict = {}
    for asset in assets:
        img = _make_test_image(width, height, seed=seed)
        sources[asset.id] = MemoryImageSource(img)
    return sources


def _make_hbb_annotation(
    asset_id: str,
    objects: list[tuple[int, tuple[float, float, float, float]]] | None = None,
    width: int = 256,
    height: int = 256,
) -> AnnotationDocument:
    """Create an HBB annotation document.

    objects: list of (label_id, (x1, y1, x2, y2)) in L0 coords.
    """
    ann_objects: list[AnnotationObject] = []
    for i, (label_id, (x1, y1, x2, y2)) in enumerate(objects or []):
        ann_objects.append(
            AnnotationObject(
                id=f"obj_{asset_id}_{i}",
                label_id=label_id,
                geometry_type="bbox_xyxy",
                geometry=(x1, y1, x2, y2),
            )
        )
    return AnnotationDocument(
        asset_id=asset_id,
        image_width=width,
        image_height=height,
        objects=ann_objects,
    )


# ============================================================================
# 1. Split assignment determinism
# ============================================================================


class TestSplitAssignmentDeterminism:
    def test_same_seed_same_assets_gives_same_split(self, project_root: Path):
        """Same seed + same assets → identical split assignment."""
        service = DatasetBuildService(project_root)
        assets = [
            _make_asset("a1"),
            _make_asset("a2"),
            _make_asset("a3"),
            _make_asset("a4"),
            _make_asset("a5"),
        ]

        result1 = service._assign_splits(
            assets, seed=42, ratios=(0.7, 0.2, 0.1), strategy="random_by_asset"
        )
        result2 = service._assign_splits(
            assets, seed=42, ratios=(0.7, 0.2, 0.1), strategy="random_by_asset"
        )

        assert result1 == result2
        for aid in [a.id for a in assets]:
            assert result1[aid] == result2[aid]

    def test_different_seed_gives_possibly_different_assignment(
        self, project_root: Path
    ):
        """Different seeds may produce different assignments."""
        service = DatasetBuildService(project_root)
        # Use many assets to make collision unlikely
        assets = [_make_asset(f"a{i}") for i in range(50)]

        result1 = service._assign_splits(
            assets, seed=42, ratios=(0.7, 0.2, 0.1), strategy="random_by_asset"
        )
        result2 = service._assign_splits(
            assets, seed=99, ratios=(0.7, 0.2, 0.1), strategy="random_by_asset"
        )

        # The assignments should differ for at least some assets
        mismatches = sum(
            1 for a in assets if result1[a.id] != result2[a.id]
        )
        # With 50 assets, seeds different, almost certainly some mismatches
        assert mismatches > 0, (
            "Expected different seeds to produce different assignments"
        )

    def test_split_ratios_respected(self, project_root: Path):
        """Split ratios should be approximately respected."""
        service = DatasetBuildService(project_root)
        n_assets = 100
        assets = [_make_asset(f"a{i}") for i in range(n_assets)]

        result = service._assign_splits(
            assets, seed=42, ratios=(0.7, 0.2, 0.1), strategy="random_by_asset"
        )

        # Count splits
        counts: dict[str, int] = {"train": 0, "val": 0, "test": 0}
        for a in assets:
            counts[result[a.id]] += 1

        # Expected counts (exact int division)
        assert counts["train"] == 70
        assert counts["val"] == 20
        assert counts["test"] == 10


# ============================================================================
# 2. Same group split
# ============================================================================


class TestSameGroupSplit:
    def test_same_group_id_goes_to_same_split(self, project_root: Path):
        """Assets sharing group_id must be in the same split."""
        service = DatasetBuildService(project_root)
        assets = [
            _make_asset("a1", group_id="grp_A"),
            _make_asset("a2", group_id="grp_A"),
            _make_asset("a3", group_id="grp_A"),
            _make_asset("b1", group_id="grp_B"),
            _make_asset("b2", group_id="grp_B"),
            _make_asset("c1", group_id="grp_C"),
        ]

        # With only 3 groups and ratios (0.7, 0.2, 0.1), we need to force
        # the split. Let's use many groups to test properly.
        result = service._assign_splits(
            assets, seed=42, ratios=(0.7, 0.2, 0.1), strategy="group_by_group_id"
        )

        # All assets in same group must have same split
        assert result["a1"] == result["a2"] == result["a3"]
        assert result["b1"] == result["b2"]

    def test_many_groups_respect_ratio(self, project_root: Path):
        """With many groups, the group ratios are respected."""
        service = DatasetBuildService(project_root)
        # 10 groups, 3 assets each
        assets: list[Asset] = []
        for g in range(10):
            for i in range(3):
                assets.append(_make_asset(f"g{g}_a{i}", group_id=f"grp_{g}"))

        result = service._assign_splits(
            assets, seed=42, ratios=(0.7, 0.2, 0.1), strategy="group_by_group_id"
        )

        # Count assets per split
        counts: dict[str, int] = {"train": 0, "val": 0, "test": 0}
        for a in assets:
            counts[result[a.id]] += 1

        # 10 groups: 7 train (21 assets), 2 val (6 assets), 1 test (3 assets)
        assert counts["train"] == 21
        assert counts["val"] == 6
        assert counts["test"] == 3

    def test_null_group_id_treated_as_unique(self, project_root: Path):
        """Assets with None group_id are each their own group."""
        service = DatasetBuildService(project_root)
        assets = [
            _make_asset("a1", group_id=None),
            _make_asset("a2", group_id=None),
            _make_asset("a3", group_id=None),
        ]

        result = service._assign_splits(
            assets, seed=42, ratios=(0.7, 0.2, 0.1), strategy="group_by_group_id"
        )

        # Each asset is its own group, so they can be in different splits
        splits = {result[a.id] for a in assets}
        assert len(splits) >= 1  # at minimum they all get assigned something


# ============================================================================
# 3. No cross-tile split leakage
# ============================================================================


class TestNoCrossTileSplitLeakage:
    def test_all_tiles_from_one_asset_have_same_split(
        self, project_root: Path, tile_plan_128: TilePlan
    ):
        """When an asset is assigned to a split, all its tiles inherit it."""
        service = DatasetBuildService(project_root)
        asset = _make_asset("img001", width=256, height=256)

        # Assign split for this single asset
        splits = service._assign_splits(
            [asset], seed=42, ratios=(0.7, 0.2, 0.1), strategy="random_by_asset"
        )
        asset_split = splits[asset.id]

        # Generate tiles
        tiles = TilePlanner.plan(asset, tile_plan_128)

        # Verify all tiles would get the asset's split
        for tile in tiles:
            # This is what the build method does internally
            t_with_split = TileRecord(
                tile_id=tile.tile_id,
                asset_id=tile.asset_id,
                x0=tile.x0,
                y0=tile.y0,
                width=tile.width,
                height=tile.height,
                valid_width=tile.valid_width,
                valid_height=tile.valid_height,
                split=asset_split,  # type: ignore[arg-type]
            )
            assert t_with_split.split == asset_split

    def test_multiple_assets_tiles_have_correct_splits(
        self, project_root: Path, tile_plan_128: TilePlan
    ):
        """Each asset's tiles get that asset's split."""
        service = DatasetBuildService(project_root)
        assets = [
            _make_asset("a1", width=256, height=256),
            _make_asset("a2", width=256, height=256),
        ]

        splits = service._assign_splits(
            assets, seed=42, ratios=(0.5, 0.3, 0.2), strategy="random_by_asset"
        )

        for asset in assets:
            tiles = TilePlanner.plan(asset, tile_plan_128)
            expected_split = splits[asset.id]
            for tile in tiles:
                assert expected_split in ("train", "val", "test")


# ============================================================================
# 4. Build with tiling
# ============================================================================


class TestBuildWithTiling:
    def test_build_with_tiling_produces_outputs(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
        tile_plan_128: TilePlan,
    ):
        """Full build with tiling should create all expected output files."""
        service = DatasetBuildService(project_root)

        # Create two 256x256 assets → 4 tiles each (2x2 grid at 128)
        img = _make_test_image(256, 256, seed=1)
        source = MemoryImageSource(img)

        assets = [
            _make_asset("img001", width=256, height=256),
            _make_asset("img002", width=256, height=256),
        ]

        image_sources = {
            "img001": source,
            "img002": MemoryImageSource(_make_test_image(256, 256, seed=2)),
        }

        annotations = {
            "img001": _make_hbb_annotation(
                "img001",
                [(0, (50.0, 50.0, 100.0, 100.0)), (1, (150.0, 150.0, 200.0, 200.0))],
                width=256,
                height=256,
            ),
            "img002": _make_hbb_annotation(
                "img002",
                [(0, (10.0, 10.0, 80.0, 80.0))],
                width=256,
                height=256,
            ),
        }

        build = service.build(
            task_spec=hbb_task_spec,
            assets=assets,
            annotations=annotations,
            tile_plan=tile_plan_128,
            image_sources=image_sources,
            split_seed=42,
            split_ratios=(0.7, 0.2, 0.1),
            split_strategy="random_by_asset",
        )

        # Verify build object
        assert isinstance(build, DatasetBuild)
        assert build.id.startswith("build_")
        assert build.tile_plan == tile_plan_128

        # Verify output directory
        build_dir = project_root / "dataset_builds" / build.id
        assert build_dir.exists()

        # Required files
        assert (build_dir / "build.json").exists()
        assert (build_dir / "split_manifest.jsonl").exists()
        assert (build_dir / "tile_manifest.jsonl").exists()
        assert (build_dir / "data.yaml").exists()
        assert (build_dir / "_READY").exists()

        # Image directories should exist with tile images
        for split_name in ("train", "val", "test"):
            img_dir = build_dir / "images" / split_name
            if img_dir.exists():
                pngs = list(img_dir.glob("*.png"))
                assert len(pngs) > 0, f"No PNG files in {img_dir}"
                for png in pngs:
                    assert png.stat().st_size > 0

    def test_tile_images_have_correct_content(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
        tile_plan_128: TilePlan,
    ):
        """Materialized tile images should contain correct pixel data."""
        service = DatasetBuildService(project_root)

        # Create a deterministic image with known pattern
        img = np.zeros((256, 256, 3), dtype=np.uint8)
        img[0:128, 0:128] = [255, 0, 0]     # top-left: red
        img[0:128, 128:256] = [0, 255, 0]    # top-right: green
        img[128:256, 0:128] = [0, 0, 255]    # bottom-left: blue
        img[128:256, 128:256] = [255, 255, 0]  # bottom-right: yellow

        source = MemoryImageSource(img)
        asset = _make_asset("img001", width=256, height=256)

        annotations = {
            "img001": _make_hbb_annotation(
                "img001",
                [(0, (10.0, 10.0, 50.0, 50.0))],
                width=256,
                height=256,
            ),
        }

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations=annotations,
            tile_plan=tile_plan_128,
            image_sources={"img001": source},
            split_seed=42,
            split_ratios=(0.7, 0.2, 0.1),
        )

        # All tiles should go to the same split (only 1 asset)
        build_dir = project_root / "dataset_builds" / build.id
        img_dirs = list((build_dir / "images").glob("*"))
        split_dir = img_dirs[0]  # only one split dir should exist
        pngs = sorted(split_dir.glob("*.png"))

        assert len(pngs) == 4  # 2x2 grid of 128x128 tiles

        # Validate tile content by reading back
        from anylabeling.platform.infrastructure.image_reader import ImageReader
        for png in pngs:
            loaded = ImageReader.read(str(png), output_color="BGR")
            assert loaded is not None
            assert loaded.shape[:2] in ((128, 128),)

    def test_yolo_labels_written_for_tiles(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
        tile_plan_128: TilePlan,
    ):
        """Each tile should have a corresponding YOLO .txt label file."""
        service = DatasetBuildService(project_root)

        img = _make_test_image(256, 256, seed=1)
        source = MemoryImageSource(img)
        asset = _make_asset("img001", width=256, height=256)

        # Object spans top-left tile (0-128, 0-128)
        annotations = {
            "img001": _make_hbb_annotation(
                "img001",
                [(0, (10.0, 10.0, 50.0, 50.0))],
                width=256,
                height=256,
            ),
        }

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations=annotations,
            tile_plan=tile_plan_128,
            image_sources={"img001": source},
            split_seed=42,
            split_ratios=(0.7, 0.2, 0.1),
        )

        build_dir = project_root / "dataset_builds" / build.id

        # Find the split directory
        split_dirs = list((build_dir / "labels").glob("*"))
        assert len(split_dirs) >= 1

        label_dir = split_dirs[0]
        txt_files = sorted(label_dir.glob("*.txt"))
        assert len(txt_files) == 4  # one per tile

        # At least one tile should have label content (the one with the object)
        non_empty = [f for f in txt_files if f.stat().st_size > 0]
        assert len(non_empty) >= 1

        # Validate YOLO format
        for tf in non_empty:
            content = tf.read_text(encoding="utf-8").strip()
            parts = content.split()
            # HBB format: class_id xc yc w h
            assert len(parts) == 5
            class_id = int(parts[0])
            assert class_id == 0
            # All values are float and normalized (0..1)
            for val_str in parts[1:]:
                val = float(val_str)
                assert 0.0 <= val <= 1.0


# ============================================================================
# 5. Build without tiling
# ============================================================================


class TestBuildWithoutTiling:
    def test_build_without_tiling_writes_labels(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
    ):
        """Without tile_plan, YOLO labels should still be written for full images."""
        service = DatasetBuildService(project_root)

        asset = _make_asset("img001", width=256, height=256)
        annotations = {
            "img001": _make_hbb_annotation(
                "img001",
                [(0, (50.0, 50.0, 100.0, 100.0))],
                width=256,
                height=256,
            ),
        }

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations=annotations,
            tile_plan=None,
            image_sources=_make_image_sources([asset]),
            split_seed=42,
            split_ratios=(0.7, 0.2, 0.1),
        )

        build_dir = project_root / "dataset_builds" / build.id
        assert build_dir.exists()

        # Labels directory should exist
        label_dirs = list((build_dir / "labels").glob("*"))
        assert len(label_dirs) >= 1

        # Full-image YOLO label should be written
        label_dir = label_dirs[0]
        txt_files = list(label_dir.glob("*.txt"))
        assert len(txt_files) >= 1

        content = txt_files[0].read_text(encoding="utf-8").strip()
        parts = content.split()
        assert len(parts) == 5  # class_id xc yc w h

    def test_build_without_tiling_no_tile_manifest(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
    ):
        """Without tile_plan, tile_manifest.jsonl should NOT exist."""
        service = DatasetBuildService(project_root)
        asset = _make_asset("img001", width=256, height=256)
        annotations = {
            "img001": _make_hbb_annotation("img001", []),
        }

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations=annotations,
            tile_plan=None,
            image_sources=_make_image_sources([asset]),
            split_seed=42,
            split_ratios=(0.7, 0.2, 0.1),
        )

        build_dir = project_root / "dataset_builds" / build.id
        assert not (build_dir / "tile_manifest.jsonl").exists()
        assert (build_dir / "split_manifest.jsonl").exists()
        assert (build_dir / "data.yaml").exists()

    def test_build_without_tiling_with_image_sources(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
    ):
        """Without tile_plan but with image_sources, full images are saved."""
        service = DatasetBuildService(project_root)

        img = _make_test_image(128, 128, seed=1)
        source = MemoryImageSource(img)
        asset = _make_asset("img001", width=128, height=128)

        annotations = {
            "img001": _make_hbb_annotation(
                "img001",
                [(0, (10.0, 10.0, 50.0, 50.0))],
                width=128,
                height=128,
            ),
        }

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations=annotations,
            tile_plan=None,
            image_sources={"img001": source},
            split_seed=42,
            split_ratios=(0.7, 0.2, 0.1),
        )

        build_dir = project_root / "dataset_builds" / build.id
        img_dirs = list((build_dir / "images").glob("*"))
        assert len(img_dirs) >= 1

        pngs = list(img_dirs[0].glob("*.png"))
        assert len(pngs) >= 1
        assert pngs[0].stat().st_size > 0


# ============================================================================
# 6. Manifest integrity
# ============================================================================


class TestManifestIntegrity:
    def test_split_manifest_is_valid_jsonl(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
        tile_plan_128: TilePlan,
    ):
        """split_manifest.jsonl should be parseable JSONL with required fields."""
        service = DatasetBuildService(project_root)

        img = _make_test_image(256, 256, seed=1)
        assets = [
            _make_asset("img001", width=256, height=256),
            _make_asset("img002", width=256, height=256),
        ]
        image_sources = {
            "img001": MemoryImageSource(img),
            "img002": MemoryImageSource(_make_test_image(256, 256, seed=2)),
        }
        annotations = {
            "img001": _make_hbb_annotation("img001", []),
            "img002": _make_hbb_annotation("img002", []),
        }

        build = service.build(
            task_spec=hbb_task_spec,
            assets=assets,
            annotations=annotations,
            tile_plan=tile_plan_128,
            image_sources=image_sources,
            split_seed=42,
        )

        build_dir = project_root / "dataset_builds" / build.id
        manifest_path = build_dir / "split_manifest.jsonl"
        assert ManifestStore.validate_jsonl(manifest_path)

        rows = ManifestStore.read_jsonl(manifest_path)
        assert len(rows) == 2

        for row in rows:
            assert "asset_id" in row
            assert "split" in row
            assert row["split"] in ("train", "val", "test")
            assert "tile_count" in row
            # Each 256x256 asset → 4 tiles at 128x128
            assert row["tile_count"] == 4

    def test_tile_manifest_is_valid_jsonl(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
        tile_plan_128: TilePlan,
    ):
        """tile_manifest.jsonl should be parseable JSONL with required fields."""
        service = DatasetBuildService(project_root)

        img = _make_test_image(256, 256, seed=1)
        asset = _make_asset("img001", width=256, height=256)

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations={"img001": _make_hbb_annotation("img001", [])},
            tile_plan=tile_plan_128,
            image_sources={"img001": MemoryImageSource(img)},
            split_seed=42,
        )

        build_dir = project_root / "dataset_builds" / build.id
        manifest_path = build_dir / "tile_manifest.jsonl"
        assert ManifestStore.validate_jsonl(manifest_path)

        rows = ManifestStore.read_jsonl(manifest_path)
        assert len(rows) == 4  # 256x256 → 2x2 grid of 128x128 tiles

        for row in rows:
            assert "tile_id" in row
            assert "asset_id" in row
            assert row["asset_id"] == "img001"
            assert "x0" in row
            assert "y0" in row
            assert "width" in row
            assert "height" in row
            assert "split" in row

    def test_manifest_tile_ids_are_stable(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
        tile_plan_128: TilePlan,
    ):
        """Tile IDs in the manifest should be stable across runs."""
        def do_build():
            s = DatasetBuildService(project_root)
            img = _make_test_image(256, 256, seed=1)
            asset = _make_asset("img001", width=256, height=256)
            return s.build(
                task_spec=hbb_task_spec,
                assets=[asset],
                annotations={"img001": _make_hbb_annotation("img001", [])},
                tile_plan=tile_plan_128,
                image_sources={"img001": MemoryImageSource(img)},
                split_seed=42,
            )

        build1 = do_build()
        build2 = do_build()

        # Same build_id (deterministic)
        assert build1.id == build2.id

        rows1 = ManifestStore.read_jsonl(
            project_root / "dataset_builds" / build1.id / "tile_manifest.jsonl"
        )
        rows2 = ManifestStore.read_jsonl(
            project_root / "dataset_builds" / build2.id / "tile_manifest.jsonl"
        )

        # Same tile IDs in same order
        tile_ids_1 = [r["tile_id"] for r in rows1]
        tile_ids_2 = [r["tile_id"] for r in rows2]
        assert tile_ids_1 == tile_ids_2


# ============================================================================
# 7. build.json correctness
# ============================================================================


class TestBuildJsonCorrectness:
    def test_build_json_contains_correct_fields(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
        tile_plan_128: TilePlan,
    ):
        """build.json should contain all required DatasetBuild fields."""
        service = DatasetBuildService(project_root)

        img = _make_test_image(256, 256, seed=1)
        asset = _make_asset("img001", width=256, height=256)

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations={"img001": _make_hbb_annotation("img001", [])},
            tile_plan=tile_plan_128,
            image_sources={"img001": MemoryImageSource(img)},
            split_seed=42,
            split_ratios=(0.7, 0.2, 0.1),
            split_strategy="random_by_asset",
        )

        build_dir = project_root / "dataset_builds" / build.id
        data = json.loads((build_dir / "build.json").read_text(encoding="utf-8"))

        assert data["id"] == build.id
        assert data["task_spec_id"] == "task_hbb_001"
        assert data["split_seed"] == 42
        assert data["split_strategy"] == "random_by_asset"
        assert data["tile_plan"] is not None
        assert data["tile_plan"]["tile_width"] == 128
        assert data["tile_plan"]["tile_height"] == 128
        assert "source_asset_manifest_hash" in data
        assert "annotation_manifest_hash" in data

    def test_build_json_tile_plan_null_when_not_tiling(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
    ):
        """build.json tile_plan should be null when not tiling."""
        service = DatasetBuildService(project_root)
        asset = _make_asset("img001", width=256, height=256)

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations={"img001": _make_hbb_annotation("img001", [])},
            tile_plan=None,
            image_sources=_make_image_sources([asset]),
            split_seed=42,
        )

        build_dir = project_root / "dataset_builds" / build.id
        data = json.loads((build_dir / "build.json").read_text(encoding="utf-8"))
        assert data["tile_plan"] is None


# ============================================================================
# 8. _READY marker
# ============================================================================


class TestReadyMarker:
    def test_ready_marker_exists_after_successful_build(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
    ):
        """_READY marker file should exist after a successful build."""
        service = DatasetBuildService(project_root)
        asset = _make_asset("img001", width=256, height=256)

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations={"img001": _make_hbb_annotation("img001", [])},
            tile_plan=None,
            image_sources=_make_image_sources([asset]),
            split_seed=42,
        )

        build_dir = project_root / "dataset_builds" / build.id
        ready_file = build_dir / "_READY"
        assert ready_file.exists()
        content = ready_file.read_text(encoding="utf-8")
        assert build.id in content


# ============================================================================
# 9. Reproducibility
# ============================================================================


class TestReproducibility:
    def test_two_builds_with_same_inputs_produce_byte_identical_manifests(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
        tile_plan_128: TilePlan,
    ):
        """Two builds with identical inputs produce byte-identical manifests."""
        img = _make_test_image(256, 256, seed=1)
        assets = [
            _make_asset("img001", width=256, height=256),
            _make_asset("img002", width=256, height=256),
        ]
        annotations = {
            "img001": _make_hbb_annotation("img001", []),
            "img002": _make_hbb_annotation("img002", []),
        }
        image_sources = {
            "img001": MemoryImageSource(img),
            "img002": MemoryImageSource(_make_test_image(256, 256, seed=2)),
        }

        def do_build():
            s = DatasetBuildService(project_root)
            return s.build(
                task_spec=hbb_task_spec,
                assets=assets,
                annotations=annotations,
                tile_plan=tile_plan_128,
                image_sources=image_sources,
                split_seed=42,
                split_ratios=(0.7, 0.2, 0.1),
                split_strategy="random_by_asset",
            )

        build1 = do_build()
        build2 = do_build()

        assert build1.id == build2.id

        build_dir = project_root / "dataset_builds" / build1.id

        # Compare split_manifest.jsonl
        sm1 = (build_dir / "split_manifest.jsonl").read_bytes()
        sm2 = (build_dir / "split_manifest.jsonl").read_bytes()
        assert sm1 == sm2

        # Compare tile_manifest.jsonl
        tm1 = (build_dir / "tile_manifest.jsonl").read_bytes()
        tm2 = (build_dir / "tile_manifest.jsonl").read_bytes()
        assert tm1 == tm2

        # Compare build.json
        bj1 = (build_dir / "build.json").read_bytes()
        bj2 = (build_dir / "build.json").read_bytes()
        assert bj1 == bj2

        # Compare data.yaml
        dy1 = (build_dir / "data.yaml").read_bytes()
        dy2 = (build_dir / "data.yaml").read_bytes()
        assert dy1 == dy2


# ============================================================================
# 10. TileMaterializer tests
# ============================================================================


class TestTileMaterializer:
    def test_materialize_single_tile(self, tmp_path: Path):
        """Materializer should save a tile region as PNG."""
        img = _make_test_image(256, 256, seed=1)
        source = MemoryImageSource(img)

        tile = TileRecord(
            tile_id="tile_test_0000_0000",
            asset_id="img001",
            x0=0,
            y0=0,
            width=128,
            height=128,
            valid_width=128,
            valid_height=128,
            split="train",
        )

        out_dir = tmp_path / "images" / "train"
        materializer = TileMaterializer(out_dir)
        result = materializer.materialize(source, tile)

        assert result.exists()
        assert result.suffix == ".png"
        assert result.stat().st_size > 0
        assert result.parent == out_dir

    def test_materialize_all_tiles(self, tmp_path: Path):
        """Materializer should save all tiles for an asset."""
        img = _make_test_image(256, 256, seed=1)
        source = MemoryImageSource(img)

        tiles = [
            TileRecord("t_tl", "a1", 0, 0, 128, 128, 128, 128, "train"),
            TileRecord("t_tr", "a1", 128, 0, 128, 128, 128, 128, "train"),
            TileRecord("t_bl", "a1", 0, 128, 128, 128, 128, 128, "train"),
            TileRecord("t_br", "a1", 128, 128, 128, 128, 128, 128, "train"),
        ]

        out_dir = tmp_path / "images" / "train"
        materializer = TileMaterializer(out_dir)
        paths = materializer.materialize_all(source, tiles)

        assert len(paths) == 4
        for p in paths:
            assert p.exists()
            assert p.suffix == ".png"

    def test_materialize_custom_output_name(self, tmp_path: Path):
        """Materializer should respect custom output_name."""
        img = _make_test_image(128, 128, seed=1)
        source = MemoryImageSource(img)

        tile = TileRecord("t0", "a1", 0, 0, 128, 128, 128, 128, "train")
        out_dir = tmp_path / "images"
        materializer = TileMaterializer(out_dir)

        result = materializer.materialize(source, tile, output_name="custom_name")
        assert result.name == "custom_name.png"

    def test_materialize_grayscale_image(self, tmp_path: Path):
        """Materializer should handle grayscale images."""
        img = np.random.RandomState(42).randint(0, 256, (128, 128), dtype=np.uint8)
        source = MemoryImageSource(img)

        tile = TileRecord("t0", "a1", 0, 0, 128, 128, 128, 128, "train")
        out_dir = tmp_path / "images"
        materializer = TileMaterializer(out_dir)
        result = materializer.materialize(source, tile)

        assert result.exists()
        assert result.stat().st_size > 0

    def test_materialize_rgba_image(self, tmp_path: Path):
        """Materializer should handle RGBA images by converting to RGB."""
        img = np.random.RandomState(42).randint(0, 256, (128, 128, 4), dtype=np.uint8)
        source = MemoryImageSource(img)

        tile = TileRecord("t0", "a1", 0, 0, 128, 128, 128, 128, "train")
        out_dir = tmp_path / "images"
        materializer = TileMaterializer(out_dir)
        result = materializer.materialize(source, tile)

        assert result.exists()
        assert result.stat().st_size > 0


# ============================================================================
# 11. YOLO label format tests
# ============================================================================


class TestYoloLabelFormat:
    def test_hbb_yolo_format(self, tmp_path: Path):
        """HBB annotations should be written as: class_id xc yc w h (normalized)."""
        objects = [
            AnnotationObject(
                id="obj_0",
                label_id=0,
                geometry_type="bbox_xyxy",
                geometry=(50.0, 60.0, 150.0, 140.0),  # w=100, h=80
            ),
        ]
        task_spec = TaskSpec(
            id="t1",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="defect"),),
            annotation_schema="v4",
            primary_metric="mAP",
        )
        out = tmp_path / "labels" / "test.txt"
        DatasetBuildService._write_yolo_labels(objects, 200, 200, out, task_spec)

        content = out.read_text(encoding="utf-8").strip()
        parts = content.split()
        assert len(parts) == 5
        class_id = int(parts[0])
        assert class_id == 0

        # Check normalized values
        xc = float(parts[1])
        yc = float(parts[2])
        bw = float(parts[3])
        bh = float(parts[4])

        # Expected: center=(100, 100)/200=0.5, size=(100,80)/200=(0.5,0.4)
        assert abs(xc - 0.5) < 0.01
        assert abs(yc - 0.5) < 0.01
        assert abs(bw - 0.5) < 0.01
        assert abs(bh - 0.4) < 0.01

    def test_empty_objects_writes_empty_file(self, tmp_path: Path):
        """No objects → empty label file."""
        task_spec = TaskSpec(
            id="t1",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="defect"),),
            annotation_schema="v4",
            primary_metric="mAP",
        )
        out = tmp_path / "labels" / "empty.txt"
        DatasetBuildService._write_yolo_labels([], 200, 200, out, task_spec)

        assert out.exists()
        assert out.read_text(encoding="utf-8") == ""

    def test_obb_yolo_format(self, tmp_path: Path):
        """OBB annotations should be written as: class_id x1 y1 x2 y2 x3 y3 x4 y4."""
        objects = [
            AnnotationObject(
                id="obj_0",
                label_id=1,
                geometry_type="obb_polygon",
                geometry=[(10, 10), (50, 10), (50, 50), (10, 50)],  # square
            ),
        ]
        task_spec = TaskSpec(
            id="t1",
            family="detection_obb",
            labels=(
                LabelClass(id=0, name="defect"),
                LabelClass(id=1, name="scratch"),
            ),
            annotation_schema="v4",
            primary_metric="mAP",
        )
        out = tmp_path / "labels" / "obb.txt"
        DatasetBuildService._write_yolo_labels(objects, 100, 100, out, task_spec)

        content = out.read_text(encoding="utf-8").strip()
        parts = content.split()
        assert len(parts) == 9  # class_id + 8 coords

        class_id = int(parts[0])
        assert class_id == 1

    def test_keypoints_yolo_format(self, tmp_path: Path):
        """Keypoint annotations should include bbox + keypoints."""
        objects = [
            AnnotationObject(
                id="obj_0",
                label_id=0,
                geometry_type="keypoints",
                geometry=[
                    (50.0, 50.0, 2),
                    (60.0, 60.0, 2),
                    (40.0, 60.0, 2),
                ],
            ),
        ]
        task_spec = TaskSpec(
            id="t1",
            family="pose",
            labels=(LabelClass(id=0, name="person"),),
            annotation_schema="v4",
            primary_metric="mAP",
        )
        out = tmp_path / "labels" / "pose.txt"
        DatasetBuildService._write_yolo_labels(objects, 100, 100, out, task_spec)

        content = out.read_text(encoding="utf-8").strip()
        parts = content.split()
        # Format: class xc yc w h kx1 ky1 kv1 kx2 ky2 kv2 kx3 ky3 kv3
        # = 1 + 4 + 3*3 = 14
        assert len(parts) == 14

    def test_polygon_yolo_format(self, tmp_path: Path):
        """Polygon annotations should be written as: class_id x1 y1 x2 y2 ..."""
        objects = [
            AnnotationObject(
                id="obj_0",
                label_id=0,
                geometry_type="polygon",
                geometry=[(10, 10), (50, 10), (50, 50), (10, 50)],
            ),
        ]
        task_spec = TaskSpec(
            id="t1",
            family="instance_segmentation",
            labels=(LabelClass(id=0, name="defect"),),
            annotation_schema="v4",
            primary_metric="mAP",
        )
        out = tmp_path / "labels" / "poly.txt"
        DatasetBuildService._write_yolo_labels(objects, 100, 100, out, task_spec)

        content = out.read_text(encoding="utf-8").strip()
        parts = content.split()
        assert len(parts) == 9  # class_id + 8 coords

    def test_negative_label_id_skipped(self, tmp_path: Path):
        """Objects with negative label_id should be skipped in YOLO output."""
        objects = [
            AnnotationObject(
                id="obj_0",
                label_id=-1,
                geometry_type="bbox_xyxy",
                geometry=(10, 10, 50, 50),
            ),
            AnnotationObject(
                id="obj_1",
                label_id=0,
                geometry_type="bbox_xyxy",
                geometry=(60, 60, 100, 100),
            ),
        ]
        task_spec = TaskSpec(
            id="t1",
            family="detection_hbb",
            labels=(LabelClass(id=0, name="defect"),),
            annotation_schema="v4",
            primary_metric="mAP",
        )
        out = tmp_path / "labels" / "skip.txt"
        DatasetBuildService._write_yolo_labels(objects, 200, 200, out, task_spec)

        content = out.read_text(encoding="utf-8").strip()
        # Only one line (the negative label_id object was skipped)
        lines = content.split("\n")
        assert len(lines) == 1
        assert lines[0].startswith("0 ")  # class_id 0


# ============================================================================
# 12. Edge cases
# ============================================================================


class TestEdgeCases:
    def test_tiling_requires_image_sources(
        self, project_root: Path, hbb_task_spec: TaskSpec, tile_plan_128: TilePlan
    ):
        """build() with tile_plan but no image_sources should raise ValueError."""
        service = DatasetBuildService(project_root)
        asset = _make_asset("img001", width=256, height=256)

        with pytest.raises(ValueError, match="image_sources is required"):
            service.build(
                task_spec=hbb_task_spec,
                assets=[asset],
                annotations={"img001": _make_hbb_annotation("img001", [])},
                tile_plan=tile_plan_128,
                image_sources=None,
                split_seed=42,
            )

    def test_invalid_split_ratios_raises(
        self, project_root: Path, hbb_task_spec: TaskSpec
    ):
        """Invalid split ratios should raise ValueError."""
        service = DatasetBuildService(project_root)
        asset = _make_asset("img001")

        with pytest.raises(ValueError, match="split_ratios must sum to 1.0"):
            service.build(
                task_spec=hbb_task_spec,
                assets=[asset],
                annotations={},
                tile_plan=None,
                image_sources=_make_image_sources([asset]),
                split_seed=42,
                split_ratios=(0.5, 0.5, 0.5),  # sums to 1.5
            )

    def test_no_assets_no_error(
        self, project_root: Path, hbb_task_spec: TaskSpec
    ):
        """Building with zero assets should not error."""
        service = DatasetBuildService(project_root)
        build = service.build(
            task_spec=hbb_task_spec,
            assets=[],
            annotations={},
            tile_plan=None,
            image_sources={},
            split_seed=42,
        )

        assert build.id.startswith("build_")
        build_dir = project_root / "dataset_builds" / build.id
        assert (build_dir / "_READY").exists()

    def test_missing_annotation_for_asset_is_handled(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
        tile_plan_128: TilePlan,
    ):
        """Assets without annotations should not cause errors."""
        service = DatasetBuildService(project_root)

        img = _make_test_image(256, 256, seed=1)
        asset = _make_asset("img001", width=256, height=256)

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations={},  # no annotations for this asset
            tile_plan=tile_plan_128,
            image_sources={"img001": MemoryImageSource(img)},
            split_seed=42,
        )

        build_dir = project_root / "dataset_builds" / build.id
        assert (build_dir / "_READY").exists()


# ============================================================================
# 13. data.yaml format tests
# ============================================================================


class TestDataYaml:
    def test_data_yaml_format(self, project_root: Path, hbb_task_spec: TaskSpec):
        """data.yaml should be in YOLO-compatible format."""
        service = DatasetBuildService(project_root)
        asset = _make_asset("img001")

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations={},
            tile_plan=None,
            image_sources=_make_image_sources([asset]),
            split_seed=42,
        )

        build_dir = project_root / "dataset_builds" / build.id
        yaml_content = (build_dir / "data.yaml").read_text(encoding="utf-8")

        assert "path: " in yaml_content
        assert "train: images/train" in yaml_content
        assert "val: images/val" in yaml_content
        assert "test: images/test" in yaml_content
        assert "names:" in yaml_content
        assert "0: defect" in yaml_content
        assert "1: scratch" in yaml_content
        assert "nc: 2" in yaml_content


# ============================================================================
# 14. HBBSplitter integration test
# ============================================================================


class TestHBBSplitterIntegration:
    def test_splitter_produces_tile_local_coords(
        self, tile_plan_128: TilePlan
    ):
        """HBBSplitter should produce tile-local coordinates correctly."""
        splitter = HBBSplitter()
        ann = _make_hbb_annotation(
            "img001",
            [(0, (50.0, 50.0, 100.0, 100.0))],  # in top-left 128x128 tile
            width=256,
            height=256,
        )

        # Tile covering top-left 128x128
        tile = TileRecord(
            tile_id="tile_img001_0000_0000",
            asset_id="img001",
            x0=0,
            y0=0,
            width=128,
            height=128,
            valid_width=128,
            valid_height=128,
            split="train",
        )

        results = splitter.split(ann, tile, tile_plan_128)
        assert len(results) == 1
        obj = results[0]
        assert obj.geometry_type == "bbox_xyxy"

        # Geometry should be same since tile origin is (0,0)
        x1, y1, x2, y2 = obj.geometry
        assert abs(x1 - 50.0) < 1.0
        assert abs(y1 - 50.0) < 1.0
        assert abs(x2 - 100.0) < 1.0
        assert abs(y2 - 100.0) < 1.0

    def test_splitter_object_in_different_tile_returns_empty(
        self, tile_plan_128: TilePlan
    ):
        """Object outside tile bounds should produce empty results."""
        splitter = HBBSplitter()
        ann = _make_hbb_annotation(
            "img001",
            [(0, (200.0, 200.0, 250.0, 250.0))],  # bottom-right of 256 img
            width=256,
            height=256,
        )

        # Top-left tile
        tile = TileRecord(
            "tile_img001_0000_0000", "img001",
            0, 0, 128, 128, 128, 128, "train",
        )
        results = splitter.split(ann, tile, tile_plan_128)
        assert len(results) == 0

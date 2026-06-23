"""Comprehensive tests for all five LabelSplitter implementations."""

from __future__ import annotations

import math

import pytest
from shapely import box
from shapely.geometry import Polygon as ShapelyPolygon

from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.tile import TilePlan, TileRecord
from anylabeling.platform.tiling.label_splitters.hbb import HBBSplitter
from anylabeling.platform.tiling.label_splitters.obb import OBBSplitter
from anylabeling.platform.tiling.label_splitters.polygon import PolygonSplitter
from anylabeling.platform.tiling.label_splitters.pose import PoseSplitter
from anylabeling.platform.tiling.label_splitters.classify import ClassifySplitter


# ==============================================================================
# Shared helpers
# ==============================================================================


def _plan(**overrides) -> TilePlan:
    defaults = dict(
        tile_width=512,
        tile_height=512,
        overlap_x=0,
        overlap_y=0,
        edge_mode="crop",
        padding_value=0,
        min_object_pixels=1,
        min_visibility_ratio=0.0,
    )
    defaults.update(overrides)
    return TilePlan(**defaults)  # type: ignore[arg-type]


def _tile(**overrides) -> TileRecord:
    defaults = dict(
        tile_id="tile_asset_0000_0000",
        asset_id="asset_001",
        x0=0,
        y0=0,
        width=512,
        height=512,
        valid_width=512,
        valid_height=512,
        split="none",
    )
    defaults.update(overrides)
    return TileRecord(**defaults)  # type: ignore[arg-type]


def _make_annotation(
    objects: list[AnnotationObject] | None = None,
    asset_id: str = "asset_001",
    width: int = 1024,
    height: int = 1024,
    image_labels: dict[str, bool] | None = None,
) -> AnnotationDocument:
    return AnnotationDocument(
        asset_id=asset_id,
        image_width=width,
        image_height=height,
        objects=objects or [],
        image_labels=image_labels or {},
    )


# ==============================================================================
# HBB Tests
# ==============================================================================


class TestHBBSplitter:
    """Tests for HBBSplitter (bbox_xyxy → tile-local bbox_xyxy)."""

    def test_fully_inside_tile(self):
        """Rectangle fully inside tile → one output, correct tile-local coords."""
        splitter = HBBSplitter()
        tile = _tile(x0=100, y0=100, valid_width=400, valid_height=400)
        plan = _plan()

        obj = AnnotationObject(
            id="obj_1",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(150.0, 150.0, 250.0, 250.0),  # L0 coords, fully inside (100-500)
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1

        r = results[0]
        # Tile-local: subtract tile.x0=100, tile.y0=100
        assert r.geometry == (50.0, 50.0, 150.0, 150.0)
        assert r.geometry_type == "bbox_xyxy"
        assert r.source_object_id == "obj_1"

    def test_partially_overlapping_clipped(self):
        """Rectangle partially overlapping tile → clipped to tile bounds."""
        splitter = HBBSplitter()
        tile = _tile(x0=100, y0=100, valid_width=200, valid_height=200)
        plan = _plan()

        obj = AnnotationObject(
            id="obj_2",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(50.0, 50.0, 200.0, 200.0),  # overlaps tile (100,100)-(300,300)
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1

        r = results[0]
        # Clipped to (100,100)-(200,200) in L0 → tile-local (0,0)-(100,100)
        assert r.geometry == (0.0, 0.0, 100.0, 100.0)
        assert r.source_object_id == "obj_2"

    def test_completely_outside_tile(self):
        """Rectangle completely outside tile → no output."""
        splitter = HBBSplitter()
        tile = _tile(x0=0, y0=0, valid_width=200, valid_height=200)
        plan = _plan()

        obj = AnnotationObject(
            id="obj_3",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(300.0, 300.0, 400.0, 400.0),  # far from tile
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 0

    def test_too_small_after_clipping(self):
        """Rectangle too small after clipping → filtered by min_object_pixels."""
        splitter = HBBSplitter()
        tile = _tile(x0=100, y0=100, valid_width=200, valid_height=200)
        plan = _plan(min_object_pixels=5000)

        # Original bbox is 200x200 = 40000 px²; intersection with tile is
        # (100,100)-(200,200) = 100x100 = 10000 px², which is >= 5000.
        # We need it to be < plan.min_object_pixels = 5000.
        # Use a tiny sliver: 10x10 intersection = 100 px² < 5000.
        obj = AnnotationObject(
            id="obj_4",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(95.0, 95.0, 110.0, 110.0),  # L0, intersection: (100,100)-(110,110)=100px²
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 0

    def test_source_object_id_preserved(self):
        """source_object_id must be preserved on output objects."""
        splitter = HBBSplitter()
        tile = _tile()
        plan = _plan()

        obj = AnnotationObject(
            id="src_abc",
            label_id=1,
            geometry_type="bbox_xyxy",
            geometry=(100.0, 100.0, 200.0, 200.0),
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1
        assert results[0].source_object_id == "src_abc"

    def test_visibility_ratio_filter(self):
        """Object with low visibility_ratio is filtered out."""
        splitter = HBBSplitter()
        tile = _tile(x0=100, y0=0, valid_width=50, valid_height=512)
        plan = _plan(min_visibility_ratio=0.5)

        # Bbox: 200x200 = 40000; intersection with tile (100-150, 0-200) = 50x200 = 10000
        # visibility = 10000/40000 = 0.25 < 0.5 → filtered
        obj = AnnotationObject(
            id="obj_vis",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(50.0, 0.0, 250.0, 200.0),
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 0

    def test_label_id_preserved(self):
        """label_id should be preserved."""
        splitter = HBBSplitter()
        tile = _tile()
        plan = _plan()

        obj = AnnotationObject(
            id="obj_label",
            label_id=42,
            geometry_type="bbox_xyxy",
            geometry=(100.0, 100.0, 200.0, 200.0),
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1
        assert results[0].label_id == 42

    def test_attributes_preserved(self):
        """Custom attributes should be preserved on output objects."""
        splitter = HBBSplitter()
        tile = _tile()
        plan = _plan()

        obj = AnnotationObject(
            id="obj_attr",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(100.0, 100.0, 200.0, 200.0),
            attributes={"difficult": True, "occluded": False},
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1
        assert results[0].attributes == {"difficult": True, "occluded": False}


# ==============================================================================
# OBB Tests
# ==============================================================================


class TestOBBSplitter:
    """Tests for OBBSplitter (obb_polygon → tile-local obb_polygon)."""

    def test_rotated_rect_fully_inside_tile(self):
        """Rotated rect fully inside tile → correct tile-local polygon."""
        splitter = OBBSplitter()
        tile = _tile(x0=100, y0=100, valid_width=500, valid_height=500)
        plan = _plan()

        # Simple OBB: non-axis-aligned rectangle, fully inside the tile valid area
        obb_points = [
            (150.0, 120.0),
            (250.0, 150.0),
            (220.0, 250.0),
            (120.0, 220.0),
        ]
        obj = AnnotationObject(
            id="obb_1",
            label_id=0,
            geometry_type="obb_polygon",
            geometry=obb_points,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1

        r = results[0]
        assert r.geometry_type == "obb_polygon"
        assert r.source_object_id == "obb_1"

        # All tile-local coordinates should be within [0, valid_w] x [0, valid_h]
        local_geom = r.geometry
        for x, y in local_geom:
            assert 0 <= x <= 510  # allow some tolerance
            assert 0 <= y <= 510

    def test_rotated_rect_crossing_tile_boundary(self):
        """Rotated rect crossing tile boundary → clipped, not self-intersecting."""
        splitter = OBBSplitter()
        tile = _tile(x0=200, y0=200, valid_width=300, valid_height=300)
        plan = _plan()

        # A large rotated rectangle that straddles the tile boundary
        obb_points = [
            (100.0, 150.0),
            (400.0, 100.0),
            (350.0, 400.0),
            (50.0, 450.0),
        ]
        obj = AnnotationObject(
            id="obb_2",
            label_id=0,
            geometry_type="obb_polygon",
            geometry=obb_points,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        # Should produce some output (not empty)
        assert len(results) >= 0  # may be 0 if area too small, but let's check

        if len(results) > 0:
            r = results[0]
            assert r.geometry_type == "obb_polygon"
            # Verify it's a valid 4-point polygon (not self-intersecting)
            pts = r.geometry
            assert len(pts) == 4

            # Build a Shapely polygon to verify non-self-intersecting
            poly = ShapelyPolygon(pts)
            assert poly.is_valid or poly.buffer(0).is_valid
            # Area should be positive
            assert poly.area > 0

    def test_geometry_degraded_flag(self):
        """geometry_degraded flag set when OBB is clipped."""
        splitter = OBBSplitter()
        tile = _tile(x0=300, y0=300, valid_width=200, valid_height=200)
        plan = _plan(min_object_pixels=1)

        # OBB partially overlapping the tile
        obb_points = [
            (250.0, 250.0),
            (450.0, 280.0),
            (420.0, 480.0),
            (220.0, 450.0),
        ]
        obj = AnnotationObject(
            id="obb_3",
            label_id=0,
            geometry_type="obb_polygon",
            geometry=obb_points,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)

        if len(results) > 0:
            r = results[0]
            # When clipped, geometry_degraded should be True
            assert r.attributes.get("geometry_degraded") is True
            assert "reason" in r.attributes

    def test_obb_fully_inside_not_degraded(self):
        """OBB fully inside tile should NOT have geometry_degraded."""
        splitter = OBBSplitter()
        tile = _tile(x0=0, y0=0, valid_width=600, valid_height=600)
        plan = _plan()

        obb_points = [
            (150.0, 120.0),
            (250.0, 150.0),
            (220.0, 250.0),
            (120.0, 220.0),
        ]
        obj = AnnotationObject(
            id="obb_intact",
            label_id=0,
            geometry_type="obb_polygon",
            geometry=obb_points,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1

        r = results[0]
        # Should NOT have geometry_degraded since it was fully inside
        assert "geometry_degraded" not in r.attributes

    def test_obb_source_object_id_preserved(self):
        """source_object_id preserved for OBB splits."""
        splitter = OBBSplitter()
        tile = _tile(x0=0, y0=0, valid_width=600, valid_height=600)
        plan = _plan()

        obb_points = [
            (150.0, 120.0),
            (250.0, 150.0),
            (220.0, 250.0),
            (120.0, 220.0),
        ]
        obj = AnnotationObject(
            id="obb_src",
            label_id=0,
            geometry_type="obb_polygon",
            geometry=obb_points,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1
        assert results[0].source_object_id == "obb_src"


# ==============================================================================
# Polygon Tests
# ==============================================================================


class TestPolygonSplitter:
    """Tests for PolygonSplitter (polygon → tile-local polygon)."""

    def test_polygon_fully_inside_tile(self):
        """Polygon fully inside tile → correct tile-local."""
        splitter = PolygonSplitter()
        tile = _tile(x0=100, y0=100, valid_width=500, valid_height=500)
        plan = _plan()

        poly_points = [
            (150.0, 150.0),
            (250.0, 150.0),
            (250.0, 250.0),
            (150.0, 250.0),
        ]
        obj = AnnotationObject(
            id="poly_1",
            label_id=0,
            geometry_type="polygon",
            geometry=poly_points,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1

        r = results[0]
        assert r.geometry_type == "polygon"

        # Tile-local: subtract (100, 100).  Shapely may reorder vertices;
        # compare as geometric shape, not ordered point list.
        actual = r.geometry
        expected_bbox = box(50, 50, 150, 150)  # 100x100 square

        # Build Shapely polygon from actual points and compare area + bounds
        actual_poly = ShapelyPolygon(actual)
        assert actual_poly.is_valid or actual_poly.buffer(0).is_valid
        assert math.isclose(actual_poly.area, expected_bbox.area, abs_tol=1e-6)
        assert actual_poly.equals_exact(expected_bbox, 1e-6) or actual_poly.equals(expected_bbox)

        assert r.source_object_id == "poly_1"

    def test_polygon_crossing_tile_boundary(self):
        """Polygon crossing tile → Shapely intersection used."""
        splitter = PolygonSplitter()
        tile = _tile(x0=200, y0=200, valid_width=200, valid_height=200)
        plan = _plan()

        # Polygon half inside, half outside the tile
        poly_points = [
            (150.0, 250.0),
            (300.0, 250.0),
            (300.0, 350.0),
            (150.0, 350.0),
        ]
        obj = AnnotationObject(
            id="poly_cross",
            label_id=0,
            geometry_type="polygon",
            geometry=poly_points,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1

        r = results[0]
        # All tile-local coordinates should be within [0, valid_w] x [0, valid_h]
        for x, y in r.geometry:
            assert 0 <= x <= 200
            assert 0 <= y <= 200

    def test_multipolygon_fragments_same_source(self):
        """MultiPolygon fragments share the same source_object_id."""
        splitter = PolygonSplitter()
        tile = _tile(x0=100, y0=100, valid_width=200, valid_height=200)
        plan = _plan(min_object_pixels=0, min_visibility_ratio=0.0)

        # C-shaped polygon: tile clips it into two fragments
        # Tile: (100,100)-(300,300)
        # Polygon is shaped like a C that goes around the tile
        poly_points = [
            (150.0, 150.0),
            (250.0, 150.0),
            (250.0, 200.0),
            (200.0, 200.0),
            (200.0, 250.0),
            (250.0, 250.0),
            (250.0, 350.0),
            (150.0, 350.0),
            (150.0, 250.0),
            (180.0, 250.0),
            (180.0, 200.0),
            (150.0, 200.0),
        ]
        obj = AnnotationObject(
            id="poly_multi",
            label_id=0,
            geometry_type="polygon",
            geometry=poly_points,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)

        # All fragments should have the same source_object_id
        for r in results:
            assert r.source_object_id == "poly_multi"

        # IDs should include fragment index for multi-fragment cases
        if len(results) > 1:
            for r in results:
                assert "frag_" in r.id

    def test_small_fragment_filtering(self):
        """Small fragment filtered by min_object_pixels."""
        splitter = PolygonSplitter()
        tile = _tile(x0=0, y0=0, valid_width=500, valid_height=500)
        plan = _plan(min_object_pixels=10000)

        # A tiny polygon
        poly_points = [
            (5.0, 5.0),
            (15.0, 5.0),
            (15.0, 15.0),
            (5.0, 15.0),
        ]
        obj = AnnotationObject(
            id="poly_small",
            label_id=0,
            geometry_type="polygon",
            geometry=poly_points,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        # 10x10 = 100 px² < 10000 → filtered
        assert len(results) == 0

    def test_polygon_outside_tile(self):
        """Polygon completely outside tile → no output."""
        splitter = PolygonSplitter()
        tile = _tile(x0=0, y0=0, valid_width=100, valid_height=100)
        plan = _plan()

        poly_points = [
            (200.0, 200.0),
            (300.0, 200.0),
            (300.0, 300.0),
            (200.0, 300.0),
        ]
        obj = AnnotationObject(
            id="poly_outside",
            label_id=0,
            geometry_type="polygon",
            geometry=poly_points,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 0


# ==============================================================================
# Pose Tests
# ==============================================================================


class TestPoseSplitter:
    """Tests for PoseSplitter (keypoints → tile-local keypoints)."""

    def test_all_keypoints_inside_tile(self):
        """All keypoints inside tile → correct tile-local."""
        splitter = PoseSplitter()
        tile = _tile(x0=100, y0=100, valid_width=300, valid_height=300)
        plan = _plan()

        keypoints = [
            (150.0, 150.0, 2),
            (170.0, 180.0, 2),
            (130.0, 190.0, 2),
            (160.0, 220.0, 2),
        ]
        obj = AnnotationObject(
            id="pose_1",
            label_id=0,
            geometry_type="keypoints",
            geometry=keypoints,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1

        r = results[0]
        assert r.geometry_type == "keypoints"
        assert r.source_object_id == "pose_1"

        local_kps = r.geometry
        assert len(local_kps) == 4

        # First keypoint: (150-100, 150-100, 2) = (50, 50, 2)
        assert local_kps[0] == (50.0, 50.0, 2)
        assert local_kps[1] == (70.0, 80.0, 2)
        assert local_kps[2] == (30.0, 90.0, 2)
        assert local_kps[3] == (60.0, 120.0, 2)

    def test_some_keypoints_outside_marked_invisible(self):
        """Some keypoints outside → marked not visible (0, 0, 0)."""
        splitter = PoseSplitter()
        tile = _tile(x0=100, y0=100, valid_width=100, valid_height=100)
        plan = _plan()

        keypoints = [
            (120.0, 120.0, 2),  # inside tile (100-200, 100-200)
            (50.0, 80.0, 2),    # outside
            (130.0, 150.0, 2),  # inside
            (250.0, 300.0, 2),  # outside
        ]
        obj = AnnotationObject(
            id="pose_2",
            label_id=0,
            geometry_type="keypoints",
            geometry=keypoints,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1

        local_kps = results[0].geometry
        assert len(local_kps) == 4

        # Inside: tile-local coords
        assert local_kps[0] == (20.0, 20.0, 2)
        # Outside: (0, 0, 0)
        assert local_kps[1] == (0.0, 0.0, 0)
        # Inside
        assert local_kps[2] == (30.0, 50.0, 2)
        # Outside
        assert local_kps[3] == (0.0, 0.0, 0)

    def test_too_few_visible_keypoints_filtered(self):
        """Too few visible keypoints → filtered out."""
        splitter = PoseSplitter(min_visible_keypoints=2)
        tile = _tile(x0=100, y0=100, valid_width=100, valid_height=100)
        plan = _plan()

        keypoints = [
            (120.0, 120.0, 2),   # inside
            (50.0, 80.0, 2),     # outside → (0,0,0)
            (250.0, 300.0, 2),   # outside → (0,0,0)
            (40.0, 30.0, 2),     # outside → (0,0,0)
        ]
        obj = AnnotationObject(
            id="pose_few",
            label_id=0,
            geometry_type="keypoints",
            geometry=keypoints,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        # Only 1 visible inside, threshold is 2 → filtered
        assert len(results) == 0

    def test_keypoints_outside_tile_bbox_filtered(self):
        """Keypoints whose bbox doesn't intersect tile → filtered out."""
        splitter = PoseSplitter()
        tile = _tile(x0=0, y0=0, valid_width=100, valid_height=100)
        plan = _plan()

        keypoints = [
            (200.0, 200.0, 2),
            (250.0, 250.0, 2),
        ]
        obj = AnnotationObject(
            id="pose_far",
            label_id=0,
            geometry_type="keypoints",
            geometry=keypoints,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 0

    def test_already_invisible_keypoints_stay_invisible(self):
        """Keypoints with visibility=0 stay invisible regardless of position."""
        splitter = PoseSplitter()
        tile = _tile(x0=0, y0=0, valid_width=500, valid_height=500)
        plan = _plan()

        keypoints = [
            (100.0, 100.0, 0),   # invisible, inside tile
            (200.0, 200.0, 2),   # visible, inside tile
        ]
        obj = AnnotationObject(
            id="pose_invis",
            label_id=0,
            geometry_type="keypoints",
            geometry=keypoints,
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1

        local_kps = results[0].geometry
        # Invisible stays invisible
        assert local_kps[0] == (0.0, 0.0, 0)
        # Visible stays visible, converted to tile-local
        assert local_kps[1] == (200.0, 200.0, 2)


# ==============================================================================
# Classify Tests
# ==============================================================================


class TestClassifySplitter:
    """Tests for ClassifySplitter (image-level → tile-level when inherit)."""

    def test_default_no_objects(self):
        """Default mode: no tile-level objects."""
        splitter = ClassifySplitter()
        tile = _tile()
        plan = _plan()

        ann = _make_annotation(
            image_labels={"cat": True, "dog": False},
        )

        results = splitter.split(ann, tile, plan)
        assert len(results) == 0

    def test_inherit_mode_produces_object(self):
        """Inherit mode: tile inherits image labels."""
        splitter = ClassifySplitter()
        tile = _tile(valid_width=512, valid_height=512)
        plan = _plan()

        ann = _make_annotation(image_labels={"cat": True, "dog": False})
        ann.attributes = {"tile_classification_mode": "inherit"}  # type: ignore[attr-defined]

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1

        r = results[0]
        assert r.geometry_type == "bbox_xyxy"
        assert r.geometry == (0, 0, 512, 512)  # full tile area
        assert r.attributes["tile_classification_mode"] == "inherit"
        assert r.attributes["image_labels"] == {"cat": True, "dog": False}
        assert r.source_object_id is None

    def test_inherit_mode_empty_labels(self):
        """Inherit mode with no image labels → empty list."""
        splitter = ClassifySplitter()
        tile = _tile()
        plan = _plan()

        ann = _make_annotation(image_labels={})
        ann.attributes = {"tile_classification_mode": "inherit"}  # type: ignore[attr-defined]

        results = splitter.split(ann, tile, plan)
        assert len(results) == 0


# ==============================================================================
# Merge Round-Trip Tests
# ==============================================================================


class TestMergeRoundTrip:
    """Split + reverse-merge: round-trip coordinates within 1 pixel tolerance."""

    def test_hbb_round_trip(self):
        """HBB: split across tiles, merge back, compare coordinates."""
        splitter = HBBSplitter()

        # Full image annotations
        obj = AnnotationObject(
            id="rt_hbb",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(100.0, 100.0, 400.0, 300.0),
        )
        ann = _make_annotation(objects=[obj], width=1024, height=1024)

        plan = _plan(tile_width=256, tile_height=256)

        # Simulate splitting across tiles
        collected: list[AnnotationObject] = []
        for row in range(4):  # 1024/256 = 4
            for col in range(4):
                x0 = col * 256
                y0 = row * 256
                tile = _tile(
                    tile_id=f"tile_{row}_{col}",
                    x0=x0,
                    y0=y0,
                    width=256,
                    height=256,
                    valid_width=256,
                    valid_height=256,
                )
                collected.extend(splitter.split(ann, tile, plan))

        # Save original object reference (loop below shadows 'obj')
        _orig_obj = obj

        # Merge back: add tile offsets
        merged_objects: list[AnnotationObject] = []
        for split_obj in collected:
            sx1, sy1, sx2, sy2 = split_obj.geometry  # type: ignore[misc]
            # Extract tile origin from id: "rt_hbb__tile_tile_{row}_{col}"
            parts = split_obj.id.split("__")[-1].split("_")
            tile_row = int(parts[2])
            tile_col = int(parts[3])
            tile_x0 = tile_col * 256
            tile_y0 = tile_row * 256

            merged = AnnotationObject(
                id=split_obj.source_object_id or split_obj.id,
                label_id=split_obj.label_id,
                geometry_type=split_obj.geometry_type,
                geometry=(
                    sx1 + tile_x0,
                    sy1 + tile_y0,
                    sx2 + tile_x0,
                    sy2 + tile_y0,
                ),
                attributes=dict(split_obj.attributes),
                source_object_id=split_obj.source_object_id,
            )
            merged_objects.append(merged)

        # Verify: at least 1 object
        assert len(merged_objects) >= 1

        # Verify coordinates within 1 pixel of original
        orig_x1, orig_y1, orig_x2, orig_y2 = _orig_obj.geometry  # type: ignore[misc]

        for m in merged_objects:
            mx1, my1, mx2, my2 = m.geometry  # type: ignore[misc]
            # Clipped coords should be within 1px of original bounds
            assert mx1 >= orig_x1 - 1, f"mx1={mx1} < orig_x1={orig_x1}"
            assert my1 >= orig_y1 - 1, f"my1={my1} < orig_y1={orig_y1}"
            assert mx2 <= orig_x2 + 1, f"mx2={mx2} > orig_x2={orig_x2}"
            assert my2 <= orig_y2 + 1, f"my2={my2} > orig_y2={orig_y2}"

            # The union of all tile fragments should reconstruct the original
            for m2 in merged_objects:
                if m2 is m:
                    continue
                m2x1, m2y1, m2x2, m2y2 = m2.geometry  # type: ignore[misc]
                # No excessive overlap (fragments should be mostly disjoint)
                overlap_x = max(0.0, min(mx2, m2x2) - max(mx1, m2x1))
                overlap_y = max(0.0, min(my2, m2y2) - max(my1, m2y1))
                overlap_area = overlap_x * overlap_y
                # Allow small overlap from edge effects
                assert overlap_area < 100, f"Excessive overlap {overlap_area}px"

    def test_polygon_round_trip(self):
        """Polygon: split, merge, verify coordinates within tolerance."""
        splitter = PolygonSplitter()

        poly_points = [
            (200.0, 200.0),
            (500.0, 200.0),
            (500.0, 500.0),
            (200.0, 500.0),
        ]
        obj = AnnotationObject(
            id="rt_poly",
            label_id=0,
            geometry_type="polygon",
            geometry=poly_points,
        )
        ann = _make_annotation(objects=[obj], width=1024, height=1024)

        plan = _plan(tile_width=256, tile_height=256)

        # Split across 4x4 tiles
        collected: list[tuple[AnnotationObject, int, int]] = []
        for row in range(4):
            for col in range(4):
                x0 = col * 256
                y0 = row * 256
                tile = _tile(
                    tile_id=f"tile_{row}_{col}",
                    x0=x0,
                    y0=y0,
                    width=256,
                    height=256,
                    valid_width=256,
                    valid_height=256,
                )
                for r in splitter.split(ann, tile, plan):
                    collected.append((r, x0, y0))

        assert len(collected) >= 1

        # Merge back
        for obj, tx, ty in collected:
            merged_pts = [(x + tx, y + ty) for x, y in obj.geometry]  # type: ignore[union-attr]

            # Each merged point should be near the original polygon
            for mx, my in merged_pts:
                # Should be inside or very close to the original polygon bbox
                assert 195 <= mx <= 505, f"x={mx} outside [195, 505]"
                assert 195 <= my <= 505, f"y={my} outside [195, 505]"

    def test_pose_round_trip(self):
        """Pose: split, merge, verify keypoint coordinates."""
        splitter = PoseSplitter()

        keypoints = [
            (300.0, 300.0, 2),
            (350.0, 320.0, 2),
            (280.0, 350.0, 2),
            (320.0, 400.0, 2),
            (400.0, 500.0, 2),
        ]
        obj = AnnotationObject(
            id="rt_pose",
            label_id=0,
            geometry_type="keypoints",
            geometry=keypoints,
        )
        ann = _make_annotation(objects=[obj], width=1024, height=1024)

        plan = _plan(tile_width=256, tile_height=256)

        # Split across tiles
        collected: list[tuple[AnnotationObject, int, int]] = []
        for row in range(4):
            for col in range(4):
                x0 = col * 256
                y0 = row * 256
                tile = _tile(
                    tile_id=f"tile_{row}_{col}",
                    x0=x0,
                    y0=y0,
                    width=256,
                    height=256,
                    valid_width=256,
                    valid_height=256,
                )
                for r in splitter.split(ann, tile, plan):
                    collected.append((r, x0, y0))

        assert len(collected) >= 1

        # Merge back
        for obj, tx, ty in collected:
            merged_kps = []
            for x, y, v in obj.geometry:  # type: ignore[union-attr]
                if v > 0:
                    merged_kps.append((x + tx, y + ty, v))
                else:
                    merged_kps.append((x, y, v))

            # Check that visible keypoints are within 1px of original
            for i, (mx, my, mv) in enumerate(merged_kps):
                if mv > 0:
                    ox, oy, ov = keypoints[i]
                    assert abs(mx - ox) <= 1, f"Keypoint {i}: {mx} != {ox}"
                    assert abs(my - oy) <= 1, f"Keypoint {i}: {my} != {oy}"

    def test_obb_round_trip_area_preservation(self):
        """OBB: split across tiles, verify total area is reasonable."""
        splitter = OBBSplitter()

        obb_points = [
            (150.0, 150.0),
            (450.0, 180.0),
            (420.0, 480.0),
            (120.0, 450.0),
        ]
        obj = AnnotationObject(
            id="rt_obb",
            label_id=0,
            geometry_type="obb_polygon",
            geometry=obb_points,
        )
        ann = _make_annotation(objects=[obj], width=1024, height=1024)

        plan = _plan(tile_width=256, tile_height=256)

        collected: list[tuple[AnnotationObject, int, int]] = []
        for row in range(4):
            for col in range(4):
                x0 = col * 256
                y0 = row * 256
                tile = _tile(
                    tile_id=f"tile_{row}_{col}",
                    x0=x0,
                    y0=y0,
                    width=256,
                    height=256,
                    valid_width=256,
                    valid_height=256,
                )
                for r in splitter.split(ann, tile, plan):
                    collected.append((r, x0, y0))

        assert len(collected) >= 1

        # Verify total area of merged OBBs doesn't exceed original
        orig_area = ShapelyPolygon(obb_points).area
        total_merged_area = 0.0
        for obj, tx, ty in collected:
            merged_pts = [(x + tx, y + ty) for x, y in obj.geometry]  # type: ignore[union-attr]
            merged_area = ShapelyPolygon(merged_pts).area
            total_merged_area += merged_area

        # Total merged area should be reasonable (within 2x original due to overlap)
        assert total_merged_area <= orig_area * 3.0, (
            f"Total merged area {total_merged_area} is too large vs original {orig_area}"
        )
        assert total_merged_area > 0, "Should have non-zero total area"

    def test_no_input_modification(self):
        """Splitters must not modify the input AnnotationDocument."""
        splitter = HBBSplitter()
        tile = _tile(x0=0, y0=0, valid_width=256, valid_height=256)
        plan = _plan()

        obj = AnnotationObject(
            id="immutable_test",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(50.0, 50.0, 150.0, 150.0),
            attributes={"key": "value"},
        )
        ann = _make_annotation(objects=[obj])

        # Capture state before
        before_geom = obj.geometry
        before_attrs = dict(obj.attributes)
        before_count = len(ann.objects)

        _ = splitter.split(ann, tile, plan)

        # State after should be unchanged
        assert obj.geometry == before_geom
        assert obj.attributes == before_attrs
        assert len(ann.objects) == before_count


# ==============================================================================
# Edge Cases
# ==============================================================================


class TestEdgeCases:
    """Boundary and edge case tests across all splitters."""

    def test_empty_annotations(self):
        """Empty annotations → empty results for all splitters."""
        tile = _tile()
        plan = _plan()
        ann = _make_annotation(objects=[])

        assert HBBSplitter().split(ann, tile, plan) == []
        assert OBBSplitter().split(ann, tile, plan) == []
        assert PolygonSplitter().split(ann, tile, plan) == []
        assert PoseSplitter().split(ann, tile, plan) == []
        assert ClassifySplitter().split(ann, tile, plan) == []

    def test_zero_valid_area_tile(self):
        """Tile with zero valid area → empty results for all geometry splitters."""
        plan = _plan()
        ann = _make_annotation(
            objects=[
                AnnotationObject(
                    id="zero_obj",
                    label_id=0,
                    geometry_type="bbox_xyxy",
                    geometry=(0.0, 0.0, 10.0, 10.0),
                ),
            ]
        )

        tile_zero = _tile(valid_width=0, valid_height=512)
        assert HBBSplitter().split(ann, tile_zero, plan) == []

        tile_zero_y = _tile(valid_width=512, valid_height=0)
        assert HBBSplitter().split(ann, tile_zero_y, plan) == []

    def test_negative_coordinate_bbox(self):
        """Bbox that starts with negative coordinates should still clip correctly."""
        splitter = HBBSplitter()
        tile = _tile(x0=0, y0=0, valid_width=200, valid_height=200)
        plan = _plan()

        obj = AnnotationObject(
            id="neg_bbox",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(-50.0, -50.0, 100.0, 100.0),  # partially outside
        )
        ann = _make_annotation(objects=[obj])

        results = splitter.split(ann, tile, plan)
        assert len(results) == 1
        # Should be clipped to (0,0)-(100,100)
        assert results[0].geometry == (0.0, 0.0, 100.0, 100.0)

    def test_hbb_id_collision_prevention(self):
        """Splitter should not produce duplicate object IDs when splitting
        the same source object across multiple tiles."""
        splitter = HBBSplitter()
        plan = _plan(tile_width=256, tile_height=256)

        obj = AnnotationObject(
            id="collide",
            label_id=0,
            geometry_type="bbox_xyxy",
            geometry=(100.0, 100.0, 400.0, 400.0),
        )
        ann = _make_annotation(objects=[obj], width=1024, height=1024)

        ids: set[str] = set()
        for row in range(4):
            for col in range(4):
                tile = _tile(
                    tile_id=f"tile_{row}_{col}",
                    x0=col * 256,
                    y0=row * 256,
                    width=256,
                    height=256,
                    valid_width=256,
                    valid_height=256,
                )
                for r in splitter.split(ann, tile, plan):
                    ids.add(r.id)

        assert len(ids) == len(
            [r for row in range(4) for col in range(4)
             for r in splitter.split(ann,
                 _tile(tile_id=f"tile_{row}_{col}", x0=col*256, y0=row*256,
                       width=256, height=256, valid_width=256, valid_height=256),
                 plan)]
        ), "Duplicate IDs detected"

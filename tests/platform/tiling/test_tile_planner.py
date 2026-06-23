"""Tests for deterministic tile planning (TilePlanner)."""

from __future__ import annotations

import pytest

from anylabeling.platform.domain.asset import Asset
from anylabeling.platform.domain.tile import TilePlan, TileRecord
from anylabeling.platform.tiling.tile_planner import TilePlanner


# =============================================================================
# Helpers
# =============================================================================

def _make_plan(
    tile_w: int = 512,
    tile_h: int = 512,
    overlap_x: int = 0,
    overlap_y: int = 0,
    edge_mode: str = "crop",
) -> TilePlan:
    return TilePlan(
        tile_width=tile_w,
        tile_height=tile_h,
        overlap_x=overlap_x,
        overlap_y=overlap_y,
        edge_mode=edge_mode,  # type: ignore[arg-type]
        padding_value=0,
        min_object_pixels=1,
        min_visibility_ratio=0.0,
    )


def _make_asset(
    asset_id: str = "img_001",
    width: int = 1024,
    height: int = 1024,
) -> Asset:
    return Asset(id=asset_id, path=f"{asset_id}.jpg", width=width, height=height)


# =============================================================================
# Test 1: No overlap — tiles cover image exactly, no gaps
# =============================================================================

class TestNoOverlap:
    """Tiles without overlap should partition the image cleanly."""

    def test_exact_fit(self):
        """Image dims are exact multiples of tile size."""
        plan = _make_plan(tile_w=256, tile_h=256, edge_mode="crop")
        asset = _make_asset(width=1024, height=1024)
        records = TilePlanner.plan(asset, plan)

        assert len(records) == 16  # 4x4

        # Check all tiles have expected dimensions
        for r in records:
            assert r.width == 256
            assert r.height == 256
            assert r.valid_width == 256
            assert r.valid_height == 256

    def test_no_gaps(self):
        """Adjacent tiles must have no gap and no overlap."""
        plan = _make_plan(tile_w=100, tile_h=100, edge_mode="crop")
        asset = _make_asset(width=300, height=300)
        records = TilePlanner.plan(asset, plan)

        # Verify horizontal adjacency
        for row in range(3):
            for col in range(1, 3):
                left = records[row * 3 + col - 1]
                right = records[row * 3 + col]
                assert left.x0 + left.width == right.x0, (
                    f"Gap or overlap between tiles at row={row} col={col-1}->{col}"
                )

        # Verify vertical adjacency
        for col in range(3):
            for row in range(1, 3):
                top = records[(row - 1) * 3 + col]
                bottom = records[row * 3 + col]
                assert top.y0 + top.height == bottom.y0, (
                    f"Gap or overlap between tiles at col={col} row={row-1}->{row}"
                )

    def test_full_coverage(self):
        """Union of all tiles covers the entire image."""
        plan = _make_plan(tile_w=100, tile_h=100, edge_mode="crop")
        asset = _make_asset(width=300, height=200)
        records = TilePlanner.plan(asset, plan)

        # Check last tile reaches image boundary
        last_col = max(r.x0 + r.width for r in records)
        last_row = max(r.y0 + r.height for r in records)
        assert last_col == 300
        assert last_row == 200


# =============================================================================
# Test 2: 20% overlap — adjacent tiles overlap by correct pixel amount
# =============================================================================

class TestOverlap:
    """Tiles with overlap should overlap by exactly the specified pixel amount."""

    def test_horizontal_overlap_amount(self):
        plan = _make_plan(tile_w=500, tile_h=500, overlap_x=100, overlap_y=0, edge_mode="crop")
        asset = _make_asset(width=1500, height=500)
        records = TilePlanner.plan(asset, plan)

        # Two adjacent tiles in first row
        t0 = records[0]
        t1 = records[1]
        expected_overlap = (t0.x0 + t0.width) - t1.x0
        assert expected_overlap == 100, f"Expected overlap 100px, got {expected_overlap}"

    def test_vertical_overlap_amount(self):
        plan = _make_plan(tile_w=500, tile_h=500, overlap_x=0, overlap_y=100, edge_mode="crop")
        asset = _make_asset(width=500, height=1500)
        records = TilePlanner.plan(asset, plan)

        t0 = records[0]
        t1 = records[1]  # same col, next row
        expected_overlap = (t0.y0 + t0.height) - t1.y0
        assert expected_overlap == 100, f"Expected overlap 100px, got {expected_overlap}"

    def test_grid_with_overlap(self):
        """1000x1000 image, 500x500 tiles, 100px overlap → 3x3 grid."""
        plan = _make_plan(tile_w=500, tile_h=500, overlap_x=100, overlap_y=100, edge_mode="crop")
        asset = _make_asset(width=1000, height=1000)
        records = TilePlanner.plan(asset, plan)

        # stride = 400, cols = ceil(1000/400) = 3, rows = 3
        assert len(records) == 9

    def test_overlap_must_be_less_than_tile_size(self):
        plan = _make_plan(tile_w=100, tile_h=100, overlap_x=100, overlap_y=0)
        asset = _make_asset(width=200, height=200)
        with pytest.raises(ValueError):
            TilePlanner.plan(asset, plan)

    def test_negative_overlap_raises(self):
        """Negative overlap would create gaps between tiles (stride > tile size)."""
        plan = _make_plan(tile_w=512, tile_h=512, overlap_x=-10, overlap_y=0)
        asset = _make_asset(width=1024, height=1024)
        with pytest.raises(ValueError, match="Overlap must be non-negative"):
            TilePlanner.plan(asset, plan)

    def test_negative_overlap_y_raises(self):
        plan = _make_plan(tile_w=512, tile_h=512, overlap_x=0, overlap_y=-5)
        asset = _make_asset(width=1024, height=1024)
        with pytest.raises(ValueError, match="Overlap must be non-negative"):
            TilePlanner.plan(asset, plan)


# =============================================================================
# Test 3: Bottom-right edge with crop — last tiles have smaller dimensions
# =============================================================================

class TestEdgeCrop:
    """Crop mode: tiles at the right/bottom edge are clipped to image bounds."""

    def test_right_edge_crop(self):
        plan = _make_plan(tile_w=400, tile_h=400, edge_mode="crop")
        asset = _make_asset(width=1000, height=400)
        records = TilePlanner.plan(asset, plan)
        # cols = ceil(1000/400) = 3
        assert len(records) == 3

        last = records[-1]
        assert last.x0 == 800
        assert last.width == 200  # 1000 - 800
        assert last.valid_width == 200
        assert last.height == 400
        assert last.valid_height == 400

    def test_bottom_edge_crop(self):
        plan = _make_plan(tile_w=400, tile_h=400, edge_mode="crop")
        asset = _make_asset(width=400, height=1000)
        records = TilePlanner.plan(asset, plan)
        # rows = ceil(1000/400) = 3
        assert len(records) == 3

        last = records[-1]
        assert last.y0 == 800
        assert last.height == 200  # 1000 - 800
        assert last.valid_height == 200

    def test_corner_crop(self):
        """Bottom-right corner has reduced width AND height."""
        plan = _make_plan(tile_w=400, tile_h=400, edge_mode="crop")
        asset = _make_asset(width=1000, height=1000)
        records = TilePlanner.plan(asset, plan)
        # 3x3 = 9 tiles
        assert len(records) == 9

        # Last tile (row=2, col=2) should be bottom-right corner
        corner = records[-1]
        assert corner.x0 == 800
        assert corner.y0 == 800
        assert corner.width == 200
        assert corner.height == 200
        assert corner.valid_width == 200
        assert corner.valid_height == 200


# =============================================================================
# Test 4: Bottom-right edge with pad — all tiles have full size
# =============================================================================

class TestEdgePad:
    """Pad mode: edge tiles keep full tile dimensions, valid_width/height
    indicates the real content region."""

    def test_right_edge_pad(self):
        plan = _make_plan(tile_w=400, tile_h=400, edge_mode="pad")
        asset = _make_asset(width=1000, height=400)
        records = TilePlanner.plan(asset, plan)
        assert len(records) == 3

        last = records[-1]
        assert last.x0 == 800
        assert last.width == 400  # full tile width
        assert last.valid_width == 200  # only 200px of real content
        assert last.height == 400
        assert last.valid_height == 400

    def test_bottom_edge_pad(self):
        plan = _make_plan(tile_w=400, tile_h=400, edge_mode="pad")
        asset = _make_asset(width=400, height=1000)
        records = TilePlanner.plan(asset, plan)
        assert len(records) == 3

        last = records[-1]
        assert last.y0 == 800
        assert last.height == 400  # full tile height
        assert last.valid_height == 200

    def test_corner_pad(self):
        """Bottom-right corner: full dimensions, valid_w/h < tile_w/h."""
        plan = _make_plan(tile_w=400, tile_h=400, edge_mode="pad")
        asset = _make_asset(width=1000, height=1000)
        records = TilePlanner.plan(asset, plan)
        assert len(records) == 9

        corner = records[-1]
        assert corner.x0 == 800
        assert corner.y0 == 800
        assert corner.width == 400
        assert corner.height == 400
        assert corner.valid_width == 200
        assert corner.valid_height == 200

    def test_interior_pad_tile_has_full_valid(self):
        """Interior tiles in pad mode still have valid == full."""
        plan = _make_plan(tile_w=400, tile_h=400, edge_mode="pad")
        asset = _make_asset(width=1200, height=1200)
        records = TilePlanner.plan(asset, plan)

        # First tile (top-left) is interior
        first = records[0]
        assert first.valid_width == first.width
        assert first.valid_height == first.height


# =============================================================================
# Test 5: Tile order is deterministic
# =============================================================================

class TestDeterministic:
    """Same input must produce same output every time."""

    def test_idempotent(self):
        plan = _make_plan(tile_w=256, tile_h=256, overlap_x=50, overlap_y=50, edge_mode="crop")
        asset = _make_asset(width=1024, height=768)
        records1 = TilePlanner.plan(asset, plan)
        records2 = TilePlanner.plan(asset, plan)
        assert len(records1) == len(records2)
        for r1, r2 in zip(records1, records2):
            assert r1 == r2

    def test_tile_id_format(self):
        plan = _make_plan(tile_w=256, tile_h=256, edge_mode="crop")
        asset = _make_asset(asset_id="abc123", width=1024, height=512)
        records = TilePlanner.plan(asset, plan)

        # Row-major order: row 0 col 0, row 0 col 1, ..., row 0 col 3,
        #                   row 1 col 0, row 1 col 1, ...
        assert records[0].tile_id == "tile_abc123_0000_0000"
        assert records[1].tile_id == "tile_abc123_0000_0001"
        assert records[4].tile_id == "tile_abc123_0001_0000"
        assert records[7].tile_id == "tile_abc123_0001_0003"

    def test_row_major_order(self):
        """Tiles should be in row-major order (top-left to bottom-right)."""
        plan = _make_plan(tile_w=100, tile_h=100, edge_mode="crop")
        asset = _make_asset(width=300, height=200)
        records = TilePlanner.plan(asset, plan)
        # 3 cols x 2 rows
        assert len(records) == 6

        # Check positions are increasing in row-major order
        for i in range(len(records) - 1):
            a, b = records[i], records[i + 1]
            # Either same row (y equal) and b is to the right,
            # or b is in a later row
            if a.y0 == b.y0:
                assert b.x0 > a.x0
            else:
                assert b.y0 > a.y0

    def test_split_field_is_none(self):
        """All tiles should have split="none" by default."""
        plan = _make_plan(tile_w=256, tile_h=256, edge_mode="crop")
        asset = _make_asset(width=1024, height=1024)
        records = TilePlanner.plan(asset, plan)
        for r in records:
            assert r.split == "none"


# =============================================================================
# Test 6: Tile count calculation is correct
# =============================================================================

class TestTileCount:
    """Verify tile count math for various image sizes and tile dimensions."""

    @pytest.mark.parametrize("img_w, img_h, tile_w, tile_h, overlap, expected", [
        # Exact division, no overlap
        (1024, 1024, 256, 256, 0, 16),
        # Not exact division, no overlap
        (1000, 1000, 256, 256, 0, 16),  # ceil(1000/256)=4, 4x4=16
        # Single tile
        (100, 100, 256, 256, 0, 1),
        # Single row
        (1000, 100, 200, 200, 0, 5),
        # 20% overlap
        (1000, 1000, 500, 500, 100, 9),  # stride=400, ceil(1000/400)=3, 3x3=9
        # Small image, large tiles
        (50, 50, 512, 512, 0, 1),
    ])
    def test_tile_count(self, img_w, img_h, tile_w, tile_h, overlap, expected):
        plan = _make_plan(tile_w=tile_w, tile_h=tile_h, overlap_x=overlap, overlap_y=overlap, edge_mode="crop")
        asset = _make_asset(width=img_w, height=img_h)
        records = TilePlanner.plan(asset, plan)
        assert len(records) == expected, (
            f"Expected {expected} tiles for {img_w}x{img_h} image, "
            f"tile={tile_w}x{tile_h}, overlap={overlap}"
        )


# =============================================================================
# Test 7: Large image (8192×8192, tile 1024×1024, overlap 204px = 20%)
# =============================================================================

class TestLargeImage:
    """Verify correct tile count for a large 8192x8192 image."""

    def test_tile_count_8192_tile_1024_overlap_204(self):
        """8192x8192, tile 1024x1024, overlap 204px → stride=820, 10x10=100 tiles."""
        plan = _make_plan(
            tile_w=1024, tile_h=1024,
            overlap_x=204, overlap_y=204,
            edge_mode="crop",
        )
        asset = _make_asset(width=8192, height=8192)
        records = TilePlanner.plan(asset, plan)
        assert len(records) == 100

    def test_large_image_crop_last_tile_dimensions(self):
        """Last tile should have correct crop dimensions."""
        plan = _make_plan(tile_w=1024, tile_h=1024, overlap_x=204, overlap_y=204, edge_mode="crop")
        asset = _make_asset(width=8192, height=8192)
        records = TilePlanner.plan(asset, plan)

        # stride = 1024 - 204 = 820
        # cols = ceil(8192/820) = 10
        # last col x0 = 9 * 820 = 7380, width = 8192 - 7380 = 812
        # last row y0 = 7380, height = 812
        corner = records[-1]
        assert corner.x0 == 7380
        assert corner.y0 == 7380
        assert corner.width == 812
        assert corner.height == 812

    def test_large_image_pad_last_tile_dimensions(self):
        """Pad mode: last tile keeps full dimensions but valid_w/h is correct."""
        plan = _make_plan(tile_w=1024, tile_h=1024, overlap_x=204, overlap_y=204, edge_mode="pad")
        asset = _make_asset(width=8192, height=8192)
        records = TilePlanner.plan(asset, plan)

        corner = records[-1]
        assert corner.x0 == 7380
        assert corner.y0 == 7380
        assert corner.width == 1024
        assert corner.height == 1024
        assert corner.valid_width == 812
        assert corner.valid_height == 812


# =============================================================================
# Edge cases
# =============================================================================

class TestEdgeCases:
    """Additional edge-case tests."""

    def test_single_tile_equals_image(self):
        plan = _make_plan(tile_w=100, tile_h=100, edge_mode="crop")
        asset = _make_asset(width=100, height=100)
        records = TilePlanner.plan(asset, plan)
        assert len(records) == 1
        assert records[0].x0 == 0
        assert records[0].y0 == 0
        assert records[0].width == 100
        assert records[0].height == 100

    def test_tile_larger_than_image(self):
        plan = _make_plan(tile_w=500, tile_h=500, edge_mode="crop")
        asset = _make_asset(width=100, height=100)
        records = TilePlanner.plan(asset, plan)
        assert len(records) == 1
        assert records[0].width == 100
        assert records[0].height == 100

    def test_negative_dimensions_asset_raises(self):
        plan = _make_plan(tile_w=256, tile_h=256)
        asset = Asset(id="bad", path="bad.jpg", width=-1, height=100)
        with pytest.raises(ValueError):
            TilePlanner.plan(asset, plan)

    def test_zero_dimensions_tile_raises(self):
        plan = _make_plan(tile_w=0, tile_h=256)
        asset = _make_asset()
        with pytest.raises(ValueError):
            TilePlanner.plan(asset, plan)

    def test_all_tiles_have_unique_ids(self):
        plan = _make_plan(tile_w=100, tile_h=100, overlap_x=20, overlap_y=20, edge_mode="crop")
        asset = _make_asset(width=500, height=500)
        records = TilePlanner.plan(asset, plan)
        ids = [r.tile_id for r in records]
        assert len(ids) == len(set(ids))

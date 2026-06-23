"""Tests for tile_grid.py — pure tile math, no Qt dependencies.

Verifies:
- tiles_for_rect splits an image-coordinate rectangle into deterministic tile keys
- Tile keys include image_id, level, x, y
- Clipped source rects are correct
- Edge tiles partial at image boundaries
- Tile size is configurable
"""

from __future__ import annotations

import math
import pathlib
import sys
import types
import unittest
from importlib import util as importlib_util

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
VIEWPORT_DIR = REPO_ROOT / "anylabeling" / "views" / "labeling" / "viewport"


def _ensure_package(name, path=None):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [] if path is None else [str(path)]
    return module


def _load_module(name, path):
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None) == str(path):
        return existing
    spec = importlib_util.spec_from_file_location(name, path)
    module = importlib_util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_tile_grid():
    _ensure_package("anylabeling")
    _ensure_package("anylabeling.views")
    _ensure_package("anylabeling.views.labeling")
    _ensure_package("anylabeling.views.labeling.viewport", VIEWPORT_DIR)

    rect_module = _load_module(
        "anylabeling.views.labeling.viewport.rect",
        VIEWPORT_DIR / "rect.py",
    )

    tile_grid_module = _load_module(
        "anylabeling.views.labeling.viewport.tile_grid",
        VIEWPORT_DIR / "tile_grid.py",
    )
    return tile_grid_module, rect_module.RectF


tile_grid_module, RectF = _load_tile_grid()
# Classes may not exist yet (RED phase)
TileKey = getattr(tile_grid_module, "TileKey", None)
tiles_for_rect = getattr(tile_grid_module, "tiles_for_rect", None)


def _require_impl():
    if TileKey is None or tiles_for_rect is None:
        raise unittest.SkipTest("tile_grid not yet implemented")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TileKeyConstructionTest(unittest.TestCase):
    def test_tile_key_creation_and_fields(self):
        _require_impl()
        key = TileKey(image_id="img_001", level=0, x=3, y=7)
        self.assertEqual(key.image_id, "img_001")
        self.assertEqual(key.level, 0)
        self.assertEqual(key.x, 3)
        self.assertEqual(key.y, 7)

    def test_tile_key_equality(self):
        _require_impl()
        a = TileKey(image_id="a", level=0, x=1, y=2)
        b = TileKey(image_id="a", level=0, x=1, y=2)
        c = TileKey(image_id="a", level=0, x=2, y=2)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_tile_key_hashable(self):
        _require_impl()
        key = TileKey(image_id="img", level=0, x=0, y=0)
        d = {key: "value"}
        self.assertEqual(d[key], "value")


class TilesForRectExactTilesTest(unittest.TestCase):
    """Tests where the requested rect aligns exactly with tile boundaries."""

    def test_single_full_tile(self):
        _require_impl()
        # A 512×512 rect at origin → exactly 1 tile
        tiles = tiles_for_rect(
            image_id="img",
            level=0,
            image_rect=RectF(0, 0, 512, 512),
            tile_size=512,
        )
        self.assertEqual(len(tiles), 1)
        key, src = tiles[0]
        self.assertEqual(key, TileKey(image_id="img", level=0, x=0, y=0))
        self.assertEqual(src, RectF(0, 0, 512, 512))

    def test_four_full_tiles_2x2(self):
        _require_impl()
        tiles = tiles_for_rect(
            image_id="img",
            level=0,
            image_rect=RectF(0, 0, 1024, 1024),
            tile_size=512,
        )
        self.assertEqual(len(tiles), 4)
        keys = {t[0] for t in tiles}
        expected = {
            TileKey(image_id="img", level=0, x=0, y=0),
            TileKey(image_id="img", level=0, x=1, y=0),
            TileKey(image_id="img", level=0, x=0, y=1),
            TileKey(image_id="img", level=0, x=1, y=1),
        }
        self.assertEqual(keys, expected)

    def test_rect_offset_not_at_origin(self):
        _require_impl()
        # Rect starting at tile (1,1) through tile (2,2) exclusive
        tiles = tiles_for_rect(
            image_id="img",
            level=0,
            image_rect=RectF(512, 512, 1536, 1536),
            tile_size=512,
        )
        keys = {t[0] for t in tiles}
        expected = {
            TileKey(image_id="img", level=0, x=1, y=1),
            TileKey(image_id="img", level=0, x=2, y=1),
            TileKey(image_id="img", level=0, x=1, y=2),
            TileKey(image_id="img", level=0, x=2, y=2),
        }
        self.assertEqual(keys, expected)


class TilesForRectPartialTilesTest(unittest.TestCase):
    """Tests where rect edges don't align with tile boundaries."""

    def test_partial_tile_clips_source_rect(self):
        _require_impl()
        # Request 200×200 at (100, 100) which straddles tile boundaries
        tiles = tiles_for_rect(
            image_id="img",
            level=0,
            image_rect=RectF(100, 100, 300, 300),
            tile_size=512,
        )
        # Should be 1 tile (0,0) but clipped to (100,100)-(300,300)
        self.assertEqual(len(tiles), 1)
        key, src = tiles[0]
        self.assertEqual(key, TileKey(image_id="img", level=0, x=0, y=0))
        self.assertEqual(src, RectF(100, 100, 300, 300))

    def test_crossing_tile_boundary_generates_multiple_tiles(self):
        _require_impl()
        # A rect that crosses tile (0,0) into tile (1,0)
        tiles = tiles_for_rect(
            image_id="img",
            level=0,
            image_rect=RectF(400, 100, 600, 300),
            tile_size=512,
        )
        self.assertEqual(len(tiles), 2)
        keys = {t[0] for t in tiles}
        self.assertIn(TileKey(image_id="img", level=0, x=0, y=0), keys)
        self.assertIn(TileKey(image_id="img", level=0, x=1, y=0), keys)

        # Verify clipped source rects
        for key, src in tiles:
            if key.x == 0:
                self.assertEqual(src, RectF(400, 100, 512, 300))
            elif key.x == 1:
                self.assertEqual(src, RectF(512, 100, 600, 300))

    def test_crossing_both_axes(self):
        _require_impl()
        # A rect crossing the tile corner at (512, 512)
        tiles = tiles_for_rect(
            image_id="img",
            level=0,
            image_rect=RectF(400, 400, 600, 600),
            tile_size=512,
        )
        self.assertEqual(len(tiles), 4)
        expected_srcs = {
            TileKey(image_id="img", level=0, x=0, y=0): RectF(400, 400, 512, 512),
            TileKey(image_id="img", level=0, x=1, y=0): RectF(512, 400, 600, 512),
            TileKey(image_id="img", level=0, x=0, y=1): RectF(400, 512, 512, 600),
            TileKey(image_id="img", level=0, x=1, y=1): RectF(512, 512, 600, 600),
        }
        for key, src in tiles:
            self.assertEqual(src, expected_srcs[key],
                             f"Wrong src for {key}: expected {expected_srcs[key]}, got {src}")


class TilesForRectEdgeTilesTest(unittest.TestCase):
    """Tests at image boundaries where tiles are partially outside."""

    def test_first_tile_at_origin(self):
        _require_impl()
        tiles = tiles_for_rect(
            image_id="img",
            level=0,
            image_rect=RectF(0, 0, 100, 100),
            tile_size=512,
        )
        self.assertEqual(len(tiles), 1)
        key, src = tiles[0]
        self.assertEqual(key, TileKey(image_id="img", level=0, x=0, y=0))
        self.assertEqual(src, RectF(0, 0, 100, 100))

    def test_tiles_not_bounded_by_image_size(self):
        """tiles_for_rect returns tiles for the requested rect regardless
        of whether they exceed the image dimensions.  Clipping is the
        caller's responsibility (via ImageProvider.prepare_region)."""
        _require_impl()
        # Rect far outside any reasonable image — still returns tiles.
        # 5000/512=9.76 → tiles 9-11 (3×3 = 9 tiles for 1000×1000 px rect)
        tiles = tiles_for_rect(
            image_id="img",
            level=0,
            image_rect=RectF(5000, 5000, 6000, 6000),
            tile_size=512,
        )
        self.assertEqual(len(tiles), 9)
        keys = {t[0] for t in tiles}
        self.assertIn(TileKey(image_id="img", level=0, x=9, y=9), keys)


class TilesForRectLevelTest(unittest.TestCase):
    """Tests that level is propagated to tile keys."""

    def test_level_propagated_to_keys(self):
        _require_impl()
        tiles = tiles_for_rect(
            image_id="img",
            level=2,
            image_rect=RectF(0, 0, 512, 512),
            tile_size=512,
        )
        self.assertEqual(len(tiles), 1)
        key, _ = tiles[0]
        self.assertEqual(key.level, 2)

    def test_level_does_not_affect_source_rects(self):
        """Source rects are always in level-0 coordinates."""
        _require_impl()
        tiles_l0 = tiles_for_rect(
            image_id="img", level=0,
            image_rect=RectF(100, 200, 300, 400), tile_size=512,
        )
        tiles_l1 = tiles_for_rect(
            image_id="img", level=1,
            image_rect=RectF(100, 200, 300, 400), tile_size=512,
        )
        # Same source rects regardless of level
        self.assertEqual(tiles_l0[0][1], tiles_l1[0][1])


class TilesForRectConfigurableTileSizeTest(unittest.TestCase):
    def test_tile_size_256(self):
        _require_impl()
        tiles = tiles_for_rect(
            image_id="img", level=0,
            image_rect=RectF(0, 0, 512, 512), tile_size=256,
        )
        self.assertEqual(len(tiles), 4)
        keys = {t[0] for t in tiles}
        self.assertIn(TileKey(image_id="img", level=0, x=0, y=0), keys)
        self.assertIn(TileKey(image_id="img", level=0, x=1, y=1), keys)

    def test_tile_size_1024(self):
        _require_impl()
        tiles = tiles_for_rect(
            image_id="img", level=0,
            image_rect=RectF(0, 0, 2048, 1024), tile_size=1024,
        )
        self.assertEqual(len(tiles), 2)
        keys = {t[0] for t in tiles}
        self.assertIn(TileKey(image_id="img", level=0, x=0, y=0), keys)
        self.assertIn(TileKey(image_id="img", level=0, x=1, y=0), keys)

    def test_default_tile_size_is_512(self):
        """When tile_size is not specified, default to 512."""
        _require_impl()
        tiles = tiles_for_rect(
            image_id="img", level=0,
            image_rect=RectF(0, 0, 512, 512),
        )
        self.assertEqual(len(tiles), 1)
        key, _ = tiles[0]
        self.assertEqual(key, TileKey(image_id="img", level=0, x=0, y=0))


if __name__ == "__main__":
    unittest.main()

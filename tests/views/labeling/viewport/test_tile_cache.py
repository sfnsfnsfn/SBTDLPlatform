"""Tests for tile_cache.py — LRU cache with byte-based eviction.

Verifies:
- Cache stores and retrieves tile data by TileKey
- Size tracking in bytes
- LRU eviction when over max_bytes
- Evicts least recently used entries first
- Does not cache shape data (convention, not enforced)
"""

from __future__ import annotations

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


def _load_tile_types():
    _ensure_package("anylabeling")
    _ensure_package("anylabeling.views")
    _ensure_package("anylabeling.views.labeling")
    _ensure_package("anylabeling.views.labeling.viewport", VIEWPORT_DIR)

    tile_grid_module = _load_module(
        "anylabeling.views.labeling.viewport.tile_grid",
        VIEWPORT_DIR / "tile_grid.py",
    )
    tile_cache_module = _load_module(
        "anylabeling.views.labeling.viewport.tile_cache",
        VIEWPORT_DIR / "tile_cache.py",
    )
    return tile_grid_module, tile_cache_module


tile_grid_module, tile_cache_module = _load_tile_types()
TileKey = getattr(tile_grid_module, "TileKey", None)
TileCache = getattr(tile_cache_module, "TileCache", None)


def _require_impl():
    if TileKey is None or TileCache is None:
        raise unittest.SkipTest("tile_cache not yet implemented")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TileCacheBasicTest(unittest.TestCase):
    def test_put_and_get(self):
        _require_impl()
        cache = TileCache(max_bytes=1024 * 1024)  # 1 MB
        key = TileKey(image_id="img", level=0, x=0, y=0)
        data = b"tile pixel data"

        cache.put(key, data)
        self.assertEqual(cache.get(key), data)

    def test_get_missing_returns_none(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        key = TileKey(image_id="img", level=0, x=0, y=0)
        self.assertIsNone(cache.get(key))

    def test_contains(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        key = TileKey(image_id="img", level=0, x=0, y=0)
        cache.put(key, b"data")
        self.assertTrue(cache.contains(key))
        self.assertFalse(cache.contains(TileKey(image_id="img", level=0, x=1, y=0)))

    def test_put_overwrites_existing(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        key = TileKey(image_id="img", level=0, x=0, y=0)
        cache.put(key, b"old")
        cache.put(key, b"new")
        self.assertEqual(cache.get(key), b"new")


class TileCacheSizeTrackingTest(unittest.TestCase):
    def test_total_bytes_starts_at_zero(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        self.assertEqual(cache.total_bytes, 0)

    def test_total_bytes_increases_with_put(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        cache.put(TileKey(image_id="img", level=0, x=0, y=0), b"1234567890")  # 10 bytes
        self.assertEqual(cache.total_bytes, 10)

    def test_total_bytes_sums_multiple_entries(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        cache.put(TileKey(image_id="img", level=0, x=0, y=0), b"12345")    # 5
        cache.put(TileKey(image_id="img", level=0, x=1, y=0), b"1234567890")  # 10
        self.assertEqual(cache.total_bytes, 15)

    def test_overwrite_updates_size_correctly(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        key = TileKey(image_id="img", level=0, x=0, y=0)
        cache.put(key, b"1234567890")   # 10 bytes
        cache.put(key, b"12345")        # overwrite with 5 bytes
        self.assertEqual(cache.total_bytes, 5)

    def test_len_returns_entry_count(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        self.assertEqual(len(cache), 0)
        cache.put(TileKey(image_id="img", level=0, x=0, y=0), b"a")
        cache.put(TileKey(image_id="img", level=0, x=1, y=0), b"b")
        self.assertEqual(len(cache), 2)


class TileCacheEvictionTest(unittest.TestCase):
    def test_no_eviction_when_under_limit(self):
        _require_impl()
        cache = TileCache(max_bytes=1000)
        cache.put(TileKey(image_id="img", level=0, x=0, y=0), b"a" * 500)
        cache.put(TileKey(image_id="img", level=0, x=1, y=0), b"b" * 400)
        # 500 + 400 = 900 < 1000, no eviction
        self.assertEqual(cache.total_bytes, 900)
        self.assertEqual(len(cache), 2)

    def test_evicts_when_over_limit(self):
        _require_impl()
        cache = TileCache(max_bytes=100)
        cache.put(TileKey(image_id="img", level=0, x=0, y=0), b"a" * 60)  # 60 bytes
        cache.put(TileKey(image_id="img", level=0, x=1, y=0), b"b" * 30)  # 30 bytes
        # total = 90, still under
        self.assertEqual(len(cache), 2)

        cache.put(TileKey(image_id="img", level=0, x=2, y=0), b"c" * 50)  # 50 bytes
        # Would be 90 + 50 = 140 > 100, evict LRU
        # After eviction + new put, total should be <= 100
        self.assertLessEqual(cache.total_bytes, 100)
        # The first entry (60 bytes, least recently used) should be gone
        self.assertFalse(cache.contains(TileKey(image_id="img", level=0, x=0, y=0)))

    def test_evicts_lru_not_most_recent(self):
        _require_impl()
        cache = TileCache(max_bytes=100)
        key_a = TileKey(image_id="img", level=0, x=0, y=0)
        key_b = TileKey(image_id="img", level=0, x=1, y=0)
        key_c = TileKey(image_id="img", level=0, x=2, y=0)

        cache.put(key_a, b"a" * 40)
        cache.put(key_b, b"b" * 40)
        # Access key_a to make key_b the LRU
        cache.get(key_a)
        cache.put(key_c, b"c" * 40)
        # total = 120 > 100, evict key_b (LRU), not key_a
        self.assertFalse(cache.contains(key_b))
        self.assertTrue(cache.contains(key_a))
        self.assertTrue(cache.contains(key_c))

    def test_eviction_may_remove_multiple_if_one_not_enough(self):
        _require_impl()
        cache = TileCache(max_bytes=50)
        cache.put(TileKey(image_id="img", level=0, x=0, y=0), b"a" * 30)
        cache.put(TileKey(image_id="img", level=0, x=1, y=0), b"b" * 30)
        # Put 40 bytes → total 30+30+40=100 > 50
        # Evict both old entries to make room
        cache.put(TileKey(image_id="img", level=0, x=2, y=0), b"c" * 40)
        self.assertLessEqual(cache.total_bytes, 50)
        self.assertTrue(cache.contains(TileKey(image_id="img", level=0, x=2, y=0)))

    def test_entry_larger_than_max_bytes_is_still_stored(self):
        """An entry larger than max_bytes is stored (cache drains to 0 first)."""
        _require_impl()
        cache = TileCache(max_bytes=50)
        cache.put(TileKey(image_id="img", level=0, x=0, y=0), b"x" * 10)
        # Put a giant entry
        cache.put(TileKey(image_id="img", level=0, x=1, y=0), b"y" * 100)
        # The giant entry replaces everything
        self.assertEqual(cache.total_bytes, 100)
        self.assertEqual(len(cache), 1)


class TileCacheClearTest(unittest.TestCase):
    def test_clear_removes_all_entries(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        cache.put(TileKey(image_id="img", level=0, x=0, y=0), b"a" * 100)
        cache.put(TileKey(image_id="img", level=0, x=1, y=0), b"b" * 200)
        cache.clear()
        self.assertEqual(len(cache), 0)
        self.assertEqual(cache.total_bytes, 0)

    def test_clear_when_switching_images(self):
        """Simulate switching images: clear cache, new image_id."""
        _require_impl()
        cache = TileCache(max_bytes=1024)
        cache.put(TileKey(image_id="img1", level=0, x=0, y=0), b"old")
        cache.clear()
        cache.put(TileKey(image_id="img2", level=0, x=0, y=0), b"new")
        self.assertEqual(cache.get(TileKey(image_id="img2", level=0, x=0, y=0)), b"new")


class TileCacheImageSeparationTest(unittest.TestCase):
    """Tiles from different images or levels are independent keys."""

    def test_different_images_are_independent(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        key_a = TileKey(image_id="img_a", level=0, x=0, y=0)
        key_b = TileKey(image_id="img_b", level=0, x=0, y=0)
        cache.put(key_a, b"data_a")
        cache.put(key_b, b"data_b")

        self.assertEqual(cache.get(key_a), b"data_a")
        self.assertEqual(cache.get(key_b), b"data_b")
        self.assertNotEqual(cache.get(key_a), cache.get(key_b))

    def test_different_levels_are_independent(self):
        _require_impl()
        cache = TileCache(max_bytes=1024)
        key_l0 = TileKey(image_id="img", level=0, x=0, y=0)
        key_l1 = TileKey(image_id="img", level=1, x=0, y=0)
        cache.put(key_l0, b"level0")
        cache.put(key_l1, b"level1")

        self.assertEqual(cache.get(key_l0), b"level0")
        self.assertEqual(cache.get(key_l1), b"level1")


if __name__ == "__main__":
    unittest.main()

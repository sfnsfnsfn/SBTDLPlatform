"""Tests for Phase 4.5: label_widget provider integration.

Verifies that ``LabelingWidget._try_create_image_provider()`` returns
a QImageRegionProvider for large images and None for small images.

Imports are done lazily inside test methods to avoid pulling in the
full Qt dependency chain at module level (which conflicts with other
test files' PyQt6 stubs).
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

import cv2
import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


def _require_label_widget():
    """Import label_widget; skip test if not available (stub mode conflict).

    Import is done lazily per-test to avoid triggering real PyQt6/Cavas
    imports at module collection time, which would conflict with other
    test files' PyQt6 stubs.
    """
    try:
        from anylabeling.views.labeling.label_widget import (  # noqa: F401
            PROVIDER_THRESHOLD_MEGAPIXELS as _THR,
            PROVIDER_TILE_CACHE_BYTES as _CACHE,
            LabelingWidget as _LW,
        )
        return _THR, _CACHE, _LW
    except (ImportError, ModuleNotFoundError):
        raise unittest.SkipTest("label_widget not importable (stub mode)")


def _create_image(width, height):
    """Create a BGR numpy image and save to a temp PNG, return the path."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    # Add a simple pattern
    img[::32, :] = 128
    img[:, ::32] = 128
    return img


class TryCreateImageProviderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.tmpdir_path = pathlib.Path(cls.tmpdir.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _save(self, name, width, height):
        img = _create_image(width, height)
        path = str(self.tmpdir_path / name)
        cv2.imwrite(path, img)
        return path

    def test_small_image_returns_none(self):
        """800×600 = 0.48 Mpx < threshold → None (pixmap path)."""
        _, _, LabelingWidget = _require_label_widget()
        path = self._save("small.png", 800, 600)
        result = LabelingWidget._try_create_image_provider(path)
        self.assertIsNone(result)

    def test_large_image_returns_provider(self):
        """4100×4100 = 16.81 Mpx > 16 Mpx threshold → QImageRegionProvider."""
        try:
            from anylabeling.views.labeling.viewport import QImageRegionProvider
        except ImportError:
            self.skipTest("QImageRegionProvider not importable (stub mode)")

        threshold, _, LabelingWidget = _require_label_widget()
        # Create an image just over threshold in one dimension.
        # Avoid square sqrt(thresh)² which produces huge files for high thresholds.
        w = 2000
        h = int((threshold * 1_000_000) / w) + 1  # definitely over threshold
        path = self._save("large.png", w, h)
        result = LabelingWidget._try_create_image_provider(path)
        self.assertIsInstance(result, QImageRegionProvider)
        self.assertEqual(result.image_width, w)
        self.assertEqual(result.image_height, h)

    def test_below_threshold_returns_none(self):
        """3999×3999 ≈ 16 Mpx < 100 Mpx → None."""
        _, _, LabelingWidget = _require_label_widget()
        path = self._save("below_threshold.png", 3999, 3999)
        result = LabelingWidget._try_create_image_provider(path)
        self.assertIsNone(result)

    def test_nonexistent_file_returns_none(self):
        _, _, LabelingWidget = _require_label_widget()
        result = LabelingWidget._try_create_image_provider(
            "/nonexistent/path/image.png"
        )
        self.assertIsNone(result)

    def test_none_filename_returns_none(self):
        _, _, LabelingWidget = _require_label_widget()
        result = LabelingWidget._try_create_image_provider(None)
        self.assertIsNone(result)

    def test_empty_filename_returns_none(self):
        _, _, LabelingWidget = _require_label_widget()
        result = LabelingWidget._try_create_image_provider("")
        self.assertIsNone(result)


class ProviderThresholdConstantTest(unittest.TestCase):
    def test_threshold_is_positive(self):
        threshold, _, _ = _require_label_widget()
        self.assertGreater(threshold, 0)

    def test_threshold_constant_is_integer(self):
        threshold, _, _ = _require_label_widget()
        self.assertIsInstance(threshold, int)

    def test_tile_cache_bytes_constant_is_positive(self):
        _, cache_bytes, _ = _require_label_widget()
        self.assertGreater(cache_bytes, 0)


if __name__ == "__main__":
    unittest.main()

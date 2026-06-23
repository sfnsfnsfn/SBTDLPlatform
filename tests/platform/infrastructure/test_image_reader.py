"""Tests for ImageReader — unified image file reading.

Covers: JPG/PNG/TIFF, multi-page TIFF, 8/16/float32 bit depth,
RGB/BGR/AS_IS color output, ROI reading, metadata, error handling.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage


# ---------------------------------------------------------------------------
# Test fixtures — synthetic images
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tmp_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("image_reader")


@pytest.fixture(scope="module")
def rgb_jpg(tmp_dir) -> Path:
    """8-bit RGB JPEG, 64×32 pixels with color blocks."""
    path = tmp_dir / "rgb.jpg"
    arr = np.zeros((32, 64, 3), dtype=np.uint8)
    arr[0:16, 0:32] = [255, 0, 0]
    arr[0:16, 32:64] = [0, 255, 0]
    arr[16:32, 0:32] = [0, 0, 255]
    arr[16:32, 32:64] = [128, 128, 128]
    PILImage.fromarray(arr).save(str(path))
    return path


@pytest.fixture(scope="module")
def gray_png(tmp_dir) -> Path:
    """8-bit grayscale PNG, 32×32 pixels."""
    path = tmp_dir / "gray.png"
    arr = np.linspace(0, 255, 32 * 32, dtype=np.uint8).reshape(32, 32)
    PILImage.fromarray(arr, mode="L").save(str(path))
    return path


@pytest.fixture(scope="module")
def rgba_png(tmp_dir) -> Path:
    """8-bit RGBA PNG, 16×16, semi-transparent."""
    path = tmp_dir / "rgba.png"
    arr = np.zeros((16, 16, 4), dtype=np.uint8)
    arr[:, :] = [255, 0, 0, 128]
    PILImage.fromarray(arr, mode="RGBA").save(str(path))
    return path


@pytest.fixture(scope="module")
def single_tiff(tmp_dir) -> Path:
    """Single-page 8-bit RGB TIFF."""
    path = tmp_dir / "single.tiff"
    arr = np.random.randint(0, 255, (20, 30, 3), dtype=np.uint8)
    PILImage.fromarray(arr).save(str(path))
    return path


@pytest.fixture(scope="module")
def multi_page_tiff(tmp_dir) -> Path:
    """3-page 8-bit RGB TIFF. Page 0=red, 1=green, 2=blue."""
    path = tmp_dir / "multi.tiff"
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    pages = []
    for c in colors:
        arr = np.full((10, 10, 3), c, dtype=np.uint8)
        pages.append(PILImage.fromarray(arr))
    pages[0].save(str(path), save_all=True, append_images=pages[1:])
    return path


@pytest.fixture(scope="module")
def tiff_16bit(tmp_dir) -> Path:
    """Single-page 16-bit grayscale TIFF."""
    path = tmp_dir / "16bit.tiff"
    arr = np.linspace(0, 65535, 32 * 32, dtype=np.uint16).reshape(32, 32)
    PILImage.fromarray(arr, mode="I;16").save(str(path))
    return path


@pytest.fixture(scope="module")
def tiff_float32(tmp_dir) -> Path:
    """Single-page float32 grayscale TIFF."""
    path = tmp_dir / "float32.tiff"
    arr = np.random.rand(16, 16).astype(np.float32)
    PILImage.fromarray(arr, mode="F").save(str(path))
    return path


@pytest.fixture(scope="module")
def corrupt_jpg(tmp_dir) -> Path:
    """Not a valid image."""
    path = tmp_dir / "corrupt.jpg"
    path.write_bytes(b"this is not a jpeg file")
    return path


@pytest.fixture(scope="module")
def missing_file(tmp_dir) -> Path:
    """Does not exist."""
    return tmp_dir / "does_not_exist.png"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _import_reader():
    from anylabeling.platform.infrastructure.image_reader import ImageReader
    return ImageReader


# ---------------------------------------------------------------------------
# Tests: read() — basic formats
# ---------------------------------------------------------------------------


class TestReadBasicFormats:

    def test_read_rgb_jpg(self, rgb_jpg):
        r = _import_reader()
        arr = r.read(str(rgb_jpg))
        assert isinstance(arr, np.ndarray)
        assert arr.dtype == np.uint8
        assert arr.shape == (32, 64, 3)
        assert arr[0, 0, 0] > 200 and arr[0, 0, 1] < 50  # red block

    def test_read_gray_png(self, gray_png):
        r = _import_reader()
        arr = r.read(str(gray_png))
        assert arr.shape[:2] == (32, 32)

    def test_read_rgba_returns_rgb(self, rgba_png):
        r = _import_reader()
        arr = r.read(str(rgba_png))
        assert arr.shape[2] == 3  # alpha stripped

    def test_read_single_tiff_rgb(self, single_tiff):
        r = _import_reader()
        arr = r.read(str(single_tiff))
        assert arr.shape == (20, 30, 3)


class TestColorOutput:

    def test_bgr_vs_rgb(self, rgb_jpg):
        r = _import_reader()
        rgb = r.read(str(rgb_jpg), output_color="RGB")
        bgr = r.read(str(rgb_jpg), output_color="BGR")
        assert np.array_equal(rgb[:, :, 0], bgr[:, :, 2])
        assert np.array_equal(rgb[:, :, 2], bgr[:, :, 0])

    def test_as_is_keeps_shape(self, gray_png):
        r = _import_reader()
        arr = r.read(str(gray_png), output_color="AS_IS")
        assert arr.ndim == 2  # grayscale stays 2D

    def test_default_equals_rgb(self, rgb_jpg):
        r = _import_reader()
        a1 = r.read(str(rgb_jpg))
        a2 = r.read(str(rgb_jpg), output_color="RGB")
        assert np.array_equal(a1, a2)

    def test_invalid_color_raises(self, rgb_jpg):
        r = _import_reader()
        with pytest.raises(ValueError, match="output_color"):
            r.read(str(rgb_jpg), output_color="XYZ")


class TestMultiPageTIFF:

    def test_read_page_0_red(self, multi_page_tiff):
        r = _import_reader()
        arr = r.read(str(multi_page_tiff), page=0)
        assert arr[0, 0, 0] > 200 and arr[0, 0, 1] < 50

    def test_read_page_1_green(self, multi_page_tiff):
        r = _import_reader()
        arr = r.read(str(multi_page_tiff), page=1)
        assert arr[0, 0, 1] > 200

    def test_read_page_2_blue(self, multi_page_tiff):
        r = _import_reader()
        arr = r.read(str(multi_page_tiff), page=2)
        assert arr[0, 0, 2] > 200

    def test_pages_count(self, multi_page_tiff, single_tiff, rgb_jpg):
        r = _import_reader()
        assert r.pages(str(multi_page_tiff)) == 3
        assert r.pages(str(single_tiff)) == 1
        assert r.pages(str(rgb_jpg)) == 1

    def test_read_pages_all(self, multi_page_tiff):
        r = _import_reader()
        pages = r.read_pages(str(multi_page_tiff))
        assert len(pages) == 3
        assert all(p.shape == (10, 10, 3) for p in pages)

    def test_pages_matches_seekable_count(self, multi_page_tiff):
        r = _import_reader()
        n = r.pages(str(multi_page_tiff))
        assert n == 3
        # All pages should be readable
        for i in range(n):
            arr = r.read(str(multi_page_tiff), page=i)
            assert arr.shape == (10, 10, 3)


class TestBitDepth:

    def test_16bit_tiff(self, tiff_16bit):
        r = _import_reader()
        arr = r.read(str(tiff_16bit))
        assert arr.dtype == np.uint16

    def test_float32_tiff(self, tiff_float32):
        r = _import_reader()
        arr = r.read(str(tiff_float32))
        assert arr.dtype == np.float32

    def test_16bit_as_is_2d(self, tiff_16bit):
        r = _import_reader()
        arr = r.read(str(tiff_16bit), output_color="AS_IS")
        assert arr.ndim == 2
        assert arr.dtype == np.uint16


class TestMetadata:

    def test_metadata_rgb(self, rgb_jpg):
        r = _import_reader()
        meta = r.metadata(str(rgb_jpg))
        assert meta.width == 64
        assert meta.height == 32
        assert meta.channels == 3
        assert meta.bit_depth == 8

    def test_metadata_gray(self, gray_png):
        r = _import_reader()
        meta = r.metadata(str(gray_png))
        assert meta.width == 32
        assert meta.height == 32

    def test_metadata_16bit(self, tiff_16bit):
        r = _import_reader()
        meta = r.metadata(str(tiff_16bit))
        assert meta.bit_depth == 16


class TestReadRegion:

    def test_read_region_center(self, rgb_jpg):
        r = _import_reader()
        roi = r.read_region(str(rgb_jpg), rect_l0=(16, 8, 32, 16), output_size=(32, 16))
        assert roi.shape == (16, 32, 3)

    def test_read_region_equals_read(self, rgb_jpg):
        r = _import_reader()
        roi = r.read_region(str(rgb_jpg), rect_l0=(0, 0, 64, 32), output_size=(64, 32))
        full = r.read(str(rgb_jpg))
        assert np.array_equal(roi, full)

    def test_read_region_downscale(self, rgb_jpg):
        r = _import_reader()
        roi = r.read_region(str(rgb_jpg), rect_l0=(0, 0, 64, 32), output_size=(32, 16))
        assert roi.shape == (16, 32, 3)

    def test_read_region_clips_bounds(self, rgb_jpg):
        r = _import_reader()
        roi = r.read_region(str(rgb_jpg), rect_l0=(50, 25, 30, 20), output_size=(30, 20))
        assert roi.shape[0] > 0 and roi.shape[1] > 0


class TestErrorHandling:

    def test_missing_file(self, missing_file):
        r = _import_reader()
        with pytest.raises(FileNotFoundError):
            r.read(str(missing_file))

    def test_corrupt_file(self, corrupt_jpg):
        r = _import_reader()
        with pytest.raises((OSError, ValueError, RuntimeError)):
            r.read(str(corrupt_jpg))

    def test_metadata_missing(self, missing_file):
        r = _import_reader()
        with pytest.raises(FileNotFoundError):
            r.metadata(str(missing_file))


class TestPathObject:

    def test_str_and_path_equal(self, rgb_jpg):
        r = _import_reader()
        assert np.array_equal(r.read(str(rgb_jpg)), r.read(rgb_jpg))

    def test_metadata_str_and_path_equal(self, rgb_jpg):
        r = _import_reader()
        assert r.metadata(str(rgb_jpg)) == r.metadata(rgb_jpg)

"""Tests for the image source abstraction layer."""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest
from PIL import Image as PILImage

from anylabeling.platform.infrastructure.image_sources.base import (
    ImageMetadata,
    LargeImageSource,
)
from anylabeling.platform.infrastructure.image_sources.memory_image_source import (
    MemoryImageSource,
)
from anylabeling.platform.infrastructure.image_sources.tiff_image_source import (
    TiffImageSource,
)


# =============================================================================
# ImageMetadata tests
# =============================================================================


class TestImageMetadata:
    """Verify ImageMetadata dataclass behaviour."""

    def test_creation_with_valid_fields(self):
        meta = ImageMetadata(
            width=1024, height=768, channels=3,
            bit_depth=8, supports_roi=True, supports_pyramid=False,
        )
        assert meta.width == 1024
        assert meta.height == 768
        assert meta.channels == 3
        assert meta.bit_depth == 8
        assert meta.supports_roi is True
        assert meta.supports_pyramid is False

    def test_is_frozen_immutable(self):
        meta = ImageMetadata(100, 100, 3, 8, True, False)
        with pytest.raises(Exception):
            meta.width = 200  # type: ignore[misc]

    def test_equality(self):
        a = ImageMetadata(100, 100, 3, 8, True, False)
        b = ImageMetadata(100, 100, 3, 8, True, False)
        c = ImageMetadata(200, 100, 3, 8, True, False)
        assert a == b
        assert a != c

    def test_isinstance_check_on_protocol(self):
        """LargeImageSource is a runtime-checkable Protocol."""
        meta = ImageMetadata(100, 100, 3, 8, True, False)
        # ImageMetadata does NOT implement the protocol
        assert not isinstance(meta, LargeImageSource)


# =============================================================================
# MemoryImageSource tests
# =============================================================================


class TestMemoryImageSource:
    """Verify in-memory image source."""

    # --- metadata ------------------------------------------------------------

    def test_metadata_rgb(self):
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        src = MemoryImageSource(data)
        meta = src.metadata()
        assert meta.width == 200
        assert meta.height == 100
        assert meta.channels == 3
        assert meta.bit_depth == 8
        assert meta.supports_roi is True
        assert meta.supports_pyramid is False

    def test_metadata_grayscale(self):
        data = np.zeros((50, 50), dtype=np.uint8)
        src = MemoryImageSource(data)
        meta = src.metadata()
        assert meta.width == 50
        assert meta.height == 50
        assert meta.channels == 1

    def test_metadata_rgba(self):
        data = np.zeros((10, 10, 4), dtype=np.uint8)
        src = MemoryImageSource(data)
        meta = src.metadata()
        assert meta.channels == 4

    def test_metadata_16bit(self):
        data = np.zeros((10, 10), dtype=np.uint16)
        src = MemoryImageSource(data)
        meta = src.metadata()
        assert meta.bit_depth == 16

    # --- read_region ---------------------------------------------------------

    def test_read_region_identity(self):
        """Reading the whole image at native resolution returns same data."""
        data = np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8)
        src = MemoryImageSource(data)
        result = src.read_region((0, 0, 64, 64), (64, 64))
        assert result.shape == (64, 64, 3)
        assert result.dtype == np.uint8
        np.testing.assert_array_equal(result, data)

    def test_read_region_subset(self):
        data = np.arange(100 * 100 * 3, dtype=np.uint8).reshape((100, 100, 3))
        src = MemoryImageSource(data)
        result = src.read_region((10, 20, 30, 40), (30, 40))
        np.testing.assert_array_equal(result, data[20:60, 10:40])

    def test_read_region_downscale(self):
        data = np.random.randint(0, 256, (128, 128, 3), dtype=np.uint8)
        src = MemoryImageSource(data)
        result = src.read_region((0, 0, 128, 128), (64, 64))
        assert result.shape == (64, 64, 3)
        assert result.dtype == np.uint8

    def test_read_region_upscale(self):
        data = np.random.randint(0, 256, (32, 32, 3), dtype=np.uint8)
        src = MemoryImageSource(data)
        result = src.read_region((0, 0, 32, 32), (64, 64))
        assert result.shape == (64, 64, 3)

    def test_read_region_grayscale_output(self):
        data = np.random.randint(0, 256, (64, 64), dtype=np.uint8)
        src = MemoryImageSource(data)
        result = src.read_region((0, 0, 64, 64), (32, 32))
        assert result.ndim == 3
        assert result.shape[2] == 1  # grayscale → (H,W,1)

    def test_read_region_out_of_bounds_raises(self):
        data = np.zeros((100, 100, 3), dtype=np.uint8)
        src = MemoryImageSource(data)
        with pytest.raises(ValueError):
            src.read_region((90, 90, 20, 20), (20, 20))

    def test_read_region_negative_origin_raises(self):
        data = np.zeros((100, 100, 3), dtype=np.uint8)
        src = MemoryImageSource(data)
        with pytest.raises(ValueError):
            src.read_region((-5, 0, 50, 50), (50, 50))

    def test_read_region_zero_dimensions_raises(self):
        data = np.zeros((100, 100, 3), dtype=np.uint8)
        src = MemoryImageSource(data)
        with pytest.raises(ValueError):
            src.read_region((0, 0, 0, 50), (50, 50))
        with pytest.raises(ValueError):
            src.read_region((0, 0, 50, 0), (50, 50))

    # --- read_pixel ----------------------------------------------------------

    def test_read_pixel_rgb(self):
        data = np.zeros((50, 50, 3), dtype=np.uint8)
        data[10, 20] = [100, 150, 200]
        src = MemoryImageSource(data)
        assert src.read_pixel(20, 10) == (100, 150, 200)

    def test_read_pixel_grayscale(self):
        data = np.zeros((50, 50), dtype=np.uint8)
        data[5, 5] = 77
        src = MemoryImageSource(data)
        assert src.read_pixel(5, 5) == (77,)

    def test_read_pixel_out_of_bounds_raises(self):
        data = np.zeros((50, 50, 3), dtype=np.uint8)
        src = MemoryImageSource(data)
        with pytest.raises(IndexError):
            src.read_pixel(100, 100)

    # --- construction --------------------------------------------------------

    def test_rejects_1d_array(self):
        with pytest.raises(ValueError):
            MemoryImageSource(np.array([1, 2, 3]))

    def test_rejects_4d_array(self):
        with pytest.raises(ValueError):
            MemoryImageSource(np.zeros((1, 1, 1, 1)))

    # --- protocol compliance ------------------------------------------------

    def test_is_large_image_source(self):
        src = MemoryImageSource(np.zeros((10, 10, 3), dtype=np.uint8))
        assert isinstance(src, LargeImageSource)


# =============================================================================
# TiffImageSource tests
# =============================================================================


class TestTiffImageSource:
    """Verify TIFF-backed image source using Pillow."""

    @pytest.fixture
    def rgb_tiff_path(self) -> str:
        """Create a small RGB TIFF file for testing."""
        data = np.random.randint(0, 256, (50, 80, 3), dtype=np.uint8)
        img = PILImage.fromarray(data)
        fd, path = tempfile.mkstemp(suffix=".tiff")
        os.close(fd)
        img.save(path, format="TIFF")
        yield path
        os.unlink(path)

    @pytest.fixture
    def grayscale_tiff_path(self) -> str:
        """Create a small grayscale TIFF file for testing."""
        data = np.random.randint(0, 256, (30, 40), dtype=np.uint8)
        img = PILImage.fromarray(data)
        fd, path = tempfile.mkstemp(suffix=".tiff")
        os.close(fd)
        img.save(path, format="TIFF")
        yield path
        os.unlink(path)

    # --- metadata ------------------------------------------------------------

    def test_metadata_no_full_decode(self, rgb_tiff_path: str):
        src = TiffImageSource(rgb_tiff_path)
        meta = src.metadata()
        assert meta.width == 80
        assert meta.height == 50
        assert meta.channels == 3
        # TiffImageSource declares supports_roi honestly
        assert isinstance(meta.supports_roi, bool)

    def test_metadata_grayscale(self, grayscale_tiff_path: str):
        src = TiffImageSource(grayscale_tiff_path)
        meta = src.metadata()
        assert meta.width == 40
        assert meta.height == 30

    def test_metadata_is_stable(self, rgb_tiff_path: str):
        """Calling metadata() multiple times returns identical results."""
        src = TiffImageSource(rgb_tiff_path)
        meta1 = src.metadata()
        meta2 = src.metadata()
        assert meta1 == meta2

    # --- read_region ---------------------------------------------------------

    def test_read_region_full(self, rgb_tiff_path: str):
        src = TiffImageSource(rgb_tiff_path)
        result = src.read_region((0, 0, 80, 50), (80, 50))
        assert result.shape == (50, 80, 3)
        assert result.dtype == np.uint8

    def test_read_region_subset(self, rgb_tiff_path: str):
        src = TiffImageSource(rgb_tiff_path)
        result = src.read_region((10, 10, 30, 20), (30, 20))
        assert result.shape == (20, 30, 3)

    def test_read_region_downscale(self, rgb_tiff_path: str):
        src = TiffImageSource(rgb_tiff_path)
        result = src.read_region((0, 0, 80, 50), (40, 25))
        assert result.shape == (25, 40, 3)

    def test_read_region_out_of_bounds_raises(self, rgb_tiff_path: str):
        src = TiffImageSource(rgb_tiff_path)
        with pytest.raises(ValueError):
            src.read_region((70, 40, 20, 20), (20, 20))

    # --- read_pixel ----------------------------------------------------------

    def test_read_pixel(self, rgb_tiff_path: str):
        src = TiffImageSource(rgb_tiff_path)
        pixel = src.read_pixel(5, 5)
        assert len(pixel) == 3
        assert all(0 <= v <= 255 for v in pixel)

    def test_read_pixel_grayscale(self, grayscale_tiff_path: str):
        src = TiffImageSource(grayscale_tiff_path)
        pixel = src.read_pixel(5, 5)
        assert len(pixel) == 1

    def test_read_pixel_out_of_bounds_raises(self, rgb_tiff_path: str):
        src = TiffImageSource(rgb_tiff_path)
        with pytest.raises(IndexError):
            src.read_pixel(9999, 9999)

    # --- construction --------------------------------------------------------

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            TiffImageSource("/nonexistent/path/image.tiff")

    # --- protocol compliance ------------------------------------------------

    def test_is_large_image_source(self, rgb_tiff_path: str):
        src = TiffImageSource(rgb_tiff_path)
        assert isinstance(src, LargeImageSource)

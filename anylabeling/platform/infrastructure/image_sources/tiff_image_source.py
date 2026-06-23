"""TIFF image source using Pillow — no UI/framework imports beyond PIL.

First version declares capability honestly: supports_roi=False unless
the underlying codec can prove efficient random access.
"""

from __future__ import annotations

import os
import numpy as np
from PIL import Image

from anylabeling.platform.infrastructure.image_sources.base import (
    ImageMetadata,
    LargeImageSource,
)


class TiffImageSource:
    """Wraps a TIFF file via Pillow as a ``LargeImageSource``.

    ``metadata()`` reads the header only (``Image.open`` in Pillow is lazy).
    ``supports_roi`` defaults to ``False`` — tiled TIFFs with efficient
    tile-level access can be added in a future version.
    """

    def __init__(self, image_path: str) -> None:
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"TIFF file not found: {image_path}")
        self._image_path: str = os.path.abspath(image_path)
        self._pil: Image.Image | None = None
        self._meta: ImageMetadata | None = None
        self._read_header()

    # ------------------------------------------------------------------
    # LargeImageSource protocol
    # ------------------------------------------------------------------

    def metadata(self) -> ImageMetadata:
        if self._meta is None:
            self._read_header()
        assert self._meta is not None
        return self._meta

    def read_region(
        self,
        rect_l0: tuple[int, int, int, int],
        output_size: tuple[int, int],
        level_hint: int | None = None,
    ) -> np.ndarray:
        x0, y0, w, h = rect_l0
        meta = self.metadata()
        if x0 < 0 or y0 < 0 or x0 + w > meta.width or y0 + h > meta.height:
            raise ValueError(
                f"rect_l0 {rect_l0} exceeds image bounds {meta.width}x{meta.height}"
            )
        if w <= 0 or h <= 0:
            raise ValueError(f"rect_l0 dimensions must be positive: {rect_l0}")

        out_w, out_h = output_size
        if out_w <= 0 or out_h <= 0:
            raise ValueError(f"output_size must be positive: {output_size}")

        pil_img = self._get_pil()
        crop = pil_img.crop((x0, y0, x0 + w, y0 + h))

        if (w, h) == (out_w, out_h):
            return np.array(crop, dtype=np.uint8)

        crop = crop.resize((out_w, out_h), Image.Resampling.LANCZOS)
        return np.array(crop, dtype=np.uint8)

    def read_pixel(self, x: int, y: int) -> tuple[int, ...]:
        meta = self.metadata()
        if x < 0 or x >= meta.width or y < 0 or y >= meta.height:
            raise IndexError(
                f"Pixel ({x}, {y}) out of bounds for {meta.width}x{meta.height}"
            )
        pil_img = self._get_pil()
        pixel = pil_img.getpixel((x, y))
        if isinstance(pixel, int):
            return (pixel,)
        return tuple(pixel)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read_header(self) -> None:
        """Read image dimensions and metadata from the TIFF header.

        Pillow's ``Image.open`` is lazy — it does NOT decode the full image.
        """
        pil_img = Image.open(self._image_path)
        self._pil = pil_img  # Keep reference, still lazy

        mode_to_channels = {
            "1": 1, "L": 1, "P": 1, "I": 1, "F": 1,
            "RGB": 3, "RGBA": 4, "CMYK": 4, "YCbCr": 3,
            "LAB": 3, "HSV": 3, "I;16": 1, "I;16B": 1,
        }
        channels = mode_to_channels.get(pil_img.mode, len(pil_img.getbands()))

        # Determine bit depth from mode
        if "16" in pil_img.mode:
            bit_depth = 16
        elif pil_img.mode == "I" or pil_img.mode == "F":
            bit_depth = 32
        else:
            bit_depth = 8

        # Check for tiled TIFF (indicates efficient ROI potential)
        supports_roi = False
        supports_pyramid = False
        if hasattr(pil_img, "tag_v2"):
            try:
                # Tiled TIFF has tag 277 (SamplesPerPixel), 256 (ImageWidth), etc.
                # Tag 322 = TileWidth — presence indicates tiled TIFF
                tile_width = pil_img.tag_v2.get(322)
                if tile_width is not None:
                    supports_roi = True  # Tiled TIFF can read tiles efficiently
            except Exception:
                pass
            try:
                # Check for sub-IFDs (pyramid levels)
                subifds = pil_img.tag_v2.get(330)
                if subifds:
                    supports_pyramid = True
            except Exception:
                pass

        self._meta = ImageMetadata(
            width=pil_img.width,
            height=pil_img.height,
            channels=channels,
            bit_depth=bit_depth,
            supports_roi=supports_roi,
            supports_pyramid=supports_pyramid,
        )

    def _get_pil(self) -> Image.Image:
        """Get or open the Pillow image (lazy, cached after first open)."""
        if self._pil is None:
            self._read_header()
        assert self._pil is not None
        return self._pil


__all__ = ["TiffImageSource"]

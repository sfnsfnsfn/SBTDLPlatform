"""In-memory image source backed by a numpy array — no UI/framework imports."""

from __future__ import annotations

import numpy as np
from PIL import Image

from anylabeling.platform.infrastructure.image_sources.base import (
    ImageMetadata,
    LargeImageSource,
)


class MemoryImageSource:
    """Wraps an in-memory numpy array as a ``LargeImageSource``.

    Always reports ``supports_roi=True``.  Used for normal-sized images
    that fit entirely in memory and for unit testing.
    """

    def __init__(self, data: np.ndarray) -> None:
        if data.ndim not in (2, 3):
            raise ValueError(
                f"Expected 2D (H,W) or 3D (H,W,C) array, got shape {data.shape}"
            )
        self._data: np.ndarray = data

    def metadata(self) -> ImageMetadata:
        h, w = self._data.shape[:2]
        channels = 1 if self._data.ndim == 2 else self._data.shape[2]
        bit_depth = 8 if self._data.dtype == np.uint8 else 16
        return ImageMetadata(
            width=w,
            height=h,
            channels=channels,
            bit_depth=bit_depth,
            supports_roi=True,
            supports_pyramid=False,
        )

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

        is_grayscale = self._data.ndim == 2
        crop = self._data[y0 : y0 + h, x0 : x0 + w]

        if (w, h) == (out_w, out_h):
            if is_grayscale:
                return crop[:, :, np.newaxis].astype(np.uint8)
            return crop.astype(np.uint8)

        # PIL.fromarray only accepts 2D (H,W) for grayscale or 3D (H,W,3/4) for color.
        # (H,W,1) is not a supported mode, so keep grayscale as 2D for PIL.
        pil_img = Image.fromarray(crop)
        pil_img = pil_img.resize((out_w, out_h), Image.Resampling.LANCZOS)
        result = np.array(pil_img, dtype=np.uint8)
        if is_grayscale:
            return result[:, :, np.newaxis]
        return result

    def read_pixel(self, x: int, y: int) -> tuple[int, ...]:
        meta = self.metadata()
        if x < 0 or x >= meta.width or y < 0 or y >= meta.height:
            raise IndexError(
                f"Pixel ({x}, {y}) out of bounds for {meta.width}x{meta.height}"
            )
        values = self._data[y, x]
        if self._data.ndim == 2:
            return (int(values),)
        return tuple(int(v) for v in values)


__all__ = ["MemoryImageSource"]

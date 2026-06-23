"""File-based image source — serves pixels from a local image file via ImageReader."""

from __future__ import annotations

import cv2  # still needed for cv2.resize in read_region
import numpy as np

from anylabeling.platform.infrastructure.image_reader import ImageReader
from anylabeling.platform.infrastructure.image_sources.base import (
    ImageMetadata,
    LargeImageSource,
)


class FileImageSource:
    """Implements :class:`LargeImageSource` backed by a local image file.

    Uses ImageReader (PIL backend) to read the full image into memory on
    construction, then serves region reads from the in-memory array.
    Suitable for images up to ~100 megapixels on a typical workstation.
    """

    def __init__(self, file_path: str) -> None:
        img = ImageReader.read(file_path, output_color="BGR")
        if img.ndim == 2:
            img = img[:, :, np.newaxis]
        self._image: np.ndarray = img

        h, w = img.shape[:2]
        c = img.shape[2] if img.ndim == 3 else 1
        self._meta = ImageMetadata(
            width=w, height=h, channels=c, bit_depth=8,
            supports_roi=True, supports_pyramid=False,
        )

    def metadata(self) -> ImageMetadata:
        return self._meta

    def read_region(
        self,
        rect_l0: tuple[int, int, int, int],
        output_size: tuple[int, int],
        level_hint: int | None = None,
    ) -> np.ndarray:
        x0, y0, rw, rh = rect_l0
        h, w = self._image.shape[:2]
        x0 = max(0, min(x0, w - 1))
        y0 = max(0, min(y0, h - 1))
        rw = max(1, min(rw, w - x0))
        rh = max(1, min(rh, h - y0))
        roi = self._image[y0: y0 + rh, x0: x0 + rw]
        out_w, out_h = output_size
        if (rw, rh) != (out_w, out_h):
            roi = cv2.resize(roi, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        return roi

    def read_pixel(self, x: int, y: int) -> tuple[int, ...]:
        h, w = self._image.shape[:2]
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        values = self._image[y, x]
        if isinstance(values, np.ndarray):
            return tuple(int(v) for v in values)
        return (int(values),)

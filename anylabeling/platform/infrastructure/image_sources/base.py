"""Image source protocol and metadata — pure Python, no UI/framework imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class ImageMetadata:
    """Immutable image metadata obtained without a full decode.

    All dimension fields refer to the level-0 (full-resolution) image.
    """

    width: int
    height: int
    channels: int  # 1 (grayscale), 3 (RGB), 4 (RGBA)
    bit_depth: int  # 8, 16
    supports_roi: bool  # Can read arbitrary regions efficiently?
    supports_pyramid: bool  # Has multi-resolution levels?


@runtime_checkable
class LargeImageSource(Protocol):
    """Protocol for anything that can serve image pixels at level-0 coordinates.

    Implementations may back the data with files, in-memory arrays, or
    remote tile servers.  All coordinates throughout this protocol are in
    **level-0 image pixels**.
    """

    def metadata(self) -> ImageMetadata:
        """Return image metadata WITHOUT triggering a full image decode."""
        ...

    def read_region(
        self,
        rect_l0: tuple[int, int, int, int],  # (x0, y0, width, height)
        output_size: tuple[int, int],          # (width, height) for output
        level_hint: int | None = None,         # Pyramid level hint
    ) -> np.ndarray:
        """Read a rectangular region and return it at *output_size* dimensions.

        Parameters
        ----------
        rect_l0:
            ``(x0, y0, width, height)`` in level-0 image coordinates.
        output_size:
            ``(out_width, out_height)`` — the returned array will have
            exactly these spatial dimensions.
        level_hint:
            Optional pyramid level.  ``None`` means implementation chooses.

        Returns
        -------
        np.ndarray
            Array of shape ``(out_height, out_width, channels)``, dtype ``uint8``.
        """
        ...

    def read_pixel(self, x: int, y: int) -> tuple[int, ...]:
        """Read a single pixel at level-0 coordinates.

        Returns a tuple of channel values, e.g. ``(r, g, b)`` or ``(v,)``.
        """
        ...


__all__ = [
    "ImageMetadata",
    "LargeImageSource",
]

"""Qt-backed image source using QImageReader for any format Qt supports.

NOTE: This module imports PyQt6 — it is an intentionally bounded adapter
that bridges the Qt imaging layer to the platform ``LargeImageSource``
contract.  Domain and tiling modules MUST NOT depend on this module.
"""

from __future__ import annotations

import os
import numpy as np

from anylabeling.platform.infrastructure.image_sources.base import (
    ImageMetadata,
    LargeImageSource,
)


class QtImageSource:
    """Wraps a disk image via QImageReader as a ``LargeImageSource``.

    ``supports_roi`` is set based on QImageReader's reported capabilities.
    ``metadata()`` reads only the header — no full decode.
    """

    def __init__(self, image_path: str) -> None:
        from PyQt6.QtGui import QImageReader

        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        self._image_path: str = os.path.abspath(image_path)
        self._reader_caps: dict = self._probe_reader()

        reader = QImageReader(self._image_path)
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid():
            raise RuntimeError(
                f"QImageReader could not read size from {self._image_path}"
            )
        self._width: int = size.width()
        self._height: int = size.height()

    # ------------------------------------------------------------------
    # LargeImageSource protocol
    # ------------------------------------------------------------------

    def metadata(self) -> ImageMetadata:
        return ImageMetadata(
            width=self._width,
            height=self._height,
            channels=3,  # read_region() always converts to Format_RGB888 → (H,W,3)
            bit_depth=8,
            supports_roi=self._reader_caps.get("supports_clip_rect", False),
            supports_pyramid=False,
        )

    def read_region(
        self,
        rect_l0: tuple[int, int, int, int],
        output_size: tuple[int, int],
        level_hint: int | None = None,
    ) -> np.ndarray:
        """Read a region of the image, rescaling to ``output_size``.

        .. note::

           This method creates a new ``QImageReader`` on every call, which
           incurs a file-open + header-decode + full-decode cycle each time.
           For tiled access patterns with many tiles (e.g. 100+), this means
           100+ independent file open/close and decode operations.

           We cannot safely reuse the ``QImageReader`` instance from
           ``__init__`` because ``read()`` consumes the reader's internal
           state and Qt does not guarantee that calling ``read()`` again on
           the same reader after changing ``ClipRect``/``ScaledSize`` will
           re-decode without side effects (e.g. cached metadata, stream
           position).  For now, re-opening is the safe default.
        """
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QImage, QImageReader

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

        reader = QImageReader(self._image_path)
        reader.setAutoTransform(True)
        reader.setClipRect(QRect(x0, y0, w, h))
        reader.setScaledSize(QRect(0, 0, out_w, out_h).size())

        qimage: QImage = reader.read()
        if qimage.isNull():
            raise RuntimeError(
                f"QImageReader failed for {self._image_path}: {reader.errorString()}"
            )

        # Convert QImage to numpy array (H, W, C) uint8
        qimage = qimage.convertToFormat(QImage.Format.Format_RGB888)
        width = qimage.width()
        height = qimage.height()
        ptr = qimage.constBits()
        ptr.setsize(height * width * 3)
        arr = np.array(ptr, dtype=np.uint8).reshape((height, width, 3))
        return arr.copy()

    def read_pixel(self, x: int, y: int) -> tuple[int, ...]:
        arr = self.read_region((x, y, 1, 1), (1, 1))
        return tuple(int(v) for v in arr[0, 0])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _probe_reader() -> dict:
        """Probe QImageReader capabilities without opening a specific file."""
        from PyQt6.QtGui import QImageIOHandler, QImageReader

        caps: dict = {}
        try:
            caps["supports_clip_rect"] = QImageReader.supportsOption(
                QImageIOHandler.ImageOption.ClipRect
            )
        except Exception:
            caps["supports_clip_rect"] = False
        try:
            caps["supports_size"] = QImageReader.supportsOption(
                QImageIOHandler.ImageOption.Size
            )
        except Exception:
            caps["supports_size"] = False
        return caps


__all__ = ["QtImageSource"]

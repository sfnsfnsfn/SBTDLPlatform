"""ImageReader — unified image file reading, the single entry point for all
image I/O in the project.

Routes to the best backend (PIL → Qt → OpenCV) based on the operation.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from anylabeling.platform.infrastructure.image_sources.base import ImageMetadata

logger = logging.getLogger(__name__)

_VALID_COLORS = frozenset({"RGB", "BGR", "AS_IS"})


class ImageReader:
    """Unified image file reader — the single entry point for all image I/O.

    All methods are static.  Backend selection (automatic):

    - ``metadata()``    → Qt (zero pixel decode) → PIL → OpenCV
    - ``read()``        → PIL (RGB-native) → Qt → OpenCV
    - ``read_region()`` → Qt (ROI without full decode) → PIL crop
    - ``read_pages()``  → PIL only (sole multi-page TIFF backend)
    """

    # ------------------------------------------------------------------
    # Public: pixel reading
    # ------------------------------------------------------------------

    @staticmethod
    def read(
        path: str | Path,
        *,
        output_color: str = "RGB",
        page: int = 0,
    ) -> np.ndarray:
        """Read the full image into a numpy array of shape ``(H, W, C)``.

        Args:
            path: File path.
            output_color: ``"RGB"`` (default), ``"BGR"``, or ``"AS_IS"``.
            page: 0-based page index for multi-page images.

        Returns:
            numpy array.

        Raises:
            FileNotFoundError: *path* does not exist.
            ValueError: Invalid *output_color*.
            IndexError: *page* out of range.
        """
        if output_color not in _VALID_COLORS:
            raise ValueError(
                f"output_color must be one of {sorted(_VALID_COLORS)}, "
                f"got {output_color!r}"
            )
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Image file not found: {path}")

        # Try PIL first (RGB-native, best format support)
        try:
            arr = ImageReader._read_pil(str(path), page=page)
        except Exception:
            # Fallback: Qt → OpenCV
            try:
                arr = ImageReader._read_qt(str(path))
            except Exception:
                arr = ImageReader._read_cv2(str(path))

        return ImageReader._apply_color(arr, output_color)

    @staticmethod
    def read_region(
        path: str | Path,
        rect_l0: tuple[int, int, int, int],
        output_size: tuple[int, int],
    ) -> np.ndarray:
        """Read a rectangular ROI without decoding the full image.

        Args:
            path: File path.
            rect_l0: ``(x0, y0, width, height)`` in level-0 image coords.
            output_size: ``(out_w, out_h)`` for the returned array.

        Returns:
            numpy array of shape ``(out_h, out_w, 3)``.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Image file not found: {path}")

        x0, y0, rw, rh = rect_l0
        out_w, out_h = output_size

        # Try Qt first (ROI without full decode)
        try:
            _qt_core = __import__("PyQt6.QtCore", fromlist=["QRect", "Qt"])
            _qt_gui = __import__("PyQt6.QtGui", fromlist=["QImage", "QImageReader"])
            QRect = _qt_core.QRect
            QImage = _qt_gui.QImage
            QImageReader = _qt_gui.QImageReader
            Qt = _qt_core.Qt

            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            reader.setClipRect(QRect(x0, y0, rw, rh))
            qimg = reader.read()
            if qimg.isNull():
                raise OSError("QImageReader region decode failed")
            if (rw, rh) != (out_w, out_h):
                qimg = qimg.scaled(
                    out_w, out_h,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            qimg = qimg.convertToFormat(QImage.Format.Format_RGB888)
            w, h = qimg.width(), qimg.height()
            ptr = qimg.constBits()
            arr = np.ndarray(
                (h, w, 3), dtype=np.uint8,
                buffer=memoryview(ptr),  # type: ignore[arg-type]
            ).copy()
            return arr
        except Exception:
            pass

        # Fallback: read full image and crop
        full = ImageReader.read(str(path))
        h, w = full.shape[:2]
        x0c = max(0, min(x0, w - 1))
        y0c = max(0, min(y0, h - 1))
        rwc = max(1, min(rw, w - x0c))
        rhc = max(1, min(rh, h - y0c))
        crop = full[y0c:y0c + rhc, x0c:x0c + rwc]
        if (rwc, rhc) != (out_w, out_h):
            import cv2
            crop = cv2.resize(crop, (out_w, out_h))
        return crop

    @staticmethod
    def read_pages(path: str | Path) -> list[np.ndarray]:
        """Read all pages of a multi-page image (e.g. TIFF stack)."""
        n = ImageReader.pages(str(path))
        return [ImageReader.read(str(path), page=i) for i in range(n)]

    # ------------------------------------------------------------------
    # Public: metadata
    # ------------------------------------------------------------------

    @staticmethod
    def metadata(path: str | Path) -> ImageMetadata:
        """Return image metadata WITHOUT pixel decoding.

        Qt first (zero decode) → PIL → OpenCV last resort.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Image file not found: {path}")

        try:
            return ImageReader._metadata_qt(str(path))
        except Exception:
            try:
                return ImageReader._metadata_pil(str(path))
            except Exception:
                return ImageReader._metadata_cv2(str(path))

    @staticmethod
    def pages(path: str | Path) -> int:
        """Return number of pages in a multi-page image."""
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Image file not found: {path}")
        try:
            from PIL import Image as PILImage
            img = PILImage.open(str(path))
            count = 1
            try:
                while True:
                    img.seek(count)
                    count += 1
            except EOFError:
                pass
            img.close()
            return count
        except Exception:
            return 1

    # ------------------------------------------------------------------
    # Internal: backend pixel readers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_pil(filepath: str, page: int = 0) -> np.ndarray:
        """Read via PIL — RGB-native, best format support."""
        from PIL import Image as PILImage

        img = PILImage.open(filepath)
        if page > 0:
            try:
                img.seek(page)
            except EOFError:
                img.close()
                raise IndexError(
                    f"Page {page} out of range for {filepath}"
                )
        arr = np.asarray(img)
        img.close()
        return arr

    @staticmethod
    def _read_qt(filepath: str) -> np.ndarray:
        """Read via QImage — full decode."""
        _qt_gui = __import__("PyQt6.QtGui", fromlist=["QImage", "QImageReader"])
        QImage = _qt_gui.QImage
        QImageReader = _qt_gui.QImageReader

        reader = QImageReader(filepath)
        reader.setAutoTransform(True)
        qimg = reader.read()
        if qimg.isNull():
            raise OSError(f"QImageReader failed to decode: {filepath}")
        qimg = qimg.convertToFormat(QImage.Format.Format_RGB888)
        w, h = qimg.width(), qimg.height()
        ptr = qimg.constBits()
        return np.ndarray(
            (h, w, 3), dtype=np.uint8,
            buffer=memoryview(ptr),  # type: ignore[arg-type]
        ).copy()

    @staticmethod
    def _read_cv2(filepath: str) -> np.ndarray:
        """Read via OpenCV — last-resort fallback (BGR native)."""
        import cv2

        arr = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        if arr is None:
            raise OSError(f"OpenCV failed to decode: {filepath}")
        return arr

    # ------------------------------------------------------------------
    # Internal: metadata backends
    # ------------------------------------------------------------------

    @staticmethod
    def _metadata_qt(filepath: str) -> ImageMetadata:
        """Metadata via QImageReader — zero pixel decode."""
        _qt_gui = __import__("PyQt6.QtGui", fromlist=["QImageReader"])
        QImageReader = _qt_gui.QImageReader

        reader = QImageReader(filepath)
        size = reader.size()
        if not size.isValid():
            raise OSError(f"QImageReader cannot read: {filepath}")
        w, h = size.width(), size.height()
        ch, bd = ImageReader._detect_channels_and_depth(filepath)
        return ImageMetadata(
            width=w, height=h, channels=ch, bit_depth=bd,
            supports_roi=True, supports_pyramid=False,
        )

    @staticmethod
    def _metadata_pil(filepath: str) -> ImageMetadata:
        """Metadata via PIL."""
        from PIL import Image as PILImage

        with PILImage.open(filepath) as img:
            w, h = img.size
            ch, bd = ImageReader._channels_depth_from_pil(img)
        return ImageMetadata(
            width=w, height=h, channels=ch, bit_depth=bd,
            supports_roi=False, supports_pyramid=False,
        )

    @staticmethod
    def _metadata_cv2(filepath: str) -> ImageMetadata:
        """Metadata via OpenCV — last resort."""
        import cv2

        img = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise OSError(f"OpenCV cannot read: {filepath}")
        h, w = img.shape[:2]
        ch = 1 if img.ndim == 2 else img.shape[2]
        return ImageMetadata(
            width=w, height=h, channels=ch, bit_depth=8,
            supports_roi=False, supports_pyramid=False,
        )

    # ------------------------------------------------------------------
    # Internal: helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_color(arr: np.ndarray, output_color: str) -> np.ndarray:
        """Normalize color channels to the requested output format."""
        if output_color == "AS_IS":
            return arr

        if arr.ndim == 2:
            # Grayscale → expand to 3-channel
            arr = np.stack([arr, arr, arr], axis=-1)
            if output_color == "BGR":
                return arr  # grayscale has no color order
            return arr

        if arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[:, :, :3]  # strip alpha

        # PIL returns RGB. If BGR requested, reverse channel order.
        if output_color == "BGR" and arr.ndim == 3 and arr.shape[2] == 3:
            return arr[:, :, ::-1]  # R,G,B → B,G,R

        return arr

    @staticmethod
    def _detect_channels_and_depth(filepath: str) -> tuple[int, int]:
        """Detect channel count and bit depth, preferring PIL accuracy."""
        try:
            from PIL import Image as PILImage
            with PILImage.open(filepath) as img:
                return ImageReader._channels_depth_from_pil(img)
        except Exception:
            return 3, 8

    @staticmethod
    def _channels_depth_from_pil(img) -> tuple[int, int]:
        """Extract (channels, bit_depth) from an open PIL Image."""
        mode = img.mode
        # Channel count
        if mode in ("1", "L", "P"):
            ch = 1
        elif mode in ("RGB", "YCbCr", "LAB", "HSV"):
            ch = 3
        elif mode in ("RGBA", "CMYK"):
            ch = 4
        elif mode.startswith("I"):
            ch = 1
        elif mode == "F":
            ch = 1
        else:
            ch = len(img.getbands()) if hasattr(img, "getbands") else 3
        # Bit depth
        if mode == "1":
            bd = 1
        elif mode in ("L", "P", "RGB", "RGBA", "YCbCr", "LAB", "HSV", "CMYK"):
            bd = 8
        elif "16" in mode:
            bd = 16
        elif mode == "I" or mode == "F":
            # Check actual dtype
            arr = np.asarray(img)
            if arr.dtype == np.uint16:
                bd = 16
            elif arr.dtype == np.float32:
                bd = 32
            else:
                bd = 32
        else:
            bd = 8
        return ch, bd


# Module-level aliases
read = ImageReader.read
read_region = ImageReader.read_region
read_pages = ImageReader.read_pages
metadata = ImageReader.metadata
pages = ImageReader.pages

__all__ = [
    "ImageReader",
    "read",
    "read_region",
    "read_pages",
    "metadata",
    "pages",
]

from __future__ import annotations

import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from .rect import RectF


class EmptyImageRegionError(ValueError):
    """Raised when a requested image rect has no overlap with the image."""


@dataclass(frozen=True)
class ImageRegion:
    """Region metadata for one image-coordinate read request."""

    requested_rect: RectF
    clipped_rect: RectF
    target_size: tuple[int, int]


@dataclass(frozen=True)
class ImageReadResult:
    """Result envelope returned by an ImageProvider implementation."""

    region: ImageRegion
    image: Any = None

    @property
    def requested_rect(self) -> RectF:
        return self.region.requested_rect

    @property
    def clipped_rect(self) -> RectF:
        return self.region.clipped_rect

    @property
    def target_size(self) -> tuple[int, int]:
        return self.region.target_size


class ImageProvider(ABC):
    """Contract for reading finite image-coordinate regions."""

    @property
    @abstractmethod
    def image_width(self) -> int:
        raise NotImplementedError

    @property
    @abstractmethod
    def image_height(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def read_region(
        self, image_rect: RectF, target_size: tuple[int, int]
    ) -> ImageReadResult:
        raise NotImplementedError

    def prepare_region(
        self, image_rect: RectF, target_size: tuple[int, int]
    ) -> ImageRegion:
        """Round outward, clip to image bounds, and validate one read request."""
        self._validate_image_size()
        normalized_target_size = self._validate_target_size(target_size)
        image_rect.validate()

        x0 = max(0, math.floor(image_rect.x0))
        y0 = max(0, math.floor(image_rect.y0))
        x1 = min(self.image_width, math.ceil(image_rect.x1))
        y1 = min(self.image_height, math.ceil(image_rect.y1))

        if x0 >= x1 or y0 >= y1:
            raise EmptyImageRegionError(
                "Requested image rect does not overlap image bounds: "
                f"{image_rect} vs {self.image_width}x{self.image_height}"
            )

        return ImageRegion(
            requested_rect=image_rect,
            clipped_rect=RectF(float(x0), float(y0), float(x1), float(y1)),
            target_size=normalized_target_size,
        )

    def _validate_image_size(self) -> None:
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError(
                "Image width and height must be positive: "
                f"{self.image_width}x{self.image_height}"
            )

    @staticmethod
    def _validate_target_size(target_size: tuple[int, int]) -> tuple[int, int]:
        if not isinstance(target_size, tuple) or len(target_size) != 2:
            raise ValueError(
                "target_size must be a (width, height) tuple: "
                f"{target_size}"
            )

        width, height = target_size
        if (
            not isinstance(width, int)
            or isinstance(width, bool)
            or not isinstance(height, int)
            or isinstance(height, bool)
            or width <= 0
            or height <= 0
        ):
            raise ValueError(
                f"target_size width and height must be positive integers: {target_size}"
            )

        return width, height


# Maximum pyramid levels (level N = 1 / 2^N).
# Level 0 = original, level 1 = 1/2, ..., level 3 = 1/8.
_MAX_PYRAMID_LEVELS = 4  # levels 0..3
_MAX_PYRAMID_LEVEL_BYTES = 256 * 1024 * 1024


class QImageRegionProvider(ImageProvider):
    """ImageProvider with an in-memory multi-resolution image pyramid.

    On first access, only pyramid levels that fit the per-level byte
    budget are cached in memory. ``read_region()`` selects the cached
    level closest to 1:1 source/target ratio, or falls back to QImageReader.
    """

    def __init__(self, image_path: str) -> None:
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        self._image_path = os.path.abspath(image_path)
        self._image_width: Optional[int] = None
        self._image_height: Optional[int] = None
        self._pyramid: list[Any] = []  # [level_0_qpixmap or None, ...]
        self._pyramid_built = False
        self._read_metadata()

    # ------------------------------------------------------------------
    # ImageProvider abstract properties
    # ------------------------------------------------------------------

    @property
    def image_width(self) -> int:
        if self._image_width is None:
            raise RuntimeError("Image metadata not loaded")
        return self._image_width

    @property
    def image_height(self) -> int:
        if self._image_height is None:
            raise RuntimeError("Image metadata not loaded")
        return self._image_height

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def image_path(self) -> str:
        return self._image_path

    # Minimum pyramid level used for GPU-accelerated drawing.
    # Level 0 pixmaps (e.g. 30980×30276 = 3.6 GB) hurt GPU texture
    # cache efficiency.  Level 1 (1/2, 900 MB) gives imperceptibly
    # different quality while keeping GPU sampling fast.
    _MIN_GPU_LEVEL = 1

    def get_pyramid_pixmap(self, clip_w, clip_h, target_w, target_h):
        """Return (QPixmap, level_index, scale) for GPU-accelerated drawing.

        Selects the pyramid level closest to 1:1 source/target ratio,
        clamped to ``_MIN_GPU_LEVEL`` for GPU cache efficiency.
        If no cached level is available, returns (None, 0, 1.0).
        """
        self._ensure_pyramid()
        ideal = self._select_level(clip_w, clip_h, target_w, target_h)
        start = max(ideal, self._MIN_GPU_LEVEL)

        # Walk up from start level to find a cached pixmap.
        for level in range(start, _MAX_PYRAMID_LEVELS):
            pixmap = self._pyramid[level]
            if self._is_valid_pixmap(pixmap):
                scale = 1.0 / (1 << level)
                return pixmap, level, scale

        # Nothing cached (should not happen: at least level 3 is cached).
        return None, 0, 1.0

    def read_region(
        self, image_rect: RectF, target_size: tuple[int, int]
    ) -> ImageReadResult:
        """Read the specified image-coordinate region at target resolution."""
        region = self.prepare_region(image_rect, target_size)
        clipped = region.clipped_rect
        clip_w = int(clipped.x1 - clipped.x0)
        clip_h = int(clipped.y1 - clipped.y0)
        tw, th = region.target_size

        if clip_w <= 0 or clip_h <= 0:
            raise EmptyImageRegionError(
                f"Zero-area clipped rect: {clipped}"
            )

        self._ensure_pyramid()

        # Select the pyramid level whose source-pixel-to-target-pixel
        # ratio is closest to 1:1 — gives best quality/speed balance.
        level = self._select_level(clip_w, clip_h, tw, th)
        return self._read_from_level(region, clipped, clip_w, clip_h, tw, th, level)

    # ------------------------------------------------------------------
    # Internal: pyramid construction
    # ------------------------------------------------------------------

    def _ensure_pyramid(self):
        """Build cacheable pyramid levels on first access."""
        if self._pyramid_built:
            return
        import time as _time
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QImageReader

        # Build only pyramid levels that fit the memory budget.
        for lvl in range(_MAX_PYRAMID_LEVELS):
            scale = 1.0 / (1 << lvl)  # 1, 1/2, 1/4, 1/8
            lvl_w = max(1, int(self._image_width * scale))
            lvl_h = max(1, int(self._image_height * scale))
            if not self._should_cache_pyramid_level(lvl, lvl_w, lvl_h):
                self._pyramid.append(None)
                continue

            _t0 = _time.perf_counter()
            reader = QImageReader(self._image_path)
            reader.setAutoTransform(True)
            reader.setScaledSize(QRect(0, 0, lvl_w, lvl_h).size())
            qimg = reader.read()
            _elapsed = (_time.perf_counter() - _t0) * 1000

            if qimg.isNull():
                self._pyramid.append(None)
                continue

            # Convert to QPixmap for GPU-resident storage.
            # drawPixmap with source rect uses GPU scaling.
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap.fromImage(qimg)
            self._pyramid.append(pixmap if self._is_valid_pixmap(pixmap) else None)

        self._pyramid_built = True

    @staticmethod
    def _should_cache_pyramid_level(level: int, width: int, height: int) -> bool:
        del level
        return width * height * 4 <= _MAX_PYRAMID_LEVEL_BYTES

    # ------------------------------------------------------------------
    # Internal: level selection
    # ------------------------------------------------------------------

    def _select_level(
        self, clip_w: int, clip_h: int, target_w: int, target_h: int
    ) -> int:
        """Select the pyramid level closest to 1:1 source/target ratio.

        For each cached level, compute how many source pixels map to one
        target pixel.  Pick the level where this ratio is closest to 1.0.
        Level 0 (original file) is always available as fallback.
        """
        best_level = 0
        best_distance = float("inf")

        for lvl, qimg in enumerate(self._pyramid):
            if not self._is_valid_pixmap(qimg):
                continue
            scale = 1.0 / (1 << lvl)
            src_w = clip_w * scale
            src_h = clip_h * scale
            ratio = max(src_w / target_w, src_h / target_h)
            distance = abs(ratio - 1.0)
            if distance < best_distance:
                best_distance = distance
                best_level = lvl

        return best_level

    # ------------------------------------------------------------------
    # Internal: read from selected level
    # ------------------------------------------------------------------

    def _read_from_level(
        self, region, clipped, clip_w, clip_h, tw, th, level: int
    ):
        """Read the requested region from the given pyramid level."""
        src_qimage = self._pyramid[level]

        if not self._is_valid_pixmap(src_qimage):
            # Level not cached — fall back to file.
            if level == 0:
                return self._read_from_file(
                    region, clipped, clip_w, clip_h, tw, th
                )
            # Try the next coarser cached level.
            for fallback in range(level + 1, _MAX_PYRAMID_LEVELS):
                if self._is_valid_pixmap(self._pyramid[fallback]):
                    return self._read_from_level(
                        region, clipped, clip_w, clip_h, tw, th, fallback
                    )
            # No cached level available, use file.
            return self._read_from_file(
                region, clipped, clip_w, clip_h, tw, th
            )

        from PyQt6.QtCore import QRect, Qt

        scale = 1.0 / (1 << level)

        # Map level-0 coordinates to pyramid-level coordinates.
        sx0 = max(0, int(clipped.x0 * scale))
        sy0 = max(0, int(clipped.y0 * scale))
        sx1 = min(src_qimage.width(), int(clipped.x1 * scale + 0.5) + 1)
        sy1 = min(src_qimage.height(), int(clipped.y1 * scale + 0.5) + 1)
        sw = max(1, sx1 - sx0)
        sh = max(1, sy1 - sy0)

        cropped = src_qimage.copy(QRect(sx0, sy0, sw, sh))
        if cropped.isNull():
            # Copy failed — fall back to file.
            return self._read_from_file(
                region, clipped, clip_w, clip_h, tw, th
            )

        scaled = cropped.scaled(
            tw, th,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.isNull():
            return self._read_from_file(
                region, clipped, clip_w, clip_h, tw, th
            )
        return ImageReadResult(region=region, image=scaled)

    def _read_from_file(self, region, clipped, clip_w, clip_h, tw, th):
        """Read region directly from the original file via QImageReader."""
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QImage, QImageReader, QPixmap

        reader = QImageReader(self._image_path)
        reader.setAutoTransform(True)
        reader.setClipRect(QRect(
            int(clipped.x0), int(clipped.y0), clip_w, clip_h
        ))
        reader.setScaledSize(QRect(0, 0, tw, th).size())

        qimage: QImage = reader.read()
        if qimage.isNull():
            raise RuntimeError(
                f"QImageReader failed for {self._image_path}: "
                f"{reader.errorString()}"
            )
        pixmap = QPixmap.fromImage(qimage)
        if pixmap.isNull():
            raise RuntimeError(
                f"QPixmap creation failed for {self._image_path}: "
                f"{reader.errorString()}"
            )
        return ImageReadResult(region=region, image=pixmap)

    @staticmethod
    def _is_valid_pixmap(pixmap: Any) -> bool:
        if pixmap is None:
            return False
        is_null = getattr(pixmap, "isNull", None)
        return not (callable(is_null) and is_null())

    def _read_metadata(self) -> None:
        """Read image dimensions from the file header via QImageReader."""
        from PyQt6.QtGui import QImageReader

        reader = QImageReader(self._image_path)
        size = reader.size()
        if not size.isValid():
            raise RuntimeError(
                f"QImageReader could not read size from {self._image_path}"
            )
        self._image_width = size.width()
        self._image_height = size.height()

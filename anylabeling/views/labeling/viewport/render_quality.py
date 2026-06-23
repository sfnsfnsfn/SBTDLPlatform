from __future__ import annotations

from enum import Enum


class RenderQuality(Enum):
    NEAREST = "nearest"
    SMOOTH = "smooth"
    HIGH = "high"


def apply_render_quality(painter, quality: RenderQuality) -> None:
    """Apply image resampling hints for the current paint operation."""
    quality = RenderQuality(quality)
    smooth_enabled = quality is not RenderQuality.NEAREST
    painter.setRenderHint(
        _smooth_pixmap_transform_hint(painter),
        smooth_enabled,
    )


def _smooth_pixmap_transform_hint(painter):
    render_hint = getattr(type(painter), "RenderHint", None)
    if render_hint is None:
        render_hint = getattr(painter, "RenderHint", None)
    if render_hint is not None:
        return render_hint.SmoothPixmapTransform

    try:
        from PyQt6 import QtGui
    except ImportError as exc:
        raise RuntimeError(
            "PyQt6 is required to apply render quality"
        ) from exc

    return QtGui.QPainter.RenderHint.SmoothPixmapTransform

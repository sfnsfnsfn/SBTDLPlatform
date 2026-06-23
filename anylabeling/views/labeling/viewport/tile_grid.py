# FUTURE: Tile decomposition for online renderer. Implemented, zero consumers.
"""Pure tile math: decompose an image-coordinate rectangle into tile keys.

Tiles are at a fixed ``tile_size`` in image pixels.  Each tile is
identified by a ``TileKey(image_id, level, x, y)`` and has a
corresponding source rectangle in level-0 image coordinates.

Callers are responsible for clipping source rectangles to image
bounds (via ``ImageProvider.prepare_region``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .rect import RectF

DEFAULT_TILE_SIZE = 512


@dataclass(frozen=True)
class TileKey:
    """Globally unique key for one tile in a multi-resolution grid."""

    image_id: str
    level: int
    x: int
    y: int


def tiles_for_rect(
    image_id: str,
    level: int,
    image_rect: RectF,
    tile_size: int = DEFAULT_TILE_SIZE,
) -> list[tuple[TileKey, RectF]]:
    """Decompose *image_rect* into a list of ``(TileKey, source_rect)`` pairs.

    The source rectangle for each tile is the intersection of the tile's
    footprint with *image_rect*, clipped to tile boundaries.  *image_rect*
    is in level-0 image coordinates regardless of *level*.

    Parameters
    ----------
    image_id:
        Opaque identifier for the image (e.g. file path or hash).
    level:
        Pyramid level.  0 = full resolution.  Level is propagated to
        tile keys but does **not** affect source rectangle coordinates.
    image_rect:
        The image-coordinate rectangle to cover, in level-0 pixels.
    tile_size:
        Edge length of a tile in image pixels (default 512).

    Returns
    -------
    list[tuple[TileKey, RectF]]
        Deterministically ordered list of ``(key, source_rect)`` pairs.
    """
    image_rect.validate()
    if tile_size <= 0:
        raise ValueError(f"tile_size must be positive: {tile_size}")

    # Tile index range (inclusive start, exclusive end)
    x_start = int(math.floor(image_rect.x0 / tile_size))
    y_start = int(math.floor(image_rect.y0 / tile_size))
    x_end = int(math.floor((image_rect.x1 - 1) / tile_size)) + 1
    y_end = int(math.floor((image_rect.y1 - 1) / tile_size)) + 1

    result: list[tuple[TileKey, RectF]] = []

    for ty in range(y_start, y_end):
        tile_y0 = float(ty * tile_size)
        tile_y1 = float(tile_y0 + tile_size)
        for tx in range(x_start, x_end):
            tile_x0 = float(tx * tile_size)
            tile_x1 = float(tile_x0 + tile_size)

            # Intersection of tile footprint with requested rect
            src_x0 = max(tile_x0, image_rect.x0)
            src_y0 = max(tile_y0, image_rect.y0)
            src_x1 = min(tile_x1, image_rect.x1)
            src_y1 = min(tile_y1, image_rect.y1)

            if src_x0 < src_x1 and src_y0 < src_y1:
                key = TileKey(image_id=image_id, level=level, x=tx, y=ty)
                src = RectF(src_x0, src_y0, src_x1, src_y1)
                result.append((key, src))

    return result

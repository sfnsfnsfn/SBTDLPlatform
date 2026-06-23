from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TilePlan:
    """Parameters that govern how a large image is sliced into tiles.

    ``overlap_x`` and ``overlap_y`` are in pixels, not percentages.
    ``edge_mode`` controls how the right/bottom edge is handled when the image
    dimensions are not exact multiples of the stride.
    """

    tile_width: int
    tile_height: int
    overlap_x: int  # in pixels, not percentage
    overlap_y: int  # in pixels, not percentage
    edge_mode: Literal["crop", "pad"]
    padding_value: int | tuple[int, ...]
    min_object_pixels: int
    min_visibility_ratio: float


@dataclass(frozen=True)
class TileRecord:
    """A single tile produced from an asset according to a TilePlan.

    ``x0`` and ``y0`` are L0 image coordinates of the tile origin.
    ``valid_width`` and ``valid_height`` describe the region that contains
    real image data (relevant when ``edge_mode == "pad"``).
    """

    tile_id: str
    asset_id: str
    x0: int  # L0 coordinate
    y0: int  # L0 coordinate
    width: int
    height: int
    valid_width: int
    valid_height: int
    split: Literal["train", "val", "test", "none"]


__all__ = [
    "TilePlan",
    "TileRecord",
]

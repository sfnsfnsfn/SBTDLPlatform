"""Deterministic tile planning for large-image assets — pure Python, no UI imports."""

from __future__ import annotations

from anylabeling.platform.domain.asset import Asset
from anylabeling.platform.domain.tile import TilePlan, TileRecord


class TilePlanner:
    """Generate a deterministic ordered list of ``TileRecord`` for an ``Asset``
    governed by a ``TilePlan``.

    All coordinates are in level-0 image pixels.  Tiles are emitted in
    row-major order (top-left to bottom-right).

    Tile IDs follow the pattern ``tile_{asset_id}_{row:04d}_{col:04d}``
    and are stable across runs for the same asset + plan.
    """

    @staticmethod
    def plan(asset: Asset, tile_plan: TilePlan) -> list[TileRecord]:
        """Generate deterministic ordered ``TileRecord`` instances.

        Parameters
        ----------
        asset:
            Asset descriptor with ``width`` and ``height`` in L0 pixels.
        tile_plan:
            Tile slicing parameters (tile size, overlap in pixels,
            edge mode, padding value, etc.).

        Returns
        -------
        list[TileRecord]
            Tile records in row-major order.  The ``split`` field is always
            ``"none"`` — callers assign train/val/test splits later.

        Notes
        -----
        The following ``TilePlan`` fields are **not** consumed by the planner
        itself but are forwarded to downstream stages:

        * ``padding_value`` — used by the materializer when filling padded
          regions of edge tiles (``edge_mode="pad"``).
        * ``min_object_pixels`` — used by label splitters to filter out
          object instances that occupy too few pixels in a tile.
        * ``min_visibility_ratio`` — used by label splitters to filter out
          object instances whose visible fraction in a tile is too low.
        """
        if tile_plan.overlap_x < 0 or tile_plan.overlap_y < 0:
            raise ValueError(
                f"Overlap must be non-negative: "
                f"overlap=({tile_plan.overlap_x},{tile_plan.overlap_y})"
            )

        stride_x = tile_plan.tile_width - tile_plan.overlap_x
        stride_y = tile_plan.tile_height - tile_plan.overlap_y

        if stride_x <= 0 or stride_y <= 0:
            raise ValueError(
                f"Overlap must be strictly less than tile size: "
                f"overlap=({tile_plan.overlap_x},{tile_plan.overlap_y}) "
                f"tile=({tile_plan.tile_width},{tile_plan.tile_height})"
            )
        if tile_plan.tile_width <= 0 or tile_plan.tile_height <= 0:
            raise ValueError(
                f"Tile dimensions must be positive: "
                f"({tile_plan.tile_width},{tile_plan.tile_height})"
            )
        if asset.width <= 0 or asset.height <= 0:
            raise ValueError(
                f"Asset dimensions must be positive: {asset.width}x{asset.height}"
            )

        cols = max(1, (asset.width + stride_x - 1) // stride_x)
        rows = max(1, (asset.height + stride_y - 1) // stride_y)

        records: list[TileRecord] = []

        for row in range(rows):
            y0 = row * stride_y
            tile_h = tile_plan.tile_height
            valid_h = min(tile_h, asset.height - y0)
            if tile_plan.edge_mode == "crop":
                tile_h = valid_h

            for col in range(cols):
                x0 = col * stride_x
                tile_w = tile_plan.tile_width
                valid_w = min(tile_w, asset.width - x0)
                if tile_plan.edge_mode == "crop":
                    tile_w = valid_w

                tile_id = f"tile_{asset.id}_{row:04d}_{col:04d}"

                records.append(
                    TileRecord(
                        tile_id=tile_id,
                        asset_id=asset.id,
                        x0=x0,
                        y0=y0,
                        width=tile_w,
                        height=tile_h,
                        valid_width=valid_w,
                        valid_height=valid_h,
                        split="none",
                    )
                )

        return records


__all__ = ["TilePlanner"]

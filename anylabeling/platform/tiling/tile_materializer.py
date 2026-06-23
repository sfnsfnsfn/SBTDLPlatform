"""Materialize tile images from LargeImageSource to disk — pure Python, no UI imports."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from anylabeling.platform.domain.tile import TileRecord
from anylabeling.platform.infrastructure.image_sources.base import LargeImageSource


class TileMaterializer:
    """Materializes tile images from LargeImageSource to disk.

    Uses ``source.read_region()`` to extract tile pixels and saves them
    as PNG files in a structured output directory.

    Typical usage::

        materializer = TileMaterializer(output_dir / "images")
        paths = materializer.materialize_all(source, tiles)
    """

    def __init__(self, output_dir: str | Path) -> None:
        """Initialize with an output base directory.

        Parameters
        ----------
        output_dir:
            Base directory where tile images will be saved.  Subdirectories
            are created automatically on write.
        """
        self.output_dir = Path(output_dir)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def materialize(
        self,
        source: LargeImageSource,
        tile: TileRecord,
        output_name: str | None = None,
    ) -> Path:
        """Read a tile region from *source* and save it as a PNG file.

        Parameters
        ----------
        source:
            Any ``LargeImageSource`` implementation (file-backed or in-memory).
        tile:
            Tile descriptor with ``x0``, ``y0``, ``width``, ``height``.
        output_name:
            Base filename without extension.  Defaults to ``tile.tile_id``.

        Returns
        -------
        Path
            Absolute path to the saved PNG file.
        """
        name = output_name or tile.tile_id
        out_path = self.output_dir / f"{name}.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Read the region at 1:1 resolution (output_size == tile size)
        pixels: np.ndarray = source.read_region(
            rect_l0=(tile.x0, tile.y0, tile.width, tile.height),
            output_size=(tile.width, tile.height),
        )

        # read_region returns (H, W, C).  OpenCV expects BGR for imwrite when
        # saving as PNG, but the source provides RGB(A).  Convert accordingly.
        if pixels.ndim == 3 and pixels.shape[2] >= 3:
            # RGB → BGR for cv2.imwrite
            save_array = pixels[:, :, :3][:, :, ::-1]
        elif pixels.ndim == 3 and pixels.shape[2] == 1:
            save_array = pixels[:, :, 0]
        else:
            save_array = pixels

        cv2.imwrite(str(out_path), save_array)
        return out_path

    def materialize_all(
        self,
        source: LargeImageSource,
        tiles: list[TileRecord],
    ) -> list[Path]:
        """Materialize all *tiles* for a single asset.

        Each tile is saved as ``{tile.tile_id}.png`` in ``output_dir``.

        Parameters
        ----------
        source:
            LargeImageSource for the asset.
        tiles:
            List of tile records to materialize.

        Returns
        -------
        list[Path]
            Output file paths in the same order as *tiles*.
        """
        return [self.materialize(source, t) for t in tiles]


__all__ = ["TileMaterializer"]

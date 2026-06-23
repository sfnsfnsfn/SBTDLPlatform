"""HBB (Horizontal Bounding Box) label splitter for detection_hbb tasks."""

from __future__ import annotations

from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.tile import TilePlan, TileRecord


class HBBSplitter:
    """Split ``bbox_xyxy`` annotations from L0 coords to tile-local coords.

    Clips each bounding box to the tile's valid region and filters by
    visibility ratio and minimum pixel area.
    """

    task_family: str = "detection_hbb"

    def split(
        self,
        annotations: AnnotationDocument,
        tile: TileRecord,
        plan: TilePlan,
    ) -> list[AnnotationObject]:
        """Split HBB annotations for a single tile.

        Parameters
        ----------
        annotations:
            Full-image AnnotationDocument with objects in L0 coordinates.
        tile:
            Tile descriptor with ``x0``, ``y0``, ``valid_width``, ``valid_height``.
        plan:
            Tile plan carrying ``min_visibility_ratio`` and ``min_object_pixels``.

        Returns
        -------
        list[AnnotationObject]
            Tile-local ``bbox_xyxy`` objects with ``source_object_id`` preserved.
        """
        results: list[AnnotationObject] = []

        # Tile valid area in L0 coordinates
        tx1 = tile.x0
        ty1 = tile.y0
        tx2 = tile.x0 + tile.valid_width
        ty2 = tile.y0 + tile.valid_height

        if tx2 <= tx1 or ty2 <= ty1:
            return results

        for obj in annotations.objects:
            if obj.geometry_type != "bbox_xyxy":
                continue

            x1, y1, x2, y2 = obj.geometry  # type: ignore[misc]

            # Compute intersection of bbox with tile valid area
            ix1 = max(x1, tx1)
            iy1 = max(y1, ty1)
            ix2 = min(x2, tx2)
            iy2 = min(y2, ty2)

            if ix1 >= ix2 or iy1 >= iy2:
                continue  # no intersection

            # Area-based filtering
            inter_area = (ix2 - ix1) * (iy2 - iy1)
            orig_area = (x2 - x1) * (y2 - y1)

            if orig_area <= 0:
                continue

            visibility = inter_area / orig_area
            if visibility < plan.min_visibility_ratio:
                continue
            if inter_area < plan.min_object_pixels:
                continue

            # Convert to tile-local coordinates
            local_geom = (
                ix1 - tile.x0,
                iy1 - tile.y0,
                ix2 - tile.x0,
                iy2 - tile.y0,
            )

            results.append(
                AnnotationObject(
                    id=f"{obj.id}__tile_{tile.tile_id}",
                    label_id=obj.label_id,
                    geometry_type="bbox_xyxy",
                    geometry=local_geom,
                    attributes=dict(obj.attributes),
                    source_object_id=obj.id,
                )
            )

        return results


__all__ = ["HBBSplitter"]

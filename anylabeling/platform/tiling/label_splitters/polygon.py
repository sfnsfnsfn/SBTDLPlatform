"""Polygon label splitter for instance_segmentation tasks.

Uses Shapely for robust geometric intersection and handles MultiPolygon
fragmentation when a polygon straddles multiple tiles.
"""

from __future__ import annotations

from shapely import box
from shapely.geometry import Polygon
from shapely.validation import make_valid

from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.tile import TilePlan, TileRecord


class PolygonSplitter:
    """Split ``polygon`` annotations from L0 coords to tile-local coords.

    When a polygon is cut by tile boundaries the intersection may yield
    multiple fragments (MultiPolygon).  Each fragment becomes a separate
    ``AnnotationObject`` sharing the same ``source_object_id``.
    """

    task_family: str = "instance_segmentation"

    def split(
        self,
        annotations: AnnotationDocument,
        tile: TileRecord,
        plan: TilePlan,
    ) -> list[AnnotationObject]:
        """Split polygon annotations for a single tile.

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
            Tile-local ``polygon`` objects with ``source_object_id`` preserved.
        """
        results: list[AnnotationObject] = []

        # Tile valid area as Shapely box
        tile_box = box(
            tile.x0,
            tile.y0,
            tile.x0 + tile.valid_width,
            tile.y0 + tile.valid_height,
        )

        for obj in annotations.objects:
            if obj.geometry_type != "polygon":
                continue

            points = obj.geometry  # type: ignore[assignment]
            if len(points) < 3:
                continue

            # Build polygon; repair invalid geometry
            poly = Polygon(points)
            if not poly.is_valid:
                poly = make_valid(poly)
                if poly.is_empty:
                    continue

            orig_area = poly.area
            if orig_area <= 0:
                continue

            # Compute intersection with tile
            clipped = poly.intersection(tile_box)

            if clipped.is_empty:
                continue

            # Collect polygon fragments (handles both Polygon and MultiPolygon)
            fragments: list[Polygon] = []
            if clipped.geom_type == "Polygon":
                if clipped.area > 0:
                    fragments.append(clipped)
            elif clipped.geom_type == "MultiPolygon":
                for frag in clipped.geoms:
                    if isinstance(frag, Polygon) and frag.area > 0:
                        fragments.append(frag)
            else:
                # Point, LineString, or GeometryCollection — skip
                continue

            for i, frag in enumerate(fragments):
                frag_area = frag.area

                if frag_area < plan.min_object_pixels:
                    continue

                # Visibility: fragment area relative to original polygon area
                if frag_area / orig_area < plan.min_visibility_ratio:
                    continue

                # Convert exterior ring to tile-local coordinates
                local_coords = [
                    (x - tile.x0, y - tile.y0)
                    for x, y in frag.exterior.coords[:-1]  # skip closing point
                ]

                uid = (
                    f"{obj.id}__tile_{tile.tile_id}__frag_{i}"
                    if len(fragments) > 1
                    else f"{obj.id}__tile_{tile.tile_id}"
                )

                results.append(
                    AnnotationObject(
                        id=uid,
                        label_id=obj.label_id,
                        geometry_type="polygon",
                        geometry=local_coords,
                        attributes=dict(obj.attributes),
                        source_object_id=obj.id,
                    )
                )

        return results


__all__ = ["PolygonSplitter"]

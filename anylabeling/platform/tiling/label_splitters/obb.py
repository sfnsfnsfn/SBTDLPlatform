"""OBB (Oriented Bounding Box) label splitter for detection_obb tasks.

CRITICAL: Never clamp corner points directly — that produces self-intersecting
quadrilaterals.  Always compute the geometric intersection via Shapely, then
reconstruct an OBB from the clipped region.
"""

from __future__ import annotations

import hashlib

from shapely import box
from shapely.geometry import Polygon

from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.tile import TilePlan, TileRecord


class OBBSplitter:
    """Split ``obb_polygon`` annotations from L0 coords to tile-local coords.

    Uses Shapely polygon intersection to clip rotated boxes against tile
    boundaries without introducing self-intersections.
    """

    task_family: str = "detection_obb"

    def split(
        self,
        annotations: AnnotationDocument,
        tile: TileRecord,
        plan: TilePlan,
    ) -> list[AnnotationObject]:
        """Split OBB annotations for a single tile.

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
            Tile-local ``obb_polygon`` objects with ``source_object_id`` preserved.
        """
        results: list[AnnotationObject] = []

        # Tile valid area as Shapely box in L0 coordinates
        tile_box = box(
            tile.x0,
            tile.y0,
            tile.x0 + tile.valid_width,
            tile.y0 + tile.valid_height,
        )

        for obj in annotations.objects:
            if obj.geometry_type != "obb_polygon":
                continue

            points = obj.geometry  # type: ignore[assignment] — list of (x, y)
            if len(points) < 3:
                continue

            # Build the original OBB polygon
            obb_poly = Polygon(points)
            if not obb_poly.is_valid:
                obb_poly = obb_poly.buffer(0)
                if obb_poly.is_empty:
                    continue

            orig_area = obb_poly.area
            if orig_area <= 0:
                continue

            # Compute geometric intersection with tile
            clipped = obb_poly.intersection(tile_box)

            if clipped.is_empty:
                continue

            # Discard degenerate intersections (points, lines)
            if clipped.geom_type not in ("Polygon", "MultiPolygon"):
                continue

            # For MultiPolygon, use the largest fragment
            if clipped.geom_type == "MultiPolygon":
                fragments = [g for g in clipped.geoms if g.area > 0]
                if not fragments:
                    continue
                clipped = max(fragments, key=lambda g: g.area)

            if not isinstance(clipped, Polygon):
                continue

            clipped_area = clipped.area

            # Filter by visibility ratio
            visibility = clipped_area / orig_area
            if visibility < plan.min_visibility_ratio:
                continue
            if clipped_area < plan.min_object_pixels:
                continue

            # Reconstruct OBB: compute minimum rotated rectangle of the clipped region
            min_rect = clipped.minimum_rotated_rectangle

            if not isinstance(min_rect, Polygon) or min_rect.is_empty:
                continue

            # Extract 4 corner points from the min-area rect
            coords = list(min_rect.exterior.coords)[:4]  # exterior closes, take first 4

            # Convert to tile-local coordinates
            local_coords = [(x - tile.x0, y - tile.y0) for x, y in coords]

            # Determine if geometry was degraded
            attrs = dict(obj.attributes)
            degraded = not self._is_same_rect(obb_poly, clipped)
            if degraded:
                attrs["geometry_degraded"] = True
                attrs["reason"] = "clipped_polygon_to_min_area_rect"

            # Generate a stable tile-local object id
            uid = self._make_tile_object_id(obj.id, tile.tile_id, local_coords)

            results.append(
                AnnotationObject(
                    id=uid,
                    label_id=obj.label_id,
                    geometry_type="obb_polygon",
                    geometry=local_coords,
                    attributes=attrs,
                    source_object_id=obj.id,
                )
            )

        return results

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_same_rect(
        original: Polygon,
        clipped: Polygon,
        tol: float = 1e-6,
    ) -> bool:
        """Return True if the clipped polygon is essentially the same rectangle
        as the original (no degradation from clipping)."""
        if original.equals_exact(clipped, tol):
            return True
        if abs(original.area - clipped.area) < tol:
            return True
        return False

    @staticmethod
    def _make_tile_object_id(
        source_id: str,
        tile_id: str,
        coords: list[tuple[float, float]],
    ) -> str:
        """Produce a stable, unique object id for the tile-local annotation."""
        h = hashlib.sha1(
            f"{source_id}_{tile_id}_{coords}".encode("utf-8")
        ).hexdigest()[:8]
        return f"{source_id}__tile_{tile_id}__{h}"


__all__ = ["OBBSplitter"]

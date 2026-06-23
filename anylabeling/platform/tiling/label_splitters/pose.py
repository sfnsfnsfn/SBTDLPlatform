"""Pose (keypoints) label splitter for pose estimation tasks.

Keypoints straddling tile boundaries are handled by marking out-of-tile
keypoints as invisible (0, 0, 0) and filtering instances with too few
remaining visible keypoints.
"""

from __future__ import annotations

from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.tile import TilePlan, TileRecord


class PoseSplitter:
    """Split ``keypoints`` annotations from L0 coords to tile-local coords.

    Each keypoint is a ``(x, y, visible)`` tuple.  Keypoints outside the
    tile valid area are set to ``(0, 0, 0)``.  Objects with fewer than
    ``min_visible_keypoints`` inside the tile are discarded.
    """

    task_family: str = "pose"

    def __init__(self, min_visible_keypoints: int = 1):
        self._min_visible = min_visible_keypoints

    def split(
        self,
        annotations: AnnotationDocument,
        tile: TileRecord,
        plan: TilePlan,
    ) -> list[AnnotationObject]:
        """Split pose keypoint annotations for a single tile.

        Parameters
        ----------
        annotations:
            Full-image AnnotationDocument with objects in L0 coordinates.
        tile:
            Tile descriptor with ``x0``, ``y0``, ``valid_width``, ``valid_height``.
        plan:
            Tile plan (threshold fields are advisory; the splitter uses its own
            ``min_visible_keypoints`` and also respects ``min_object_pixels``).

        Returns
        -------
        list[AnnotationObject]
            Tile-local ``keypoints`` objects with ``source_object_id`` preserved.
        """
        results: list[AnnotationObject] = []

        # Tile valid area bounds in L0 coordinates
        tx1 = tile.x0
        ty1 = tile.y0
        tx2 = tile.x0 + tile.valid_width
        ty2 = tile.y0 + tile.valid_height

        if tx2 <= tx1 or ty2 <= ty1:
            return results

        for obj in annotations.objects:
            if obj.geometry_type != "keypoints":
                continue

            keypoints = obj.geometry  # type: ignore[assignment] — list[(x,y,v)]

            # Compute bounding box of visible keypoints to test tile intersection
            visible_kps = [(x, y) for x, y, v in keypoints if v > 0]
            if not visible_kps:
                continue

            kp_xs = [x for x, _ in visible_kps]
            kp_ys = [y for _, y in visible_kps]
            kp_x1, kp_x2 = min(kp_xs), max(kp_xs)
            kp_y1, kp_y2 = min(kp_ys), max(kp_ys)

            # Quick rejection: bbox of visible keypoints doesn't intersect tile
            if kp_x2 <= tx1 or kp_x1 >= tx2 or kp_y2 <= ty1 or kp_y1 >= ty2:
                continue

            # Remap keypoints: inside tile → tile-local; outside → (0,0,0)
            remapped: list[tuple[float, float, int]] = []
            for x, y, v in keypoints:
                if v <= 0:
                    remapped.append((0.0, 0.0, 0))
                elif tx1 <= x <= tx2 and ty1 <= y <= ty2:
                    remapped.append((x - tile.x0, y - tile.y0, v))
                else:
                    remapped.append((0.0, 0.0, 0))

            # Count visible keypoints inside tile
            visible_count = sum(1 for _, _, v in remapped if v > 0)

            if visible_count < self._min_visible:
                continue

            results.append(
                AnnotationObject(
                    id=f"{obj.id}__tile_{tile.tile_id}",
                    label_id=obj.label_id,
                    geometry_type="keypoints",
                    geometry=remapped,
                    attributes=dict(obj.attributes),
                    source_object_id=obj.id,
                )
            )

        return results


__all__ = ["PoseSplitter"]

"""Classification label splitter for image classification tasks.

Classification is image-level by default — no tiling.  When tile
classification is explicitly enabled via the ``tile_classification_mode``
attribute, tiles may inherit image-level labels.
"""

from __future__ import annotations

from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.tile import TilePlan, TileRecord


class ClassifySplitter:
    """Split classification annotations.

    Image-level classification labels are not geometry-based — they apply
    to the whole image.  By default no tile-level objects are produced.
    When tile classification is enabled, tiles inherit the image-level
    labels via a synthetic ``AnnotationObject``.
    """

    task_family: str = "classification"

    def split(
        self,
        annotations: AnnotationDocument,
        tile: TileRecord,
        plan: TilePlan,
    ) -> list[AnnotationObject]:
        """Split classification annotations for a single tile.

        Parameters
        ----------
        annotations:
            Full-image AnnotationDocument with ``image_labels`` dict.
        tile:
            Tile descriptor.
        plan:
            Tile plan (may carry tile classification config in the future).

        Returns
        -------
        list[AnnotationObject]
            Normally empty.  When tile classification is enabled via
            ``annotations.attributes.get("tile_classification_mode") == "inherit"``,
            a single synthetic ``AnnotationObject`` is returned per tile
            carrying the image-level labels.

        Notes
        -----
        The "inherit" strategy is encoded as an attribute on the
        ``AnnotationDocument``.  This avoids coupling the splitter to
        a configuration system.
        """
        mode = getattr(annotations, "attributes", {}).get(
            "tile_classification_mode", None
        )

        if mode != "inherit":
            # Default: classification is image-level, no tile objects
            return []

        if not annotations.image_labels:
            return []

        # Inherit: create one synthetic object carrying image-level labels.
        # The geometry is set to the full tile valid area so downstream
        # consumers (e.g. dataset builders) know the scope.
        tile_geom = (0, 0, tile.valid_width, tile.valid_height)

        return [
            AnnotationObject(
                id=f"cls__tile_{tile.tile_id}",
                label_id=-1,  # synthetic — real labels in attributes
                geometry_type="bbox_xyxy",
                geometry=tile_geom,
                attributes={
                    "tile_classification_mode": "inherit",
                    "image_labels": dict(annotations.image_labels),
                },
                source_object_id=None,
            )
        ]


__all__ = ["ClassifySplitter"]

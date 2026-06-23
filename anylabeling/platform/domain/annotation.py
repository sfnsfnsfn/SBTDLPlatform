from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class AnnotationObject:
    """A single labelled object on an image, stored in L0 image coordinates.

    ``geometry`` depends on ``geometry_type``:

    * ``bbox_xyxy`` – ``tuple[float, float, float, float]`` (x1, y1, x2, y2)
    * ``polygon`` – ``list[tuple[float, float]]``
    * ``obb_polygon`` – ``list[tuple[float, float]]`` (4-point quadrilateral)
    * ``keypoints`` – ``list[tuple[float, float, int]]`` (x, y, visibility)
    * ``raster_mask`` – run-length encoded dict or dense mask reference
    """

    id: str
    label_id: int
    geometry_type: Literal[
        "bbox_xyxy",
        "polygon",
        "obb_polygon",
        "keypoints",
        "raster_mask",
    ]
    geometry: object  # depends on geometry_type
    attributes: dict = field(default_factory=dict)
    source_object_id: str | None = None


@dataclass
class AnnotationDocument:
    """All annotations for a single asset, stored in L0 image coordinates.

    ``image_labels`` maps label category names to boolean flags (e.g.
    classification tags at the image level).
    """

    asset_id: str
    image_width: int
    image_height: int
    objects: list[AnnotationObject] = field(default_factory=list)
    image_labels: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class AnnotationSuggestion:
    """AI-generated annotation that awaits user review before acceptance.

    Suggestions are rendered with dashed outlines and confidence badges
    to distinguish them from manually-created or accepted annotations.
    """

    id: str
    asset_id: str
    model_id: str
    model_name: str
    confidence: float
    shapes: list[dict]  # list of Shape-compatible dicts
    status: str  # "pending" | "accepted" | "rejected"
    created_at: str  # ISO 8601 timestamp


__all__ = [
    "AnnotationObject",
    "AnnotationDocument",
    "AnnotationSuggestion",
]

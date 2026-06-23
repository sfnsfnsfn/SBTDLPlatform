"""
XLabelCodec: codec for X-AnyLabeling JSON format.

Implements the AnnotationCodec Protocol from anylabeling.platform.application.ports.
Converts between X-AnyLabeling JSON and platform AnnotationDocument.

Architecture constraint: this module does NOT import from views.*.
"""
from __future__ import annotations

import json
import logging
import math
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from anylabeling.platform.domain.annotation import (
    AnnotationDocument,
    AnnotationObject,
)

# ---------------------------------------------------------------------------
# shape_type -> geometry_type mapping (X-AnyLabeling JSON to platform domain)
# ---------------------------------------------------------------------------
_SHAPE_TYPE_MAP: dict[str, str] = {
    "rectangle": "bbox_xyxy",
    "rotation": "obb_polygon",
    "polygon": "polygon",
    "point": "keypoints",
}

# Reverse mapping for save
_GEOMETRY_TYPE_TO_SHAPE_TYPE: dict[str, str] = {
    v: k for k, v in _SHAPE_TYPE_MAP.items()
}


def _is_finite(value: float) -> bool:
    """Check if a float value is finite (not NaN, not Inf)."""
    return math.isfinite(value)


def _segments_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    """Check if two line segments (p1-p2) and (p3-p4) intersect.

    Uses orientation test.  Does NOT count collinear overlapping as intersection
    (endpoint sharing is allowed for polygon vertices).
    """

    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on_segment(a, b, c):
        return (
            min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])
        )

    o1 = orient(p1, p2, p3)
    o2 = orient(p1, p2, p4)
    o3 = orient(p3, p4, p1)
    o4 = orient(p3, p4, p2)

    if o1 == 0 and on_segment(p1, p2, p3):
        return True
    if o2 == 0 and on_segment(p1, p2, p4):
        return True
    if o3 == 0 and on_segment(p3, p4, p1):
        return True
    if o4 == 0 and on_segment(p3, p4, p2):
        return True

    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def _polygon_is_self_intersecting(points: list[tuple[float, float]]) -> bool:
    """Check if a polygon (list of vertices) is self-intersecting.

    Only checks non-adjacent edges.  Polygons with fewer than 4 vertices
    cannot self-intersect.
    """
    n = len(points)
    if n < 4:
        return False

    edges = [
        (points[i], points[(i + 1) % n])
        for i in range(n)
    ]

    for i in range(n):
        for j in range(i + 2, n):
            # Skip the edge that closes the loop (adjacent in wrap-around)
            if i == 0 and j == n - 1:
                continue
            if _segments_intersect(
                edges[i][0], edges[i][1], edges[j][0], edges[j][1]
            ):
                return True
    return False


class XLabelCodec:
    """Codec for X-AnyLabeling JSON format.

    Implements AnnotationCodec Protocol.
    Converts between X-AnyLabeling JSON and platform AnnotationDocument.

    Shape type mapping:
    - "rectangle" -> geometry_type="bbox_xyxy", 4-point CCW to (x1,y1,x2,y2)
    - "rotation"  -> geometry_type="obb_polygon", 4 points
    - "polygon"   -> geometry_type="polygon", N points
    - "point"     -> geometry_type="keypoints", N points
    - no shapes + has flags -> classification (image_labels)

    Unknown shape types -> validation warning, not silent discard.
    """

    def __init__(self, classes: list[str] | None = None) -> None:
        """Initialize codec with optional class name list.

        Args:
            classes: Ordered list of class names.  When provided, label_ids
                     are indices into this list during load/save.
        """
        self._classes: list[str] = list(classes) if classes else []

    # ------------------------------------------------------------------
    # load_annotations
    # ------------------------------------------------------------------
    def load_annotations(
        self,
        file_path: str | Path,
        image_width: int,
        image_height: int,
    ) -> AnnotationDocument:
        """Read X-AnyLabeling JSON file -> AnnotationDocument.

        Shape type mapping:
        - "rectangle" -> geometry_type="bbox_xyxy", 4-point to (x1,y1,x2,y2)
        - "rotation"  -> geometry_type="obb_polygon", 4 points
        - "polygon"   -> geometry_type="polygon", N points
        - "point"     -> geometry_type="keypoints", N points
        - no shapes + has flags -> classification

        Unknown shape types -> stored as polygon with warning info in attributes.
        """
        file_path = Path(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)

        asset_id = data.get("imagePath", file_path.stem)
        shapes: list[dict[str, Any]] = data.get("shapes", [])
        flags: dict[str, Any] = data.get("flags", {})

        objects: list[AnnotationObject] = []
        validation_warnings: list[str] = []

        for shape in shapes:
            shape_type = shape.get("shape_type", "")
            label_name = shape.get("label", "")
            points_raw = shape.get("points", [])
            difficult = shape.get("difficult", False)
            group_id = shape.get("group_id", None)
            description = shape.get("description", "")
            shape_attributes = shape.get("attributes", {})

            # Determine geometry_type
            geometry_type = _SHAPE_TYPE_MAP.get(shape_type)
            if geometry_type is None:
                # Unknown shape type -> treat as polygon with warning
                validation_warnings.append(
                    f"Unknown shape_type '{shape_type}' for label '{label_name}' "
                    f"in {file_path} — treating as polygon"
                )
                geometry_type = "polygon"

            # Convert points to list[tuple[float, float]]
            points: list[tuple[float, float]] = [
                (float(p[0]), float(p[1])) for p in points_raw
            ]

            # Build geometry value per geometry_type
            if geometry_type == "bbox_xyxy":
                # 4 points CCW -> (x1, y1, x2, y2)
                geometry = self._points_to_bbox_xyxy(points)
            elif geometry_type == "obb_polygon":
                geometry = points
            elif geometry_type == "polygon":
                geometry = points
            elif geometry_type == "keypoints":
                # point shapes: each shape may have multiple points
                # Store as list[tuple[float, float, int]]
                geometry = [(x, y, 2) for (x, y) in points]
            else:
                geometry = points  # fallback

            # Map label name to label_id
            label_id = self._get_or_create_label_id(label_name)

            obj = AnnotationObject(
                id=str(uuid.uuid4()),
                label_id=label_id,
                geometry_type=geometry_type,  # type: ignore[arg-type]
                geometry=geometry,
                attributes={
                    "label": label_name,
                    "difficult": difficult,
                    "group_id": group_id,
                    "description": description,
                    "shape_attributes": shape_attributes,
                },
            )
            objects.append(obj)

        # Log any validation warnings collected during load
        for warning in validation_warnings:
            logger.warning(warning)

        # Classification: no shapes, has non-empty flags with boolean values
        image_labels: dict[str, bool] = {}
        if not shapes and flags:
            # only boolean-valued flags count as classification labels
            image_labels = {
                k: bool(v)
                for k, v in flags.items()
                if isinstance(v, (bool, int, float)) and v
            }

        doc = AnnotationDocument(
            asset_id=asset_id,
            image_width=image_width,
            image_height=image_height,
            objects=objects,
            image_labels=image_labels,
        )

        # Run post-load validation and log any issues found.
        load_issues = self.validate_annotations(doc)
        for issue in load_issues:
            logger.warning("Validation issue in %s: %s", file_path, issue)

        return doc

    # ------------------------------------------------------------------
    # save_annotations
    # ------------------------------------------------------------------
    def save_annotations(
        self, doc: AnnotationDocument, file_path: str | Path
    ) -> None:
        """AnnotationDocument -> X-AnyLabeling JSON.

        Reverse of load_annotations.

        Validation issues detected here are logged as warnings but do
        **not** block the save — the user can still inspect the output
        and decide whether to correct the annotations later.
        """
        file_path = Path(file_path)

        # Pre-save validation: log issues but do not block.
        save_issues = self.validate_annotations(doc)
        for issue in save_issues:
            logger.warning("Validation issue in %s: %s", file_path, issue)

        shapes: list[dict[str, Any]] = []
        for obj in doc.objects:
            label_name = self._get_label_name(obj)
            shape_type = _GEOMETRY_TYPE_TO_SHAPE_TYPE.get(
                obj.geometry_type, "polygon"
            )

            # Convert geometry back to points
            points = self._geometry_to_points(obj)

            shape: dict[str, Any] = {
                "label": label_name,
                "score": None,
                "points": points,
                "group_id": obj.attributes.get("group_id"),
                "difficult": obj.attributes.get("difficult", False),
                "shape_type": shape_type,
                "flags": {},
                "description": obj.attributes.get("description", ""),
                "attributes": obj.attributes.get("shape_attributes", {}),
                "kie_linking": [],
            }
            shapes.append(shape)

        # Build flags from image_labels for classification
        flags: dict[str, Any] = {}
        if doc.image_labels:
            flags = dict(doc.image_labels)

        output: dict[str, Any] = {
            "version": "4.0.0-beta.7",
            "flags": flags,
            "checked": False,
            "shapes": shapes,
            "imagePath": doc.asset_id,
            "imageData": None,
            "imageHeight": doc.image_height,
            "imageWidth": doc.image_width,
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # validate_annotations
    # ------------------------------------------------------------------
    def validate_annotations(self, doc: AnnotationDocument) -> list[str]:
        """Validate an AnnotationDocument. Returns list of issues (empty = valid).

        Checks:
        - All shapes have valid label_ids
        - All coordinates are finite and within image bounds
        - Geometry type matches declared type
        - No self-intersecting polygons
        - Required fields present
        """
        issues: list[str] = []

        for i, obj in enumerate(doc.objects):
            prefix = f"object[{i}] ({obj.id})"

            # --- label_id validation ---
            if not isinstance(obj.label_id, int) or obj.label_id < 0:
                issues.append(f"{prefix}: invalid label_id={obj.label_id}")

            # --- required fields ---
            if not obj.id:
                issues.append(f"{prefix}: missing id")
            if obj.geometry_type not in (
                "bbox_xyxy",
                "polygon",
                "obb_polygon",
                "keypoints",
                "raster_mask",
            ):
                issues.append(
                    f"{prefix}: unknown geometry_type='{obj.geometry_type}'"
                )

            # --- geometry validation ---
            geom_issues = self._validate_geometry(
                obj, doc.image_width, doc.image_height, prefix
            )
            issues.extend(geom_issues)

        return issues

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _points_to_bbox_xyxy(
        points: list[tuple[float, float]],
    ) -> tuple[float, float, float, float]:
        """4-point CCW rectangle to (x1, y1, x2, y2)."""
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        # Use first vertex as x1,y1 and opposite as x2,y2
        # assuming CCW order: (x1,y1), (x2,y1), (x2,y2), (x1,y2)
        x1, y1 = min(xs), min(ys)
        x2, y2 = max(xs), max(ys)
        return (x1, y1, x2, y2)

    @staticmethod
    def _geometry_to_points(obj: AnnotationObject) -> list[list[float]]:
        """Convert AnnotationObject geometry back to points list."""
        gt = obj.geometry_type
        geom = obj.geometry

        if gt == "bbox_xyxy" and isinstance(geom, (tuple, list)) and len(geom) == 4:
            x1, y1, x2, y2 = geom
            return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

        if gt in ("polygon", "obb_polygon") and isinstance(geom, list):
            return [[p[0], p[1]] for p in geom]

        if gt == "keypoints" and isinstance(geom, list):
            return [[p[0], p[1]] for p in geom]

        # Fallback
        return []

    def _get_or_create_label_id(self, label_name: str) -> int:
        """Map a label name to an integer id.

        If classes were provided in constructor, use exact index match.
        Otherwise, extend internal class list.
        """
        if label_name in self._classes:
            return self._classes.index(label_name)
        # auto-register unknown label
        self._classes.append(label_name)
        return len(self._classes) - 1

    def _get_label_name(self, obj: AnnotationObject) -> str:
        """Extract label name from an AnnotationObject.

        Prefers attributes["label"]; falls back to classes list.
        """
        label = obj.attributes.get("label")
        if isinstance(label, str) and label:
            return label
        if 0 <= obj.label_id < len(self._classes):
            return self._classes[obj.label_id]
        return f"class_{obj.label_id}"

    def _validate_geometry(
        self,
        obj: AnnotationObject,
        image_width: int,
        image_height: int,
        prefix: str,
    ) -> list[str]:
        """Validate geometry coordinates for a single object."""
        issues: list[str] = []
        gt = obj.geometry_type
        geom = obj.geometry

        if geom is None:
            issues.append(f"{prefix}: geometry is None")
            return issues

        if gt == "bbox_xyxy":
            if not isinstance(geom, (tuple, list)) or len(geom) != 4:
                issues.append(
                    f"{prefix}: bbox_xyxy geometry should be (x1,y1,x2,y2), "
                    f"got {type(geom).__name__}"
                )
            else:
                x1, y1, x2, y2 = float(geom[0]), float(geom[1]), float(geom[2]), float(geom[3])
                for name, val in [("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)]:
                    if not _is_finite(val):
                        issues.append(f"{prefix}: {name}={val} is not finite")
                # Check within image bounds
                issues.extend(
                    self._check_bounds(
                        [(x1, y1), (x2, y2)],
                        image_width,
                        image_height,
                        prefix,
                    )
                )

        elif gt in ("polygon", "obb_polygon"):
            if not isinstance(geom, list):
                issues.append(
                    f"{prefix}: {gt} geometry should be a list of points"
                )
            else:
                points = [(float(p[0]), float(p[1])) for p in geom]
                for j, (x, y) in enumerate(points):
                    if not _is_finite(x) or not _is_finite(y):
                        issues.append(
                            f"{prefix}: point[{j}]=({x},{y}) is not finite"
                        )
                issues.extend(
                    self._check_bounds(points, image_width, image_height, prefix)
                )
                if gt == "polygon" and len(points) >= 3:
                    if _polygon_is_self_intersecting(points):
                        issues.append(
                            f"{prefix}: polygon is self-intersecting"
                        )

        elif gt == "keypoints":
            if not isinstance(geom, list):
                issues.append(
                    f"{prefix}: keypoints geometry should be a list of (x,y,v) tuples"
                )
            else:
                for j, kp in enumerate(geom):
                    x = float(kp[0])
                    y = float(kp[1])
                    if not _is_finite(x) or not _is_finite(y):
                        issues.append(
                            f"{prefix}: keypoint[{j}]=({x},{y}) is not finite"
                        )
                    if not (0 <= x <= image_width and 0 <= y <= image_height):
                        issues.append(
                            f"{prefix}: keypoint[{j}]=({x},{y}) out of bounds"
                        )

        return issues

    @staticmethod
    def _check_bounds(
        points: list[tuple[float, float]],
        image_width: int,
        image_height: int,
        prefix: str,
    ) -> list[str]:
        """Check if any point is outside image bounds (allow small negative due to edge cases)."""
        issues: list[str] = []
        margin = -1.0  # tolerate sub-pixel negative rounding
        for j, (x, y) in enumerate(points):
            if x < margin or x > image_width + 1:
                issues.append(
                    f"{prefix}: point[{j}].x={x} outside [0, {image_width}]"
                )
            if y < margin or y > image_height + 1:
                issues.append(
                    f"{prefix}: point[{j}].y={y} outside [0, {image_height}]"
                )
        return issues


__all__ = ["XLabelCodec"]

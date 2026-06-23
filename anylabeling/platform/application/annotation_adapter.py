"""AnnotationAdapter — Shape ↔ AnnotationObject bridge.

Connects the existing `views/labeling/` annotation UI with the platform
domain model without modifying either side.
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task family → allowed Canvas shape_types
# ---------------------------------------------------------------------------
_FAMILY_SHAPE_TYPE_MAP: dict[str, list[str]] = {
    "classification": [],
    "detection_hbb": ["rectangle"],
    "detection_obb": ["rotation"],
    "instance_segmentation": ["polygon"],
    "pose": ["point"],
    "semantic_segmentation": ["polygon"],
    "anomaly": ["rectangle", "polygon"],
}


def get_allowed_shape_types(family: str) -> list[str]:
    """Return Canvas shape_type strings allowed for *family*.

    Returns empty list for families that use image_labels only (e.g. classification).
    """
    return list(_FAMILY_SHAPE_TYPE_MAP.get(family, []))


# ---------------------------------------------------------------------------
# Shape type ↔ geometry_type mapping
# ---------------------------------------------------------------------------
_SHAPE_TO_GEOMETRY: dict[str, str] = {
    "rectangle": "bbox_xyxy",
    "rotation": "obb_polygon",
    "polygon": "polygon",
    "point": "keypoints",
}
_GEOMETRY_TO_SHAPE: dict[str, str] = {
    v: k for k, v in _SHAPE_TO_GEOMETRY.items()
}


def shape_type_to_geometry_type(shape_type: str) -> str:
    """Map Canvas shape_type to platform geometry_type. Unknown → "polygon"."""
    return _SHAPE_TO_GEOMETRY.get(shape_type, "polygon")


def geometry_type_to_shape_type(geometry_type: str) -> str:
    """Map platform geometry_type to Canvas shape_type. Unknown → "polygon"."""
    return _GEOMETRY_TO_SHAPE.get(geometry_type, "polygon")


# ---------------------------------------------------------------------------
# Shape ↔ AnnotationDocument conversion
# ---------------------------------------------------------------------------

def shapes_to_annotation_doc(
    shapes: list,
    asset_id: str,
    image_width: int,
    image_height: int,
    label_name_to_id: dict[str, int],
) -> "AnnotationDocument":
    """Convert LabelingWidget Shape objects → AnnotationDocument."""
    from anylabeling.platform.domain.annotation import (
        AnnotationDocument,
        AnnotationObject,
    )

    objects: list[AnnotationObject] = []
    for shape in shapes:
        shape_type = getattr(shape, "shape_type", "polygon")
        label_name = getattr(shape, "label", "")
        label_id = label_name_to_id.get(label_name, -1)

        geometry_type = shape_type_to_geometry_type(shape_type)

        points_raw = getattr(shape, "points", [])
        if geometry_type == "bbox_xyxy":
            xs = [p.x() for p in points_raw]
            ys = [p.y() for p in points_raw]
            if xs and ys:
                geometry = (min(xs), min(ys), max(xs), max(ys))
            else:
                geometry = (0.0, 0.0, 0.0, 0.0)
        elif geometry_type == "keypoints":
            geometry = [(p.x(), p.y(), 2) for p in points_raw]
        else:
            geometry = [(p.x(), p.y()) for p in points_raw]

        obj = AnnotationObject(
            id=str(uuid.uuid4()),
            label_id=label_id,
            geometry_type=geometry_type,
            geometry=geometry,
            attributes={
                "label": label_name,
                "difficult": getattr(shape, "difficult", False),
                "group_id": getattr(shape, "group_id"),
                "description": getattr(shape, "description", ""),
            },
        )
        objects.append(obj)

    return AnnotationDocument(
        asset_id=asset_id,
        image_width=image_width,
        image_height=image_height,
        objects=objects,
    )


def annotation_doc_to_shapes(doc: "AnnotationDocument") -> list[dict]:
    """Convert AnnotationDocument → list of Shape-compatible dicts.

    Each dict has: shape_type, label, points, group_id, difficult, description.
    """
    result: list[dict] = []
    for obj in doc.objects:
        shape_type = geometry_type_to_shape_type(obj.geometry_type)
        geom = obj.geometry

        if obj.geometry_type == "bbox_xyxy" and isinstance(geom, (tuple, list)) and len(geom) == 4:
            x1, y1, x2, y2 = float(geom[0]), float(geom[1]), float(geom[2]), float(geom[3])
            points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        elif obj.geometry_type == "keypoints" and isinstance(geom, list):
            points = [(float(p[0]), float(p[1])) for p in geom]
        elif isinstance(geom, list):
            points = [(float(p[0]), float(p[1])) for p in geom]
        else:
            points = []

        result.append({
            "shape_type": shape_type,
            "label": obj.attributes.get("label", ""),
            "points": points,
            "group_id": obj.attributes.get("group_id"),
            "difficult": obj.attributes.get("difficult", False),
            "description": obj.attributes.get("description", ""),
        })

    return result


# ---------------------------------------------------------------------------
# Convenience load/save helpers
# ---------------------------------------------------------------------------

def load_annotations_for_asset(
    asset_path: str | Path,
    project_path: str | Path,
) -> list[dict] | None:
    """Load annotations for an asset. Returns Shape-compatible dicts or None."""
    asset_path = Path(asset_path)
    project_path = Path(project_path)
    ann_path = project_path / "annotations" / f"{asset_path.stem}.json"

    if not ann_path.exists():
        return None

    from anylabeling.platform.infrastructure.image_reader import ImageReader
    meta = ImageReader.metadata(str(asset_path))
    if meta.width == 0:
        return None
    w, h = meta.width, meta.height

    from anylabeling.platform.application.annotation_service import XLabelCodec
    codec = XLabelCodec()
    doc = codec.load_annotations(ann_path, w, h)
    return annotation_doc_to_shapes(doc)


def save_annotations_for_asset(
    asset_path: str | Path,
    shapes: list,
    project_path: str | Path,
    label_name_to_id: dict[str, int],
) -> None:
    """Save annotations for an asset to project/annotations/{asset_id}.json."""
    asset_path = Path(asset_path)
    project_path = Path(project_path)
    ann_dir = project_path / "annotations"
    ann_dir.mkdir(parents=True, exist_ok=True)
    ann_path = ann_dir / f"{asset_path.stem}.json"

    from anylabeling.platform.infrastructure.image_reader import ImageReader
    meta = ImageReader.metadata(str(asset_path))
    if meta.width == 0:
        return
    w, h = meta.width, meta.height

    doc = shapes_to_annotation_doc(shapes, asset_path.stem, w, h, label_name_to_id)

    from anylabeling.platform.application.annotation_service import XLabelCodec
    codec = XLabelCodec()
    codec.save_annotations(doc, ann_path)


# ---------------------------------------------------------------------------
# Phase 3b: Atomic save + crash recovery
# ---------------------------------------------------------------------------


def save_annotations_atomic(
    shapes: list,
    asset_path: str | Path,
    project_path: str | Path,
    label_name_to_id: dict[str, int],
) -> bool:
    """Save annotations atomically: write .tmp → validate → os.replace → .json.

    Uses the AtomicWriter pattern: serializes to a temporary sidecar first,
    then atomically replaces the target file.  This guarantees that readers
    (and crashes) never see a partial or corrupt file.

    Returns:
        True if the atomic write + replace succeeded.
    """
    import os as _os

    asset_path = Path(asset_path)
    project_path = Path(project_path)
    ann_dir = project_path / "annotations"
    ann_dir.mkdir(parents=True, exist_ok=True)

    target = ann_dir / f"{asset_path.stem}.json"
    tmp = target.with_suffix(".json.tmp")

    from anylabeling.platform.infrastructure.image_reader import ImageReader
    meta = ImageReader.metadata(str(asset_path))
    if meta.width == 0:
        return False
    w, h = meta.width, meta.height

    doc = shapes_to_annotation_doc(
        shapes, asset_path.stem, w, h, label_name_to_id
    )

    from anylabeling.platform.application.annotation_service import XLabelCodec
    codec = XLabelCodec()
    try:
        # 1. Write to .tmp
        codec.save_annotations(doc, tmp)

        # 2. Validate by re-reading
        loaded = codec.load_annotations(tmp, w, h)
        if loaded.asset_id != doc.asset_id:
            raise ValueError(
                "Validation failed: asset_id mismatch "
                f"({loaded.asset_id} != {doc.asset_id})"
            )

        # 3. Atomic replace
        _os.replace(tmp, target)
        return True
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.exception(
            "Atomic save failed for %s", asset_path.stem
        )
        # Best-effort cleanup
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        return False


def find_recovery_files(project_path: str | Path) -> list[Path]:
    """Scan ``annotations/`` directory for orphaned ``.tmp`` files.

    These are left behind when a crash occurs after writing the temp file
    but before the atomic ``os.replace`` completes.

    Returns:
        List of absolute paths to recoverable ``.tmp`` files.
    """
    project_path = Path(project_path)
    ann_dir = project_path / "annotations"
    if not ann_dir.is_dir():
        return []
    return sorted(ann_dir.glob("*.json.tmp"))


def recover_from_tmp(
    tmp_path: str | Path,
    image_width: int,
    image_height: int,
) -> "AnnotationDocument | None":
    """Attempt to load a ``.tmp`` recovery file.

    Returns:
        ``AnnotationDocument`` on success, ``None`` if the file is
        missing, corrupted, or otherwise unrecoverable.
    """
    tmp_path = Path(tmp_path)

    if not tmp_path.exists():
        return None

    from anylabeling.platform.application.annotation_service import XLabelCodec
    codec = XLabelCodec()
    try:
        doc = codec.load_annotations(tmp_path, image_width, image_height)
        if doc.asset_id:
            return doc
        return None
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.exception("Recovery failed for %s", tmp_path)
        return None


__all__ = [
    "get_allowed_shape_types",
    "shape_type_to_geometry_type",
    "geometry_type_to_shape_type",
    "shapes_to_annotation_doc",
    "annotation_doc_to_shapes",
    "load_annotations_for_asset",
    "save_annotations_for_asset",
    "save_annotations_atomic",
    "find_recovery_files",
    "recover_from_tmp",
]

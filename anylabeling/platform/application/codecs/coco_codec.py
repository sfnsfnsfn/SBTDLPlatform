"""COCOCodec — parse COCO JSON into AnnotationDocument objects.

COCO format:
    {
      "images": [{"id": int, "file_name": str, "width": int, "height": int}, ...],
      "annotations": [
        {"id": int, "image_id": int, "category_id": int,
         "bbox": [x, y, width, height], "area": float, ...}, ...
      ],
      "categories": [{"id": int, "name": str, "supercategory": str}, ...]
    }

Bbox format in COCO is [x, y, width, height] (top-left origin).
This codec converts to L0 xyxy format and groups by image_id.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject

logger = logging.getLogger(__name__)


class COCOCodec:
    """Parse COCO JSON into a dict of AnnotationDocument keyed by filename.

    Bbox format: COCO uses [x, y, width, height] (top-left origin).
    This codec converts to L0 [x1, y1, x2, y2].
    """

    def load_annotations(
        self,
        file_path: str | Path,
    ) -> dict[str, AnnotationDocument]:
        """Parse a COCO JSON file into AnnotationDocuments grouped by image.

        Args:
            file_path: Path to the COCO JSON file.

        Returns:
            Dict mapping filename → AnnotationDocument.
        """
        file_path = Path(file_path)

        if not file_path.is_file():
            logger.warning("COCO annotation file not found: %s", file_path)
            return {}

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to read COCO JSON %s: %s", file_path, exc)
            return {}

        images = data.get("images", [])
        annotations = data.get("annotations", [])
        categories = data.get("categories", [])

        # Build image_id → image info map
        image_map: dict[int, dict] = {}
        for img in images:
            image_map[img["id"]] = img

        # Build category_id → category info map
        category_map: dict[int, dict] = {}
        for cat in categories:
            category_map[cat["id"]] = cat

        # Group annotations by image_id
        ann_by_image: dict[int, list[dict]] = {}
        for ann in annotations:
            img_id = ann.get("image_id")
            if img_id is None:
                continue
            ann_by_image.setdefault(img_id, []).append(ann)

        # Build AnnotationDocument per image
        result: dict[str, AnnotationDocument] = {}

        for img_id, img_info in image_map.items():
            filename = img_info.get("file_name", str(img_id))
            img_w = img_info.get("width", 0)
            img_h = img_info.get("height", 0)

            anns = ann_by_image.get(img_id, [])
            objects: list[AnnotationObject] = []

            for ann in anns:
                obj = self._parse_annotation(ann, category_map)
                if obj is not None:
                    objects.append(obj)

            result[filename] = AnnotationDocument(
                asset_id=Path(filename).stem,
                image_width=img_w,
                image_height=img_h,
                objects=objects,
            )

        # Handle annotations without matching images
        orphan_imgs = set(ann_by_image) - set(image_map)
        if orphan_imgs:
            logger.warning(
                "COCO JSON %s: %d annotation(s) reference unknown image_id(s): %s",
                file_path,
                sum(len(ann_by_image[oid]) for oid in orphan_imgs),
                sorted(orphan_imgs)[:10],
            )

        return result

    def save_annotations(
        self,
        docs: dict[str, AnnotationDocument],
        file_path: str | Path,
    ) -> None:
        """Save AnnotationDocuments to a COCO JSON file.

        Args:
            docs: Dict mapping filename → AnnotationDocument.
            file_path: Where to write the COCO JSON file.
        """
        file_path = Path(file_path)

        images: list[dict] = []
        annotations: list[dict] = []
        categories: dict[int, str] = {}  # label_id → name
        ann_id = 1

        for img_id_num, (filename, doc) in enumerate(
            sorted(docs.items()), start=1
        ):
            images.append({
                "id": img_id_num,
                "file_name": filename,
                "width": doc.image_width,
                "height": doc.image_height,
            })

            for obj in doc.objects:
                if obj.label_id not in categories:
                    categories[obj.label_id] = f"class_{obj.label_id}"
                if obj.geometry_type != "bbox_xyxy":
                    continue
                x1, y1, x2, y2 = obj.geometry
                annotations.append({
                    "id": ann_id,
                    "image_id": img_id_num,
                    "category_id": obj.label_id,
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "area": (x2 - x1) * (y2 - y1),
                    "iscrowd": 0,
                })
                ann_id += 1

        cat_list = [
            {"id": cid, "name": cname, "supercategory": ""}
            for cid, cname in sorted(categories.items())
        ]

        output = {
            "images": images,
            "annotations": annotations,
            "categories": cat_list,
        }

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(output, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def validate_annotations(self, doc: AnnotationDocument) -> list[str]:
        """Validate an AnnotationDocument for COCO constraints.

        Returns list of issues (empty = valid).
        """
        issues: list[str] = []

        if doc.image_width <= 0 or doc.image_height <= 0:
            issues.append("Image dimensions must be positive")

        for i, obj in enumerate(doc.objects):
            if obj.geometry_type != "bbox_xyxy":
                issues.append(
                    f"Object {i} ({obj.id}): COCO only supports bbox_xyxy, "
                    f"got {obj.geometry_type}"
                )
                continue

            x1, y1, x2, y2 = obj.geometry
            if not (
                0 <= x1 <= doc.image_width
                and 0 <= y1 <= doc.image_height
                and 0 <= x2 <= doc.image_width
                and 0 <= y2 <= doc.image_height
            ):
                issues.append(
                    f"Object {i} ({obj.id}): coordinates out of bounds "
                    f"({x1}, {y1}, {x2}, {y2}) for "
                    f"{doc.image_width}x{doc.image_height}"
                )

        return issues

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_annotation(
        ann: dict,
        category_map: dict[int, dict] | None = None,
    ) -> AnnotationObject | None:
        """Parse a single COCO annotation entry into an AnnotationObject.

        COCO bbox: [x, y, width, height] (top-left origin).
        """
        ann_id = str(ann.get("id", "unknown"))
        category_id = ann.get("category_id", 0)
        bbox = ann.get("bbox")

        if bbox is None or len(bbox) < 4:
            logger.warning("COCO annotation %s: missing or invalid bbox", ann_id)
            return None

        x, y, w, h = bbox[0], bbox[1], bbox[2], bbox[3]

        # Convert COCO bbox [x, y, w, h] → L0 xyxy
        x1 = x
        y1 = y
        x2 = x + w
        y2 = y + h

        if w <= 0 or h <= 0:
            return None

        # Check for segmentation/iscrowd metadata
        attrs: dict = {}
        if ann.get("iscrowd", 0) == 1:
            attrs["iscrowd"] = True
        if ann.get("area") is not None:
            attrs["area"] = ann["area"]

        # Map category_id to name if category_map is available
        if category_map and category_id in category_map:
            attrs["category_name"] = category_map[category_id].get(
                "name", str(category_id)
            )

        return AnnotationObject(
            id=f"coco_{ann_id}",
            label_id=category_id,
            geometry_type="bbox_xyxy",
            geometry=(x1, y1, x2, y2),
            attributes=attrs,
        )


__all__ = ["COCOCodec"]

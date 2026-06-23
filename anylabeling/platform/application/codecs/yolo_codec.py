"""YOLOCodec — parse YOLO detection format .txt files into AnnotationDocument.

Each .txt file corresponds to one image. Each line:
    class_id x_center y_center width height  (all 0-1 normalized)

Also handles YOLO OBB format (class_id x1 y1 x2 y2 x3 y3 x4 y4, normalized)
and YOLO pose/keypoint format (class_id x y w h kx1 ky1 kv1 ...).
"""

from __future__ import annotations

import logging
from pathlib import Path

from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject

logger = logging.getLogger(__name__)


class YOLOCodec:
    """Parse YOLO detection format .txt files into AnnotationDocument.

    Each .txt corresponds to one image. Each line:
        class_id x_center y_center width height  (all 0-1 normalized)

    Also handles:
    - YOLO OBB:  class_id x1 y1 x2 y2 x3 y3 x4 y4 (9 fields, normalized)
    - YOLO pose: class_id x_center y_center width height kx1 ky1 kv1 ... (≥6 fields)

    Unknown formats with unexpected field counts are skipped with a warning.
    """

    def load_annotations(
        self,
        file_path: str | Path,
        image_width: int,
        image_height: int,
    ) -> AnnotationDocument:
        """Parse a YOLO .txt file into an AnnotationDocument.

        Args:
            file_path: Path to the YOLO .txt annotation file.
            image_width: Image width in pixels (L0 coordinate space).
            image_height: Image height in pixels (L0 coordinate space).

        Returns:
            AnnotationDocument with objects in L0 image coordinates.
        """
        file_path = Path(file_path)
        asset_id = file_path.stem
        objects: list[AnnotationObject] = []

        if not file_path.is_file():
            logger.warning("YOLO annotation file not found: %s", file_path)
            return AnnotationDocument(
                asset_id=asset_id,
                image_width=image_width,
                image_height=image_height,
                objects=[],
            )

        with open(file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped:
                    continue

                parts = stripped.split()
                num_fields = len(parts)

                try:
                    if num_fields == 5:
                        # Standard bbox format
                        obj = self._parse_bbox(
                            parts, image_width, image_height, line_num
                        )
                    elif num_fields == 9:
                        # OBB format (4 normalized corner points)
                        obj = self._parse_obb(
                            parts, image_width, image_height, line_num
                        )
                    elif num_fields >= 6 and (num_fields - 5) % 3 == 0:
                        # Pose/keypoint format: extract the bbox portion
                        obj = self._parse_bbox(
                            parts, image_width, image_height, line_num
                        )
                    else:
                        logger.warning(
                            "YOLO line %d in %s: unexpected %d fields, skipped",
                            line_num, file_path, num_fields,
                        )
                        continue

                    if obj is not None:
                        objects.append(obj)
                except (ValueError, IndexError) as exc:
                    logger.warning(
                        "YOLO line %d in %s: parse error: %s",
                        line_num, file_path, exc,
                    )
                    continue

        return AnnotationDocument(
            asset_id=asset_id,
            image_width=image_width,
            image_height=image_height,
            objects=objects,
        )

    def save_annotations(
        self, doc: AnnotationDocument, file_path: str | Path
    ) -> None:
        """Save an AnnotationDocument to a YOLO .txt file.

        All objects must have geometry_type 'bbox_xyxy' with 4-element tuple.

        Args:
            doc: AnnotationDocument to serialize.
            file_path: Where to write the YOLO .txt file.
        """
        file_path = Path(file_path)
        lines: list[str] = []

        w = doc.image_width
        h = doc.image_height

        for obj in doc.objects:
            if obj.geometry_type != "bbox_xyxy":
                continue
            x1, y1, x2, y2 = obj.geometry
            # Convert from L0 coords to YOLO normalized format
            x_center = ((x1 + x2) / 2) / w
            y_center = ((y1 + y2) / 2) / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            lines.append(
                f"{obj.label_id} {x_center:.6f} {y_center:.6f} "
                f"{bw:.6f} {bh:.6f}"
            )

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def validate_annotations(self, doc: AnnotationDocument) -> list[str]:
        """Validate an AnnotationDocument for YOLO constraints.

        Returns list of issues (empty = valid).
        """
        issues: list[str] = []

        if doc.image_width <= 0 or doc.image_height <= 0:
            issues.append("Image dimensions must be positive")

        for i, obj in enumerate(doc.objects):
            if obj.geometry_type != "bbox_xyxy":
                issues.append(
                    f"Object {i} ({obj.id}): YOLO only supports bbox_xyxy, "
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
            if x2 <= x1 or y2 <= y1:
                issues.append(
                    f"Object {i} ({obj.id}): invalid bbox ({x1}, {y1}, {x2}, {y2})"
                )

        return issues

    # ------------------------------------------------------------------
    # Internal parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_bbox(
        parts: list[str],
        image_width: int,
        image_height: int,
        line_num: int = 0,
    ) -> AnnotationObject | None:
        """Parse standard YOLO bbox: cls_id xc yc w h (normalized).

        Returns an AnnotationObject in L0 (pixel) coordinates.
        """
        cls_id = int(parts[0])
        x_c, y_c, bw, bh = map(float, parts[1:5])

        # Denormalize to L0 image coordinates
        x1 = max(0.0, (x_c - bw / 2) * image_width)
        y1 = max(0.0, (y_c - bh / 2) * image_height)
        x2 = min(float(image_width), (x_c + bw / 2) * image_width)
        y2 = min(float(image_height), (y_c + bh / 2) * image_height)

        if x2 <= x1 or y2 <= y1:
            return None

        return AnnotationObject(
            id=f"obj_{line_num}",
            label_id=cls_id,
            geometry_type="bbox_xyxy",
            geometry=(x1, y1, x2, y2),
        )

    @staticmethod
    def _parse_obb(
        parts: list[str],
        image_width: int,
        image_height: int,
        line_num: int = 0,
    ) -> AnnotationObject:
        """Parse YOLO OBB format: cls_id x1 y1 x2 y2 x3 y3 x4 y4 (normalized).

        Returns an AnnotationObject with geometry_type 'obb_polygon'.
        """
        cls_id = int(parts[0])
        coords = [float(v) for v in parts[1:9]]

        points: list[tuple[float, float]] = []
        for i in range(0, 8, 2):
            px = coords[i] * image_width
            py = coords[i + 1] * image_height
            points.append((px, py))

        return AnnotationObject(
            id=f"obj_{line_num}",
            label_id=cls_id,
            geometry_type="obb_polygon",
            geometry=points,
        )


__all__ = ["YOLOCodec"]

"""VOCCodec — parse Pascal VOC XML annotation files into AnnotationDocument.

Each image has one XML file with structure:
    <annotation>
        <filename>image.jpg</filename>
        <size>
            <width>640</width>
            <height>480</height>
            <depth>3</depth>
        </size>
        <object>
            <name>person</name>
            <bndbox>
                <xmin>10</xmin>
                <ymin>20</ymin>
                <xmax>200</xmax>
                <ymax>300</ymax>
            </bndbox>
        </object>
    </annotation>

VOC coordinates are absolute pixels (L0), so no conversion is needed.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject

logger = logging.getLogger(__name__)


class VOCCodec:
    """Parse Pascal VOC XML annotation files into AnnotationDocument.

    Each .xml file corresponds to one image.
    VOC coordinates are absolute (L0 pixels), no denormalization needed.
    """

    def load_annotations(
        self,
        file_path: str | Path,
        image_width: int = 0,
        image_height: int = 0,
    ) -> AnnotationDocument:
        """Parse a Pascal VOC XML file into an AnnotationDocument.

        Args:
            file_path: Path to the VOC .xml annotation file.
            image_width: Override image width (0 = read from XML <size>).
            image_height: Override image height (0 = read from XML <size>).

        Returns:
            AnnotationDocument with objects in L0 image coordinates.
        """
        file_path = Path(file_path)
        asset_id = file_path.stem
        objects: list[AnnotationObject] = []

        if not file_path.is_file():
            logger.warning("VOC annotation file not found: %s", file_path)
            return AnnotationDocument(
                asset_id=asset_id,
                image_width=image_width,
                image_height=image_height,
                objects=[],
            )

        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except ET.ParseError as exc:
            logger.error(
                "Failed to parse VOC XML %s: %s", file_path, exc
            )
            return AnnotationDocument(
                asset_id=asset_id,
                image_width=image_width,
                image_height=image_height,
                objects=[],
            )

        # Read image size from <size> element
        img_w = image_width
        img_h = image_height

        size_elem = root.find("size")
        if size_elem is not None and (image_width == 0 or image_height == 0):
            w_elem = size_elem.find("width")
            h_elem = size_elem.find("height")
            if w_elem is not None and img_w == 0:
                try:
                    img_w = int(w_elem.text or "0")
                except ValueError:
                    pass
            if h_elem is not None and img_h == 0:
                try:
                    img_h = int(h_elem.text or "0")
                except ValueError:
                    pass

        # Parse objects
        for i, obj_elem in enumerate(root.findall("object")):
            obj = self._parse_object(obj_elem, i)
            if obj is not None:
                objects.append(obj)

        return AnnotationDocument(
            asset_id=asset_id,
            image_width=img_w,
            image_height=img_h,
            objects=objects,
        )

    def save_annotations(
        self, doc: AnnotationDocument, file_path: str | Path
    ) -> None:
        """Save an AnnotationDocument to a Pascal VOC XML file.

        Args:
            doc: AnnotationDocument to serialize.
            file_path: Where to write the VOC .xml file.
        """
        file_path = Path(file_path)

        root = ET.Element("annotation")

        # Source
        source = ET.SubElement(root, "source")
        ET.SubElement(source, "database").text = "X-AnyLabeling"

        # Filename
        ET.SubElement(root, "filename").text = f"{doc.asset_id}.jpg"

        # Size
        size = ET.SubElement(root, "size")
        ET.SubElement(size, "width").text = str(doc.image_width)
        ET.SubElement(size, "height").text = str(doc.image_height)
        ET.SubElement(size, "depth").text = "3"

        # Segmented flag
        ET.SubElement(root, "segmented").text = "0"

        # Objects
        for obj in doc.objects:
            if obj.geometry_type != "bbox_xyxy":
                continue
            obj_elem = ET.SubElement(root, "object")
            # Use category_name from attributes or fallback to str label_id
            label_name = obj.attributes.get(
                "category_name", str(obj.label_id)
            )
            ET.SubElement(obj_elem, "name").text = str(label_name)
            ET.SubElement(obj_elem, "pose").text = (
                obj.attributes.get("pose", "Unspecified")
            )
            ET.SubElement(obj_elem, "truncated").text = "0"
            ET.SubElement(obj_elem, "difficult").text = "0"

            x1, y1, x2, y2 = obj.geometry
            bndbox = ET.SubElement(obj_elem, "bndbox")
            ET.SubElement(bndbox, "xmin").text = str(int(x1))
            ET.SubElement(bndbox, "ymin").text = str(int(y1))
            ET.SubElement(bndbox, "xmax").text = str(int(x2))
            ET.SubElement(bndbox, "ymax").text = str(int(y2))

        # Pretty-print XML
        self._indent_xml(root)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        tree = ET.ElementTree(root)
        tree.write(file_path, encoding="utf-8", xml_declaration=True)

    def validate_annotations(self, doc: AnnotationDocument) -> list[str]:
        """Validate an AnnotationDocument for VOC constraints.

        Returns list of issues (empty = valid).
        """
        issues: list[str] = []

        if doc.image_width <= 0 or doc.image_height <= 0:
            issues.append("Image dimensions must be positive")

        for i, obj in enumerate(doc.objects):
            if obj.geometry_type != "bbox_xyxy":
                issues.append(
                    f"Object {i} ({obj.id}): VOC only supports bbox_xyxy, "
                    f"got {obj.geometry_type}"
                )
                continue

            x1, y1, x2, y2 = obj.geometry
            if x2 <= x1 or y2 <= y1:
                issues.append(
                    f"Object {i} ({obj.id}): invalid bbox "
                    f"({x1}, {y1}, {x2}, {y2})"
                )

        return issues

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_object(
        obj_elem: ET.Element, index: int,
    ) -> AnnotationObject | None:
        """Parse a single VOC <object> element into an AnnotationObject.

        Args:
            obj_elem: The <object> XML element.
            index: Object index for generating unique IDs.

        Returns:
            AnnotationObject or None if parsing fails.
        """
        # Get object name (label)
        name_elem = obj_elem.find("name")
        if name_elem is None or not name_elem.text:
            logger.warning(
                "VOC object %d: missing <name>, skipped", index
            )
            return None

        label_name = name_elem.text.strip()
        if not label_name:
            return None

        # Get bounding box
        bndbox = obj_elem.find("bndbox")
        if bndbox is None:
            logger.warning(
                "VOC object %d (%s): missing <bndbox>, skipped",
                index, label_name,
            )
            return None

        try:
            xmin = float(bndbox.findtext("xmin", "0"))
            ymin = float(bndbox.findtext("ymin", "0"))
            xmax = float(bndbox.findtext("xmax", "0"))
            ymax = float(bndbox.findtext("ymax", "0"))
        except (ValueError, TypeError) as exc:
            logger.warning(
                "VOC object %d (%s): invalid bndbox values: %s",
                index, label_name, exc,
            )
            return None

        if xmax <= xmin or ymax <= ymin:
            logger.warning(
                "VOC object %d (%s): invalid bbox (%s, %s, %s, %s)",
                index, label_name, xmin, ymin, xmax, ymax,
            )
            return None

        # Collect additional attributes
        attrs: dict = {"category_name": label_name}

        for tag in ("pose", "truncated", "difficult"):
            elem = obj_elem.find(tag)
            if elem is not None and elem.text:
                attrs[tag] = elem.text

        # Use label_name as label_id (caller should map to project labels)
        return AnnotationObject(
            id=f"voc_{index}",
            label_id=hash(label_name) % 100000,
            geometry_type="bbox_xyxy",
            geometry=(xmin, ymin, xmax, ymax),
            attributes=attrs,
        )

    @staticmethod
    def _indent_xml(elem: ET.Element, level: int = 0) -> None:
        """Pretty-print XML by adding indentation."""
        indent = "\n" + "  " * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            for child in elem:
                VOCCodec._indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent
        else:
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent


__all__ = ["VOCCodec"]

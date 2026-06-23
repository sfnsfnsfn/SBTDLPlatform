"""Codec package — convert between external annotation formats and platform
AnnotationDocument.

All codecs follow the AnnotationCodec Protocol defined in
``anylabeling.platform.application.ports``.

YOLO:      One .txt per image, normalized coordinates → L0 coordinates.
COCO:      Single JSON with images/annotations/categories.
VOC:       Pascal VOC XML (one .xml per image).
"""

from anylabeling.platform.application.codecs.coco_codec import COCOCodec
from anylabeling.platform.application.codecs.voc_codec import VOCCodec
from anylabeling.platform.application.codecs.yolo_codec import YOLOCodec

__all__ = ["COCOCodec", "VOCCodec", "YOLOCodec"]

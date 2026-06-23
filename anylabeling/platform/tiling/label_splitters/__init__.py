"""Label splitters — split AnnotationObjects from L0 image coordinates
to tile-local coordinates for five task families.

Each splitter implements the ``LabelSplitter`` protocol:
- ``task_family`` — string identifying the Vision AI task family
- ``split(annotations, tile, plan)`` — returns ``list[AnnotationObject]`` in
  tile-local coordinates, with ``source_object_id`` preserved.

Splitters are pure Python with no UI or framework imports.
"""

from anylabeling.platform.tiling.label_splitters.hbb import HBBSplitter
from anylabeling.platform.tiling.label_splitters.obb import OBBSplitter
from anylabeling.platform.tiling.label_splitters.polygon import PolygonSplitter
from anylabeling.platform.tiling.label_splitters.pose import PoseSplitter
from anylabeling.platform.tiling.label_splitters.classify import ClassifySplitter

__all__ = [
    "HBBSplitter",
    "OBBSplitter",
    "PolygonSplitter",
    "PoseSplitter",
    "ClassifySplitter",
]

"""Register Ultralytics YOLO algorithm capabilities.

Importing this module registers all supported YOLO variants
with the AlgorithmRegistry.  Capabilities are pure data — no
Ultralytics or PyTorch imports are required.
"""

from __future__ import annotations

from anylabeling.platform.adapters.registry import (
    AlgorithmCapabilities,
    AlgorithmRegistry,
)

_CAPABILITIES = [
    AlgorithmCapabilities(
        adapter_id="ultralytics_yolo_classify",
        display_name="Ultralytics YOLO Classification",
        task_families=frozenset({"classification"}),
        supports_training=True,
        supports_validation=True,
        supports_export_onnx=True,
        supports_sliced_inference=False,
    ),
    AlgorithmCapabilities(
        adapter_id="ultralytics_yolo_detect",
        display_name="Ultralytics YOLO Detection (HBB)",
        task_families=frozenset({"detection_hbb"}),
        supports_training=True,
        supports_validation=True,
        supports_export_onnx=True,
        supports_sliced_inference=False,
    ),
    AlgorithmCapabilities(
        adapter_id="ultralytics_yolo_obb",
        display_name="Ultralytics YOLO OBB Detection",
        task_families=frozenset({"detection_obb"}),
        supports_training=True,
        supports_validation=True,
        supports_export_onnx=True,
        supports_sliced_inference=False,
    ),
    AlgorithmCapabilities(
        adapter_id="ultralytics_yolo_segment",
        display_name="Ultralytics YOLO Instance Segmentation",
        task_families=frozenset({"instance_segmentation"}),
        supports_training=True,
        supports_validation=True,
        supports_export_onnx=True,
        supports_sliced_inference=False,
    ),
    AlgorithmCapabilities(
        adapter_id="ultralytics_yolo_pose",
        display_name="Ultralytics YOLO Pose Estimation",
        task_families=frozenset({"pose"}),
        supports_training=True,
        supports_validation=True,
        supports_export_onnx=True,
        supports_sliced_inference=False,
    ),
]

for cap in _CAPABILITIES:
    AlgorithmRegistry.register(cap)


__all__ = []

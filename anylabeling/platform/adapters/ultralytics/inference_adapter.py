"""UltralyticsInferenceAdapter — inference capability for YOLO models.

Implements :class:`InferenceCapability` for Ultralytics YOLO models.
"""

from __future__ import annotations

import json
import sys

from anylabeling.platform.adapters.interfaces import InferenceCapability


class UltralyticsInferenceAdapter(InferenceCapability):
    """Inference adapter for Ultralytics YOLO models.

    Builds Python subprocess commands that load a YOLO model via
    ``ultralytics.YOLO`` and run prediction on images.
    """

    def get_infer_command(
        self,
        model_path: str,
        image_source: str,
        *,
        is_batch: bool = False,
        **params,
    ) -> list[str]:
        """Compose a CLI command for YOLO inference.

        Args:
            model_path: Path to the exported or trained model (.pt or .onnx).
            image_source: Path to an image file or directory.
            is_batch: If True, ``image_source`` is treated as a directory.
            **params: Additional parameters (conf, iou, imgsz, device, etc.).

        Returns:
            List of CLI tokens ready for subprocess execution.
        """
        conf = params.get("conf", 0.25)
        iou = params.get("iou", 0.45)
        imgsz = params.get("imgsz", 640)
        device = params.get("device", "cpu")
        task = params.get("task", "detect")

        if is_batch:
            return self._build_batch_script(model_path, image_source, conf, iou, imgsz, device, task)
        return self._build_single_script(model_path, image_source, conf, iou, imgsz, device, task)

    def inference_param_schema(self) -> dict:
        """Return a JSON-Schema-like dict describing inference parameters."""
        return {
            "type": "object",
            "properties": {
                "conf": {
                    "type": "number",
                    "default": 0.25,
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Confidence threshold",
                },
                "iou": {
                    "type": "number",
                    "default": 0.45,
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "IoU threshold for NMS",
                },
                "imgsz": {
                    "type": "integer",
                    "default": 640,
                    "minimum": 32,
                    "description": "Input image size",
                },
                "device": {
                    "type": "string",
                    "default": "cpu",
                    "description": "Device to run inference on (cpu, 0, cuda:0, ...)",
                },
                "task": {
                    "type": "string",
                    "default": "detect",
                    "enum": ["detect", "classify", "segment", "pose", "obb"],
                    "description": "YOLO task mode",
                },
                "augment": {
                    "type": "boolean",
                    "default": False,
                    "description": "Use test-time augmentation",
                },
                "half": {
                    "type": "boolean",
                    "default": False,
                    "description": "Use FP16 half-precision inference",
                },
                "max_det": {
                    "type": "integer",
                    "default": 300,
                    "description": "Maximum number of detections per image",
                },
            },
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_single_script(
        model_path: str,
        image_path: str,
        conf: float,
        iou: float,
        imgsz: int,
        device: str,
        task: str,
    ) -> list[str]:
        script = (
            "import json,sys\n"
            "from ultralytics import YOLO\n"
            f"model = YOLO({json.dumps(model_path)}, task={json.dumps(task)})\n"
            f"results = model({json.dumps(image_path)},"
            f"conf={conf},iou={iou},imgsz={imgsz},device={json.dumps(device)})\n"
            "output = []\n"
            "for r in results:\n"
            "    boxes = r.boxes\n"
            "    if boxes is not None:\n"
            "        for i in range(len(boxes)):\n"
            "            xyxy = boxes.xyxy[i].tolist()\n"
            "            cls_id = int(boxes.cls[i].item())\n"
            "            conf_val = float(boxes.conf[i].item())\n"
            "            output.append({'bbox': xyxy, 'class': cls_id, 'conf': conf_val})\n"
            "print(json.dumps(output, ensure_ascii=False))\n"
        )
        return [sys.executable, "-c", script]

    @staticmethod
    def _build_batch_script(
        model_path: str,
        image_dir: str,
        conf: float,
        iou: float,
        imgsz: int,
        device: str,
        task: str,
    ) -> list[str]:
        script = (
            "import json,sys\n"
            "from pathlib import Path\n"
            "from ultralytics import YOLO\n"
            f"model = YOLO({json.dumps(model_path)}, task={json.dumps(task)})\n"
            f"img_dir = {json.dumps(image_dir)}\n"
            "exts = {'.jpg','.jpeg','.png','.bmp','.tif','.tiff'}\n"
            "images = [str(p) for p in Path(img_dir).iterdir() if p.suffix.lower() in exts]\n"
            "if not images:\n"
            "    print(json.dumps([])); sys.exit(0)\n"
            f"results = model(images,conf={conf},iou={iou},imgsz={imgsz},device={json.dumps(device)})\n"
            "output = []\n"
            "for r, img_path in zip(results, images):\n"
            "    boxes = r.boxes\n"
            "    objs = []\n"
            "    if boxes is not None:\n"
            "        for i in range(len(boxes)):\n"
            "            xyxy = boxes.xyxy[i].tolist()\n"
            "            cls_id = int(boxes.cls[i].item())\n"
            "            conf_val = float(boxes.conf[i].item())\n"
            "            objs.append({'bbox': xyxy, 'class': cls_id, 'conf': conf_val})\n"
            "    output.append({'image': img_path, 'objects': objs})\n"
            "print(json.dumps(output, ensure_ascii=False))\n"
        )
        return [sys.executable, "-c", script]


__all__ = [
    "UltralyticsInferenceAdapter",
]

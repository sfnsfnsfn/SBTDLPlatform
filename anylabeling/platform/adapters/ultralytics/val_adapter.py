"""UltralyticsValAdapter — builds kwargs for YOLO model.val().

Architecture constraints:
    - ALLOWED: import ultralytics (adapter bridge only).
    - No PyQt6 imports.
"""

from __future__ import annotations

from pathlib import Path


class UltralyticsValAdapter:
    """Adapts platform val request to Ultralytics YOLO model.val() kwargs.

    Usage::

        adapter = UltralyticsValAdapter()
        kwargs = adapter.build_val_kwargs(
            model_path="runs/run_abc/train/weights/best.pt",
            data_yaml="/data/data.yaml",
            output_dir="runs/run_abc",
        )
        # kwargs can be passed as model.val(**kwargs)
    """

    def build_val_kwargs(
        self,
        model_path: str,
        data_yaml: str,
        split: str = "val",
        device: str = "0",
        batch: int = 16,
        imgsz: int = 640,
        output_dir: str = "",
    ) -> dict:
        """Build kwargs dict for YOLO model.val().

        Args:
            model_path: Path to the trained .pt model file.
            data_yaml: Absolute path to the YOLO-format data.yaml.
            split: Dataset split to validate on ("train", "val", "test").
            device: CUDA device, e.g. "0" or "cpu".
            batch: Batch size for validation.
            imgsz: Input image size.
            output_dir: Directory where Ultralytics will write val outputs.
                Defaults to the directory containing model_path.

        Returns:
            Dict with keys matching Ultralytics ``model.val()`` parameters
            (``data``, ``split``, ``batch``, ``imgsz``, ``device``, ``project``,
            ``name``, ``exist_ok``).
        """
        if not output_dir:
            output_dir = str(Path(model_path).parent)

        return {
            "data": data_yaml,
            "split": split,
            "batch": batch,
            "imgsz": imgsz,
            "device": device,
            "project": output_dir,
            "name": "val",
            "exist_ok": True,
        }


__all__ = [
    "UltralyticsValAdapter",
]

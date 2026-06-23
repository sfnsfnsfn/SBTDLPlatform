"""UltralyticsTrainAdapter — bridges platform TrainRequest to YOLO train() kwargs.

Architecture constraints:
    - ALLOWED: import ultralytics (adapter bridge only).
    - No PyQt6 imports.
    - Pure dataclass + dict transformation.
"""

from __future__ import annotations

from dataclasses import dataclass

from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.task import TaskSpec


@dataclass
class TrainRequest:
    """Request to start a training run.

    Carries all hyperparameters needed for an Ultralytics YOLO training
    session, plus references to the immutable TaskSpec and DatasetBuild
    that define *what* is being trained.
    """

    task_spec: TaskSpec
    dataset_build: DatasetBuild
    base_model: str = ""  # local .pt file path
    epochs: int = 200
    batch: int = 32
    imgsz: int = 640
    workers: int = 8
    device: str = "0"
    seed: int = 42
    # Optimizer
    lr0: float = 0.01
    lrf: float = 0.01
    momentum: float = 0.937
    weight_decay: float = 0.0005
    warmup_epochs: float = 3.0
    optimizer: str = "auto"
    cos_lr: bool = False
    amp: bool = True
    # Augmentation
    hsv_h: float = 0.015
    hsv_s: float = 0.7
    hsv_v: float = 0.4
    degrees: float = 0.0
    translate: float = 0.1
    scale: float = 0.5
    shear: float = 0.0
    perspective: float = 0.0
    fliplr: float = 0.5
    mosaic: float = 1.0
    mixup: float = 0.0
    copy_paste: float = 0.0
    close_mosaic: int = 10
    # Loss
    box: float = 7.5
    cls: float = 0.5
    dfl: float = 1.5
    pose: float = 12.0
    kobj: float = 2.0
    # Save
    save_period: int = -1
    plots: bool = True
    val: bool = True
    save: bool = True


class UltralyticsTrainAdapter:
    """Adapts platform TrainRequest to Ultralytics YOLO model.train() kwargs.

    Usage::

        adapter = UltralyticsTrainAdapter()
        kwargs = adapter.build_train_kwargs(
            request, data_yaml="/path/to/data.yaml", output_dir="/path/to/output"
        )
        # kwargs can be passed as model.train(**kwargs)
    """

    def build_train_kwargs(
        self,
        request: TrainRequest,
        data_yaml: str,
        output_dir: str,
    ) -> dict:
        """Build kwargs dict for YOLO model.train().

        Args:
            request: Training request with all hyperparameters.
            data_yaml: Absolute path to the YOLO-format data.yaml.
            output_dir: Directory where Ultralytics will write runs/.

        Returns:
            Dict with keys matching Ultralytics ``model.train()`` parameters
            (``data``, ``epochs``, ``batch``, ``imgsz``, ...).
        """
        kwargs = {
            "data": data_yaml,
            "epochs": request.epochs,
            "batch": request.batch,
            "imgsz": request.imgsz,
            "workers": request.workers,
            "device": request.device,
            "seed": request.seed,
            # Optimizer
            "lr0": request.lr0,
            "lrf": request.lrf,
            "momentum": request.momentum,
            "weight_decay": request.weight_decay,
            "warmup_epochs": request.warmup_epochs,
            "optimizer": request.optimizer,
            "cos_lr": request.cos_lr,
            "amp": request.amp,
            # Augmentation
            "hsv_h": request.hsv_h,
            "hsv_s": request.hsv_s,
            "hsv_v": request.hsv_v,
            "degrees": request.degrees,
            "translate": request.translate,
            "scale": request.scale,
            "shear": request.shear,
            "perspective": request.perspective,
            "fliplr": request.fliplr,
            "mosaic": request.mosaic,
            "mixup": request.mixup,
            "copy_paste": request.copy_paste,
            "close_mosaic": request.close_mosaic,
            # Loss
            "box": request.box,
            "cls": request.cls,
            "dfl": request.dfl,
            "pose": request.pose,
            "kobj": request.kobj,
            # Save
            "project": output_dir,
            "name": "train",
            "exist_ok": True,
            "save_period": request.save_period,
            "plots": request.plots,
            "val": request.val,
            "save": request.save,
        }
        return kwargs


__all__ = [
    "TrainRequest",
    "UltralyticsTrainAdapter",
]

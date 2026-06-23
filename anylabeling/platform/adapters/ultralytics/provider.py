"""UltralyticsProvider — AlgorithmProvider for Ultralytics YOLO models.

Wraps the existing Ultralytics adapters (train, val, export, dataset,
run_parser, inference) behind the Capability ABC interfaces and exposes
them through the :class:`AlgorithmProvider` facade.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

from anylabeling.platform.adapters.interfaces import (
    DatasetCapability,
    ExportCapability,
    InferenceCapability,
    RunParser,
    TrainCapability,
    ValCapability,
)
from anylabeling.platform.adapters.provider import AlgorithmProvider
from anylabeling.platform.adapters.registry import AlgorithmCapabilities

if TYPE_CHECKING:
    from pathlib import Path

    from anylabeling.platform.domain.model import ModelArtifact
    from anylabeling.platform.domain.run import MetricPoint


# ---------------------------------------------------------------------------
# Adapter wrappers — delegate to existing Ultralytics adapters
# ---------------------------------------------------------------------------


class _TrainAdapter(TrainCapability):
    """TrainCapability wrapper around UltralyticsTrainAdapter."""

    def __init__(self) -> None:
        from anylabeling.platform.adapters.ultralytics.train_adapter import (
            UltralyticsTrainAdapter,
        )

        self._inner = UltralyticsTrainAdapter()

    def build_train_kwargs(self, params, data_path: str, output_dir: str) -> dict:
        return self._inner.build_train_kwargs(params, data_yaml=data_path, output_dir=output_dir)

    def get_train_command(self, model_path: str, kwargs: dict) -> list[str]:
        kwargs_json = json.dumps(kwargs)
        script = (
            "import json\n"
            "from ultralytics import YOLO\n"
            f"model = YOLO({json.dumps(model_path)})\n"
            f"model.train(**json.loads({json.dumps(kwargs_json)}))\n"
        )
        return [sys.executable, "-c", script]

    def train_param_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "epochs": {"type": "integer", "default": 200, "minimum": 1},
                "batch": {"type": "integer", "default": 32, "minimum": 1},
                "imgsz": {"type": "integer", "default": 640, "minimum": 32},
                "workers": {"type": "integer", "default": 8, "minimum": 0},
                "device": {"type": "string", "default": "0"},
                "seed": {"type": "integer", "default": 42},
                "lr0": {"type": "number", "default": 0.01, "minimum": 0},
                "lrf": {"type": "number", "default": 0.01, "minimum": 0},
                "momentum": {"type": "number", "default": 0.937},
                "weight_decay": {"type": "number", "default": 0.0005},
                "warmup_epochs": {"type": "number", "default": 3.0},
                "optimizer": {"type": "string", "default": "auto"},
                "cos_lr": {"type": "boolean", "default": False},
                "amp": {"type": "boolean", "default": True},
                "mosaic": {"type": "number", "default": 1.0},
                "mixup": {"type": "number", "default": 0.0},
            },
        }


class _ValAdapter(ValCapability):
    """ValCapability wrapper around UltralyticsValAdapter."""

    def __init__(self) -> None:
        from anylabeling.platform.adapters.ultralytics.val_adapter import (
            UltralyticsValAdapter,
        )

        self._inner = UltralyticsValAdapter()

    def build_val_kwargs(self, model_path: str, data_path: str, **params) -> dict:
        return self._inner.build_val_kwargs(
            model_path=model_path,
            data_yaml=data_path,
            split=params.get("split", "val"),
            device=params.get("device", "0"),
            batch=params.get("batch", 16),
            imgsz=params.get("imgsz", 640),
            output_dir=params.get("output_dir", ""),
        )

    def get_val_command(self, model_path: str, kwargs: dict) -> list[str]:
        kwargs_json = json.dumps(kwargs)
        script = (
            "import json\n"
            "from ultralytics import YOLO\n"
            f"model = YOLO({json.dumps(model_path)})\n"
            f"model.val(**json.loads({json.dumps(kwargs_json)}))\n"
        )
        return [sys.executable, "-c", script]


class _ExportAdapter(ExportCapability):
    """ExportCapability wrapper around UltralyticsExportAdapter."""

    def __init__(self) -> None:
        from anylabeling.platform.adapters.ultralytics.export_adapter import (
            UltralyticsExportAdapter,
        )
        from anylabeling.platform.adapters.ultralytics.export_validators import (
            SUPPORTED_EXPORT_FORMATS,
        )

        self._inner = UltralyticsExportAdapter()
        self._formats = list(SUPPORTED_EXPORT_FORMATS)

    def get_supported_formats(self) -> list[str]:
        return list(self._formats)

    def build_export_kwargs(
        self, model_path: str, output_dir: str, format: str, **params
    ) -> dict:
        return self._inner.build_export_kwargs(
            model_path=model_path,
            output_dir=output_dir,
            format=format,
            imgsz=params.get("imgsz", 640),
            simplify=params.get("simplify", True),
            half=params.get("half", False),
            dynamic=params.get("dynamic", False),
            opset=params.get("opset"),
            batch=params.get("batch", 1),
        )

    def get_export_command(self, model_path: str, kwargs: dict) -> list[str]:
        kwargs_json = json.dumps(kwargs)
        script = (
            "import json\n"
            "from ultralytics import YOLO\n"
            f"model = YOLO({json.dumps(model_path)})\n"
            f"model.export(**json.loads({json.dumps(kwargs_json)}))\n"
            "print('EXPORT_OK')\n"
        )
        return [sys.executable, "-c", script]


class _DatasetAdapter(DatasetCapability):
    """DatasetCapability wrapper around UltralyticsDatasetAdapter."""

    def __init__(self) -> None:
        from anylabeling.platform.adapters.ultralytics.dataset_adapter import (
            UltralyticsDatasetAdapter,
        )

        self._inner = UltralyticsDatasetAdapter()

    def adapt(self, build, task_spec) -> dict:
        return self._inner.adapt(build, task_spec)

    def write_config(self, build, task_spec) -> Path:
        return self._inner.write_data_yaml(build, task_spec)

    def get_data_path(self, build) -> str:
        return self._inner.get_data_path(build)


class _RunParserAdapter(RunParser):
    """RunParser wrapper around UltralyticsRunParser."""

    def __init__(self) -> None:
        from anylabeling.platform.adapters.ultralytics.run_parser import (
            UltralyticsRunParser,
        )

        self._inner = UltralyticsRunParser()

    def parse_train_results(self, output_dir: str) -> list[MetricPoint]:
        from pathlib import Path

        csv_path = Path(output_dir) / "train" / "results.csv"
        return self._inner.parse_results_csv(csv_path)

    def parse_val_results(self, output_dir: str) -> dict | None:
        from pathlib import Path

        metrics_path = Path(output_dir) / "val" / "per_class_metrics.json"
        return self._inner.parse_val_per_class_metrics(metrics_path)

    def find_best_epoch(self, metrics: list[MetricPoint]) -> dict | None:
        return self._inner.find_best_epoch(metrics)

    def get_best_weight_path(self, output_dir: str) -> str | None:
        return self._inner.get_best_weight_path(output_dir)

    def get_last_weight_path(self, output_dir: str) -> str | None:
        return self._inner.get_last_weight_path(output_dir)


# ---------------------------------------------------------------------------
# UltralyticsProvider
# ---------------------------------------------------------------------------


class UltralyticsProvider(AlgorithmProvider):
    """AlgorithmProvider for Ultralytics YOLO (detection_hbb).

    Provides all six capabilities: training, validation, export, inference,
    dataset building, and run parsing.
    """

    @property
    def id(self) -> str:
        return "ultralytics_yolo_detect"

    @property
    def capabilities(self) -> AlgorithmCapabilities:
        return AlgorithmCapabilities(
            adapter_id=self.id,
            display_name="Ultralytics YOLO Detection (HBB)",
            task_families=frozenset({"detection_hbb"}),
            supports_training=True,
            supports_validation=True,
            supports_export=True,
            export_formats=frozenset(
                {
                    "onnx",
                    "openvino",
                    "engine",
                    "coreml",
                    "saved_model",
                    "pb",
                    "tflite",
                    "edgetpu",
                    "tfjs",
                    "paddle",
                    "mnn",
                    "ncnn",
                    "imx",
                    "rknn",
                    "torchscript",
                }
            ),
            supports_inference=True,
            supports_dataset_build=True,
            supports_sliced_inference=False,
        )

    # ------------------------------------------------------------------
    # Capability adapters
    # ------------------------------------------------------------------

    @property
    def train_adapter(self) -> _TrainAdapter:
        return _TrainAdapter()

    @property
    def val_adapter(self) -> _ValAdapter:
        return _ValAdapter()

    @property
    def export_adapter(self) -> _ExportAdapter:
        return _ExportAdapter()

    @property
    def inference_adapter(self) -> InferenceCapability:
        from anylabeling.platform.adapters.ultralytics.inference_adapter import (
            UltralyticsInferenceAdapter,
        )

        return UltralyticsInferenceAdapter()

    @property
    def dataset_adapter(self) -> _DatasetAdapter:
        return _DatasetAdapter()

    @property
    def run_parser(self) -> _RunParserAdapter:
        return _RunParserAdapter()


__all__ = [
    "UltralyticsProvider",
]

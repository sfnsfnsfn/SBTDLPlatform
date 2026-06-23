"""Algorithm capability interfaces for the vision platform.

Defines six abstract base classes that together form the contract every
algorithm adapter must fulfill.  Each ABC represents one *capability* an
algorithm may optionally provide:

* :class:`TrainCapability` — training
* :class:`ValCapability` — validation
* :class:`ExportCapability` — model export (ONNX, TensorRT, …)
* :class:`InferenceCapability` — inference
* :class:`DatasetCapability` — dataset format adaptation
* :class:`RunParser` — parsing training / validation output

An algorithm can implement any subset of these six capabilities.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anylabeling.platform.domain.model import ModelArtifact
    from anylabeling.platform.domain.run import MetricPoint


# ---------------------------------------------------------------------------
# TrainCapability
# ---------------------------------------------------------------------------


class TrainCapability(ABC):
    """Capability: training a model."""

    @abstractmethod
    def build_train_kwargs(self, params, data_path: str, output_dir: str) -> dict:
        """Build kwargs dict for the underlying training function.

        Args:
            params: Training request / parameter object.
            data_path: Path to the dataset configuration file.
            output_dir: Directory where training outputs will be written.

        Returns:
            Dict of keyword arguments for the algorithm's training function.
        """
        ...

    @abstractmethod
    def get_train_command(self, model_path: str, kwargs: dict) -> list[str]:
        """Compose a CLI command string list for training.

        Args:
            model_path: Path to the base model weights.
            kwargs: Keyword arguments from :meth:`build_train_kwargs`.

        Returns:
            List of CLI tokens (e.g. ``["python", "-m", "yolo", "train", ...]``).
        """
        ...

    @abstractmethod
    def train_param_schema(self) -> dict:
        """Return a JSON-Schema-like dict describing the trainable parameters.

        Returns:
            Dict describing parameter names, types, defaults, and constraints.
        """
        ...


# ---------------------------------------------------------------------------
# ValCapability
# ---------------------------------------------------------------------------


class ValCapability(ABC):
    """Capability: validating a trained model."""

    @abstractmethod
    def build_val_kwargs(self, model_path: str, data_path: str, **params) -> dict:
        """Build kwargs dict for the underlying validation function.

        Args:
            model_path: Path to the trained model weights.
            data_path: Path to the dataset configuration file.
            **params: Additional validation parameters.

        Returns:
            Dict of keyword arguments for the algorithm's validation function.
        """
        ...

    @abstractmethod
    def get_val_command(self, model_path: str, kwargs: dict) -> list[str]:
        """Compose a CLI command string list for validation.

        Args:
            model_path: Path to the trained model weights.
            kwargs: Keyword arguments from :meth:`build_val_kwargs`.

        Returns:
            List of CLI tokens.
        """
        ...


# ---------------------------------------------------------------------------
# ExportCapability
# ---------------------------------------------------------------------------


class ExportCapability(ABC):
    """Capability: exporting a trained model to deployment formats."""

    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """Return the list of export formats supported by this algorithm.

        Returns:
            List of format strings (e.g. ``["onnx", "tensorrt", "openvino"]``).
        """
        ...

    @abstractmethod
    def build_export_kwargs(
        self, model_path: str, output_dir: str, format: str, **params
    ) -> dict:
        """Build kwargs dict for the underlying export function.

        Args:
            model_path: Path to the trained model weights.
            output_dir: Directory where the exported model will be saved.
            format: Target export format (e.g. ``"onnx"``).
            **params: Additional export parameters.

        Returns:
            Dict of keyword arguments for the algorithm's export function.
        """
        ...

    @abstractmethod
    def get_export_command(self, model_path: str, kwargs: dict) -> list[str]:
        """Compose a CLI command string list for export.

        Args:
            model_path: Path to the trained model weights.
            kwargs: Keyword arguments from :meth:`build_export_kwargs`.

        Returns:
            List of CLI tokens.
        """
        ...

    def save_export_artifacts(
        self,
        export_path: str,
        model_path: str,
        output_dir: str,
        model_id: str,
        labels: list[str],
        run_id: str = "",
    ) -> ModelArtifact:
        """Save exported model artifacts to the standard directory layout.

        Default implementation copies the exported file and original model
        weights into ``<output_dir>/models/<model_id>/`` and writes metadata
        files (``model.json``, ``labels.json``, ``preprocess.json``,
        ``postprocess.json``, ``_READY`` marker).

        Subclasses may override to customize the artifact layout.

        Args:
            export_path: Path to the exported model file.
            model_path: Path to the original trained model file.
            output_dir: Parent directory where ``models/<model_id>/`` is created.
            model_id: Unique identifier for this model.
            labels: List of class label names (ordered by ID).
            run_id: ID of the training run that produced this model.

        Returns:
            A :class:`~anylabeling.platform.domain.model.ModelArtifact`
            describing the exported model.
        """
        from anylabeling.platform.domain.model import ModelArtifact
        from anylabeling.platform.infrastructure.atomic_writer import AtomicWriter

        model_dir = Path(output_dir) / "models" / model_id
        model_dir.mkdir(parents=True, exist_ok=True)

        export_dest = model_dir / f"best.{_guess_extension(export_path)}"
        pt_dest = model_dir / "best.pt"

        shutil.copy2(export_path, export_dest)
        shutil.copy2(model_path, pt_dest)

        # labels.json
        labels_data = [
            {"id": i, "name": name} for i, name in enumerate(labels)
        ]
        AtomicWriter.write_json(model_dir / "labels.json", labels_data)

        # preprocess.json
        preprocess: dict = {
            "imgsz": 640,
            "normalize": True,
            "mean": [0.0, 0.0, 0.0],
            "std": [255.0, 255.0, 255.0],
        }
        AtomicWriter.write_json(model_dir / "preprocess.json", preprocess)

        # postprocess.json
        postprocess: dict = {
            "task_family": "",
            "conf_threshold": 0.25,
            "nms_iou_threshold": 0.45,
            "max_det": 300,
        }
        AtomicWriter.write_json(model_dir / "postprocess.json", postprocess)

        # model.json
        model_data: dict = {
            "model_id": model_id,
            "run_id": run_id,
            "format": "onnx",
            "labels": labels,
        }
        AtomicWriter.write_json(model_dir / "model.json", model_data)

        # _READY marker
        (model_dir / "_READY").write_text("", encoding="utf-8")

        return ModelArtifact(
            id=model_id,
            run_id=run_id,
            format="onnx",
            path=str(model_dir),
            labels=labels,
            preprocess=preprocess,
            postprocess=postprocess,
        )


def _guess_extension(export_path: str) -> str:
    """Extract the file extension from an export path (without the dot)."""
    return Path(export_path).suffix.lstrip(".") or "onnx"


# ---------------------------------------------------------------------------
# InferenceCapability
# ---------------------------------------------------------------------------


class InferenceCapability(ABC):
    """Capability: running inference with a trained model."""

    @abstractmethod
    def get_infer_command(
        self,
        model_path: str,
        image_source: str,
        *,
        is_batch: bool = False,
        **params,
    ) -> list[str]:
        """Compose a CLI command string list for inference.

        Args:
            model_path: Path to the exported model weights.
            image_source: Path to an image file or directory.
            is_batch: If True, ``image_source`` is a directory of images
                (keyword-only).
            **params: Additional inference parameters.

        Returns:
            List of CLI tokens.
        """
        ...

    @abstractmethod
    def inference_param_schema(self) -> dict:
        """Return a JSON-Schema-like dict describing inference parameters.

        Returns:
            Dict describing parameter names, types, defaults, and constraints.
        """
        ...


# ---------------------------------------------------------------------------
# DatasetCapability
# ---------------------------------------------------------------------------


class DatasetCapability(ABC):
    """Capability: adapting a platform dataset build to algorithm-specific format."""

    @abstractmethod
    def adapt(self, build, task_spec) -> dict:
        """Convert a :class:`DatasetBuild` to algorithm-specific data dict.

        Args:
            build: A :class:`~anylabeling.platform.domain.dataset.DatasetBuild`.
            task_spec: A :class:`~anylabeling.platform.domain.task.TaskSpec`.

        Returns:
            Dict representing the algorithm-specific dataset configuration.
        """
        ...

    @abstractmethod
    def write_config(self, build, task_spec) -> Path:
        """Write the algorithm-specific config file (e.g. data.yaml).

        Args:
            build: A :class:`~anylabeling.platform.domain.dataset.DatasetBuild`.
            task_spec: A :class:`~anylabeling.platform.domain.task.TaskSpec`.

        Returns:
            :class:`pathlib.Path` to the written config file.
        """
        ...

    @abstractmethod
    def get_data_path(self, build) -> str:
        """Return the path to the config file for training/validation.

        Args:
            build: A :class:`~anylabeling.platform.domain.dataset.DatasetBuild`.

        Returns:
            Absolute path string to the dataset configuration file.
        """
        ...


# ---------------------------------------------------------------------------
# RunParser
# ---------------------------------------------------------------------------


class RunParser(ABC):
    """Capability: parsing training / validation run output."""

    @abstractmethod
    def parse_train_results(self, output_dir: str) -> list[MetricPoint]:
        """Parse training results from the run output directory.

        Args:
            output_dir: Path to the run output directory.

        Returns:
            List of :class:`~anylabeling.platform.domain.run.MetricPoint`.
        """
        ...

    @abstractmethod
    def parse_val_results(self, output_dir: str) -> dict | None:
        """Parse validation results from the run output directory.

        Args:
            output_dir: Path to the run output directory.

        Returns:
            Dict of validation metrics, or ``None`` if not available.
        """
        ...

    @abstractmethod
    def find_best_epoch(self, metrics: list[MetricPoint]) -> dict | None:
        """Find the best epoch from a list of metric points.

        Args:
            metrics: List of :class:`~anylabeling.platform.domain.run.MetricPoint`.

        Returns:
            Dict with keys ``epoch``, ``metric``, ``value``, or ``None``.
        """
        ...

    @abstractmethod
    def get_best_weight_path(self, output_dir: str) -> str | None:
        """Return the path to the best checkpoint weights.

        Args:
            output_dir: Path to the run output directory.

        Returns:
            Absolute path string, or ``None`` if not found.
        """
        ...

    @abstractmethod
    def get_last_weight_path(self, output_dir: str) -> str | None:
        """Return the path to the last checkpoint weights.

        Args:
            output_dir: Path to the run output directory.

        Returns:
            Absolute path string, or ``None`` if not found.
        """
        ...


__all__ = [
    "TrainCapability",
    "ValCapability",
    "ExportCapability",
    "InferenceCapability",
    "DatasetCapability",
    "RunParser",
]

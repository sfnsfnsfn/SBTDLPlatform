"""UltralyticsExportAdapter — builds kwargs for YOLO model.export() and
saves exported artifacts.

Architecture constraints:
    - ALLOWED: import ultralytics (adapter bridge only).
    - ALLOWED: import onnx (for checker — optional, graceful fallback).
    - No PyQt6 imports.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from anylabeling.platform.domain.model import ModelArtifact
from anylabeling.platform.infrastructure.atomic_writer import AtomicWriter


class UltralyticsExportAdapter:
    """Adapts platform export request to Ultralytics YOLO model.export() kwargs.

    Usage::

        adapter = UltralyticsExportAdapter()
        kwargs = adapter.build_export_kwargs(
            model_path="best.pt",
            output_dir="/output",
        )
        # kwargs can be passed as model.export(**kwargs)

        artifact = adapter.save_export_artifacts(
            export_path="/output/best.onnx",
            model_path="best.pt",
            output_dir="/models",
            model_id="model_abc",
            labels=["cat", "dog"],
        )
    """

    # ------------------------------------------------------------------
    # build_export_kwargs
    # ------------------------------------------------------------------

    def build_export_kwargs(
        self,
        model_path: str,
        output_dir: str,
        format: str = "onnx",
        imgsz: int = 640,
        simplify: bool = True,
        half: bool = False,
        dynamic: bool = False,
        opset: int | None = None,
        batch: int = 1,
    ) -> dict:
        """Build kwargs dict for YOLO model.export().

        Supports multiple export formats (onnx, torchscript, etc.).

        Args:
            model_path: Path to the trained .pt model file.
            output_dir: Directory where the exported file will be written.
            format: Export format (onnx, torchscript, etc.).
            imgsz: Input image size.
            simplify: Whether to run onnx-simplifier (ONNX only).
            half: FP16 export.
            dynamic: Dynamic batch size (ONNX only).
            opset: ONNX opset version (ONNX only).
            batch: Batch size for the exported model.

        Returns:
            Dict with keys for model.export().
        """
        kwargs: dict = {
            "format": format,
            "imgsz": imgsz,
            "half": half,
            "batch": batch,
        }
        if format == "onnx":
            kwargs["simplify"] = simplify
            kwargs["dynamic"] = dynamic
            if opset is not None:
                kwargs["opset"] = opset
        return kwargs

    # ------------------------------------------------------------------
    # save_export_artifacts
    # ------------------------------------------------------------------

    def save_export_artifacts(
        self,
        export_path: str,
        model_path: str,
        output_dir: str,
        model_id: str,
        labels: list[str],
        run_id: str = "",
    ) -> ModelArtifact:
        """Save exported ONNX + original PT + metadata to models/<id>/.

        Directory structure::

            models/<model_id>/
            ├── best.onnx       # exported ONNX (copied from export_path)
            ├── best.pt         # original PyTorch weights
            ├── model.json      # {model_id, run_id, format, labels, ...}
            ├── labels.json     # [{"id": 0, "name": "class1"}, ...]
            ├── preprocess.json  # {imgsz, normalize, ...}
            ├── postprocess.json # {task_family, ...}
            └── _READY

        Also runs ``onnx.checker.check_model()`` if onnx is available and
        writes ``onnx_check.json`` with: ``{load_ok, output_schema_ok, passed}``.

        Args:
            export_path: Path to the exported ONNX file.
            model_path: Path to the original .pt model file.
            output_dir: Parent directory (e.g. project root) where
                ``models/<model_id>/`` will be created.
            model_id: Unique model identifier.
            labels: List of class label names (ordered by ID).
            run_id: ID of the training run that produced this model.

        Returns:
            A :class:`ModelArtifact` describing the exported model.
        """
        model_dir = Path(output_dir) / "models" / model_id
        model_dir.mkdir(parents=True, exist_ok=True)

        onnx_dest = model_dir / "best.onnx"
        pt_dest = model_dir / "best.pt"

        # Copy ONNX
        shutil.copy2(export_path, onnx_dest)
        # Copy original PT
        shutil.copy2(model_path, pt_dest)

        # labels.json
        labels_data = [
            {"id": i, "name": name} for i, name in enumerate(labels)
        ]
        AtomicWriter.write_json(
            model_dir / "labels.json",
            labels_data,
        )

        # preprocess.json
        preprocess = {
            "imgsz": 640,
            "normalize": True,
            "mean": [0.0, 0.0, 0.0],
            "std": [255.0, 255.0, 255.0],
        }
        AtomicWriter.write_json(
            model_dir / "preprocess.json",
            preprocess,
        )

        # postprocess.json
        postprocess = {
            "task_family": "",
            "conf_threshold": 0.25,
            "nms_iou_threshold": 0.45,
            "max_det": 300,
        }
        AtomicWriter.write_json(
            model_dir / "postprocess.json",
            postprocess,
        )

        # onnx check
        onnx_check = self._run_onnx_check(str(onnx_dest))
        AtomicWriter.write_json(
            model_dir / "onnx_check.json",
            onnx_check,
        )

        # model.json
        model_data = {
            "model_id": model_id,
            "run_id": run_id,
            "format": "onnx",
            "labels": labels,
        }
        AtomicWriter.write_json(
            model_dir / "model.json",
            model_data,
        )

        # _READY marker
        ready_path = model_dir / "_READY"
        ready_path.write_text("", encoding="utf-8")

        return ModelArtifact(
            id=model_id,
            run_id=run_id,
            format="onnx",
            path=str(model_dir),
            labels=labels,
            preprocess=preprocess,
            postprocess=postprocess,
            onnx_check=onnx_check,
        )

    # ------------------------------------------------------------------
    # _run_onnx_check
    # ------------------------------------------------------------------

    @staticmethod
    def _run_onnx_check(onnx_path: str) -> dict:
        """Run ``onnx.checker.check_model()`` if onnx is available.

        Returns a dict with keys ``load_ok``, ``output_schema_ok``, ``passed``.

        If onnx is not installed, returns all ``False`` with ``load_error``.
        """
        result: dict = {
            "load_ok": False,
            "output_schema_ok": False,
            "passed": False,
        }

        try:
            import onnx
        except ImportError:
            result["load_error"] = "onnx not installed"
            return result

        try:
            model = onnx.load(onnx_path)
            result["load_ok"] = True

            onnx.checker.check_model(model)
            result["passed"] = True

            # Check output schema — at least one output with valid shape info
            if model.graph.output:
                result["output_schema_ok"] = True

        except Exception as exc:
            result["load_error"] = str(exc)

        return result


__all__ = [
    "UltralyticsExportAdapter",
]

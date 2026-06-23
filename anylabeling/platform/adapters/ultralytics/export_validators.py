"""Format-specific environment validators for YOLO model export.

Ported from ``anylabeling/services/auto_training/ultralytics/exporter.py``.
Architecture constraints: No PyQt6 imports, no Ultralytics imports.
"""

from __future__ import annotations

import importlib.util

# ---------------------------------------------------------------------------
# Supported formats
# ---------------------------------------------------------------------------

SUPPORTED_EXPORT_FORMATS: list[str] = [
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
]


def _check_pkg(name: str) -> bool:
    """Check if a Python package is importable."""
    spec = importlib.util.find_spec(name)
    return spec is not None


# ---------------------------------------------------------------------------
# Per-format validators
# ---------------------------------------------------------------------------


def _validate_onnx() -> list[str]:
    missing: list[str] = []
    for p in ("onnx", "onnxslim", "onnxruntime"):
        if not _check_pkg(p):
            missing.append(p)
    return missing


def _validate_openvino() -> list[str]:
    return [] if _check_pkg("openvino") else ["openvino"]


def _validate_tensorrt() -> list[str]:
    return [] if _check_pkg("tensorrt") else ["tensorrt"]


def _validate_coreml() -> list[str]:
    return [] if _check_pkg("coremltools") else ["coremltools"]


def _validate_tensorflow() -> list[str]:
    return [] if _check_pkg("tensorflow") else ["tensorflow"]


def _validate_paddle() -> list[str]:
    if _check_pkg("paddlepaddle") or _check_pkg("paddlepaddle-gpu"):
        return []
    return ["paddlepaddle"]


def _validate_mnn() -> list[str]:
    return [] if _check_pkg("MNN") else ["MNN"]


def _validate_ncnn() -> list[str]:
    return [] if _check_pkg("ncnn") else ["ncnn"]


def _validate_imx500() -> list[str]:
    return [] if _check_pkg("imx500-converter") else ["imx500-converter"]


def _validate_rknn() -> list[str]:
    return [] if _check_pkg("rknn-toolkit2") else ["rknn-toolkit2"]


def _validate_torchscript() -> list[str]:
    """TorchScript is built into PyTorch -- always available."""
    return []


def _validate_noop() -> list[str]:
    return []


# ---------------------------------------------------------------------------
# Validator dispatch table
# ---------------------------------------------------------------------------

_VALIDATORS: dict[str, callable] = {
    "onnx": _validate_onnx,
    "openvino": _validate_openvino,
    "engine": _validate_tensorrt,
    "coreml": _validate_coreml,
    "saved_model": _validate_tensorflow,
    "pb": _validate_tensorflow,
    "tflite": _validate_tensorflow,
    "edgetpu": _validate_tensorflow,
    "tfjs": _validate_tensorflow,
    "paddle": _validate_paddle,
    "mnn": _validate_mnn,
    "ncnn": _validate_ncnn,
    "imx": _validate_imx500,
    "rknn": _validate_rknn,
    "torchscript": _validate_torchscript,
}


def get_export_validator(export_format: str) -> callable:
    """Return the validator function for *export_format*.

    Args:
        export_format: One of the keys in ``SUPPORTED_EXPORT_FORMATS``.

    Returns:
        A callable that takes no arguments and returns ``list[str]``
        of missing package names.
    """
    return _VALIDATORS.get(export_format, _validate_noop)


def validate_export_environment(export_format: str) -> list[str]:
    """Check whether required packages for *export_format* are installed.

    Args:
        export_format: Export format key (e.g. ``"onnx"``, ``"engine"``).

    Returns:
        List of missing package names. Empty list means all OK.
    """
    validator = get_export_validator(export_format)
    return validator()


__all__ = [
    "SUPPORTED_EXPORT_FORMATS",
    "get_export_validator",
    "validate_export_environment",
]

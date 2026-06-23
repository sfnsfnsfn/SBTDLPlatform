from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelArtifact:
    """A exported model artifact produced from a training Run.

    MVP supports ``format == "onnx"`` only.  The ``format`` field is retained
    as a string (not a Literal) to allow future formats without breaking the
    contract.

    ``preprocess`` and ``postprocess`` carry the configuration needed for
    inference (mean/std, letterbox, confidence/nms thresholds, etc.).
    ``onnx_check`` is populated by the ONNX consistency self-check.
    """

    id: str
    run_id: str
    format: str  # "onnx" for MVP
    path: str
    labels: list[str] = field(default_factory=list)
    preprocess: dict = field(default_factory=dict)
    postprocess: dict = field(default_factory=dict)
    onnx_check: dict | None = None


__all__ = [
    "ModelArtifact",
]

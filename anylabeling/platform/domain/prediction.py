from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PredictionObject:
    """A single predicted object restored to L0 image coordinates.

    ``source_tile_ids`` records which tiles contributed to this prediction
    (empty list for full-image inference).
    """

    id: str
    label_id: int
    geometry_type: str
    geometry: object
    score: float
    source_tile_ids: list[str] = field(default_factory=list)


@dataclass
class UnifiedPrediction:
    """All predictions for a single asset restored to L0 image coordinates.

    Represents the output of inference — whether full-image or sliced — after
    any tile-level merge has been applied.  ``elapsed_ms`` measures wall-clock
    inference time.
    """

    asset_id: str
    task_family: str
    model_id: str
    objects: list[PredictionObject] = field(default_factory=list)
    source_tile_ids: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


__all__ = [
    "PredictionObject",
    "UnifiedPrediction",
]

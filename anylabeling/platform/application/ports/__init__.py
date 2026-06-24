from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from anylabeling.platform.domain.annotation import AnnotationDocument

from anylabeling.platform.application.ports.repositories import (
    AnnotationRepositoryPort,
    AssetRepositoryPort,
    DatasetBuildRepositoryPort,
    EvaluationRepositoryPort,
    JobRepositoryPort,
    ModelRepositoryPort,
    RunRepositoryPort,
    WorkflowQueryPort,
)


@runtime_checkable
class AnnotationCodec(Protocol):
    """Convert between external annotation formats and platform AnnotationDocument.

    All coordinates MUST be L0 image coordinates.
    """

    def load_annotations(
        self,
        file_path: str | Path,
        image_width: int,
        image_height: int,
    ) -> AnnotationDocument:
        """Load annotations from an external format file (e.g., X-AnyLabeling JSON)."""
        ...

    def save_annotations(
        self, doc: AnnotationDocument, file_path: str | Path
    ) -> None:
        """Save annotations to an external format file."""
        ...

    def validate_annotations(self, doc: AnnotationDocument) -> list[str]:
        """Validate an AnnotationDocument. Returns list of issues (empty = valid).

        Checks:
        - All shapes have valid label_ids
        - All coordinates are finite and within image bounds
        - Geometry type matches declared type
        - No self-intersecting polygons
        - Required fields present
        """
        ...


__all__ = [
    "AnnotationCodec",
    "AnnotationRepositoryPort",
    "AssetRepositoryPort",
    "DatasetBuildRepositoryPort",
    "EvaluationRepositoryPort",
    "JobRepositoryPort",
    "ModelRepositoryPort",
    "RunRepositoryPort",
    "WorkflowQueryPort",
]

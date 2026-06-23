"""Platform domain contracts — pure dataclass DTOs with no UI or framework imports."""

from anylabeling.platform.domain.task import TaskSpec, LabelClass
from anylabeling.platform.domain.asset import Asset
from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.tile import TilePlan, TileRecord
from anylabeling.platform.domain.dataset import DatasetBuild
from anylabeling.platform.domain.run import Run, MetricPoint
from anylabeling.platform.domain.prediction import UnifiedPrediction, PredictionObject
from anylabeling.platform.domain.model import ModelArtifact
from anylabeling.platform.domain.import_config import (
    ImportCancelledError,
    ImportConfig,
    ImportResult,
    PrecheckResult,
    get_supported_extensions,
)

__all__ = [
    "TaskSpec",
    "LabelClass",
    "Asset",
    "AnnotationDocument",
    "AnnotationObject",
    "TilePlan",
    "TileRecord",
    "DatasetBuild",
    "Run",
    "MetricPoint",
    "UnifiedPrediction",
    "PredictionObject",
    "ModelArtifact",
    "ImportCancelledError",
    "ImportConfig",
    "ImportResult",
    "PrecheckResult",
    "get_supported_extensions",
]

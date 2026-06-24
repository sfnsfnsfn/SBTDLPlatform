from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetRecord:
    """Persistent metadata for a single image asset in the project."""

    id: str
    rel_path: str
    width: int
    height: int
    sha256: str | None = None
    channels: int | None = None
    ext: str | None = None
    size_bytes: int = 0
    group_name: str | None = None
    is_large: bool = False
    status: str = "active"
    source_kind: str | None = None
    source_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None


@dataclass(frozen=True)
class AnnotationSummaryRecord:
    """Summary of annotations for a single asset."""

    asset_id: str
    rel_path: str
    format: str
    object_count: int = 0
    label_histogram_json: str | None = None
    checksum: str | None = None
    status: str = "active"
    updated_at: str | None = None


@dataclass(frozen=True)
class DatasetBuildRecord:
    """A reproducible dataset build manifest (persisted)."""

    id: str
    task_family: str
    output_path: str
    split_strategy: str = ""
    split_seed: int = 42
    split_ratios_json: str | None = None
    tile_plan_json: str | None = None
    preprocess_config_json: str | None = None
    manifest_hash: str = ""
    status: str = "pending"
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    deleted_at: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class RunRecord:
    """A training run record (persisted)."""

    id: str
    dataset_build_id: str
    adapter_id: str
    task_family: str
    status: str = "pending"
    config_json: str | None = None
    metrics_json: str | None = None
    best_model_path: str | None = None
    log_path: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class JobRecord:
    """A background job record (persisted)."""

    id: str
    kind: str
    state: str
    progress: float = 0.0
    entity_type: str | None = None
    entity_id: str | None = None
    payload_json: str | None = None
    log_path: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ModelRecord:
    """A trained model artifact record (persisted)."""

    id: str
    run_id: str
    name: str
    format: str
    path: str
    task_family: str
    metrics_json: str | None = None
    ready: bool = False
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class EvaluationRecord:
    """An evaluation run record (persisted)."""

    id: str
    run_id: str
    dataset_build_id: str
    status: str = "pending"
    metrics_json: str | None = None
    report_path: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None


__all__ = [
    "AssetRecord",
    "AnnotationSummaryRecord",
    "DatasetBuildRecord",
    "RunRecord",
    "JobRecord",
    "ModelRecord",
    "EvaluationRecord",
]

from __future__ import annotations

from dataclasses import dataclass, field

from anylabeling.platform.domain.tile import TilePlan


@dataclass(frozen=True)
class DatasetBuild:
    """A reproducible dataset build manifest.

    References a fixed TaskSpec, asset manifest, annotation manifest, split
    configuration, optional tiling plan, and adapter.  A DatasetBuild is
    immutable once created; parameter changes require a new build.
    """

    id: str
    task_spec_id: str
    source_asset_manifest_hash: str
    annotation_manifest_hash: str
    split_seed: int
    split_strategy: str
    tile_plan: TilePlan | None = None
    augmentation_plan_id: str | None = None
    adapter_id: str = ""
    output_path: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class ManifestIntegrityReport:
    """Result of verifying manifest integrity for a build directory.

    Flags corrupted or missing manifest files so the user can be
    notified before relying on an incomplete build.
    """

    build_id: str
    passed: bool
    checked_files: list[str] = field(default_factory=list)
    corrupted_files: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    error: str = ""


@dataclass(frozen=True)
class LeakageReport:
    """Post-build analysis of data leakage and class distribution.

    Identifies cross-split group contamination and class imbalance
    that could invalidate evaluation results.
    """

    build_id: str
    split_strategy: str
    passed: bool
    has_cross_split_groups: bool = False
    cross_split_groups: list[str] = field(default_factory=list)
    per_class_distribution: dict[str, dict[str, int]] = field(default_factory=dict)
    class_imbalance_warnings: list[str] = field(default_factory=list)


__all__ = [
    "DatasetBuild",
    "ManifestIntegrityReport",
    "LeakageReport",
]

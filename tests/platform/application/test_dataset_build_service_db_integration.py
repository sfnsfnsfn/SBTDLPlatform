"""DB integration tests for DatasetBuildService (E2-2).

Tests that DatasetBuildService writes build state to SQLite via ProjectContext.
Created during Phase E — dual-write to filesystem + SQLite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anylabeling.platform.application.dataset_build_service import (
    DatasetBuildService,
)
from anylabeling.platform.application.project_context import ProjectContext
from anylabeling.platform.domain.annotation import AnnotationDocument
from anylabeling.platform.domain.asset import Asset
from anylabeling.platform.domain.task import LabelClass, TaskSpec
from anylabeling.platform.domain.tile import TilePlan


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Create a minimal project directory structure."""
    root = tmp_path / "test_project"
    root.mkdir(parents=True)
    (root / "dataset_builds").mkdir()
    return root


@pytest.fixture
def hbb_task_spec() -> TaskSpec:
    """A detection_hbb task with two classes."""
    return TaskSpec(
        id="task_hbb_001",
        family="detection_hbb",
        labels=(
            LabelClass(id=0, name="defect"),
            LabelClass(id=1, name="scratch"),
        ),
        annotation_schema="xanylabeling_v4",
        primary_metric="mAP@0.5",
    )


@pytest.fixture
def tile_plan_128() -> TilePlan:
    """128x128 tiles with no overlap, crop edge mode."""
    return TilePlan(
        tile_width=128,
        tile_height=128,
        overlap_x=0,
        overlap_y=0,
        edge_mode="crop",
        padding_value=0,
        min_object_pixels=16,
        min_visibility_ratio=0.3,
    )


@pytest.fixture
def context(project_root: Path) -> ProjectContext:
    """An opened ProjectContext backed by a temporary SQLite database."""
    ctx = ProjectContext(project_root)
    ctx.open()
    yield ctx
    ctx.close()


# ============================================================================
# Test helpers
# ============================================================================


def _make_asset(
    asset_id: str, width: int = 256, height: int = 256
) -> Asset:
    """Create a minimal Asset."""
    return Asset(
        id=asset_id,
        path=f"images/{asset_id}.png",
        width=width,
        height=height,
        channels=3,
        bit_depth=8,
    )


def _make_empty_annotation(
    asset_id: str, width: int = 256, height: int = 256
) -> AnnotationDocument:
    """Create an AnnotationDocument with no objects."""
    return AnnotationDocument(
        asset_id=asset_id,
        image_width=width,
        image_height=height,
        objects=(),
    )


# ============================================================================
# Tests
# ============================================================================


class TestDatasetBuildServiceDbIntegration:
    """DB integration tests for DatasetBuildService."""

    # ------------------------------------------------------------------
    # 1. Build success -> status=completed in DB
    # ------------------------------------------------------------------

    def test_build_success_transitions_to_completed_in_db(
        self,
        project_root: Path,
        context: ProjectContext,
        hbb_task_spec: TaskSpec,
    ):
        """Build succeeds -> status=completed in DB, filesystem still written."""
        service = DatasetBuildService(project_root, context=context)
        asset = _make_asset("img001")

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations={
                "img001": _make_empty_annotation("img001")
            },
            tile_plan=None,
            image_sources={},
            split_seed=42,
            split_ratios=(1.0, 0.0, 0.0),
            split_strategy="random_by_asset",
        )

        # DB record exists and is marked completed
        record = context.dataset_builds.get(build.id)
        assert record is not None
        assert record.status == "completed"
        assert record.id == build.id
        assert record.task_family == "detection_hbb"
        assert record.completed_at is not None
        assert record.error_message is None

        # Filesystem artifacts still written (dual-write)
        build_dir = project_root / "dataset_builds" / build.id
        assert (build_dir / "build.json").exists()
        assert (build_dir / "_READY").exists()

    # ------------------------------------------------------------------
    # 2. Build failure -> status=failed in DB
    # ------------------------------------------------------------------

    def test_build_failure_transitions_to_failed_in_db(
        self,
        project_root: Path,
        context: ProjectContext,
        hbb_task_spec: TaskSpec,
        tile_plan_128: TilePlan,
    ):
        """Build fails -> status=failed in DB with error_message set."""
        service = DatasetBuildService(project_root, context=context)
        asset = _make_asset("img001", width=256, height=256)

        # Cause a failure after DB record creation:
        # tile_plan with empty image_sources -> ValueError during tiling loop
        with pytest.raises(ValueError, match="No image source"):
            service.build(
                task_spec=hbb_task_spec,
                assets=[asset],
                annotations={
                    "img001": _make_empty_annotation("img001")
                },
                tile_plan=tile_plan_128,
                image_sources={},  # empty -> no source for asset
                split_seed=42,
            )

        # Compute expected build_id (deterministic from inputs since
        # _make_build_id uses a hash of task_spec.id, asset IDs, seed,
        # strategy, ratios, and tile_plan — not annotation content).
        expected_id = DatasetBuildService._make_build_id(
            task_spec=hbb_task_spec,
            assets=[asset],
            split_seed=42,
            split_strategy="random_by_asset",
            split_ratios=(0.7, 0.2, 0.1),
            tile_plan=tile_plan_128,
        )

        record = context.dataset_builds.get(expected_id)
        assert record is not None
        assert record.status == "failed"
        assert record.error_message is not None
        assert "No image source" in record.error_message

    # ------------------------------------------------------------------
    # 3. Backward compat: without context, build.json still written
    # ------------------------------------------------------------------

    def test_build_without_context_still_writes_build_json(
        self,
        project_root: Path,
        hbb_task_spec: TaskSpec,
    ):
        """Without ProjectContext, only filesystem artifacts are written."""
        service = DatasetBuildService(project_root)  # no context
        asset = _make_asset("img001")

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations={
                "img001": _make_empty_annotation("img001")
            },
            tile_plan=None,
            image_sources={},
            split_seed=42,
            split_ratios=(1.0, 0.0, 0.0),
        )

        # Filesystem artifacts exist
        build_dir = project_root / "dataset_builds" / build.id
        assert (build_dir / "build.json").exists()
        assert (build_dir / "_READY").exists()
        assert (build_dir / "split_manifest.jsonl").exists()
        assert (build_dir / "data.yaml").exists()

        # No SQLite database file was created
        assert not (project_root / "project.sqlite").exists()

    # ------------------------------------------------------------------
    # 4. Record created then updated to completed
    # ------------------------------------------------------------------

    def test_build_creates_record_then_updates_status(
        self,
        project_root: Path,
        context: ProjectContext,
        hbb_task_spec: TaskSpec,
    ):
        """create() is called, then mark_completed() transitions status."""
        service = DatasetBuildService(project_root, context=context)
        asset = _make_asset("img001")

        build = service.build(
            task_spec=hbb_task_spec,
            assets=[asset],
            annotations={
                "img001": _make_empty_annotation("img001")
            },
            tile_plan=None,
            image_sources={},
            split_seed=42,
            split_ratios=(1.0, 0.0, 0.0),
        )

        # Verify record was created and status is now completed
        record = context.dataset_builds.get(build.id)
        assert record is not None
        assert record.status == "completed"
        assert record.completed_at is not None
        assert record.created_at is not None
        assert record.updated_at is not None

        # Key fields are populated
        assert record.task_family == "detection_hbb"
        assert record.output_path is not None
        assert build.id in record.output_path

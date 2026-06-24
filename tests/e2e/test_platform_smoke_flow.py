"""E2E smoke flow tests for the platform pipeline.

Tests the full lifecycle of a platform project using only the infrastructure
layer — no PyQt6 required.  Each test creates a temporary project directory
with synthetic assets and verifies the SQLite-backed repository behaviour.

Usage:
    python -m pytest tests/e2e/test_platform_smoke_flow.py -v
    python -m pytest tests/e2e/test_platform_smoke_flow.py -v -k "full_flow"
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import numpy as np
import pytest

from anylabeling.platform.application.project_context import ProjectContext
from anylabeling.platform.domain.records import (
    AnnotationSummaryRecord,
    AssetRecord,
    DatasetBuildRecord,
    EvaluationRecord,
    ModelRecord,
    RunRecord,
)
from anylabeling.platform.domain.workflow_status import (
    WorkflowStepStatus,
)
from anylabeling.platform.infrastructure.project_db_bootstrap import (
    ProjectDbBootstrap,
)

# ===================================================================
# Helpers
# ===================================================================


def _make_synthetic_image(path: Path, w: int, h: int, seed: int = 42) -> None:
    """Create a deterministic colour test PNG."""
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    import cv2

    cv2.imwrite(str(path), img)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with the expected subdirectory layout."""
    root = tmp_path / "smoke_project"
    (root / "assets").mkdir(parents=True)
    (root / "annotations").mkdir(parents=True)
    return root


@pytest.fixture
def project_context(project_dir: Path) -> ProjectContext:
    """Return an opened ProjectContext for *project_dir*."""
    ctx = ProjectContext(project_dir)
    ctx.open()
    yield ctx
    ctx.close()


# ===================================================================
# Test: ProjectContext creates an SQLite database file
# ===================================================================


class TestProjectInit:
    """Verify that opening a project creates the SQLite index."""

    def test_create_project_creates_sqlite(self, project_dir: Path) -> None:
        """Opening a ProjectContext must create a project.sqlite file."""
        ctx = ProjectContext(project_dir)
        assert not (project_dir / "project.sqlite").exists(), (
            "project.sqlite should not exist before opening"
        )
        ctx.open()
        try:
            db_path = project_dir / "project.sqlite"
            assert db_path.exists(), f"Missing: {db_path}"
            assert db_path.stat().st_size > 0, "project.sqlite is empty"
        finally:
            ctx.close()

    def test_project_context_repositories_available(
        self, project_context: ProjectContext
    ) -> None:
        """All repository properties must be accessible after opening."""
        assert project_context.db is not None
        assert project_context.assets is not None
        assert project_context.annotations is not None
        assert project_context.dataset_builds is not None
        assert project_context.runs is not None
        assert project_context.models is not None
        assert project_context.evaluations is not None
        assert project_context.workflow_query is not None

    def test_project_context_db_path_matches(
        self, project_dir: Path, project_context: ProjectContext
    ) -> None:
        """db_path() must point to project.sqlite inside the project root."""
        expected = project_dir / "project.sqlite"
        assert project_context.db_path() == expected

    def test_project_context_is_open(
        self, project_context: ProjectContext
    ) -> None:
        """is_open must be True while the context is open."""
        assert project_context.is_open is True

    def test_project_context_close_clears_state(
        self, project_context: ProjectContext
    ) -> None:
        """After close(), is_open must be False and db must raise."""
        ctx = project_context
        ctx.close()
        assert ctx.is_open is False
        with pytest.raises(RuntimeError, match="Not open"):
            _ = ctx.db  # accessing db after close must raise


# ===================================================================
# Test: Bootstrap scans legacy assets
# ===================================================================


class TestBootstrap:
    """Verify that ProjectDbBootstrap correctly scans legacy project dirs."""

    def test_bootstrap_scans_assets(self, tmp_path: Path) -> None:
        """Bootstrap must find and index all image files in assets/."""
        legacy = tmp_path / "legacy"
        (legacy / "assets").mkdir(parents=True)
        (legacy / "annotations").mkdir(parents=True)

        # Create 3 synthetic images
        for i in range(3):
            _make_synthetic_image(
                legacy / "assets" / f"img_{i:04d}.jpg", 640, 480, seed=i
            )

        # Run bootstrap
        db_path = tmp_path / "bootstrap_test.db"
        from anylabeling.platform.infrastructure.project_db import ProjectDb

        db = ProjectDb(db_path)
        db.open()
        try:
            bootstrap = ProjectDbBootstrap(db, legacy)
            report = bootstrap.run()

            assert report.assets_processed == 3, (
                f"Expected 3 assets, got {report.assets_processed}"
            )
            assert report.errors == (), (
                f"Unexpected errors: {report.errors}"
            )

            # Verify rows were written
            rows = db.query_all("SELECT rel_path FROM assets ORDER BY rel_path")
            assert len(rows) == 3
            assert rows[0]["rel_path"] == "img_0000.jpg"
            assert rows[1]["rel_path"] == "img_0001.jpg"
            assert rows[2]["rel_path"] == "img_0002.jpg"
        finally:
            db.close()

    def test_bootstrap_scans_annotations(self, tmp_path: Path) -> None:
        """Bootstrap must index annotation files from annotations/."""
        legacy = tmp_path / "legacy_ann"
        (legacy / "assets").mkdir(parents=True)
        (legacy / "annotations").mkdir(parents=True)

        # Create an asset that the annotation references
        _make_synthetic_image(legacy / "assets" / "sample.jpg", 640, 480)
        # Create a matching annotation
        ann = {"version": "4.0.0", "flags": {}, "shapes": []}
        (legacy / "annotations" / "sample.json").write_text(
            json.dumps(ann), encoding="utf-8"
        )

        from anylabeling.platform.infrastructure.project_db import ProjectDb

        db = ProjectDb(tmp_path / "ann_test.db")
        db.open()
        try:
            bootstrap = ProjectDbBootstrap(db, legacy)
            report = bootstrap.run()
            assert report.assets_processed == 1
            assert report.annotations_processed == 1
            assert report.errors == ()
        finally:
            db.close()

    def test_bootstrap_handles_missing_dirs(self, tmp_path: Path) -> None:
        """Bootstrap must handle missing optional directories gracefully."""
        empty = tmp_path / "empty_project"
        empty.mkdir()

        from anylabeling.platform.infrastructure.project_db import ProjectDb

        db = ProjectDb(tmp_path / "empty_test.db")
        db.open()
        try:
            bootstrap = ProjectDbBootstrap(db, empty)
            report = bootstrap.run()
            assert report.assets_processed == 0
            assert report.annotations_processed == 0
            assert report.dataset_builds_processed == 0
            assert report.runs_processed == 0
            assert report.models_processed == 0
            assert report.errors == ()
        finally:
            db.close()

    def test_bootstrap_dry_run_does_not_write(self, tmp_path: Path) -> None:
        """Dry-run bootstrap using :memory: must not create a file."""
        legacy = tmp_path / "dry_run"
        (legacy / "assets").mkdir(parents=True)
        (legacy / "annotations").mkdir(parents=True)

        for i in range(2):
            _make_synthetic_image(
                legacy / "assets" / f"img_{i}.jpg", 320, 240, seed=i
            )

        from anylabeling.platform.infrastructure.project_db import ProjectDb

        db = ProjectDb(":memory:")
        db.open()
        try:
            bootstrap = ProjectDbBootstrap(db, legacy)
            report = bootstrap.run()
            assert report.assets_processed == 2
            assert report.errors == ()
        finally:
            db.close()

    def test_bootstrap_idempotent(self, tmp_path: Path) -> None:
        """Running bootstrap twice must not duplicate rows."""
        legacy = tmp_path / "idempotent"
        (legacy / "assets").mkdir(parents=True)
        (legacy / "annotations").mkdir(parents=True)
        _make_synthetic_image(legacy / "assets" / "stable.png", 100, 100)

        from anylabeling.platform.infrastructure.project_db import ProjectDb

        db = ProjectDb(tmp_path / "idem_test.db")
        db.open()
        try:
            bootstrap = ProjectDbBootstrap(db, legacy)
            r1 = bootstrap.run()
            r2 = bootstrap.run()
            assert r1.assets_processed == 1
            assert r2.assets_processed <= r1.assets_processed  # already indexed

            rows = db.query_all("SELECT COUNT(*) AS cnt FROM assets")
            assert rows[0]["cnt"] == 1, "Duplicate rows after re-bootstrap"
        finally:
            db.close()


# ===================================================================
# Test: Full pipeline flow via DB records
# ===================================================================


class TestFullFlowDbRecords:
    """End-to-end: create records for each pipeline stage and verify DB state."""

    def test_full_flow_db_records(
        self, project_context: ProjectContext
    ) -> None:
        """Walk through each stage and verify the database after each step."""
        ctx = project_context
        db = ctx.db
        workflow = ctx.workflow_query

        # ------------------------------------------------------------------
        # Stage 0: Initial state — no assets
        # ------------------------------------------------------------------
        assert workflow.data_prep_status() == WorkflowStepStatus.PENDING
        assert workflow.next_action() is not None

        # ------------------------------------------------------------------
        # Stage 1: Import assets
        # ------------------------------------------------------------------
        assets_dir = ctx.project_root / "assets"
        for i in range(5):
            _make_synthetic_image(
                assets_dir / f"img_{i:04d}.jpg", 640, 480, seed=i
            )
            ctx.assets.upsert(
                AssetRecord(
                    id=f"asset-{i:04d}",
                    rel_path=f"img_{i:04d}.jpg",
                    width=640,
                    height=480,
                    ext=".jpg",
                    size_bytes=(assets_dir / f"img_{i:04d}.jpg").stat().st_size,
                    status="active",
                )
            )

        # Verify
        stats = ctx.assets.stats()
        assert stats["total"] == 5, f"Expected 5 assets, got {stats['total']}"
        assert workflow.data_prep_status() == WorkflowStepStatus.RUNNING, (
            "Data prep should be RUNNING after asset import (no annotations)"
        )

        # ------------------------------------------------------------------
        # Stage 2: Annotations
        # ------------------------------------------------------------------
        # Create an annotation summary for one asset
        ctx.annotations.upsert_summary(
            AnnotationSummaryRecord(
                asset_id="asset-0000",
                rel_path="img_0000.json",
                format="json",
                object_count=2,
                label_histogram_json=json.dumps({"defect": 2}),
            )
        )
        assert ctx.annotations.count_annotated() == 1
        assert workflow.data_prep_status() == WorkflowStepStatus.COMPLETED, (
            "Data prep should be COMPLETED after annotations exist"
        )

        # ------------------------------------------------------------------
        # Stage 3: Dataset build
        # ------------------------------------------------------------------
        build_id = f"build-{uuid.uuid4().hex[:8]}"
        build = ctx.dataset_builds.create(
            DatasetBuildRecord(
                id=build_id,
                task_family="detection_hbb",
                output_path=f"dataset_builds/{build_id}",
                split_strategy="random",
                status="pending",
            )
        )
        assert build.id == build_id

        ctx.dataset_builds.mark_completed(build_id)
        completed_build = ctx.dataset_builds.get(build_id)
        assert completed_build is not None
        assert completed_build.status == "completed"
        assert completed_build.completed_at is not None

        latest = ctx.dataset_builds.get_latest_completed()
        assert latest is not None and latest.id == build_id

        assert workflow.train_status() == WorkflowStepStatus.COMPLETED, (
            "Train should be COMPLETED after a completed dataset build"
        )

        # ------------------------------------------------------------------
        # Stage 4: Training run
        # ------------------------------------------------------------------
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        run = ctx.runs.create(
            RunRecord(
                id=run_id,
                dataset_build_id=build_id,
                adapter_id="yolo_v8",
                task_family="detection_hbb",
                status="pending",
            )
        )
        assert run.id == run_id

        ctx.runs.mark_completed(run_id)
        assert workflow.eval_status() == WorkflowStepStatus.COMPLETED, (
            "Eval should be COMPLETED after a completed training run"
        )

        # ------------------------------------------------------------------
        # Stage 5: Model creation
        # ------------------------------------------------------------------
        model_id = f"model-{uuid.uuid4().hex[:8]}"
        ctx.models.upsert(
            ModelRecord(
                id=model_id,
                run_id=run_id,
                name="smoke_model",
                format="onnx",
                path=f"models/{model_id}/model.onnx",
                task_family="detection_hbb",
                ready=True,
            )
        )
        ready_models = ctx.models.list_ready()
        assert any(m.id == model_id for m in ready_models)

        assert workflow.export_status() == WorkflowStepStatus.COMPLETED, (
            "Export should be COMPLETED after a ready model exists"
        )

        # ------------------------------------------------------------------
        # Stage 6: Evaluation
        # ------------------------------------------------------------------
        eval_id = f"eval-{uuid.uuid4().hex[:8]}"
        evaluation = ctx.evaluations.create(
            EvaluationRecord(
                id=eval_id,
                run_id=run_id,
                dataset_build_id=build_id,
                status="pending",
            )
        )
        assert evaluation.id == eval_id

        ctx.evaluations.mark_completed(
            eval_id,
            metrics_json=json.dumps(
                {"mAP": 0.85, "precision": 0.82}
            ),
        )
        completed_eval = ctx.evaluations.get(eval_id)
        assert completed_eval is not None
        assert completed_eval.status == "completed"
        assert completed_eval.metrics_json is not None

        evals = ctx.evaluations.list_by_run(run_id)
        assert any(e.id == eval_id for e in evals)

        # ------------------------------------------------------------------
        # Stage 7: Verify end state
        # ------------------------------------------------------------------
        next_action = workflow.next_action()
        assert next_action is None, (
            f"Expected no next action at end of pipeline, got {next_action!r}"
        )

        # Verify all workflow stages are COMPLETED
        assert workflow.data_prep_status() == WorkflowStepStatus.COMPLETED
        assert workflow.train_status() == WorkflowStepStatus.COMPLETED
        assert workflow.eval_status() == WorkflowStepStatus.COMPLETED
        assert workflow.export_status() == WorkflowStepStatus.COMPLETED


# ===================================================================
# Test: WorkflowQuery stage transitions
# ===================================================================


class TestWorkflowStageTransitions:
    """Verify stage status transitions across the pipeline lifecycle."""

    def test_initial_all_pending(self, project_context: ProjectContext) -> None:
        """Fresh project must have PENDING data prep, BLOCKED others."""
        wq = project_context.workflow_query
        assert wq.data_prep_status() == WorkflowStepStatus.PENDING
        assert wq.train_status() == WorkflowStepStatus.BLOCKED
        assert wq.eval_status() == WorkflowStepStatus.BLOCKED
        assert wq.export_status() == WorkflowStepStatus.BLOCKED
        assert wq.next_action() is not None

    def test_assets_without_annotations_is_running(
        self, project_context: ProjectContext
    ) -> None:
        """Assets without annotations must set data_prep to RUNNING."""
        ctx = project_context
        assets_dir = ctx.project_root / "assets"
        _make_synthetic_image(assets_dir / "test.jpg", 100, 100)
        ctx.assets.upsert(
            AssetRecord(
                id="running-test",
                rel_path="test.jpg",
                width=100,
                height=100,
                ext=".jpg",
                size_bytes=(assets_dir / "test.jpg").stat().st_size,
                status="active",
            )
        )
        assert ctx.workflow_query.data_prep_status() == WorkflowStepStatus.RUNNING

    def test_train_blocked_without_build(
        self, project_context: ProjectContext
    ) -> None:
        """Training must be BLOCKED when data prep is not COMPLETED."""
        assert (
            project_context.workflow_query.train_status()
            == WorkflowStepStatus.BLOCKED
        )

    def test_eval_blocked_without_completed_run(
        self, project_context: ProjectContext
    ) -> None:
        """Evaluation must be BLOCKED when training is not COMPLETED."""
        assert (
            project_context.workflow_query.eval_status()
            == WorkflowStepStatus.BLOCKED
        )

    def test_export_blocked_without_ready_model(
        self, project_context: ProjectContext
    ) -> None:
        """Export must be BLOCKED when evaluation is not COMPLETED."""
        assert (
            project_context.workflow_query.export_status()
            == WorkflowStepStatus.BLOCKED
        )

    def test_next_action_returns_string_for_pending(
        self, project_context: ProjectContext
    ) -> None:
        """next_action() must return a string when stages are pending."""
        action = project_context.workflow_query.next_action()
        assert isinstance(action, str) and len(action) > 0

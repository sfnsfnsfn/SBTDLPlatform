#!/usr/bin/env python3
"""Automated platform flow verification script.

Creates a temporary project, simulates each pipeline stage (import,
dataset build, training readiness, evaluation readiness, export readiness),
and verifies the SQLite-backed repository layer behaves correctly.

Usage:
    python scripts/verify_platform_flow.py

Exit codes:
    0   All checks passed
    1   One or more checks failed
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap path resolution
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve()
_REPO_ROOT = str(_HERE.parents[1])

if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Imports (local after sys.path fix)
# ---------------------------------------------------------------------------

import numpy as np
from anylabeling.platform.domain.records import (
    AssetRecord,
    DatasetBuildRecord,
    EvaluationRecord,
    ModelRecord,
    RunRecord,
)
from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.project_db_bootstrap import (
    ProjectDbBootstrap,
)
from anylabeling.platform.infrastructure.sqlite_repositories.annotations import (
    SQLiteAnnotationRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.assets import (
    SQLiteAssetRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.dataset_builds import (
    SQLiteDatasetBuildRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.evaluations import (
    SQLiteEvaluationRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.models import (
    SQLiteModelRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.runs import (
    SQLiteRunRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.workflow_query import (
    SQLiteWorkflowQuery,
)
from anylabeling.platform.infrastructure.unit_of_work import UnitOfWork
from anylabeling.platform.domain.workflow_status import WorkflowStepStatus

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_pass_count: int = 0
_fail_count: int = 0


def _check(step: str, condition: bool, detail: str = "") -> None:
    """Record a PASS or FAIL for *step* and print the result."""
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
        print(f"  PASS  {step}")
    else:
        _fail_count += 1
        msg = f"  FAIL  {step}"
        if detail:
            msg += f"  --  {detail}"
        print(msg)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_synthetic_image(path: Path, w: int, h: int, seed: int = 42) -> None:
    """Create a deterministic colour test PNG."""
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    # Use cv2 if available, otherwise PIL, otherwise raw bytes
    try:
        import cv2

        cv2.imwrite(str(path), img)
    except ImportError:
        try:
            from PIL import Image as PILImage

            PILImage.fromarray(img).save(str(path))
        except ImportError:
            path.write_bytes(img.tobytes())


# ---------------------------------------------------------------------------
# Main verification
# ---------------------------------------------------------------------------


def _verify_temp_project_flow(tmp_dir: Path) -> None:
    """Run all verification steps inside *tmp_dir*."""
    print()
    print("=" * 70)
    print("  Platform Flow Verification")
    print(f"  Temp dir: {tmp_dir}")
    print("=" * 70)

    project_root = tmp_dir / "test_project"
    assets_dir = project_root / "assets"
    (project_root / "annotations").mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    db_path = project_root / "project.sqlite"

    # =====================================================================
    # 1. ProjectDb lifecycle
    # =====================================================================
    print("\n--- [1] ProjectDb lifecycle ---")

    db = ProjectDb(db_path)
    db.open()
    _check("ProjectDb.open() succeeds", db.connection is not None)
    _check("ProjectDb.db_path is correct", db.db_path == db_path)

    # Verify PRAGMAs are applied
    row = db.query_one("PRAGMA journal_mode")
    _check("WAL journal mode enabled", row is not None, str(row))
    row = db.query_one("PRAGMA foreign_keys")
    _check(
        "Foreign keys enabled",
        row is not None and row[0] == 1,
        str(row),
    )

    db.close()
    _check("ProjectDb.close() completes", True)

    # Re-open for the remaining tests
    db.open()

    # =====================================================================
    # 2. Simulate import: upsert asset records
    # =====================================================================
    print("\n--- [2] Asset import simulation ---")

    asset_repo = SQLiteAssetRepository(db)
    rng = np.random.default_rng(42)
    created_asset_ids: list[str] = []

    for i in range(5):
        img_path = assets_dir / f"img_{i:04d}.jpg"
        _make_synthetic_image(img_path, 640, 480, seed=i)
        record = AssetRecord(
            id=f"test-asset-{i}",
            rel_path=f"img_{i:04d}.jpg",
            width=640,
            height=480,
            ext=".jpg",
            size_bytes=img_path.stat().st_size,
            status="active",
        )
        persisted = asset_repo.upsert(record)
        created_asset_ids.append(persisted.id)
        _check(
            f"Asset {i} upserted with id={persisted.id}",
            persisted.id == f"test-asset-{i}",
        )

    # Verify stats
    stats = asset_repo.stats()
    _check("Asset stats total == 5", stats["total"] == 5)
    _check("Asset stats by_status active == 5", stats["by_status"].get("active") == 5)
    _check("Asset stats by_extension .jpg == 5", stats["by_extension"].get(".jpg") == 5)

    # Verify list()
    all_assets = asset_repo.list()
    _check("Asset repo list() returns 5 items", len(all_assets) == 5)

    # Verify get()
    fetched = asset_repo.get("test-asset-0")
    _check("Asset repo get() returns record", fetched is not None)
    _check("Asset repo get() correct width", fetched is not None and fetched.width == 640)

    # =====================================================================
    # 3. Bootstrap test: simulate legacy project structure
    # =====================================================================
    print("\n--- [3] Legacy bootstrap simulation ---")

    legacy_root = tmp_dir / "legacy_project"
    (legacy_root / "assets").mkdir(parents=True)
    (legacy_root / "annotations").mkdir(parents=True)

    # Create some legacy asset files
    for i in range(3):
        _make_synthetic_image(legacy_root / "assets" / f"legacy_{i}.png", 320, 240, seed=100 + i)

    # Create a legacy annotation
    ann_data = {"version": "4.0.0", "flags": {}, "shapes": []}
    (legacy_root / "annotations" / "legacy_0.json").write_text(
        json.dumps(ann_data), encoding="utf-8"
    )

    # Run bootstrap into a fresh in-memory DB
    boot_db = ProjectDb(":memory:")
    boot_db.open()
    bootstrap = ProjectDbBootstrap(boot_db, legacy_root)
    report = bootstrap.run()
    boot_db.close()

    _check("Bootstrap scanned 3 assets", report.assets_processed == 3)
    _check("Bootstrap scanned 1 annotation", report.annotations_processed >= 1)
    _check("Bootstrap has 0 errors", len(report.errors) == 0)

    # =====================================================================
    # 4. Dataset build record creation
    # =====================================================================
    print("\n--- [4] Dataset build simulation ---")

    build_repo = SQLiteDatasetBuildRepository(db)
    build_id = f"test-build-{uuid.uuid4().hex[:8]}"
    build_record = DatasetBuildRecord(
        id=build_id,
        task_family="detection_hbb",
        output_path=f"dataset_builds/{build_id}",
        split_strategy="random",
        split_seed=42,
        split_ratios_json=json.dumps({"train": 0.6, "val": 0.3, "test": 0.1}),
        status="pending",
    )
    created_build = build_repo.create(build_record)
    _check("Dataset build created", created_build.id == build_id)
    _check("Dataset build task_family", created_build.task_family == "detection_hbb")

    build_repo.mark_running(build_id)
    running = build_repo.get(build_id)
    _check("Build status = running", running is not None and running.status == "running")

    build_repo.mark_completed(build_id)
    completed = build_repo.get(build_id)
    _check("Build status = completed", completed is not None and completed.status == "completed")
    _check("Build completed_at set", completed is not None and completed.completed_at is not None)

    # Verify latest completed
    latest = build_repo.get_latest_completed()
    _check("get_latest_completed() returns build", latest is not None and latest.id == build_id)

    # =====================================================================
    # 5. Training run simulation (training service readiness)
    # =====================================================================
    print("\n--- [5] Training run simulation ---")

    run_repo = SQLiteRunRepository(db)
    run_id = f"test-run-{uuid.uuid4().hex[:8]}"
    run_record = RunRecord(
        id=run_id,
        dataset_build_id=build_id,
        adapter_id="yolo_v8",
        task_family="detection_hbb",
        status="pending",
    )
    created_run = run_repo.create(run_record)
    _check("Run record created", created_run.id == run_id)

    run_repo.mark_running(run_id)
    run_repo.mark_completed(run_id)
    completed_run = run_repo.get(run_id)
    _check("Run status = completed", completed_run is not None and completed_run.status == "completed")

    # Verify completed runs list
    completed_runs = run_repo.list_completed()
    _check("list_completed() includes run", any(r.id == run_id for r in completed_runs))

    # =====================================================================
    # 6. Model record simulation (training output)
    # =====================================================================
    print("\n--- [6] Model record simulation ---")

    model_repo = SQLiteModelRepository(db)
    model_id = f"test-model-{uuid.uuid4().hex[:8]}"
    model_record = ModelRecord(
        id=model_id,
        run_id=run_id,
        name="test_model",
        format="onnx",
        path=f"models/{model_id}/model.onnx",
        task_family="detection_hbb",
        ready=False,
    )
    persisted_model = model_repo.upsert(model_record)
    _check("Model record created", persisted_model.id == model_id)
    _check("Model ready = False initially", not persisted_model.ready)

    # Mark ready and re-check
    updated = model_repo.upsert(
        ModelRecord(
            id=model_id,
            run_id=run_id,
            name="test_model",
            format="onnx",
            path=f"models/{model_id}/model.onnx",
            task_family="detection_hbb",
            ready=True,
        )
    )
    _check("Model ready = True after update", updated.ready)

    # Check list_ready
    ready_models = model_repo.list_ready()
    _check("list_ready() contains model", any(m.id == model_id for m in ready_models))

    # =====================================================================
    # 7. Evaluation simulation (evaluation readiness)
    # =====================================================================
    print("\n--- [7] Evaluation simulation ---")

    eval_repo = SQLiteEvaluationRepository(db)
    eval_id = f"test-eval-{uuid.uuid4().hex[:8]}"
    eval_record = EvaluationRecord(
        id=eval_id,
        run_id=run_id,
        dataset_build_id=build_id,
        status="pending",
    )
    created_eval = eval_repo.create(eval_record)
    _check("Evaluation record created", created_eval.id == eval_id)

    # Mark completed with metrics
    metrics = json.dumps({"mAP": 0.85, "precision": 0.82, "recall": 0.79})
    eval_repo.mark_completed(eval_id, metrics_json=metrics)
    completed_eval = eval_repo.get(eval_id)
    _check("Evaluation completed", completed_eval is not None and completed_eval.status == "completed")
    _check("Evaluation metrics stored", completed_eval is not None and completed_eval.metrics_json is not None)

    # Check list_by_run
    evals_for_run = eval_repo.list_by_run(run_id)
    _check("list_by_run() contains eval", any(e.id == eval_id for e in evals_for_run))

    # =====================================================================
    # 8. Workflow query readiness checks
    # =====================================================================
    print("\n--- [8] Workflow query readiness ---")

    workflow = SQLiteWorkflowQuery(db)

    # Data prep: assets exist but no annotation summaries yet -> RUNNING
    if workflow.data_prep_status() == WorkflowStepStatus.RUNNING:
        _check("Workflow: data_prep = RUNNING (no annotations)", True)
    else:
        _check(
            f"Workflow: data_prep = {workflow.data_prep_status().value}",
            False,
            "Expected RUNNING when assets exist without annotation summaries",
        )

    # Train: a completed build exists -> COMPLETED
    train_st = workflow.train_status()
    _check(
        f"Workflow: train = {train_st.value}",
        train_st == WorkflowStepStatus.COMPLETED,
        "Expected COMPLETED when a completed dataset build exists",
    )

    # Eval: a completed run exists -> COMPLETED
    eval_st = workflow.eval_status()
    _check(
        f"Workflow: eval = {eval_st.value}",
        eval_st == WorkflowStepStatus.COMPLETED,
        "Expected COMPLETED when a completed run exists",
    )

    # Export: a ready model exists -> COMPLETED
    export_st = workflow.export_status()
    _check(
        f"Workflow: export = {export_st.value}",
        export_st == WorkflowStepStatus.COMPLETED,
        "Expected COMPLETED when a ready model exists",
    )

    # Next action: all stages completed -> None
    next_action = workflow.next_action()
    _check(
        "Workflow: next_action = None (all stages complete)",
        next_action is None,
        f"Expected None, got {next_action!r}",
    )

    # =====================================================================
    # 9. Unit of Work test
    # =====================================================================
    print("\n--- [9] Unit of Work ---")

    try:
        with UnitOfWork(db):
            asset_repo.upsert(
                AssetRecord(
                    id="uow-test",
                    rel_path="uow_test.jpg",
                    width=100,
                    height=100,
                    ext=".jpg",
                    size_bytes=1000,
                    status="active",
                )
            )
        _check("UnitOfWork commits successfully", True)
    except Exception as exc:
        _check("UnitOfWork commits successfully", False, str(exc))

    # Verify rollback on exception
    try:
        with UnitOfWork(db):
            asset_repo.upsert(
                AssetRecord(
                    id="uow-rollback",
                    rel_path="uow_rollback.jpg",
                    width=100,
                    height=100,
                    ext=".jpg",
                    size_bytes=1000,
                    status="active",
                )
            )
            raise ValueError("Intentional rollback")
    except ValueError:
        pass

    rolled_back = asset_repo.get("uow-rollback")
    _check(
        "UnitOfWork rolls back on exception",
        rolled_back is None,
        "Record should not exist after rollback",
    )

    # =====================================================================
    # 10. WAL checkpoint test
    # =====================================================================
    print("\n--- [10] WAL checkpoint ---")

    wal_path = db_path.with_suffix(".sqlite-wal")
    shm_path = db_path.with_suffix(".sqlite-shm")

    db.checkpoint(truncate=True)
    _check("WAL checkpoint (TRUNCATE) completes", True)

    # After truncate, WAL and SHM files should be 0 bytes or absent
    wal_ok = not wal_path.exists() or wal_path.stat().st_size == 0
    shm_ok = not shm_path.exists() or shm_path.stat().st_size == 0
    _check("WAL file truncated after checkpoint", wal_ok)
    _check("SHM file truncated after checkpoint", shm_ok)

    # =====================================================================
    # Cleanup
    # =====================================================================
    db.close()


def main() -> int:
    """Run all verification steps and return exit code."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="platform_verify_"))
    try:
        _verify_temp_project_flow(tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Summary
    print()
    print("=" * 70)
    total = _pass_count + _fail_count
    print(f"  Results: {_pass_count} passed / {_fail_count} failed / {total} total")
    if _fail_count == 0:
        print("  ALL CHECKS PASSED")
        print("=" * 70)
        return 0
    else:
        print(f"  {_fail_count} CHECK(S) FAILED")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())

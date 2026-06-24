"""Tests for SQLiteWorkflowQuery -- pipeline stage status and next-action logic.

Covers:
  1. Empty project (all tables empty) -- every stage shows PENDING/BLOCKED.
  2. Partial progress -- assets imported but no annotations yet.
  3. Full pipeline ready -- every stage completed, next_action is None.
  4. Failed build blocks train -- data prep done but build failed.
  5. No ready model blocks export -- everything done except mark model ready.
"""

from __future__ import annotations

import pathlib
import sys
import types
from importlib import util as importlib_util

import pytest

# ---------------------------------------------------------------------------
# Manual package bootstrap (same pattern as existing infra tests)
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PLATFORM_DIR = REPO_ROOT / "anylabeling" / "platform"
INFRA_DIR = PLATFORM_DIR / "infrastructure"
DOMAIN_DIR = PLATFORM_DIR / "domain"
SQLITE_REPOS_DIR = INFRA_DIR / "sqlite_repositories"


def _ensure_package(name: str, path: pathlib.Path | None = None) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [] if path is None else [str(path)]
    return module


def _load_module(name: str, path: pathlib.Path) -> types.ModuleType:
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None) == str(path):
        return existing
    spec = importlib_util.spec_from_file_location(name, path)
    module = importlib_util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bootstrap() -> None:
    _ensure_package("anylabeling")
    _ensure_package("anylabeling.platform", PLATFORM_DIR)
    _ensure_package("anylabeling.platform.domain", DOMAIN_DIR)
    _ensure_package("anylabeling.platform.infrastructure", INFRA_DIR)
    _ensure_package(
        "anylabeling.platform.infrastructure.sqlite_repositories",
        SQLITE_REPOS_DIR,
    )

    _load_module(
        "anylabeling.platform.domain.records",
        DOMAIN_DIR / "records.py",
    )
    _load_module(
        "anylabeling.platform.domain.workflow_status",
        DOMAIN_DIR / "workflow_status.py",
    )
    _load_module(
        "anylabeling.platform.infrastructure.project_db",
        INFRA_DIR / "project_db.py",
    )
    _load_module(
        "anylabeling.platform.infrastructure.sqlite_repositories.workflow_query",
        SQLITE_REPOS_DIR / "workflow_query.py",
    )


_bootstrap()

from anylabeling.platform.domain.workflow_status import WorkflowStepStatus
from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.sqlite_repositories.workflow_query import (
    SQLiteWorkflowQuery,
)

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def db(tmp_path: pathlib.Path) -> ProjectDb:
    """Return an open ProjectDb backed by a temp-file database."""
    db_path = tmp_path / "test.db"
    database = ProjectDb(db_path)
    database.open()
    yield database
    database.close()


@pytest.fixture
def query(db: ProjectDb) -> SQLiteWorkflowQuery:
    """Return a SQLiteWorkflowQuery against the temp database."""
    return SQLiteWorkflowQuery(db)


# ===================================================================
# Helpers – seed the database for each scenario
# ===================================================================


def _create_default_tables(db: ProjectDb) -> None:
    """Ensure the tables the query reads from actually exist.

    We create (or re-use) the minimal schema for each table so that
    the raw INSERTs below work without relying on the full repository
    classes.  Each statement is ``CREATE TABLE IF NOT EXISTS`` so it is
    safe to call multiple times.
    """
    db.execute("""\
CREATE TABLE IF NOT EXISTS assets (
    id             TEXT PRIMARY KEY,
    rel_path       TEXT NOT NULL UNIQUE,
    width          INTEGER NOT NULL,
    height         INTEGER NOT NULL,
    sha256         TEXT,
    channels       INTEGER,
    ext            TEXT,
    size_bytes     INTEGER NOT NULL DEFAULT 0,
    group_name     TEXT,
    is_large       INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'active',
    source_kind    TEXT,
    source_version TEXT,
    created_at     TEXT,
    updated_at     TEXT,
    deleted_at     TEXT
)""")
    db.execute("""\
CREATE TABLE IF NOT EXISTS annotation_summaries (
    asset_id            TEXT PRIMARY KEY,
    rel_path            TEXT NOT NULL,
    format              TEXT NOT NULL,
    object_count        INTEGER NOT NULL DEFAULT 0,
    label_histogram_json TEXT,
    checksum            TEXT,
    status              TEXT NOT NULL DEFAULT 'active',
    updated_at          TEXT
)""")
    db.execute("""\
CREATE TABLE IF NOT EXISTS dataset_builds (
    id                    TEXT PRIMARY KEY,
    task_family           TEXT NOT NULL,
    output_path           TEXT NOT NULL,
    split_strategy        TEXT NOT NULL DEFAULT '',
    split_seed            INTEGER NOT NULL DEFAULT 42,
    split_ratios_json     TEXT,
    tile_plan_json        TEXT,
    preprocess_config_json TEXT,
    manifest_hash         TEXT NOT NULL DEFAULT '',
    status                TEXT NOT NULL DEFAULT 'pending',
    created_at            TEXT,
    updated_at            TEXT,
    completed_at          TEXT,
    deleted_at            TEXT,
    error_message         TEXT
)""")
    db.execute("""\
CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    dataset_build_id TEXT NOT NULL,
    adapter_id       TEXT NOT NULL,
    task_family      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    config_json      TEXT,
    metrics_json     TEXT,
    best_model_path  TEXT,
    log_path         TEXT,
    started_at       TEXT,
    finished_at      TEXT,
    updated_at       TEXT,
    error_message    TEXT
)""")
    db.execute("""\
CREATE TABLE IF NOT EXISTS models (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    format      TEXT NOT NULL,
    path        TEXT NOT NULL,
    task_family TEXT NOT NULL,
    metrics_json TEXT,
    ready       INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT,
    updated_at  TEXT
)""")


def _insert_asset(db: ProjectDb, asset_id: str, rel_path: str = "",
                  status: str = "active") -> None:
    db.execute(
        "INSERT INTO assets (id, rel_path, width, height, size_bytes, ext, status) "
        "VALUES (?, ?, 100, 100, 1000, '.jpg', ?)",
        (asset_id, rel_path or f"img/{asset_id}.jpg", status),
    )


def _insert_annotation(db: ProjectDb, asset_id: str, object_count: int = 1) -> None:
    db.execute(
        "INSERT INTO annotation_summaries "
        "(asset_id, rel_path, format, object_count, status) "
        "VALUES (?, ?, 'test', ?, 'active')",
        (asset_id, f"ann/{asset_id}.json", object_count),
    )


def _insert_build(db: ProjectDb, build_id: str, status: str = "completed",
                  error_message: str | None = None) -> None:
    db.execute(
        "INSERT INTO dataset_builds "
        "(id, task_family, output_path, status, error_message) "
        "VALUES (?, 'detection_hbb', ?, ?, ?)",
        (build_id, f"builds/{build_id}", status, error_message),
    )


def _insert_run(db: ProjectDb, run_id: str, build_id: str,
                status: str = "completed") -> None:
    db.execute(
        "INSERT INTO runs (id, dataset_build_id, adapter_id, task_family, status) "
        "VALUES (?, ?, 'ultralytics.v1', 'detection_hbb', ?)",
        (run_id, build_id, status),
    )


def _insert_model(db: ProjectDb, model_id: str, run_id: str,
                  ready: int = 1) -> None:
    db.execute(
        "INSERT INTO models (id, run_id, name, format, path, task_family, ready) "
        "VALUES (?, ?, 'yolo11s', 'onnx', ?, 'detection_hbb', ?)",
        (model_id, run_id, f"models/{model_id}.onnx", ready),
    )


# ===================================================================
# Test: Empty project
# ===================================================================


class TestEmptyProject:
    """All tables empty -- every stage is PENDING or blocked by prerequisite."""

    def test_data_prep_status(self, query: SQLiteWorkflowQuery) -> None:
        _create_default_tables(query._db)
        assert query.data_prep_status() is WorkflowStepStatus.PENDING

    def test_train_status(self, query: SQLiteWorkflowQuery) -> None:
        _create_default_tables(query._db)
        # Blocked because data_prep is not COMPLETED
        assert query.train_status() is WorkflowStepStatus.BLOCKED

    def test_eval_status(self, query: SQLiteWorkflowQuery) -> None:
        _create_default_tables(query._db)
        # Blocked because train is not COMPLETED
        assert query.eval_status() is WorkflowStepStatus.BLOCKED

    def test_export_status(self, query: SQLiteWorkflowQuery) -> None:
        _create_default_tables(query._db)
        # Blocked because eval is not COMPLETED
        assert query.export_status() is WorkflowStepStatus.BLOCKED

    def test_next_action(self, query: SQLiteWorkflowQuery) -> None:
        _create_default_tables(query._db)
        msg = query.next_action()
        assert msg is not None
        assert "Import assets" in msg or "import" in msg.lower()


# ===================================================================
# Test: Partial progress — assets imported, none annotated
# ===================================================================


class TestPartialProgress:
    """Assets exist in the project but none have annotations yet."""

    @pytest.fixture(autouse=True)
    def _seed(self, db: ProjectDb) -> None:
        _create_default_tables(db)
        _insert_asset(db, "a1")
        _insert_asset(db, "a2")

    def test_data_prep_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.data_prep_status() is WorkflowStepStatus.RUNNING

    def test_train_status(self, query: SQLiteWorkflowQuery) -> None:
        # Blocked because data_prep is not COMPLETED
        assert query.train_status() is WorkflowStepStatus.BLOCKED

    def test_eval_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.eval_status() is WorkflowStepStatus.BLOCKED

    def test_export_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.export_status() is WorkflowStepStatus.BLOCKED

    def test_next_action(self, query: SQLiteWorkflowQuery) -> None:
        msg = query.next_action()
        assert msg is not None
        assert "Annotate" in msg or "annotate" in msg.lower()

    def test_all_annotated_is_completed(
        self, db: ProjectDb, query: SQLiteWorkflowQuery
    ) -> None:
        """Once annotations exist, data_prep becomes COMPLETED."""
        _insert_annotation(db, "a1", object_count=3)
        _insert_annotation(db, "a2", object_count=5)
        assert query.data_prep_status() is WorkflowStepStatus.COMPLETED


# ===================================================================
# Test: Full pipeline ready
# ===================================================================


class TestFullPipelineReady:
    """Every stage has been completed end-to-end."""

    @pytest.fixture(autouse=True)
    def _seed(self, db: ProjectDb) -> None:
        _create_default_tables(db)
        _insert_asset(db, "a1", rel_path="train/img001.jpg")
        _insert_annotation(db, "a1", object_count=3)
        _insert_build(db, "b1", status="completed")
        _insert_run(db, "r1", build_id="b1", status="completed")
        _insert_model(db, "m1", run_id="r1", ready=1)

    def test_data_prep_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.data_prep_status() is WorkflowStepStatus.COMPLETED

    def test_train_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.train_status() is WorkflowStepStatus.COMPLETED

    def test_eval_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.eval_status() is WorkflowStepStatus.COMPLETED

    def test_export_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.export_status() is WorkflowStepStatus.COMPLETED

    def test_next_action(self, query: SQLiteWorkflowQuery) -> None:
        assert query.next_action() is None


# ===================================================================
# Test: Failed build blocks train
# ===================================================================


class TestFailedBuildBlocksTrain:
    """Data preparation is complete, but the dataset build failed."""

    @pytest.fixture(autouse=True)
    def _seed(self, db: ProjectDb) -> None:
        _create_default_tables(db)
        _insert_asset(db, "a1")
        _insert_annotation(db, "a1", object_count=3)
        _insert_build(db, "b1", status="failed", error_message="OOM during split")

    def test_data_prep_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.data_prep_status() is WorkflowStepStatus.COMPLETED

    def test_train_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.train_status() is WorkflowStepStatus.BLOCKED

    def test_eval_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.eval_status() is WorkflowStepStatus.BLOCKED

    def test_export_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.export_status() is WorkflowStepStatus.BLOCKED

    def test_next_action(self, query: SQLiteWorkflowQuery) -> None:
        msg = query.next_action()
        assert msg is not None
        assert "Build" in msg or "build" in msg.lower() or "Fix" in msg


# ===================================================================
# Test: No ready model blocks export
# ===================================================================


class TestNoReadyModelBlocksExport:
    """Data prep, training, and evaluation completed, but no ready model."""

    @pytest.fixture(autouse=True)
    def _seed(self, db: ProjectDb) -> None:
        _create_default_tables(db)
        _insert_asset(db, "a1")
        _insert_annotation(db, "a1", object_count=3)
        _insert_build(db, "b1", status="completed")
        _insert_run(db, "r1", build_id="b1", status="completed")
        # Model exists but is NOT marked ready
        _insert_model(db, "m1", run_id="r1", ready=0)

    def test_data_prep_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.data_prep_status() is WorkflowStepStatus.COMPLETED

    def test_train_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.train_status() is WorkflowStepStatus.COMPLETED

    def test_eval_status(self, query: SQLiteWorkflowQuery) -> None:
        assert query.eval_status() is WorkflowStepStatus.COMPLETED

    def test_export_status(self, query: SQLiteWorkflowQuery) -> None:
        # Export not complete because no model has ready=1;
        # eval is COMPLETED so this is PENDING (not blocked by prereq)
        assert query.export_status() is WorkflowStepStatus.PENDING

    def test_next_action(self, query: SQLiteWorkflowQuery) -> None:
        msg = query.next_action()
        assert msg is not None
        assert "Export" in msg or "export" in msg.lower()

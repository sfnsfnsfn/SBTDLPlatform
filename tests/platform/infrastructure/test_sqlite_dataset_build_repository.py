"""Tests for SQLiteDatasetBuildRepository.

Tests the full state machine: pending -> running -> completed,
pending -> running -> failed, list_completed filtering, get_latest_completed
ordering, and soft-delete semantics.
"""

from __future__ import annotations

import pathlib
import sys
import types
from importlib import util as importlib_util

import pytest

# ---------------------------------------------------------------------------
# Manual package bootstrap (same pattern as test_project_db.py)
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
        "anylabeling.platform.infrastructure.project_db",
        INFRA_DIR / "project_db.py",
    )
    _load_module(
        "anylabeling.platform.infrastructure.sqlite_repositories.dataset_builds",
        SQLITE_REPOS_DIR / "dataset_builds.py",
    )


_bootstrap()

from anylabeling.platform.domain.records import DatasetBuildRecord
from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.sqlite_repositories.dataset_builds import (
    SQLiteDatasetBuildRepository,
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
def build_repo(db: ProjectDb) -> SQLiteDatasetBuildRepository:
    return SQLiteDatasetBuildRepository(db)


# ===================================================================
# Tests
# ===================================================================


class TestSQLiteDatasetBuildRepository:
    """State-transition and query tests for SQLiteDatasetBuildRepository."""

    # ------------------------------------------------------------------
    # Create / get
    # ------------------------------------------------------------------

    def test_create_returns_record_with_timestamps(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        record = DatasetBuildRecord(
            id="b1",
            task_family="detection_hbb",
            output_path="builds/b1",
        )
        created = build_repo.create(record)
        assert created.id == "b1"
        assert created.task_family == "detection_hbb"
        assert created.output_path == "builds/b1"
        assert created.status == "pending"
        assert created.created_at is not None
        assert created.updated_at is not None

    def test_create_with_full_record(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        record = DatasetBuildRecord(
            id="b2",
            task_family="segmentation",
            output_path="builds/b2",
            split_strategy="random_by_asset",
            split_seed=42,
            split_ratios_json='{"train": 0.8, "val": 0.2}',
            tile_plan_json='{"tile_width": 1024}',
            preprocess_config_json='{"mean": [0, 0, 0]}',
        )
        created = build_repo.create(record)
        assert created.id == "b2"
        assert created.split_strategy == "random_by_asset"
        assert created.split_seed == 42
        assert created.split_ratios_json is not None

    def test_get_returns_none_for_missing(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        assert build_repo.get("nonexistent") is None

    def test_get_returns_record_after_create(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        fetched = build_repo.get("b1")
        assert fetched is not None
        assert fetched.id == "b1"
        assert fetched.task_family == "detection_hbb"

    # ------------------------------------------------------------------
    # State machine: pending -> running -> completed
    # ------------------------------------------------------------------

    def test_mark_running_transitions_status(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        build_repo.mark_running("b1")
        fetched = build_repo.get("b1")
        assert fetched is not None
        assert fetched.status == "running"
        assert fetched.updated_at is not None

    def test_full_cycle_pending_to_running_to_completed(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        build_repo.mark_running("b1")
        build_repo.mark_completed("b1")
        fetched = build_repo.get("b1")
        assert fetched is not None
        assert fetched.status == "completed"
        assert fetched.completed_at is not None
        assert fetched.updated_at is not None

    def test_full_cycle_pending_to_running_to_failed(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        build_repo.mark_running("b1")
        error_msg = "Split ratio MSE exceeds tolerance"
        build_repo.mark_failed("b1", error_msg)
        fetched = build_repo.get("b1")
        assert fetched is not None
        assert fetched.status == "failed"
        assert fetched.error_message == error_msg
        assert fetched.completed_at is not None
        assert fetched.updated_at is not None

    # ------------------------------------------------------------------
    # list_completed
    # ------------------------------------------------------------------

    def test_list_completed_returns_only_completed(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        build_repo.create(DatasetBuildRecord(
            id="b2", task_family="detection_hbb", output_path="builds/b2",
        ))
        build_repo.create(DatasetBuildRecord(
            id="b3", task_family="detection_hbb", output_path="builds/b3",
        ))

        build_repo.mark_running("b1")
        build_repo.mark_completed("b1")
        build_repo.mark_running("b2")
        build_repo.mark_failed("b2", "OOM")
        # b3 stays pending

        completed = build_repo.list_completed()
        assert len(completed) == 1
        assert completed[0].id == "b1"

    def test_list_completed_excludes_failed(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        build_repo.mark_running("b1")
        build_repo.mark_failed("b1", "Error")
        completed = build_repo.list_completed()
        assert len(completed) == 0

    def test_list_completed_returns_empty_when_none_completed(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        assert build_repo.list_completed() == []

    # ------------------------------------------------------------------
    # get_latest_completed
    # ------------------------------------------------------------------

    def test_get_latest_completed_returns_most_recent(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        build_repo.create(DatasetBuildRecord(
            id="b2", task_family="detection_hbb", output_path="builds/b2",
        ))

        build_repo.mark_running("b1")
        build_repo.mark_completed("b1")
        build_repo.mark_running("b2")
        build_repo.mark_completed("b2")

        latest = build_repo.get_latest_completed()
        assert latest is not None
        assert latest.id == "b2"
        assert latest.status == "completed"

    def test_get_latest_completed_returns_none_when_none(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        assert build_repo.get_latest_completed() is None

    def test_get_latest_completed_excludes_failed(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        build_repo.mark_running("b1")
        build_repo.mark_completed("b1")

        build_repo.create(DatasetBuildRecord(
            id="b2", task_family="detection_hbb", output_path="builds/b2",
        ))
        build_repo.mark_running("b2")
        build_repo.mark_failed("b2", "error")

        latest = build_repo.get_latest_completed()
        assert latest is not None
        assert latest.id == "b1"

    # ------------------------------------------------------------------
    # Soft delete
    # ------------------------------------------------------------------

    def test_mark_deleted_sets_deleted_at(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        build_repo.mark_deleted("b1")
        fetched = build_repo.get("b1")
        assert fetched is not None
        assert fetched.deleted_at is not None

    def test_soft_deleted_build_excluded_from_list_completed(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        build_repo.mark_running("b1")
        build_repo.mark_completed("b1")
        build_repo.mark_deleted("b1")

        completed = build_repo.list_completed()
        assert len(completed) == 0

    def test_soft_delete_does_not_affect_other_builds(
        self, build_repo: SQLiteDatasetBuildRepository
    ) -> None:
        build_repo.create(DatasetBuildRecord(
            id="b1", task_family="detection_hbb", output_path="builds/b1",
        ))
        build_repo.create(DatasetBuildRecord(
            id="b2", task_family="detection_hbb", output_path="builds/b2",
        ))

        build_repo.mark_running("b1")
        build_repo.mark_completed("b1")
        build_repo.mark_running("b2")
        build_repo.mark_completed("b2")

        build_repo.mark_deleted("b1")

        completed = build_repo.list_completed()
        assert len(completed) == 1
        assert completed[0].id == "b2"

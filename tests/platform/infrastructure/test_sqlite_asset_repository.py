"""Tests for SQLiteAssetRepository — upsert, get, list, stats, soft-delete.

Covers:
  1. upsert inserts a new record and sets timestamps.
  2. upsert with existing rel_path updates the record in-place.
  3. get returns a record by id but excludes soft-deleted rows.
  4. list returns all active records, supports offset/limit, and
     optionally filters by group_name or status.
  5. list excludes soft-deleted records by default.
  6. stats returns aggregate counts by status, extension, and group.
  7. mark_deleted sets deleted_at and hides the record from queries.
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
        "anylabeling.platform.infrastructure.sqlite_repositories.assets",
        SQLITE_REPOS_DIR / "assets.py",
    )


_bootstrap()

from anylabeling.platform.domain.records import AssetRecord
from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.sqlite_repositories.assets import (
    SQLiteAssetRepository,
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
def repo(db: ProjectDb) -> SQLiteAssetRepository:
    return SQLiteAssetRepository(db)


@pytest.fixture
def sample_record() -> AssetRecord:
    """A standard asset record used across multiple tests."""
    return AssetRecord(
        id="asset-1",
        rel_path="images/sample.jpg",
        width=1920,
        height=1080,
        sha256="abc123",
        channels=3,
        ext=".jpg",
        size_bytes=204800,
        group_name="test_group",
        is_large=False,
        status="active",
    )


# ===================================================================
# SQLiteAssetRepository tests
# ===================================================================


class TestSQLiteAssetRepositoryUpsert:
    """Tests for the upsert method — insert and update semantics."""

    def test_upsert_inserts_new_record(
        self, repo: SQLiteAssetRepository, sample_record: AssetRecord
    ) -> None:
        created = repo.upsert(sample_record)
        assert created.id == "asset-1"
        assert created.rel_path == "images/sample.jpg"
        assert created.width == 1920
        assert created.height == 1080
        # Timestamps should have been populated
        assert created.created_at is not None
        assert created.updated_at is not None
        # Soft-delete marker should be None
        assert created.deleted_at is None

    def test_upsert_returns_persisted_record(
        self, repo: SQLiteAssetRepository, sample_record: AssetRecord
    ) -> None:
        repo.upsert(sample_record)
        fetched = repo.get("asset-1")
        assert fetched is not None
        assert fetched.rel_path == "images/sample.jpg"
        assert fetched.sha256 == "abc123"
        assert fetched.group_name == "test_group"

    def test_upsert_updates_existing_by_rel_path(
        self, repo: SQLiteAssetRepository
    ) -> None:
        """Insert then upsert with same rel_path should update fields."""
        repo.upsert(AssetRecord(
            id="asset-v1",
            rel_path="images/duplicate.jpg",
            width=800,
            height=600,
            size_bytes=50000,
            ext=".jpg",
            status="active",
        ))
        # Upsert with same rel_path but new data
        updated = repo.upsert(AssetRecord(
            id="asset-v2",
            rel_path="images/duplicate.jpg",
            width=1920,
            height=1080,
            size_bytes=200000,
            ext=".jpg",
            status="active",
        ))
        # The id should reflect the latest upsert
        assert updated.id == "asset-v2"
        assert updated.width == 1920
        assert updated.height == 1080
        assert updated.size_bytes == 200000
        # Verify only one row exists for this rel_path
        all_rows = repo.list()
        matching = [r for r in all_rows if r.rel_path == "images/duplicate.jpg"]
        assert len(matching) == 1

    def test_upsert_sets_created_at_once(
        self, repo: SQLiteAssetRepository
    ) -> None:
        """created_at should be set on insert and preserved on update."""
        first = repo.upsert(AssetRecord(
            id="a1", rel_path="img/persist.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", status="active",
        ))
        created_at = first.created_at
        assert created_at is not None

        second = repo.upsert(AssetRecord(
            id="a1", rel_path="img/persist.jpg", width=200, height=200,
            size_bytes=2000, ext=".jpg", status="active",
        ))
        # updated_at should have changed; created_at should stay the same
        assert second.created_at == created_at
        assert second.updated_at is not None


class TestSQLiteAssetRepositoryGet:
    """Tests for the get method — retrieval by id."""

    def test_get_returns_record(
        self, repo: SQLiteAssetRepository, sample_record: AssetRecord
    ) -> None:
        repo.upsert(sample_record)
        fetched = repo.get("asset-1")
        assert fetched is not None
        assert fetched.id == "asset-1"
        assert fetched.rel_path == "images/sample.jpg"

    def test_get_returns_none_for_missing(
        self, repo: SQLiteAssetRepository
    ) -> None:
        assert repo.get("nonexistent") is None

    def test_get_excludes_soft_deleted(
        self, repo: SQLiteAssetRepository, sample_record: AssetRecord
    ) -> None:
        repo.upsert(sample_record)
        repo.mark_deleted("asset-1")
        assert repo.get("asset-1") is None


class TestSQLiteAssetRepositoryList:
    """Tests for the list method — pagination and filtering."""

    @pytest.fixture
    def multi_asset_repo(
        self, repo: SQLiteAssetRepository
    ) -> SQLiteAssetRepository:
        """Populate the repo with several assets of varied groups/statuses."""
        assets = [
            AssetRecord(
                id=f"a{i}", rel_path=f"group1/img{i}.jpg", width=100, height=100,
                size_bytes=1000, ext=".jpg", group_name="group1", status="active",
            )
            for i in range(3)
        ] + [
            AssetRecord(
                id=f"b{i}", rel_path=f"group2/img{i}.png", width=200, height=200,
                size_bytes=2000, ext=".png", group_name="group2", status="active",
            )
            for i in range(2)
        ] + [
            AssetRecord(
                id="archived-1", rel_path="misc/old.tif", width=300, height=300,
                size_bytes=3000, ext=".tif", group_name="misc", status="archived",
            )
        ]
        for a in assets:
            repo.upsert(a)
        return repo

    def test_list_returns_all_active(
        self, multi_asset_repo: SQLiteAssetRepository
    ) -> None:
        all_assets = multi_asset_repo.list()
        assert len(all_assets) == 6  # all 6 are active (non-deleted)

    def test_list_with_offset(
        self, multi_asset_repo: SQLiteAssetRepository
    ) -> None:
        result = multi_asset_repo.list(offset=3)
        assert len(result) == 3  # 6 total - 3 offset

    def test_list_with_limit(
        self, multi_asset_repo: SQLiteAssetRepository
    ) -> None:
        result = multi_asset_repo.list(limit=2)
        assert len(result) == 2

    def test_list_with_offset_and_limit(
        self, multi_asset_repo: SQLiteAssetRepository
    ) -> None:
        result = multi_asset_repo.list(offset=2, limit=2)
        assert len(result) == 2

    def test_list_filters_by_group(
        self, multi_asset_repo: SQLiteAssetRepository
    ) -> None:
        result = multi_asset_repo.list(group_name="group1")
        assert len(result) == 3
        assert all(r.group_name == "group1" for r in result)

    def test_list_filters_by_status(
        self, multi_asset_repo: SQLiteAssetRepository
    ) -> None:
        result = multi_asset_repo.list(status="archived")
        assert len(result) == 1
        assert result[0].id == "archived-1"

    def test_list_filters_by_group_and_status(
        self, multi_asset_repo: SQLiteAssetRepository
    ) -> None:
        result = multi_asset_repo.list(group_name="group1", status="active")
        assert len(result) == 3
        assert all(r.group_name == "group1" for r in result)
        assert all(r.status == "active" for r in result)

    def test_list_excludes_deleted(
        self, repo: SQLiteAssetRepository
    ) -> None:
        repo.upsert(AssetRecord(
            id="keep", rel_path="stay.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", status="active",
        ))
        repo.upsert(AssetRecord(
            id="remove", rel_path="go.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", status="active",
        ))
        repo.mark_deleted("remove")
        all_assets = repo.list()
        assert len(all_assets) == 1
        assert all_assets[0].id == "keep"

    def test_list_returns_empty_when_all_deleted(
        self, repo: SQLiteAssetRepository
    ) -> None:
        repo.upsert(AssetRecord(
            id="gone", rel_path="gone.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", status="active",
        ))
        repo.mark_deleted("gone")
        assert repo.list() == []

    def test_list_returns_empty_for_mismatched_filter(
        self, multi_asset_repo: SQLiteAssetRepository
    ) -> None:
        result = multi_asset_repo.list(group_name="nonexistent")
        assert result == []


class TestSQLiteAssetRepositoryStats:
    """Tests for the stats aggregation method."""

    def test_stats_empty(self, repo: SQLiteAssetRepository) -> None:
        stats = repo.stats()
        assert stats["total"] == 0
        assert stats["by_status"] == {}
        assert stats["by_extension"] == {}
        assert stats["by_group"] == {}

    def test_stats_counts_by_status(
        self, repo: SQLiteAssetRepository
    ) -> None:
        repo.upsert(AssetRecord(
            id="a1", rel_path="a.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", status="active",
        ))
        repo.upsert(AssetRecord(
            id="a2", rel_path="b.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", status="active",
        ))
        repo.upsert(AssetRecord(
            id="a3", rel_path="c.tif", width=100, height=100,
            size_bytes=1000, ext=".tif", status="archived",
        ))
        stats = repo.stats()
        assert stats["total"] == 3
        assert stats["by_status"]["active"] == 2
        assert stats["by_status"]["archived"] == 1

    def test_stats_counts_by_extension(
        self, repo: SQLiteAssetRepository
    ) -> None:
        repo.upsert(AssetRecord(
            id="a1", rel_path="a.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", status="active",
        ))
        repo.upsert(AssetRecord(
            id="a2", rel_path="b.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", status="active",
        ))
        repo.upsert(AssetRecord(
            id="a3", rel_path="c.png", width=100, height=100,
            size_bytes=1000, ext=".png", status="active",
        ))
        stats = repo.stats()
        assert stats["by_extension"][".jpg"] == 2
        assert stats["by_extension"][".png"] == 1

    def test_stats_counts_by_group(
        self, repo: SQLiteAssetRepository
    ) -> None:
        repo.upsert(AssetRecord(
            id="a1", rel_path="g1/a.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", group_name="group1", status="active",
        ))
        repo.upsert(AssetRecord(
            id="a2", rel_path="g1/b.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", group_name="group1", status="active",
        ))
        repo.upsert(AssetRecord(
            id="a3", rel_path="g2/c.png", width=100, height=100,
            size_bytes=1000, ext=".png", group_name="group2", status="active",
        ))
        stats = repo.stats()
        assert stats["by_group"]["group1"] == 2
        assert stats["by_group"]["group2"] == 1

    def test_stats_excludes_deleted(
        self, repo: SQLiteAssetRepository
    ) -> None:
        repo.upsert(AssetRecord(
            id="a1", rel_path="a.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", status="active",
        ))
        repo.upsert(AssetRecord(
            id="a2", rel_path="b.jpg", width=100, height=100,
            size_bytes=1000, ext=".jpg", status="active",
        ))
        repo.mark_deleted("a2")
        stats = repo.stats()
        assert stats["total"] == 1


class TestSQLiteAssetRepositoryMarkDeleted:
    """Tests for the mark_deleted (soft-delete) method."""

    def test_mark_deleted_sets_timestamp(
        self, repo: SQLiteAssetRepository, sample_record: AssetRecord
    ) -> None:
        repo.upsert(sample_record)
        repo.mark_deleted("asset-1")
        # Direct DB check: deleted_at should be set
        row = repo._db.query_one(
            "SELECT deleted_at FROM assets WHERE id = ?", ("asset-1",)
        )
        assert row is not None
        assert row["deleted_at"] is not None

    def test_mark_deleted_excludes_from_get(
        self, repo: SQLiteAssetRepository, sample_record: AssetRecord
    ) -> None:
        repo.upsert(sample_record)
        repo.mark_deleted("asset-1")
        assert repo.get("asset-1") is None

    def test_mark_deleted_excludes_from_list(
        self, repo: SQLiteAssetRepository, sample_record: AssetRecord
    ) -> None:
        repo.upsert(sample_record)
        repo.mark_deleted("asset-1")
        all_assets = repo.list()
        assert len(all_assets) == 0

    def test_mark_deleted_excludes_from_stats(
        self, repo: SQLiteAssetRepository, sample_record: AssetRecord
    ) -> None:
        repo.upsert(sample_record)
        repo.mark_deleted("asset-1")
        stats = repo.stats()
        assert stats["total"] == 0

    def test_mark_deleted_idempotent(
        self, repo: SQLiteAssetRepository, sample_record: AssetRecord
    ) -> None:
        """Calling mark_deleted twice should not raise."""
        repo.upsert(sample_record)
        repo.mark_deleted("asset-1")
        repo.mark_deleted("asset-1")  # second call — no-op
        assert repo.get("asset-1") is None

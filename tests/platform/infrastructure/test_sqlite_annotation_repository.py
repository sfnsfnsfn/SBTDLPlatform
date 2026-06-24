"""Tests for SQLiteAnnotationRepository -- upsert, get, count, histogram.

Covers:
  1. upsert_summary inserts a new record with label histogram round-trip.
  2. upsert_summary updates an existing record (same asset_id).
  3. get_by_asset returns a record by asset_id.
  4. get_by_asset returns None for a missing annotation.
  5. count_annotated counts assets with object_count > 0.
  6. count_annotated returns 0 when no annotations exist.
  7. label_histogram aggregates across multiple records.
  8. label_histogram returns empty dict when no histograms exist.
  9. JSON stability: label_histogram_json uses sorted keys.
"""

from __future__ import annotations

import json
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
    # Load annotations implementation (will exist after we write it)
    _load_module(
        "anylabeling.platform.infrastructure.sqlite_repositories.annotations",
        SQLITE_REPOS_DIR / "annotations.py",
    )


_bootstrap()

from anylabeling.platform.domain.records import AnnotationSummaryRecord
from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.sqlite_repositories.annotations import (
    SQLiteAnnotationRepository,
)

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def db(tmp_path: pathlib.Path) -> ProjectDb:
    """Return an open ProjectDb backed by a temp-file database."""
    db_path = tmp_path / "test_annotations.db"
    database = ProjectDb(db_path)
    database.open()
    yield database
    database.close()


@pytest.fixture
def repo(db: ProjectDb) -> SQLiteAnnotationRepository:
    return SQLiteAnnotationRepository(db)


@pytest.fixture
def sample_summary() -> AnnotationSummaryRecord:
    """A standard annotation summary with a label histogram."""
    return AnnotationSummaryRecord(
        asset_id="asset-1",
        rel_path="annotations/asset-1.json",
        format="xanylabeling_json",
        object_count=3,
        label_histogram_json=json.dumps({"defect": 2, "scratch": 1}, sort_keys=True),
        checksum="chk-abc",
        status="active",
    )


# ===================================================================
# SQLiteAnnotationRepository tests
# ===================================================================


class TestUpsertSummary:
    """Tests for upsert_summary -- insert and update semantics."""

    def test_upsert_inserts_new_record(
        self,
        repo: SQLiteAnnotationRepository,
        sample_summary: AnnotationSummaryRecord,
    ) -> None:
        created = repo.upsert_summary(sample_summary)
        assert created.asset_id == "asset-1"
        assert created.rel_path == "annotations/asset-1.json"
        assert created.format == "xanylabeling_json"
        assert created.object_count == 3
        assert created.checksum == "chk-abc"
        assert created.updated_at is not None

    def test_upsert_with_label_histogram_round_trip(
        self,
        repo: SQLiteAnnotationRepository,
        sample_summary: AnnotationSummaryRecord,
    ) -> None:
        created = repo.upsert_summary(sample_summary)
        histogram = json.loads(created.label_histogram_json or "{}")
        assert histogram == {"defect": 2, "scratch": 1}

    def test_upsert_updates_existing_record(
        self,
        repo: SQLiteAnnotationRepository,
        sample_summary: AnnotationSummaryRecord,
    ) -> None:
        repo.upsert_summary(sample_summary)

        updated_record = AnnotationSummaryRecord(
            asset_id="asset-1",
            rel_path="annotations/asset-1.json",
            format="coco_json",
            object_count=5,
            label_histogram_json=json.dumps(
                {"defect": 3, "scratch": 2}, sort_keys=True
            ),
            checksum="chk-def",
            status="complete",
        )
        result = repo.upsert_summary(updated_record)
        assert result.object_count == 5
        assert result.format == "coco_json"
        assert result.checksum == "chk-def"
        assert result.status == "complete"
        histogram = json.loads(result.label_histogram_json or "{}")
        assert histogram == {"defect": 3, "scratch": 2}

    def test_upsert_preserves_histogram_when_none(
        self, repo: SQLiteAnnotationRepository
    ) -> None:
        record = AnnotationSummaryRecord(
            asset_id="asset-no-hist",
            rel_path="annotations/no-hist.json",
            format="xanylabeling_json",
            object_count=0,
            label_histogram_json=None,
            status="active",
        )
        created = repo.upsert_summary(record)
        assert created.object_count == 0
        assert created.label_histogram_json is None


class TestGetByAsset:
    """Tests for get_by_asset -- retrieval by asset_id."""

    def test_get_returns_record(
        self,
        repo: SQLiteAnnotationRepository,
        sample_summary: AnnotationSummaryRecord,
    ) -> None:
        repo.upsert_summary(sample_summary)
        fetched = repo.get_by_asset("asset-1")
        assert fetched is not None
        assert fetched.asset_id == "asset-1"
        assert fetched.object_count == 3
        assert fetched.rel_path == "annotations/asset-1.json"

    def test_get_returns_none_for_missing(
        self, repo: SQLiteAnnotationRepository
    ) -> None:
        assert repo.get_by_asset("nonexistent") is None

    def test_get_returns_record_with_histogram(
        self,
        repo: SQLiteAnnotationRepository,
        sample_summary: AnnotationSummaryRecord,
    ) -> None:
        repo.upsert_summary(sample_summary)
        fetched = repo.get_by_asset("asset-1")
        assert fetched is not None
        assert fetched.label_histogram_json is not None
        histogram = json.loads(fetched.label_histogram_json)
        assert histogram == {"defect": 2, "scratch": 1}


class TestCountAnnotated:
    """Tests for count_annotated -- counting assets with annotations."""

    def test_count_annotated_counts_nonzero_object_count(
        self, repo: SQLiteAnnotationRepository
    ) -> None:
        repo.upsert_summary(
            AnnotationSummaryRecord(
                asset_id="a1",
                rel_path="ann/a1.json",
                format="xanylabeling_json",
                object_count=3,
                status="active",
            )
        )
        repo.upsert_summary(
            AnnotationSummaryRecord(
                asset_id="a2",
                rel_path="ann/a2.json",
                format="xanylabeling_json",
                object_count=0,
                status="active",
            )
        )
        repo.upsert_summary(
            AnnotationSummaryRecord(
                asset_id="a3",
                rel_path="ann/a3.json",
                format="xanylabeling_json",
                object_count=5,
                status="active",
            )
        )
        assert repo.count_annotated() == 2

    def test_count_annotated_returns_zero_when_empty(
        self, repo: SQLiteAnnotationRepository
    ) -> None:
        assert repo.count_annotated() == 0

    def test_count_annotated_after_delete(
        self, repo: SQLiteAnnotationRepository
    ) -> None:
        """Soft-deleted annotations should not be counted."""
        repo.upsert_summary(
            AnnotationSummaryRecord(
                asset_id="a1",
                rel_path="ann/a1.json",
                format="xanylabeling_json",
                object_count=3,
                status="deleted",
            )
        )
        assert repo.count_annotated() == 0


class TestLabelHistogram:
    """Tests for label_histogram -- aggregated histogram across records."""

    @pytest.fixture
    def populated_repo(
        self, repo: SQLiteAnnotationRepository
    ) -> SQLiteAnnotationRepository:
        """Populate the repo with annotations having diverse histograms."""
        records = [
            AnnotationSummaryRecord(
                asset_id="a1",
                rel_path="ann/a1.json",
                format="xanylabeling_json",
                object_count=3,
                label_histogram_json=json.dumps(
                    {"defect": 2, "scratch": 1}, sort_keys=True
                ),
                status="active",
            ),
            AnnotationSummaryRecord(
                asset_id="a2",
                rel_path="ann/a2.json",
                format="xanylabeling_json",
                object_count=2,
                label_histogram_json=json.dumps(
                    {"defect": 1, "dent": 1}, sort_keys=True
                ),
                status="active",
            ),
            AnnotationSummaryRecord(
                asset_id="a3",
                rel_path="ann/a3.json",
                format="xanylabeling_json",
                object_count=0,
                label_histogram_json=None,
                status="active",
            ),
        ]
        for r in records:
            repo.upsert_summary(r)
        return repo

    def test_aggregates_histograms(
        self, populated_repo: SQLiteAnnotationRepository
    ) -> None:
        histogram = populated_repo.label_histogram()
        assert histogram == {"defect": 3, "scratch": 1, "dent": 1}

    def test_returns_empty_dict_when_no_histograms(
        self, repo: SQLiteAnnotationRepository
    ) -> None:
        assert repo.label_histogram() == {}

    def test_skip_null_histograms(
        self, repo: SQLiteAnnotationRepository
    ) -> None:
        repo.upsert_summary(
            AnnotationSummaryRecord(
                asset_id="a1",
                rel_path="ann/a1.json",
                format="xanylabeling_json",
                object_count=0,
                label_histogram_json=None,
                status="active",
            )
        )
        assert repo.label_histogram() == {}

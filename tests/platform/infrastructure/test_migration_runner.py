"""Tests for MigrationRunner — applies SQL migrations idempotently.

Covers:
  1. All expected tables exist after running migration.
  2. Running migration twice is idempotent (no error, same tables).
  3. The version is recorded in schema_migrations.
  4. Structural completeness: all 11 tables present.
"""

from __future__ import annotations

import pathlib
import sys
import types
from importlib import util as importlib_util

import pytest

# ---------------------------------------------------------------------------
# Manual package bootstrap — same pattern as test_project_db.py
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PLATFORM_DIR = REPO_ROOT / "anylabeling" / "platform"
INFRA_DIR = PLATFORM_DIR / "infrastructure"
MIGRATIONS_DIR = INFRA_DIR / "migrations"


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
    _ensure_package("anylabeling.platform.infrastructure", INFRA_DIR)
    _load_module(
        "anylabeling.platform.infrastructure.project_db",
        INFRA_DIR / "project_db.py",
    )
    _load_module(
        "anylabeling.platform.infrastructure.migration_runner",
        INFRA_DIR / "migration_runner.py",
    )


_bootstrap()

from anylabeling.platform.infrastructure.migration_runner import MigrationRunner
from anylabeling.platform.infrastructure.project_db import ProjectDb

# ---------------------------------------------------------------------------
# Expected tables from 0001_init.sql
# ---------------------------------------------------------------------------

EXPECTED_TABLES = [
    "schema_migrations",
    "project_meta",
    "labels",
    "assets",
    "annotation_summaries",
    "dataset_builds",
    "runs",
    "jobs",
    "models",
    "evaluations",
    "events",
]


# ===================================================================
# MigrationRunner tests
# ===================================================================


class TestMigrationRunner:
    """Tests for MigrationRunner."""

    def test_migration_creates_all_tables(self, tmp_path: pathlib.Path) -> None:
        """Running the migration creates every expected table."""
        db_path = tmp_path / "project.db"
        db = ProjectDb(db_path)
        db.open()
        try:
            runner = MigrationRunner(db, MIGRATIONS_DIR)
            applied = runner.run()

            assert len(applied) >= 1
            assert "0001_init" in applied

            tables = db.query_all(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            table_names = {row["name"] for row in tables}

            for name in EXPECTED_TABLES:
                assert name in table_names, f"Missing table: {name}"
        finally:
            db.close()

    def test_idempotent_migration(self, tmp_path: pathlib.Path) -> None:
        """Running migration twice does not error and produces identical tables."""
        db_path = tmp_path / "project.db"
        db = ProjectDb(db_path)
        db.open()
        try:
            runner = MigrationRunner(db, MIGRATIONS_DIR)

            applied1 = runner.run()
            assert "0001_init" in applied1
            tables1 = {
                row["name"]
                for row in db.query_all(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            }

            # Second run — must not raise and must report nothing applied
            applied2 = runner.run()
            assert applied2 == [], f"Expected no new migrations, got {applied2}"

            tables2 = {
                row["name"]
                for row in db.query_all(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            }

            assert tables1 == tables2
        finally:
            db.close()

    def test_version_recorded(self, tmp_path: pathlib.Path) -> None:
        """After migration the version is persisted in schema_migrations."""
        db_path = tmp_path / "project.db"
        db = ProjectDb(db_path)
        db.open()
        try:
            runner = MigrationRunner(db, MIGRATIONS_DIR)
            runner.run()

            versions = db.query_all(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
            version_names = [row["version"] for row in versions]
            assert "0001_init" in version_names
        finally:
            db.close()

    def test_all_expected_tables_present(self, tmp_path: pathlib.Path) -> None:
        """Structural check — all 11 tables exist after full migration."""
        db_path = tmp_path / "project.db"
        db = ProjectDb(db_path)
        db.open()
        try:
            runner = MigrationRunner(db, MIGRATIONS_DIR)
            runner.run()

            tables = db.query_all(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            table_names = [row["name"] for row in tables]

            for name in EXPECTED_TABLES:
                assert name in table_names, f"Missing table: {name}"

            assert len(table_names) >= len(EXPECTED_TABLES)
        finally:
            db.close()

"""Tests for ProjectDb — SQLite database wrapper for project metadata.

Covers:
  1. open() creates the SQLite file on disk.
  2. Row factory provides dict-like access.
  3. Explicit transaction via transaction() + ROLLBACK.
  4. checkpoint() does not raise.
  5. WAL journal mode is enabled.
  6. Foreign keys pragma is enabled.
  7. close() then open() again round-trips data.
"""

from __future__ import annotations

import pathlib
import sys
import types
from importlib import util as importlib_util

import pytest

# ---------------------------------------------------------------------------
# Manual package bootstrap — same pattern as test_project_file_store.py
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PLATFORM_DIR = REPO_ROOT / "anylabeling" / "platform"
INFRA_DIR = PLATFORM_DIR / "infrastructure"


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


_bootstrap()

from anylabeling.platform.infrastructure.project_db import ProjectDb


# ===================================================================
# ProjectDb tests
# ===================================================================


class TestProjectDbOpen:
    """Tests for ProjectDb.open()."""

    def test_open_creates_sqlite_file(self, tmp_path: pathlib.Path) -> None:
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        try:
            assert db_path.exists(), "SQLite file was not created"
            assert db_path.stat().st_size > 0, "SQLite file is empty"
        finally:
            db.close()

    def test_uses_row_factory(self, tmp_path: pathlib.Path) -> None:
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        try:
            db.execute("CREATE TABLE test (id INTEGER, value TEXT)")
            db.execute("INSERT INTO test (id, value) VALUES (?, ?)", (1, "hello"))
            row = db.query_one("SELECT * FROM test WHERE id = ?", (1,))
            assert row is not None
            # sqlite3.Row supports both index and column-name access
            assert row["id"] == 1, "Row factory does not support column-name access"
            assert row["value"] == "hello"
        finally:
            db.close()

    def test_transaction_rollback(self, tmp_path: pathlib.Path) -> None:
        """Use transaction() to get the connection and roll back explicitly."""
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        try:
            db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            db.execute("INSERT INTO test (id, value) VALUES (?, ?)", (1, "hello"))

            # Explicit transaction via the connection
            conn = db.transaction()
            conn.execute("BEGIN")
            conn.execute("INSERT INTO test (id, value) VALUES (?, ?)", (2, "world"))
            conn.execute("INSERT INTO test (id, value) VALUES (?, ?)", (3, "!!!"))
            conn.execute("ROLLBACK")

            # Only the first insert should remain
            rows = db.query_all("SELECT * FROM test ORDER BY id", ())
            assert len(rows) == 1, f"Expected 1 row after rollback, got {len(rows)}"
            assert rows[0]["value"] == "hello"
        finally:
            db.close()

    def test_checkpoint_does_not_raise(self, tmp_path: pathlib.Path) -> None:
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        try:
            # Both checkpoint variants should complete without error
            db.checkpoint()
            db.checkpoint(truncate=True)
        finally:
            db.close()

    def test_wal_mode_enabled(self, tmp_path: pathlib.Path) -> None:
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        try:
            row = db.query_one("PRAGMA journal_mode", ())
            assert row is not None
            # WAL mode returns "wal" (or "WAL" depending on the PRAGMA output)
            assert row[0].lower() == "wal", (
                f"Expected WAL journal mode, got {row[0]}"
            )
        finally:
            db.close()

    def test_foreign_keys_enabled(self, tmp_path: pathlib.Path) -> None:
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        try:
            row = db.query_one("PRAGMA foreign_keys", ())
            assert row is not None
            assert row[0] == 1, (
                f"Expected foreign_keys=1, got {row[0]}"
            )
        finally:
            db.close()

    def test_close_then_open_again(self, tmp_path: pathlib.Path) -> None:
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO test (id, value) VALUES (?, ?)", (1, "hello"))
        db.close()

        # Reopen and verify data persists
        db2 = ProjectDb(db_path)
        db2.open()
        try:
            row = db2.query_one("SELECT * FROM test WHERE id = ?", (1,))
            assert row is not None
            assert row["value"] == "hello"
        finally:
            db2.close()

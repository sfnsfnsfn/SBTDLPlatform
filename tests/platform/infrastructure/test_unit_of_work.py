"""Tests for UnitOfWork — explicit transaction boundary for ProjectDb.

Covers:
  1. Context manager commits on normal exit.
  2. Context manager rolls back on exception exit.
  3. Explicit commit() persists data immediately.
  4. Explicit rollback() discards changes immediately.
  5. Nested UnitOfWork raises RuntimeError.
  6. commit() then __exit__ does not raise (safe double-close).
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


def _ensure_package(
    name: str, path: pathlib.Path | None = None
) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [] if path is None else [str(path)]
    return module


def _load_module(name: str, path: pathlib.Path) -> types.ModuleType:
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None) == str(
        path
    ):
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
# UnitOfWork tests
# ===================================================================


class TestUnitOfWorkEnterExit:
    """Tests for the UnitOfWork context-manager lifecycle."""

    def test_enter_exit_commits_on_success(
        self, tmp_path: pathlib.Path
    ) -> None:
        """INSERT inside UoW is visible after the context exits normally."""
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        try:
            from anylabeling.platform.infrastructure.unit_of_work import (
                UnitOfWork,
            )

            with UnitOfWork(db):
                db.execute(
                    "INSERT INTO test (id, value) VALUES (?, ?)", (1, "hello")
                )

            row = db.query_one("SELECT * FROM test WHERE id = ?", (1,))
            assert row is not None
            assert row["value"] == "hello"
        finally:
            db.close()

    def test_exit_rolls_back_on_exception(
        self, tmp_path: pathlib.Path
    ) -> None:
        """INSERT inside UoW is NOT visible after exception exit."""
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        try:
            from anylabeling.platform.infrastructure.unit_of_work import (
                UnitOfWork,
            )

            with pytest.raises(ValueError, match="boom"):
                with UnitOfWork(db):
                    db.execute(
                        "INSERT INTO test (id, value) VALUES (?, ?)",
                        (1, "hello"),
                    )
                    raise ValueError("boom")

            row = db.query_one("SELECT * FROM test WHERE id = ?", (1,))
            assert row is None, "Data should have been rolled back"
        finally:
            db.close()

    def test_commit_explicitly(self, tmp_path: pathlib.Path) -> None:
        """Explicit commit() persists data before the context exits."""
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        try:
            from anylabeling.platform.infrastructure.unit_of_work import (
                UnitOfWork,
            )

            with UnitOfWork(db) as uow:
                db.execute(
                    "INSERT INTO test (id, value) VALUES (?, ?)", (1, "hello")
                )
                uow.commit()

            # Data should be visible after explicit commit
            row = db.query_one("SELECT * FROM test WHERE id = ?", (1,))
            assert row is not None
            assert row["value"] == "hello"
        finally:
            db.close()

    def test_rollback_explicitly(self, tmp_path: pathlib.Path) -> None:
        """Explicit rollback() discards changes before the context exits."""
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        try:
            from anylabeling.platform.infrastructure.unit_of_work import (
                UnitOfWork,
            )

            with UnitOfWork(db) as uow:
                db.execute(
                    "INSERT INTO test (id, value) VALUES (?, ?)", (1, "hello")
                )
                uow.rollback()

            # Data should NOT be visible after explicit rollback
            row = db.query_one("SELECT * FROM test WHERE id = ?", (1,))
            assert row is None, "Data should have been rolled back"
        finally:
            db.close()

    def test_nested_uow_raises(self, tmp_path: pathlib.Path) -> None:
        """Nesting a UnitOfWork inside another raises RuntimeError."""
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        try:
            from anylabeling.platform.infrastructure.unit_of_work import (
                UnitOfWork,
            )

            with UnitOfWork(db):
                with pytest.raises(RuntimeError, match="Nested"):
                    with UnitOfWork(db):
                        pass  # pragma: no cover
        finally:
            db.close()

    def test_commit_then_exit_does_not_raise(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Calling commit() then exiting normally should not cause an error."""
        db_path = tmp_path / "test.db"
        db = ProjectDb(db_path)
        db.open()
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        try:
            from anylabeling.platform.infrastructure.unit_of_work import (
                UnitOfWork,
            )

            with UnitOfWork(db) as uow:
                db.execute(
                    "INSERT INTO test (id, value) VALUES (?, ?)", (1, "hello")
                )
                uow.commit()

            # Expect no OperationalError from a second COMMIT
            row = db.query_one("SELECT * FROM test WHERE id = ?", (1,))
            assert row is not None
        finally:
            db.close()

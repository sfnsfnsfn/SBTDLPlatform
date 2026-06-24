"""SQLite-backed repository for trained model records."""

from __future__ import annotations

import sqlite3
from anylabeling.platform.domain.records import ModelRecord
from anylabeling.platform.infrastructure.project_db import ProjectDb

from ._utils import utc_now_iso as _now


class SQLiteModelRepository:
    """SQLite-backed repository for :class:`ModelRecord` persistence.

    Manages the ``models`` table using ``INSERT … ON CONFLICT`` upsert
    semantics — every write is an upsert keyed on the model *id*.
    """

    def __init__(self, db: ProjectDb) -> None:
        self._db = db
        self._ensure_table()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        self._db.execute("""\
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

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_ready(self) -> list[ModelRecord]:
        rows = self._db.query_all(
            "SELECT * FROM models WHERE ready = 1 ORDER BY updated_at DESC"
        )
        return [self._row_to_record(r) for r in rows]

    def get_by_run(self, run_id: str) -> ModelRecord | None:
        row = self._db.query_one(
            "SELECT * FROM models WHERE run_id = ? "
            "ORDER BY updated_at DESC, rowid DESC",
            (run_id,),
        )
        return self._row_to_record(row) if row else None

    def _get_by_id(self, model_id: str) -> ModelRecord | None:
        row = self._db.query_one(
            "SELECT * FROM models WHERE id = ?", (model_id,)
        )
        return self._row_to_record(row) if row else None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def upsert(self, record: ModelRecord) -> ModelRecord:
        now = _now()
        self._db.execute(
            """\
INSERT INTO models (
    id, run_id, name, format, path, task_family,
    metrics_json, ready, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    run_id       = excluded.run_id,
    name         = excluded.name,
    format       = excluded.format,
    path         = excluded.path,
    task_family  = excluded.task_family,
    metrics_json = excluded.metrics_json,
    ready        = excluded.ready,
    created_at   = excluded.created_at,
    updated_at   = excluded.updated_at""",
            (
                record.id,
                record.run_id,
                record.name,
                record.format,
                record.path,
                record.task_family,
                record.metrics_json,
                1 if record.ready else 0,
                now if record.created_at is None else record.created_at,
                now if record.updated_at is None else record.updated_at,
            ),
        )
        result = self._get_by_id(record.id)
        assert result is not None, "Record must exist immediately after upsert"
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ModelRecord:
        return ModelRecord(
            id=row["id"],
            run_id=row["run_id"],
            name=row["name"],
            format=row["format"],
            path=row["path"],
            task_family=row["task_family"],
            metrics_json=row["metrics_json"],
            ready=bool(row["ready"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

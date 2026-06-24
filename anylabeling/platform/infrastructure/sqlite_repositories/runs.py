"""SQLite-backed repository for training run records."""

from __future__ import annotations

import sqlite3
from anylabeling.platform.domain.records import RunRecord
from anylabeling.platform.infrastructure.project_db import ProjectDb

from ._utils import utc_now_iso as _now


class SQLiteRunRepository:
    """SQLite-backed repository for :class:`RunRecord` persistence.

    Manages the ``runs`` table and uses ``INSERT … ON CONFLICT`` upsert
    semantics for all write operations.
    """

    def __init__(self, db: ProjectDb) -> None:
        self._db = db
        self._ensure_table()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        self._db.execute("""\
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

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, run_id: str) -> RunRecord | None:
        row = self._db.query_one(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        )
        return self._row_to_record(row) if row else None

    def list_completed(self) -> list[RunRecord]:
        rows = self._db.query_all(
            "SELECT * FROM runs WHERE status = 'completed' "
            "ORDER BY updated_at DESC"
        )
        return [self._row_to_record(r) for r in rows]

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def create(self, record: RunRecord) -> RunRecord:
        now = _now()
        self._db.execute(
            """\
INSERT INTO runs (
    id, dataset_build_id, adapter_id, task_family, status,
    config_json, metrics_json, best_model_path, log_path,
    started_at, finished_at, updated_at, error_message
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    dataset_build_id = excluded.dataset_build_id,
    adapter_id       = excluded.adapter_id,
    task_family      = excluded.task_family,
    status           = excluded.status,
    config_json      = excluded.config_json,
    metrics_json     = excluded.metrics_json,
    best_model_path  = excluded.best_model_path,
    log_path         = excluded.log_path,
    started_at       = excluded.started_at,
    finished_at      = excluded.finished_at,
    updated_at       = excluded.updated_at,
    error_message    = excluded.error_message""",
            (
                record.id,
                record.dataset_build_id,
                record.adapter_id,
                record.task_family,
                record.status,
                record.config_json,
                record.metrics_json,
                record.best_model_path,
                record.log_path,
                record.started_at,
                record.finished_at,
                now if record.updated_at is None else record.updated_at,
                record.error_message,
            ),
        )
        result = self.get(record.id)
        assert result is not None, "Record must exist immediately after upsert"
        return result

    def mark_running(self, run_id: str) -> None:
        now = _now()
        self._db.execute(
            "UPDATE runs SET status = 'running', "
            "started_at = ?, updated_at = ? WHERE id = ?",
            (now, now, run_id),
        )

    def mark_completed(self, run_id: str) -> None:
        now = _now()
        self._db.execute(
            "UPDATE runs SET status = 'completed', "
            "finished_at = ?, updated_at = ? WHERE id = ?",
            (now, now, run_id),
        )

    def mark_failed(self, run_id: str, error_message: str) -> None:
        now = _now()
        self._db.execute(
            "UPDATE runs SET status = 'failed', "
            "finished_at = ?, updated_at = ?, error_message = ? "
            "WHERE id = ?",
            (now, now, error_message, run_id),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            id=row["id"],
            dataset_build_id=row["dataset_build_id"],
            adapter_id=row["adapter_id"],
            task_family=row["task_family"],
            status=row["status"],
            config_json=row["config_json"],
            metrics_json=row["metrics_json"],
            best_model_path=row["best_model_path"],
            log_path=row["log_path"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            updated_at=row["updated_at"],
            error_message=row["error_message"],
        )

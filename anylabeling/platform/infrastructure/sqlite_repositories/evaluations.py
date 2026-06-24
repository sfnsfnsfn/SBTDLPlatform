"""SQLite-backed repository for evaluation records."""

from __future__ import annotations

import sqlite3
from anylabeling.platform.domain.records import EvaluationRecord
from anylabeling.platform.infrastructure.project_db import ProjectDb

from ._utils import utc_now_iso as _now


class SQLiteEvaluationRepository:
    """SQLite-backed repository for :class:`EvaluationRecord` persistence.

    Manages the ``evaluations`` table.  Uses ``INSERT … ON CONFLICT``
    upsert semantics for ``create()`` and ``mark_completed()``.
    """

    def __init__(self, db: ProjectDb) -> None:
        self._db = db
        self._ensure_table()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        self._db.execute("""\
CREATE TABLE IF NOT EXISTS evaluations (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    dataset_build_id TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    metrics_json    TEXT,
    report_path     TEXT,
    created_at      TEXT,
    updated_at      TEXT,
    completed_at    TEXT,
    error_message   TEXT
)""")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_by_run(self, run_id: str) -> list[EvaluationRecord]:
        rows = self._db.query_all(
            "SELECT * FROM evaluations WHERE run_id = ? ORDER BY created_at ASC",
            (run_id,),
        )
        return [self._row_to_record(r) for r in rows]

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def create(self, record: EvaluationRecord) -> EvaluationRecord:
        now = _now()
        self._db.execute(
            """\
INSERT INTO evaluations (
    id, run_id, dataset_build_id, status, metrics_json,
    report_path, created_at, updated_at, completed_at, error_message
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    run_id           = excluded.run_id,
    dataset_build_id = excluded.dataset_build_id,
    status           = excluded.status,
    metrics_json     = excluded.metrics_json,
    report_path      = excluded.report_path,
    created_at       = excluded.created_at,
    updated_at       = excluded.updated_at,
    completed_at     = excluded.completed_at,
    error_message    = excluded.error_message""",
            (
                record.id,
                record.run_id,
                record.dataset_build_id,
                record.status,
                record.metrics_json,
                record.report_path,
                now if record.created_at is None else record.created_at,
                now if record.updated_at is None else record.updated_at,
                record.completed_at,
                record.error_message,
            ),
        )
        result = self.get(record.id)
        assert result is not None, "Record must exist immediately after upsert"
        return result

    def get(self, evaluation_id: str) -> EvaluationRecord | None:
        """Retrieve a single evaluation record by ID."""
        row = self._db.query_one(
            "SELECT * FROM evaluations WHERE id = ?", (evaluation_id,)
        )
        return self._row_to_record(row) if row else None

    def mark_completed(
        self, evaluation_id: str, metrics_json: str | None = None
    ) -> None:
        now = _now()
        self._db.execute(
            """\
UPDATE evaluations SET
    status = 'completed',
    metrics_json = ?,
    completed_at = ?,
    updated_at = ?
WHERE id = ?""",
            (metrics_json, now, now, evaluation_id),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> EvaluationRecord:
        return EvaluationRecord(
            id=row["id"],
            run_id=row["run_id"],
            dataset_build_id=row["dataset_build_id"],
            status=row["status"],
            metrics_json=row["metrics_json"],
            report_path=row["report_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
        )

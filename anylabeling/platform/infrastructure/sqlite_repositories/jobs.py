"""SQLite-backed repository for background job records."""

from __future__ import annotations

import sqlite3
from anylabeling.platform.domain.records import JobRecord
from anylabeling.platform.infrastructure.project_db import ProjectDb

from ._utils import utc_now_iso as _now


class SQLiteJobRepository:
    """SQLite-backed repository for :class:`JobRecord` persistence.

    Manages the ``jobs`` table.  Active jobs are those whose ``state`` is
    ``'pending'`` or ``'running'`` (i.e. non-terminal).
    """

    _TERMINAL_STATES = frozenset({"completed", "failed"})

    def __init__(self, db: ProjectDb) -> None:
        self._db = db
        self._ensure_table()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        self._db.execute("""\
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    state         TEXT NOT NULL,
    progress      REAL NOT NULL DEFAULT 0.0,
    entity_type   TEXT,
    entity_id     TEXT,
    payload_json  TEXT,
    log_path      TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    finished_at   TEXT,
    error_message TEXT
)""")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> JobRecord | None:
        row = self._db.query_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return self._row_to_record(row) if row else None

    def list_active(self) -> list[JobRecord]:
        rows = self._db.query_all(
            "SELECT * FROM jobs WHERE state NOT IN "
            "('completed', 'failed') ORDER BY created_at ASC"
        )
        return [self._row_to_record(r) for r in rows]

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def create(self, record: JobRecord) -> JobRecord:
        now = _now()
        self._db.execute(
            """\
INSERT INTO jobs (
    id, kind, state, progress, entity_type, entity_id,
    payload_json, log_path, created_at, updated_at,
    finished_at, error_message
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    kind          = excluded.kind,
    state         = excluded.state,
    progress      = excluded.progress,
    entity_type   = excluded.entity_type,
    entity_id     = excluded.entity_id,
    payload_json  = excluded.payload_json,
    log_path      = excluded.log_path,
    created_at    = excluded.created_at,
    updated_at    = excluded.updated_at,
    finished_at   = excluded.finished_at,
    error_message = excluded.error_message""",
            (
                record.id,
                record.kind,
                record.state,
                record.progress,
                record.entity_type,
                record.entity_id,
                record.payload_json,
                record.log_path,
                now if record.created_at is None else record.created_at,
                now if record.updated_at is None else record.updated_at,
                record.finished_at,
                record.error_message,
            ),
        )
        result = self.get(record.id)
        assert result is not None, "Record must exist immediately after upsert"
        return result

    def update_progress(self, job_id: str, progress: float) -> None:
        now = _now()
        self._db.execute(
            "UPDATE jobs SET progress = ?, updated_at = ? WHERE id = ?",
            (progress, now, job_id),
        )

    def mark_completed(self, job_id: str) -> None:
        now = _now()
        self._db.execute(
            "UPDATE jobs SET state = 'completed', "
            "finished_at = ?, updated_at = ? WHERE id = ?",
            (now, now, job_id),
        )

    def mark_failed(self, job_id: str, error_message: str) -> None:
        now = _now()
        self._db.execute(
            "UPDATE jobs SET state = 'failed', "
            "finished_at = ?, updated_at = ?, error_message = ? "
            "WHERE id = ?",
            (now, now, error_message, job_id),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            kind=row["kind"],
            state=row["state"],
            progress=row["progress"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            payload_json=row["payload_json"],
            log_path=row["log_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            finished_at=row["finished_at"],
            error_message=row["error_message"],
        )

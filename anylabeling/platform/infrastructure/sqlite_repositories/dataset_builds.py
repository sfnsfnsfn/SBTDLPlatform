"""SQLite-backed repository for dataset build records."""

from __future__ import annotations

import sqlite3
from anylabeling.platform.domain.records import DatasetBuildRecord
from anylabeling.platform.infrastructure.project_db import ProjectDb

from ._utils import utc_now_iso as _now


class SQLiteDatasetBuildRepository:
    """SQLite-backed repository for :class:`DatasetBuildRecord` persistence.

    Manages the ``dataset_builds`` table and implements the full state machine:

        pending -> running -> completed
                          then -> failed

    Soft-delete is supported via the ``deleted_at`` column; records with a
    non-null ``deleted_at`` are excluded from ``list_completed()`` and
    ``get_latest_completed()``.
    """

    def __init__(self, db: ProjectDb) -> None:
        self._db = db
        self._ensure_table()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        self._db.execute("""\
CREATE TABLE IF NOT EXISTS dataset_builds (
    id                    TEXT PRIMARY KEY,
    task_family           TEXT NOT NULL,
    output_path           TEXT NOT NULL,
    split_strategy        TEXT NOT NULL DEFAULT '',
    split_seed            INTEGER NOT NULL DEFAULT 42,
    split_ratios_json     TEXT,
    tile_plan_json        TEXT,
    preprocess_config_json TEXT,
    manifest_hash         TEXT NOT NULL DEFAULT '',
    status                TEXT NOT NULL DEFAULT 'pending',
    created_at            TEXT,
    updated_at            TEXT,
    completed_at          TEXT,
    deleted_at            TEXT,
    error_message         TEXT
)""")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, build_id: str) -> DatasetBuildRecord | None:
        row = self._db.query_one(
            "SELECT * FROM dataset_builds WHERE id = ?", (build_id,)
        )
        return self._row_to_record(row) if row else None

    def list_completed(self) -> list[DatasetBuildRecord]:
        rows = self._db.query_all(
            "SELECT * FROM dataset_builds "
            "WHERE status = 'completed' AND deleted_at IS NULL "
            "ORDER BY completed_at DESC, ROWID DESC"
        )
        return [self._row_to_record(r) for r in rows]

    def get_latest_completed(self) -> DatasetBuildRecord | None:
        row = self._db.query_one(
            "SELECT * FROM dataset_builds "
            "WHERE status = 'completed' AND deleted_at IS NULL "
            "ORDER BY completed_at DESC, ROWID DESC LIMIT 1"
        )
        return self._row_to_record(row) if row else None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def create(self, record: DatasetBuildRecord) -> DatasetBuildRecord:
        now = _now()
        self._db.execute(
            """\
INSERT INTO dataset_builds (
    id, task_family, output_path, split_strategy, split_seed,
    split_ratios_json, tile_plan_json, preprocess_config_json,
    manifest_hash, status, created_at, updated_at,
    completed_at, deleted_at, error_message
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    task_family            = excluded.task_family,
    output_path            = excluded.output_path,
    split_strategy         = excluded.split_strategy,
    split_seed             = excluded.split_seed,
    split_ratios_json      = excluded.split_ratios_json,
    tile_plan_json         = excluded.tile_plan_json,
    preprocess_config_json = excluded.preprocess_config_json,
    manifest_hash          = excluded.manifest_hash,
    status                 = excluded.status,
    created_at             = excluded.created_at,
    updated_at             = excluded.updated_at,
    completed_at           = excluded.completed_at,
    deleted_at             = excluded.deleted_at,
    error_message          = excluded.error_message""",
            (
                record.id,
                record.task_family,
                record.output_path,
                record.split_strategy,
                record.split_seed,
                record.split_ratios_json,
                record.tile_plan_json,
                record.preprocess_config_json,
                record.manifest_hash,
                record.status,
                now if record.created_at is None else record.created_at,
                now if record.updated_at is None else record.updated_at,
                record.completed_at,
                record.deleted_at,
                record.error_message,
            ),
        )
        result = self.get(record.id)
        assert result is not None, "Record must exist immediately after upsert"
        return result

    def mark_running(self, build_id: str) -> None:
        now = _now()
        self._db.execute(
            "UPDATE dataset_builds SET status = 'running', "
            "updated_at = ? WHERE id = ?",
            (now, build_id),
        )

    def mark_completed(self, build_id: str) -> None:
        now = _now()
        self._db.execute(
            "UPDATE dataset_builds SET status = 'completed', "
            "completed_at = ?, updated_at = ? WHERE id = ?",
            (now, now, build_id),
        )

    def mark_failed(self, build_id: str, error_message: str) -> None:
        now = _now()
        self._db.execute(
            "UPDATE dataset_builds SET status = 'failed', "
            "completed_at = ?, updated_at = ?, error_message = ? "
            "WHERE id = ?",
            (now, now, error_message, build_id),
        )

    def mark_deleted(self, build_id: str) -> None:
        now = _now()
        self._db.execute(
            "UPDATE dataset_builds SET deleted_at = ?, "
            "updated_at = ? WHERE id = ?",
            (now, now, build_id),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> DatasetBuildRecord:
        return DatasetBuildRecord(
            id=row["id"],
            task_family=row["task_family"],
            output_path=row["output_path"],
            split_strategy=row["split_strategy"],
            split_seed=row["split_seed"],
            split_ratios_json=row["split_ratios_json"],
            tile_plan_json=row["tile_plan_json"],
            preprocess_config_json=row["preprocess_config_json"],
            manifest_hash=row["manifest_hash"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            deleted_at=row["deleted_at"],
            error_message=row["error_message"],
        )

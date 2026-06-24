"""SQLite-backed repository for asset records.

Manages the ``assets`` table with ``INSERT … ON CONFLICT(rel_path) DO UPDATE``
upsert semantics — keyed on the relative path rather than the asset id so that
re-importing the same file path updates rather than duplicates.

All query methods filter out soft-deleted rows (``deleted_at IS NULL``).
"""

from __future__ import annotations

import sqlite3
from anylabeling.platform.domain.records import AssetRecord
from anylabeling.platform.infrastructure.project_db import ProjectDb

from ._utils import utc_now_iso as _now


class SQLiteAssetRepository:
    """SQLite-backed repository for :class:`AssetRecord` persistence.

    Manages the ``assets`` table.  Upserts are keyed on ``rel_path`` (the
    unique constraint), so two records for the same file path collapse into
    one row.  Soft-deleted rows are excluded from all read queries.

    Args:
        db: An open :class:`ProjectDb` instance.
    """

    def __init__(self, db: ProjectDb) -> None:
        self._db = db
        self._ensure_table()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        self._db.execute("""\
CREATE TABLE IF NOT EXISTS assets (
    id             TEXT PRIMARY KEY,
    rel_path       TEXT NOT NULL UNIQUE,
    width          INTEGER NOT NULL,
    height         INTEGER NOT NULL,
    sha256         TEXT,
    channels       INTEGER,
    ext            TEXT,
    size_bytes     INTEGER NOT NULL DEFAULT 0,
    group_name     TEXT,
    is_large       INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'active',
    source_kind    TEXT,
    source_version TEXT,
    created_at     TEXT,
    updated_at     TEXT,
    deleted_at     TEXT
)""")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def upsert(self, record: AssetRecord) -> AssetRecord:
        """Insert or update an asset record keyed on ``rel_path``.

        If a row with the same ``rel_path`` already exists, all columns
        except ``created_at`` are overwritten with the new values.
        Returns the persisted record as read back from the database.
        """
        now = _now()
        self._db.execute(
            """\
INSERT INTO assets (
    id, rel_path, width, height, sha256, channels, ext,
    size_bytes, group_name, is_large, status,
    source_kind, source_version, created_at, updated_at, deleted_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(rel_path) DO UPDATE SET
    id             = excluded.id,
    width          = excluded.width,
    height         = excluded.height,
    sha256         = excluded.sha256,
    channels       = excluded.channels,
    ext            = excluded.ext,
    size_bytes     = excluded.size_bytes,
    group_name     = excluded.group_name,
    is_large       = excluded.is_large,
    status         = excluded.status,
    source_kind    = excluded.source_kind,
    source_version = excluded.source_version,
    updated_at     = excluded.updated_at,
    deleted_at     = excluded.deleted_at""",
            (
                record.id,
                record.rel_path,
                record.width,
                record.height,
                record.sha256,
                record.channels,
                record.ext,
                record.size_bytes,
                record.group_name,
                1 if record.is_large else 0,
                record.status,
                record.source_kind,
                record.source_version,
                now if record.created_at is None else record.created_at,
                now if record.updated_at is None else record.updated_at,
                record.deleted_at,
            ),
        )
        result = self.get(record.id)
        assert result is not None, "Record must exist immediately after upsert"
        return result

    def mark_deleted(self, asset_id: str) -> None:
        """Soft-delete an asset record by setting ``deleted_at``."""
        now = _now()
        self._db.execute(
            "UPDATE assets SET deleted_at = ?, updated_at = ? WHERE id = ?",
            (now, now, asset_id),
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, asset_id: str) -> AssetRecord | None:
        """Retrieve an active (non-deleted) asset record by id.

        Returns ``None`` if the record does not exist or has been
        soft-deleted.
        """
        row = self._db.query_one(
            "SELECT * FROM assets WHERE id = ? AND deleted_at IS NULL",
            (asset_id,),
        )
        return self._row_to_record(row) if row else None

    def list(
        self,
        offset: int = 0,
        limit: int | None = None,
        group_name: str | None = None,
        status: str | None = None,
    ) -> list[AssetRecord]:
        """List active asset records with optional filtering and pagination.

        Only rows where ``deleted_at IS NULL`` are returned.

        Args:
            offset: Number of rows to skip (for pagination).
            limit: Maximum number of rows to return.
            group_name: If provided, only return assets in this group.
            status: If provided, only return assets with this status.

        Returns:
            A list of :class:`AssetRecord` instances (may be empty).
        """
        clauses = ["deleted_at IS NULL"]
        params: list[str | int] = []

        if group_name is not None:
            clauses.append("group_name = ?")
            params.append(group_name)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)

        where = " AND ".join(clauses)
        sql = f"SELECT * FROM assets WHERE {where} ORDER BY rel_path ASC"

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        elif offset > 0:
            # SQLite requires LIMIT before OFFSET; -1 means no limit
            sql += " LIMIT -1"

        if offset > 0:
            sql += " OFFSET ?"
            params.append(offset)

        rows = self._db.query_all(sql, tuple(params))
        return [self._row_to_record(r) for r in rows]

    def stats(self) -> dict:
        """Return aggregate statistics about active asset records.

        Returns:
            A dictionary with keys:
            - ``total``: total active asset count
            - ``by_status``: mapping of status → count
            - ``by_extension``: mapping of file extension → count
            - ``by_group``: mapping of group name → count

        All counts exclude soft-deleted rows.
        """
        total_row = self._db.query_one(
            "SELECT COUNT(*) AS cnt FROM assets WHERE deleted_at IS NULL"
        )
        total = total_row["cnt"] if total_row else 0

        status_rows = self._db.query_all(
            "SELECT status, COUNT(*) AS cnt FROM assets "
            "WHERE deleted_at IS NULL GROUP BY status"
        )
        by_status: dict[str, int] = {r["status"]: r["cnt"] for r in status_rows}

        ext_rows = self._db.query_all(
            "SELECT ext, COUNT(*) AS cnt FROM assets "
            "WHERE deleted_at IS NULL AND ext IS NOT NULL GROUP BY ext"
        )
        by_extension: dict[str, int] = {r["ext"]: r["cnt"] for r in ext_rows}

        group_rows = self._db.query_all(
            "SELECT group_name, COUNT(*) AS cnt FROM assets "
            "WHERE deleted_at IS NULL AND group_name IS NOT NULL GROUP BY group_name"
        )
        by_group: dict[str, int] = {
            r["group_name"]: r["cnt"] for r in group_rows
        }

        return {
            "total": total,
            "by_status": by_status,
            "by_extension": by_extension,
            "by_group": by_group,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AssetRecord:
        """Convert a ``sqlite3.Row`` to an :class:`AssetRecord`."""
        return AssetRecord(
            id=row["id"],
            rel_path=row["rel_path"],
            width=row["width"],
            height=row["height"],
            sha256=row["sha256"],
            channels=row["channels"],
            ext=row["ext"],
            size_bytes=row["size_bytes"],
            group_name=row["group_name"],
            is_large=bool(row["is_large"]),
            status=row["status"],
            source_kind=row["source_kind"],
            source_version=row["source_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
        )

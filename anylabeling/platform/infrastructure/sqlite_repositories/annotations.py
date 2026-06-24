"""SQLite-backed repository for annotation summary records.

Manages the ``annotation_summaries`` table with ``INSERT … ON CONFLICT(asset_id)
DO UPDATE`` upsert semantics — keyed on ``asset_id`` so each asset has at most
one summary row.

Provides aggregated queries such as ``count_annotated`` and ``label_histogram``
that are used by the platform to power dashboard stats and project reports.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from anylabeling.platform.domain.records import AnnotationSummaryRecord
from anylabeling.platform.infrastructure.project_db import ProjectDb

from ._utils import utc_now_iso as _now


class SQLiteAnnotationRepository:
    """SQLite-backed repository for :class:`AnnotationSummaryRecord` persistence.

    Manages the ``annotation_summaries`` table.  Upserts are keyed on
    ``asset_id`` (PRIMARY KEY), so re-importing annotations for the same asset
    updates the row in place.

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
CREATE TABLE IF NOT EXISTS annotation_summaries (
    asset_id            TEXT PRIMARY KEY,
    rel_path            TEXT NOT NULL,
    format              TEXT NOT NULL,
    object_count        INTEGER NOT NULL DEFAULT 0,
    label_histogram_json TEXT,
    checksum            TEXT,
    status              TEXT NOT NULL DEFAULT 'active',
    updated_at          TEXT
)""")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def upsert_summary(
        self, record: AnnotationSummaryRecord
    ) -> AnnotationSummaryRecord:
        """Insert or update an annotation summary record keyed on ``asset_id``.

        If a row with the same ``asset_id`` already exists, all columns are
        overwritten with the new values and ``updated_at`` is refreshed.
        The ``label_histogram_json`` is stored as JSON text with sorted keys
        for deterministic serialization.

        Args:
            record: The annotation summary to persist.

        Returns:
            The persisted record as read back from the database.
        """
        now = _now()
        # Stable JSON: sort_keys=True ensures deterministic output
        hist_json = record.label_histogram_json
        if hist_json is not None:
            # Re-serialize to guarantee sorted keys regardless of input
            parsed = json.loads(hist_json)
            hist_json = json.dumps(parsed, sort_keys=True)

        self._db.execute(
            """\
INSERT INTO annotation_summaries (
    asset_id, rel_path, format, object_count,
    label_histogram_json, checksum, status, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(asset_id) DO UPDATE SET
    rel_path             = excluded.rel_path,
    format               = excluded.format,
    object_count         = excluded.object_count,
    label_histogram_json = excluded.label_histogram_json,
    checksum             = excluded.checksum,
    status               = excluded.status,
    updated_at           = excluded.updated_at""",
            (
                record.asset_id,
                record.rel_path,
                record.format,
                record.object_count,
                hist_json,
                record.checksum,
                record.status,
                now,
            ),
        )
        result = self.get_by_asset(record.asset_id)
        assert result is not None, "Record must exist immediately after upsert"
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_by_asset(self, asset_id: str) -> AnnotationSummaryRecord | None:
        """Retrieve an annotation summary record by asset id.

        Args:
            asset_id: The asset identifier to look up.

        Returns:
            An :class:`AnnotationSummaryRecord` instance, or ``None`` if no
            record exists for this asset.
        """
        row = self._db.query_one(
            "SELECT * FROM annotation_summaries WHERE asset_id = ?",
            (asset_id,),
        )
        return self._row_to_record(row) if row else None

    def count_annotated(self) -> int:
        """Return the number of assets with annotation summaries.

        Only records with ``object_count > 0`` and ``status = 'active'``
        are counted, excluding empty or soft-deleted annotations.

        Returns:
            The count of annotated assets.
        """
        row = self._db.query_one(
            "SELECT COUNT(*) AS cnt FROM annotation_summaries "
            "WHERE object_count > 0 AND status = 'active'"
        )
        return row["cnt"] if row else 0

    def label_histogram(self) -> dict[str, int]:
        """Aggregate label histograms across all active annotation summaries.

        Iterates over every active record with a non-null
        ``label_histogram_json``, parses the JSON, and sums the counts into a
        single dictionary.

        Returns:
            A dictionary mapping label names to total object counts, or an
            empty dict if no histogram data exists.
        """
        rows = self._db.query_all(
            "SELECT label_histogram_json FROM annotation_summaries "
            "WHERE status = 'active' AND label_histogram_json IS NOT NULL"
        )
        counter: Counter[str] = Counter()
        for row in rows:
            histogram = json.loads(row["label_histogram_json"])
            counter.update(histogram)
        return dict(counter)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AnnotationSummaryRecord:
        """Convert a ``sqlite3.Row`` to an :class:`AnnotationSummaryRecord`."""
        return AnnotationSummaryRecord(
            asset_id=row["asset_id"],
            rel_path=row["rel_path"],
            format=row["format"],
            object_count=row["object_count"],
            label_histogram_json=row["label_histogram_json"],
            checksum=row["checksum"],
            status=row["status"],
            updated_at=row["updated_at"],
        )

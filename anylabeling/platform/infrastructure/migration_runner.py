"""MigrationRunner — applies SQL migration files idempotently.

Reads ``.sql`` files from a *migrations* directory, sorts them by filename,
applies each pending migration inside a single transaction, and records the
version in the ``schema_migrations`` tracking table.

Typical usage::

    db = ProjectDb("/path/to/project.db")
    db.open()

    runner = MigrationRunner(db, Path("migrations"))
    applied = runner.run()
    # -> ["0001_init", "0002_add_foo", ...]
"""

from __future__ import annotations

import logging
from pathlib import Path

from anylabeling.platform.infrastructure.project_db import ProjectDb

_logger = logging.getLogger(__name__)


class MigrationRunner:
    """Reads ``.sql`` files from *migrations_dir* and applies them in order.

    Args:
        db: An open :class:`ProjectDb` instance.
        migrations_dir: Directory containing ``.sql`` migration files.
    """

    def __init__(self, db: ProjectDb, migrations_dir: str | Path) -> None:
        self._db = db
        self._migrations_dir = Path(migrations_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> list[str]:
        """Apply all pending migrations and return the list of version names.

        Each migration is executed inside its own transaction.  If a single
        migration fails the transaction is rolled back so the database is
        left in a consistent state.

        Returns:
            List of version strings (filenames without ``.sql``) that were
            applied during this call.
        """
        applied: list[str] = []
        for version, sql in self._pending():
            _logger.info("Applying migration %s ...", version)
            conn = self._db.connection
            try:
                conn.execute("BEGIN")
                _exec_statements(conn, sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)",
                    (version,),
                )
            except Exception:
                _logger.exception(
                    "Migration %s failed — rolling back.", version
                )
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")
            applied.append(version)
            _logger.info("Migration %s applied successfully.", version)
        return applied

    def applied_versions(self) -> set[str]:
        """Return the set of already-applied migration version names."""
        self._ensure_schema_migrations()
        rows = self._db.query_all(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
        return {row["version"] for row in rows}

    def pending_migrations(self) -> list[tuple[str, str]]:
        """Return ``(version, sql_content)`` for every un-applied migration.

        Migrations are sorted lexicographically by filename, which naturally
        orders ``0001_*`` before ``0002_*``.
        """
        applied = self.applied_versions()
        result: list[tuple[str, str]] = []
        for path in sorted(self._migrations_dir.glob("*.sql")):
            version = path.stem
            if version not in applied:
                result.append((version, path.read_text(encoding="utf-8")))
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_schema_migrations(self) -> None:
        """Create the ``schema_migrations`` tracking table (idempotent)."""
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  version    TEXT PRIMARY KEY,"
            "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )

    def _pending(self) -> list[tuple[str, str]]:
        """Alias for :meth:`pending_migrations` used internally."""
        return self.pending_migrations()


def _exec_statements(
    conn: sqlite3.Connection, sql: str
) -> None:
    """Execute SQL statements one by one within an existing transaction.

    Splits *sql* on semicolons and executes each non-empty statement
    individually.  This avoids the implicit-COMMIT behaviour of
    ``executescript()`` so that the caller can wrap the whole sequence
    inside ``BEGIN … COMMIT / ROLLBACK``.

    Args:
        conn: A ``sqlite3.Connection`` with an active transaction.
        sql: The full SQL content of a migration file.
    """
    import sqlite3 as _sqlite3

    for statement in sql.split(";"):
        stripped = statement.strip()
        if not stripped:
            continue
        conn.execute(stripped)


__all__ = [
    "MigrationRunner",
]

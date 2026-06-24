"""SQLite database wrapper for project metadata.

Provides a lightweight wrapper around ``sqlite3`` with sensible defaults
for a desktop annotation application: WAL mode, foreign keys enabled,
``sqlite3.Row`` row factory, and manual transaction support.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Any

_logger = logging.getLogger(__name__)


class ProjectDb:
    """Lightweight SQLite database wrapper for project metadata storage.

    Manages a connection lifecycle with pre-configured PRAGMAs suitable
    for concurrent reads in a desktop application context.

    Args:
        db_path: Filesystem path to the SQLite database file.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._connection: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def db_path(self) -> Path:
        """Return the database file path."""
        return self._db_path

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the active connection.

        Raises:
            RuntimeError: If the database has not been opened yet.
        """
        if self._connection is None:
            raise RuntimeError(
                "Database is not open. Call open() before accessing the connection."
            )
        return self._connection

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the database connection and apply performance PRAGMAs.

        The connection is configured with:

        * ``timeout=5.0`` for busy handling
        * ``isolation_level=None`` for manual transaction control
        * ``sqlite3.Row`` as the row factory (dict-like access)
        * WAL journal mode for better concurrent read performance
        * Foreign keys enabled
        * ``synchronous = NORMAL`` for a balance of safety and speed
        * ``busy_timeout = 5000`` ms
        * ``temp_store = MEMORY`` for temporary objects
        """
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=5.0,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA temp_store = MEMORY")
        self._connection = conn

    def close(self) -> None:
        """Close the database connection if it is open."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute a single SQL statement and return the cursor.

        Args:
            sql: SQL statement to execute.
            params: Optional parameters for parameterized queries.

        Returns:
            The cursor after execution.
        """
        return self.connection.execute(sql, params)

    def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        """Execute a query and return the first row, or ``None``.

        Args:
            sql: SQL SELECT statement.
            params: Optional parameters for parameterized queries.

        Returns:
            A :class:`sqlite3.Row` instance or ``None`` if no rows match.
        """
        cursor = self.connection.execute(sql, params)
        return cursor.fetchone()

    def query_all(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> list[sqlite3.Row]:
        """Execute a query and return all matching rows.

        Args:
            sql: SQL SELECT statement.
            params: Optional parameters for parameterized queries.

        Returns:
            List of :class:`sqlite3.Row` objects (may be empty).
        """
        cursor = self.connection.execute(sql, params)
        return cursor.fetchall()

    # ------------------------------------------------------------------
    # Transaction support
    # ------------------------------------------------------------------

    def transaction(self) -> sqlite3.Connection:
        """Return the connection for use as a transaction context manager.

        Usage::

            with db.transaction():
                db.execute("INSERT INTO ...", (val,))

        Because ``isolation_level`` is ``None``, the connection is in
        autocommit mode by default.  Wrapping operations in ``with
        db.transaction()`` runs them in a block that will roll back on
        exception.  For multi-statement atomic transactions, open an
        explicit ``BEGIN`` / ``COMMIT`` block::

            conn = db.transaction()
            conn.execute("BEGIN")
            conn.execute("INSERT INTO ...", (val,))
            conn.execute("COMMIT")

        Returns:
            The :class:`sqlite3.Connection` itself.
        """
        return self.connection

    # ------------------------------------------------------------------
    # WAL checkpoint
    # ------------------------------------------------------------------

    def checkpoint(self, truncate: bool = False) -> None:
        """Run a WAL checkpoint to move WAL content into the main database.

        Args:
            truncate: When True, uses ``PRAGMA wal_checkpoint(TRUNCATE)``
                which also truncates the WAL file.
                When False (default), uses ``PRAGMA wal_checkpoint(PASSIVE)``.
        """
        if truncate:
            self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        else:
            self.connection.execute("PRAGMA wal_checkpoint(PASSIVE)")

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> ProjectDb:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


__all__ = [
    "ProjectDb",
]

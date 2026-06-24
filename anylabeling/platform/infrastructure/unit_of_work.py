"""Unit of work — explicit transaction boundary for ProjectDb.

Provides a context manager that wraps a SQLite transaction (BEGIN / COMMIT /
ROLLBACK) around a unit of work.  Nested usage is detected and rejected at
runtime.
"""

from __future__ import annotations

import logging
import threading
from types import TracebackType

from anylabeling.platform.infrastructure.project_db import ProjectDb

_logger = logging.getLogger(__name__)

# Module-level registry tracking which connections currently have an active
# transaction.  This is necessary because ``sqlite3.Connection`` objects do
# not support arbitrary attribute assignment, and we need to detect nested
# ``UnitOfWork`` instances that share the same ``ProjectDb`` connection.
_ACTIVE_TRANSACTIONS: dict[int, bool] = {}
_LOCK = threading.Lock()


class UnitOfWork:
    """Explicit transaction boundary for a :class:`ProjectDb` connection.

    Usage::

        with UnitOfWork(db) as uow:
            db.execute("INSERT INTO ...", (val,))
            uow.commit()          # optional early commit

    On success the context commits automatically; on exception it rolls back.
    Calling :meth:`commit` or :meth:`rollback` explicitly marks the unit of
    work as closed so the context manager does not attempt a second commit.

    Args:
        db: An open :class:`ProjectDb` instance.

    Raises:
        RuntimeError: If a :class:`UnitOfWork` is nested inside another.
    """

    def __init__(self, db: ProjectDb) -> None:
        self._db = db
        self._conn = db.connection
        self._conn_key = id(self._conn)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> UnitOfWork:
        with _LOCK:
            if _ACTIVE_TRANSACTIONS.get(self._conn_key, False):
                raise RuntimeError("Nested UnitOfWork is not supported")
            self._conn.execute("BEGIN")
            _ACTIVE_TRANSACTIONS[self._conn_key] = True
        _logger.debug("UnitOfWork begun")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        with _LOCK:
            if not _ACTIVE_TRANSACTIONS.get(self._conn_key, False):
                return
            try:
                if exc_type is None:
                    self._conn.execute("COMMIT")
                    _logger.debug("UnitOfWork committed")
                else:
                    self._conn.execute("ROLLBACK")
                    _logger.debug("UnitOfWork rolled back")
            finally:
                _ACTIVE_TRANSACTIONS.pop(self._conn_key, None)

    # ------------------------------------------------------------------
    # Explicit transaction control
    # ------------------------------------------------------------------

    def commit(self) -> None:
        """Commit the current transaction immediately."""
        with _LOCK:
            if not _ACTIVE_TRANSACTIONS.get(self._conn_key, False):
                raise RuntimeError("No active transaction to commit")
            self._conn.execute("COMMIT")
            _ACTIVE_TRANSACTIONS.pop(self._conn_key, None)
        _logger.debug("UnitOfWork explicitly committed")

    def rollback(self) -> None:
        """Roll back the current transaction immediately."""
        with _LOCK:
            if not _ACTIVE_TRANSACTIONS.get(self._conn_key, False):
                raise RuntimeError("No active transaction to roll back")
            self._conn.execute("ROLLBACK")
            _ACTIVE_TRANSACTIONS.pop(self._conn_key, None)
        _logger.debug("UnitOfWork explicitly rolled back")


__all__ = [
    "UnitOfWork",
]

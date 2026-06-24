# Plan: Phase B — DB 基础设施

## Summary
建立 SQLite 数据库连接管理、schema 迁移执行器和事务边界三大基础设施。全部为新文件，不修改任何现有代码。ProjectDb 使用标准库 sqlite3 + WAL 模式，MigrationRunner 按版本号幂等执行 SQL，UnitOfWork 提供 context manager 事务边界。

## User Story
As a 平台开发者, I want 项目拥有 SQLite 数据库连接和迁移能力, so that 后续 Repository 层可以持久化元数据。

## Problem → Solution
当前项目无数据库层 → 新建 ProjectDb/MigrationRunner/UnitOfWork 三个独立模块

## Metadata
- **Complexity**: Medium (3 new files, ~300 lines, no existing code modified)
- **Source PRD**: .claude/PRPs/prds/sbtl-platform-v4.prd.md
- **PRD Phase**: Phase B — DB 基础设施
- **Estimated Files**: 6 (3 source + 3 test)

---

## UX Design
N/A — internal infrastructure change. No user-facing UX.

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `anylabeling/platform/infrastructure/__init__.py` | 1-26 | Infrastructure package patterns |
| P0 | `anylabeling/platform/application/project_session.py` | 1-149 | How ProjectSession will consume ProjectDb |
| P1 | `anylabeling/platform/domain/asset.py` | 1-28 | frozen dataclass pattern for records |
| P2 | `tests/platform/infrastructure/test_project_file_store.py` | all | Existing infrastructure test patterns |

---

## Patterns to Mirror

### NAMING_CONVENTION
```python
# SOURCE: project_session.py:1-149, asset.py:1-28
# Classes: PascalCase (ProjectDb, MigrationRunner, UnitOfWork)
# Methods: snake_case with type hints
# Private: _ prefix for internal (_conn, _db_path)
# Properties: @property for read-only access
# Module-level: logger = logging.getLogger(__name__)
```

### ERROR_HANDLING
```python
# SOURCE: project_session.py:87-93
if not path.exists():
    raise FileNotFoundError(f"Project path does not exist: {path}")
# Use specific built-in exceptions; log before raise
```

### LOGGING_PATTERN
```python
# SOURCE: project_session.py:17
import logging
logger = logging.getLogger(__name__)
logger.info("Project opened: %s", path)
```

### TEST_STRUCTURE
```python
# SOURCE: tests/platform/infrastructure/test_project_file_store.py
# tmp_path fixture for isolated filesystem
# AAA pattern
# Class grouping related tests
```

### IMPORT_PATTERN
```python
# SOURCE: project_session.py:13-15
from __future__ import annotations
import logging
from pathlib import Path
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `anylabeling/platform/infrastructure/project_db.py` | CREATE | SQLite connection + PRAGMA management |
| `anylabeling/platform/infrastructure/migration_runner.py` | CREATE | SQL migration executor |
| `anylabeling/platform/infrastructure/migrations/0001_init.sql` | CREATE | Initial schema (10 tables) |
| `anylabeling/platform/infrastructure/unit_of_work.py` | CREATE | Transaction boundary context manager |
| `tests/platform/infrastructure/test_project_db.py` | CREATE | ProjectDb tests |
| `tests/platform/infrastructure/test_migration_runner.py` | CREATE | Migration tests |
| `tests/platform/infrastructure/test_unit_of_work.py` | CREATE | UoW tests |

## NOT Building
- 不修改任何现有文件
- 不接入 WorkbenchWindow 或 ProjectSession
- 不实现 Repository（Phase C 负责）

---

## Step-by-Step Tasks

### Task 1: B1-1 — 实现 ProjectDb
- **ACTION**: Create `anylabeling/platform/infrastructure/project_db.py`
- **IMPLEMENT**:
```python
# project_db.py — SQLite connection with WAL mode and PRAGMA configuration
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ProjectDb:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not open. Call open() first.")
        return self._conn

    def open(self) -> None:
        self._conn = sqlite3.connect(
            str(self._db_path), timeout=5.0, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA temp_store=MEMORY")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, params: tuple | dict | None = None):
        return self.connection.execute(sql, params or ())

    def query_one(self, sql: str, params: tuple | dict | None = None):
        return self.connection.execute(sql, params or ()).fetchone()

    def query_all(self, sql: str, params: tuple | dict | None = None):
        return self.connection.execute(sql, params or ()).fetchall()

    def transaction(self):
        """Context manager for explicit transactions."""
        return self.connection  # caller uses `with db.transaction():`

    def checkpoint(self, truncate: bool = False) -> None:
        mode = "TRUNCATE" if truncate else "PASSIVE"
        self.connection.execute(f"PRAGMA wal_checkpoint({mode})")
```
- **MIRROR**: Follow `logging.getLogger(__name__)` + type hints + docstrings from project_session.py
- **IMPORTS**: `sqlite3, logging, pathlib.Path`
- **GOTCHA**: `isolation_level=None` enables autocommit mode — required for WAL. `row_factory = sqlite3.Row` must be set before any queries. SQLite connection is NOT thread-safe by default.
- **VALIDATE**: `pytest tests/platform/infrastructure/test_project_db.py -q`

### Task 2: B1-2 — 实现 MigrationRunner + 0001_init.sql
- **ACTION**: Create `migration_runner.py` and `migrations/0001_init.sql`
- **IMPLEMENT**: MigrationRunner reads .sql files from migrations/ dir sorted by version, executes them in a `schema_migrations` tracked transaction. The 0001_init.sql creates 10 tables as defined in the PRD section 4.2.
- **MIRROR**: Follow ProjectDb pattern for db access
- **IMPORTS**: `sqlite3, logging, pathlib.Path, importlib.resources`
- **GOTCHA**: Migration must be IDEMPOTENT — `CREATE TABLE IF NOT EXISTS`. Version tracking via `schema_migrations` table.
- **VALIDATE**: `pytest tests/platform/infrastructure/test_migration_runner.py -q`

### Task 3: B1-3 — 实现 UnitOfWork
- **ACTION**: Create `unit_of_work.py`
- **IMPLEMENT**: Context manager wrapping ProjectDb transaction with commit/rollback
- **MIRROR**: Python `__enter__`/`__exit__` context manager pattern
- **IMPORTS**: `logging, types`
- **GOTCHA**: Nested transactions not supported in sqlite3 — detect and raise.
- **VALIDATE**: `pytest tests/platform/infrastructure/test_unit_of_work.py -q`

---

## Testing Strategy

### Unit Tests

**test_project_db.py**:
| Test | Expected |
|---|---|
| `test_open_creates_sqlite_file` | .sqlite file exists after open() |
| `test_uses_row_factory` | query returns sqlite3.Row (dict-like access) |
| `test_transaction_rollback` | Changes rolled back on error |
| `test_checkpoint_does_not_raise` | wal_checkpoint succeeds |
| `test_wal_mode_enabled` | PRAGMA journal_mode returns 'wal' |
| `test_foreign_keys_enabled` | PRAGMA foreign_keys returns 1 |

**test_migration_runner.py**:
| Test | Expected |
|---|---|
| `test_migrate_creates_tables` | All 10 tables exist after migration |
| `test_migrate_is_idempotent` | Running twice does not error or duplicate |
| `test_schema_migrations_recorded` | Version recorded in schema_migrations |

**test_unit_of_work.py**:
| Test | Expected |
|---|---|
| `test_commit_persists` | Data visible after commit |
| `test_rollback_reverts` | Data not visible after rollback |
| `test_nested_transaction_raises` | RuntimeError on nested begin |

## Validation Commands
```bash
pytest tests/platform/infrastructure/test_project_db.py tests/platform/infrastructure/test_migration_runner.py tests/platform/infrastructure/test_unit_of_work.py -q -v
python -m compileall anylabeling/platform/infrastructure/project_db.py anylabeling/platform/infrastructure/migration_runner.py anylabeling/platform/infrastructure/unit_of_work.py
```

## Acceptance Criteria
- [ ] ProjectDb opens/executes/queries/closes correctly with WAL
- [ ] MigrationRunner creates all 10 tables idempotently
- [ ] UnitOfWork commits and rolls back correctly
- [ ] All 3 test files passing
- [ ] Zero existing code modified

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| WAL file locking on Windows | L | LOW | busy_timeout=5000 handles contention |
| importlib.resources path for SQL files | L | MEDIUM | Use `__file__`-relative path as fallback |

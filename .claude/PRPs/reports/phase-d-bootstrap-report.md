# Implementation Report: Phase D — Bootstrap/迁移 + CRITICAL 修复

## Summary
Phase D implemented in 1 turn with: (1) 3 CRITICAL fixes from the verification pipeline, (2) D1-1 ProjectDbBootstrap by Haiku agent, (3) D1-2 CLI by Haiku agent. Path-resolution artifacts fixed. Zero regressions.

## CRITICAL Fixes (from Phase B/C review)

| # | Issue | Fix |
|---|-------|-----|
| C1 | `0001_init.sql` schema mismatch with `_ensure_table()` | Rewrote migration SQL to match all 7 repository schemas exactly |
| C2 | `MigrationRunner.run()` used non-atomic `executescript()` | Replaced with `BEGIN/COMMIT` + `_exec_statements()` helper |
| C3 | `WorkflowQuery.next_action()` misleading BLOCKED message | Added `data_prep_status()` check to distinguish BLOCKED causes |

## Tasks Completed

| Task | Agent | Status | Tests |
|------|-------|--------|-------|
| D1-1: ProjectDbBootstrap | Haiku agent | OK | 7 |
| D1-2: migrate_project_db.py CLI | Haiku agent | OK | 9 |
| C1: Schema mismatch | Manual | OK | 4/4 migration tests |
| C2: Atomic migration | Manual | OK | 4/4 migration tests |
| C3: BLOCKED message | Manual | OK | 26/26 workflow query tests |

## Validation

| Check | Result |
|-------|--------|
| Phase D tests | 16/16 passed |
| CRITICAL fix tests | 34/34 passed |
| Full regression | **351 passed**, 1 pre-existing warning |
| Compile check | All new files clean |
| flake8 | 0 warnings on new files |

## Files Changed

### Fixes (3 files)
- `infrastructure/migrations/0001_init.sql` — REWRITE (schema matches repos)
- `infrastructure/migration_runner.py` — MODIFY (atomic transactions + `_exec_statements`)
- `infrastructure/sqlite_repositories/workflow_query.py` — MODIFY (BLOCKED messages)

### Phase D (6 files)
- `infrastructure/project_db_bootstrap.py` — CREATE (BootstrapReport + ProjectDbBootstrap)
- `scripts/migrate_project_db.py` — CREATE (CLI: --dry-run, --rebuild-index, --check, --checkpoint)
- `tests/infrastructure/test_project_db_bootstrap.py` — CREATE (7 tests)
- `tests/scripts/test_migrate_project_db.py` — CREATE (9 tests)
- `tests/scripts/__init__.py` — CREATE
- `tests/infrastructure/test_migration_runner.py` — MODIFY (updated EXPECTED_TABLES)

## Acceptance
- [x] Old project directory bootstraps to SQLite (D1-1)
- [x] CLI --dry-run, --rebuild-index, --check, --checkpoint (D1-2)
- [x] Migration schema matches repository schemas (C1)
- [x] Migration rollback on failure (C2)
- [x] Workflow BLOCKED distinguishes causes (C3)
- [x] 351 tests pass, zero regressions

---
*Completed: 2026-06-24*
*Agents: Haiku (writing) + Manual (fixes + review)*

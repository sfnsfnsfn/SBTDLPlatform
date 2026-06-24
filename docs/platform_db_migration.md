# Platform Database Migration Guide

## Overview

Phase D introduced a SQLite metadata index (`project.sqlite`) alongside the
legacy V3 filesystem layout.  This index provides fast queries, workflow state
tracking, and a foundation for the repository pattern used by all Phase E--G
services.

The migration flow is:

```
Legacy V3 project  --->  ProjectDbBootstrap  --->  project.sqlite (WAL mode)
```

---

## 1. Bootstrap Flow

### What is bootstrapping?

`ProjectDbBootstrap` scans a legacy project directory and populates the SQLite
index tables by reading the existing filesystem structure.  No data is copied or
moved -- the bootstrap only creates an index.

### Tables populated

| Table                  | Source directory            | File parsed            |
|------------------------|-----------------------------|------------------------|
| `assets`               | `assets/`                   | Image files (dimensions via Pillow) |
| `annotation_summaries` | `annotations/`              | `.json` / `.xml` annotation files |
| `dataset_builds`       | `dataset_builds/*/build.json` | `build.json` metadata |
| `runs`                 | `runs/*/metrics.json`       | `metrics.json` training metrics |
| `models`               | `models/*/metadata.json`    | `metadata.json` model info |

### How it works

```python
from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.project_db_bootstrap import (
    ProjectDbBootstrap,
)

db = ProjectDb("/path/to/project.sqlite")
db.open()

bootstrap = ProjectDbBootstrap(db, "/path/to/project")
report = bootstrap.run()

print(f"Assets scanned:       {report.assets_processed}")
print(f"Annotations scanned:  {report.annotations_processed}")
print(f"Dataset builds:       {report.dataset_builds_processed}")
print(f"Runs:                 {report.runs_processed}")
print(f"Models:               {report.models_processed}")
print(f"Errors (non-fatal):   {len(report.errors)}")

db.close()
```

### Idempotency

Bootstrap is **idempotent**.  Running it repeatedly on the same project:

- Re-upserts asset records (keyed on `rel_path`)
- Re-upserts annotation summaries (keyed on `asset_id`)
- Does not duplicate rows

Deterministic UUIDs (`uuid.uuid5`) are used for asset IDs so that repeated runs
produce identical primary keys.

---

## 2. Checkpoint: `PRAGMA wal_checkpoint(TRUNCATE)`

### Why checkpoint?

`ProjectDb` uses **WAL (Write-Ahead Log)** journal mode for better concurrent
read performance.  When the database is modified, changes are written to a
`.sqlite-wal` file alongside the main `.sqlite` file.  Before copying the
database file, run a WAL checkpoint to merge the WAL content back into the main
file.

### How to checkpoint

```python
from anylabeling.platform.infrastructure.project_db import ProjectDb

db = ProjectDb("/path/to/project.sqlite")
db.open()
db.checkpoint(truncate=True)
db.close()
```

Or via the CLI:

```bash
python scripts/migrate_project_db.py /path/to/project --checkpoint
```

### What it does

```
PRAGMA wal_checkpoint(TRUNCATE);
```

- Moves all pages from the WAL file into the main database file
- Truncates the WAL file to zero bytes (safe to delete)
- The `.sqlite-shm` shared-memory file is also cleared

### When to checkpoint

- **Before copying** a project (backup, share, CI artifact)
- **Before version control** commit of `project.sqlite`
- **After a large bootstrap or migration operation**

---

## 3. Copy Procedure

Safe steps to copy a project with its SQLite index:

### Step 1: Checkpoint

```bash
python scripts/migrate_project_db.py /path/to/source/project --checkpoint
```

### Step 2: Copy the database

```bash
cp /path/to/source/project/project.sqlite /path/to/destination/project/project.sqlite
```

Or use Python:

```python
import shutil
from pathlib import Path

src = Path("/path/to/source/project")
dst = Path("/path/to/destination/project")

# Ensure destination project exists
dst.mkdir(parents=True, exist_ok=True)

# Copy the database
shutil.copy2(src / "project.sqlite", dst / "project.sqlite")

# Copy assets and annotations if needed
if (src / "assets").exists():
    shutil.copytree(src / "assets", dst / "assets", dirs_exist_ok=True)
if (src / "annotations").exists():
    shutil.copytree(src / "annotations", dst / "annotations", dirs_exist_ok=True)
```

### Step 3: Verify

Open the copied database and check record counts:

```bash
python scripts/migrate_project_db.py /path/to/destination/project --check
```

Or manually query:

```bash
sqlite3 /path/to/destination/project/project.sqlite \
  "SELECT 'assets', COUNT(*) FROM assets \
   UNION ALL \
   SELECT 'annotations', COUNT(*) FROM annotation_summaries \
   UNION ALL \
   SELECT 'builds', COUNT(*) FROM dataset_builds"
```

### WAL files

After checkpointing, the `.sqlite-wal` and `.sqlite-shm` files are empty and can
be safely omitted from copy operations.  They will be re-created automatically
when the database is opened again.

---

## 4. Recovery

### Symptom: `project.sqlite` is corrupt

If the database file reports:

```
sqlite3.DatabaseError: database disk image is malformed
```

or `PRAGMA integrity_check` fails.

### Recovery procedure

1. **Delete the corrupt database** (safe -- no data loss, only index loss):

   ```bash
   rm /path/to/project/project.sqlite
   rm -f /path/to/project/project.sqlite-wal
   rm -f /path/to/project/project.sqlite-shm
   ```

2. **Rebuild the index** from the legacy filesystem:

   ```bash
   python scripts/migrate_project_db.py /path/to/project --rebuild-index
   ```

3. **Verify** the new index:

   ```bash
   python scripts/migrate_project_db.py /path/to/project --check
   ```

### What is preserved

All original files in the legacy directories remain untouched:

```
project/
├── assets/            <- intact
├── annotations/       <- intact
├── dataset_builds/    <- intact
├── runs/              <- intact
├── models/            <- intact
└── project.sqlite     <- rebuilt on demand
```

Deleting `project.sqlite` destroys only the index, not the data.  The
filesystem is the source of truth.

### Preventative measures

- Run `--checkpoint` after significant operations
- Keep backups of `project.sqlite` before major changes
- The bootstrap is idempotent -- re-running is always safe

---

## 5. CLI Reference

### `scripts/migrate_project_db.py`

```
usage: migrate_project_db.py [-h]
                             [--dry-run | --rebuild-index | --check | --checkpoint]
                             [--verbose]
                             project_path

Migrate legacy project data to SQLite index.

positional arguments:
  project_path      Path to the project directory

options:
  -h, --help        Show this help message and exit
  --dry-run         Scan without writing to DB; print what would be done
  --rebuild-index   Full bootstrap: scan and populate the SQLite index
  --check           Compare index against filesystem; report mismatches
  --checkpoint      Run a WAL checkpoint on the project SQLite index
  --verbose, -v     Increase logging verbosity (debug level)
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0    | Success |
| 1    | Error (invalid path, missing index, etc.) |

### Examples

```bash
# Preview what would be migrated (no writes)
python scripts/migrate_project_db.py ~/projects/my_dataset --dry-run

# Full bootstrap (create or update project.sqlite)
python scripts/migrate_project_db.py ~/projects/my_dataset --rebuild-index

# Verify consistency between DB and filesystem
python scripts/migrate_project_db.py ~/projects/my_dataset --check

# Run a WAL checkpoint for safe copying
python scripts/migrate_project_db.py ~/projects/my_dataset --checkpoint
```

---

## Appendix: Database Schema

The SQLite index is managed through repository classes that create tables via
`CREATE TABLE IF NOT EXISTS`.  Key tables:

### `assets`

```sql
CREATE TABLE assets (
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
);
```

### `annotation_summaries`

```sql
CREATE TABLE annotation_summaries (
    asset_id            TEXT PRIMARY KEY,
    rel_path            TEXT NOT NULL,
    format              TEXT NOT NULL,
    object_count        INTEGER NOT NULL DEFAULT 0,
    label_histogram_json TEXT,
    checksum            TEXT,
    status              TEXT NOT NULL DEFAULT 'active',
    updated_at          TEXT
);
```

### `dataset_builds`

```sql
CREATE TABLE dataset_builds (
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
);
```

### `runs`

```sql
CREATE TABLE runs (
    id              TEXT PRIMARY KEY,
    dataset_build_id TEXT NOT NULL,
    adapter_id       TEXT NOT NULL,
    task_family      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    config_json      TEXT,
    metrics_json     TEXT,
    best_model_path  TEXT,
    log_path         TEXT,
    started_at       TEXT,
    finished_at      TEXT,
    updated_at       TEXT,
    error_message    TEXT
);
```

### `models`

```sql
CREATE TABLE models (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    name        TEXT NOT NULL,
    format      TEXT NOT NULL,
    path        TEXT NOT NULL,
    task_family TEXT NOT NULL,
    metrics_json TEXT,
    ready       INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT,
    updated_at  TEXT
);
```

### `evaluations`

```sql
CREATE TABLE evaluations (
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
);
```

### `schema_migrations`

```sql
CREATE TABLE schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

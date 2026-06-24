-- 0001_init: Initial schema for X-AnyLabeling project database.
--
-- Creates all core tables with CREATE TABLE IF NOT EXISTS so the migration
-- is safe to re-run (idempotent).
--
-- IMPORTANT: The schemas below MUST match the ``_ensure_table()`` definitions
-- in each SQLite repository class EXACTLY.
--
-- Tables (10):
--   schema_migrations — tracking | project_meta — metadata | labels — definitions
--   assets — SQLiteAssetRepository | annotation_summaries — SQLiteAnnotationRepository
--   dataset_builds — SQLiteDatasetBuildRepository | runs — SQLiteRunRepository
--   jobs — SQLiteJobRepository | models — SQLiteModelRepository
--   evaluations — SQLiteEvaluationRepository | events — audit log

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

CREATE TABLE IF NOT EXISTS labels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    color       TEXT,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

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
);

CREATE TABLE IF NOT EXISTS annotation_summaries (
    asset_id            TEXT PRIMARY KEY,
    rel_path            TEXT NOT NULL,
    format              TEXT NOT NULL,
    object_count        INTEGER NOT NULL DEFAULT 0,
    label_histogram_json TEXT,
    checksum            TEXT,
    status              TEXT NOT NULL DEFAULT 'active',
    updated_at          TEXT
);

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
);

CREATE TABLE IF NOT EXISTS runs (
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
);

CREATE TABLE IF NOT EXISTS models (
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

CREATE TABLE IF NOT EXISTS evaluations (
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

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    source      TEXT,
    data        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

# Plan: Phase C — Repository 层

## Summary
定义 Record DTO 和 Repository Protocol 接口，实现 7 个 SQLite Repository 和 1 个 WorkflowQuery。需先将 `application/ports.py`（44行单文件）转为 `application/ports/` 包目录，保留原有 `AnnotationCodec` Protocol。全部为新文件和测试，不修改现有 Service 或 UI。

## User Story
As a 平台开发者, I want 标准化的数据访问接口和 SQLite 实现, so that Service 层可以通过依赖注入获取数据而不依赖文件系统扫描。

## Problem → Solution
当前无数据访问抽象层 → 新建 Record DTOs + Repository Protocols + 7 SQLite Repos + WorkflowQuery

## Metadata
- **Complexity**: Large (8 new source files, 5 test files, ~1200 lines, ports.py 结构调整)
- **Source PRD**: .claude/PRPs/prds/sbtl-platform-v4.prd.md
- **PRD Phase**: Phase C — Repository 层
- **Estimated Files**: 14 (8 source + 1 migration + 5 test)

---

## UX Design
N/A — internal infrastructure. No user-facing changes.

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `anylabeling/platform/domain/asset.py` | 1-28 | frozen dataclass pattern |
| P0 | `anylabeling/platform/domain/run.py` | 1-42 | Mutable dataclass + Literal status pattern |
| P0 | `anylabeling/platform/application/ports.py` | 1-44 | Must preserve AnnotationCodec Protocol |
| P0 | `anylabeling/platform/infrastructure/project_db.py` | NEW | Will be consumed by SQLite repos |
| P1 | `anylabeling/platform/domain/annotation.py` | 1-71 | AnnotationDocument structure |
| P1 | `anylabeling/platform/domain/dataset.py` | 1-67 | Dataset-related types |
| P2 | `tests/platform/application/test_asset_repository.py` | 1-144 | Repository test patterns |

---

## Patterns to Mirror

### DATACLASS_DTO
```python
# SOURCE: domain/asset.py:6-22
from dataclasses import dataclass

@dataclass(frozen=True)
class Asset:
    id: str
    path: str
    width: int
    height: int
    channels: int | None = None
```

### PROTOCOL_PORT
```python
# SOURCE: application/ports.py:9-41
from typing import Protocol, runtime_checkable

@runtime_checkable
class AnnotationCodec(Protocol):
    def load_annotations(self, file_path, image_width, image_height): ...
    def save_annotations(self, doc, file_path): ...
```

### IMMUTABLE_RECORD_WITH_STATUS
```python
# SOURCE: domain/run.py:16-36
from typing import Literal

@dataclass
class Run:
    id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = "queued"
    metrics: list[MetricPoint] = field(default_factory=list)
```

---

## Files to Change

### Source Files (all CREATE)
| File | Action | Contents |
|---|---|---|
| `anylabeling/platform/domain/records.py` | CREATE | AssetRecord, AnnotationSummaryRecord, DatasetBuildRecord, RunRecord, JobRecord, ModelRecord, EvaluationRecord |
| `anylabeling/platform/domain/workflow_status.py` | CREATE | WorkflowStatus value object |
| `anylabeling/platform/application/ports/__init__.py` | MOVE | From `ports.py` — preserve AnnotationCodec |
| `anylabeling/platform/application/ports/repositories.py` | CREATE | 8 Repository Protocols |
| `infrastructure/sqlite_repositories/__init__.py` | CREATE | Package init |
| `infrastructure/sqlite_repositories/assets.py` | CREATE | SQLiteAssetRepository |
| `infrastructure/sqlite_repositories/annotations.py` | CREATE | SQLiteAnnotationRepository |
| `infrastructure/sqlite_repositories/dataset_builds.py` | CREATE | SQLiteDatasetBuildRepository |
| `infrastructure/sqlite_repositories/runs.py` | CREATE | SQLiteRunRepository |
| `infrastructure/sqlite_repositories/jobs.py` | CREATE | SQLiteJobRepository |
| `infrastructure/sqlite_repositories/models.py` | CREATE | SQLiteModelRepository |
| `infrastructure/sqlite_repositories/evaluations.py` | CREATE | SQLiteEvaluationRepository |
| `infrastructure/sqlite_repositories/workflow_query.py` | CREATE | SQLiteWorkflowQuery |

### Test Files (all CREATE)
| File | Tests |
|---|---|
| `tests/platform/application/test_repository_ports_contract.py` | Protocol contract tests |
| `tests/platform/infrastructure/test_sqlite_asset_repository.py` | Asset repo CRUD |
| `tests/platform/infrastructure/test_sqlite_annotation_repository.py` | Annotation repo |
| `tests/platform/infrastructure/test_sqlite_dataset_build_repository.py` | Build state machine |
| `tests/platform/infrastructure/test_sqlite_run_job_model_repositories.py` | Run/Job/Model repos |
| `tests/platform/infrastructure/test_sqlite_workflow_query.py` | Workflow queries |

## NOT Building
- 不修改 Service 层（Phase E）
- 不修改 WorkbenchWindow（Phase F）
- 不接入 ProjectSession（Phase E）
- 不实现 Bootstrap（Phase D）

---

## Step-by-Step Tasks

### Task 1: C1-1 — 定义 Records + Repository Ports (Agent C1)
- **ACTION**: Create `domain/records.py`, convert `ports.py` → `ports/` package, create `ports/repositories.py`
- **IMPLEMENT**: 7 frozen/mutable dataclass Records (AssetRecord, AnnotationSummaryRecord, DatasetBuildRecord, RunRecord, JobRecord, ModelRecord, EvaluationRecord), WorkflowStatus value object, 8 Repository Protocols (Asset, Annotation, DatasetBuild, Run, Job, Model, Evaluation, WorkflowQuery)
- **CRITICAL**: ports.py conversion — rename to ports/__init__.py, preserve ALL existing code
- **MIRROR**: frozen=True dataclass from asset.py, Protocol from ports.py
- **VALIDATE**: `pytest tests/platform/application/test_repository_ports_contract.py -q`

### Task 2: C1-2 — SQLiteAssetRepository (Agent C1)
- **ACTION**: Create `infrastructure/sqlite_repositories/assets.py`
- **IMPLEMENT**: upsert(record), get(asset_id), list(query), stats(), mark_deleted(asset_id) using INSERT...ON CONFLICT DO UPDATE
- **MIRROR**: ProjectDb.execute/query_all pattern
- **VALIDATE**: `pytest tests/platform/infrastructure/test_sqlite_asset_repository.py -q`

### Task 3: C1-3 — SQLiteAnnotationRepository (Agent C1)
- **ACTION**: Create `infrastructure/sqlite_repositories/annotations.py`
- **IMPLEMENT**: upsert_summary, get_by_asset, count_annotated, label_histogram
- **MIRROR**: Asset repo pattern
- **VALIDATE**: `pytest tests/platform/infrastructure/test_sqlite_annotation_repository.py -q`

### Task 4: C2-1 — SQLiteDatasetBuildRepository (Agent C2)
- **ACTION**: Create `infrastructure/sqlite_repositories/dataset_builds.py`
- **IMPLEMENT**: create→mark_running→mark_completed/mark_failed state machine, list_completed, get_latest_completed
- **MIRROR**: State machine pattern with Literal status
- **VALIDATE**: `pytest tests/platform/infrastructure/test_sqlite_dataset_build_repository.py -q`

### Task 5: C2-2 — SQLiteRun/Job/Model/Evaluation Repos (Agent C2)
- **ACTION**: Create 4 repository files
- **IMPLEMENT**: Run CRUD+status, Job CRUD+progress, Model upsert+ready query, Evaluation CRUD
- **MIRROR**: Same SQLite pattern across all repos
- **VALIDATE**: `pytest tests/platform/infrastructure/test_sqlite_run_job_model_repositories.py -q`

### Task 6: C3-1 — SQLiteWorkflowQuery (Agent C3)
- **ACTION**: Create `infrastructure/sqlite_repositories/workflow_query.py`
- **IMPLEMENT**: 6 COUNT queries + next_action() logic based on status chain
- **MIRROR**: ProjectDb.query_one for scalar results
- **VALIDATE**: `pytest tests/platform/infrastructure/test_sqlite_workflow_query.py -q`

---

## Testing Strategy

### Edge Cases Checklist
- [ ] Empty tables → COUNT returns 0
- [ ] Duplicate upsert → ON CONFLICT updates existing
- [ ] Soft delete → default queries exclude deleted_at NOT NULL
- [ ] Failed status → not included in "ready" queries
- [ ] JSON serialization → dict fields stable round-trip
- [ ] Missing DB → RuntimeError before open()

## Validation Commands
```bash
# Per-repo tests
pytest tests/platform/infrastructure/test_sqlite_asset_repository.py -q -v
pytest tests/platform/infrastructure/test_sqlite_annotation_repository.py -q -v
pytest tests/platform/infrastructure/test_sqlite_dataset_build_repository.py -q -v
pytest tests/platform/infrastructure/test_sqlite_run_job_model_repositories.py -q -v
pytest tests/platform/infrastructure/test_sqlite_workflow_query.py -q -v
pytest tests/platform/application/test_repository_ports_contract.py -q -v

# Compile
python -m compileall anylabeling/platform/domain/records.py anylabeling/platform/application/ports/
```

## Acceptance Criteria
- [ ] 7 Record DTOs defined with correct field types
- [ ] 8 Repository Protocols defined
- [ ] ports.py successfully converted to ports/ package
- [ ] All 7 SQLite Repos pass their tests
- [ ] WorkflowQuery returns correct status chain
- [ ] Zero existing code modified (except ports.py → ports/)

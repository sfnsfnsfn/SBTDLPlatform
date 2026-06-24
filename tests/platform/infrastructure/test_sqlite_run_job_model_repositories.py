"""Tests for SQLite-backed run / job / model / evaluation repositories.

Tests state transitions, progress updates, ready-model queries, and
INSERT … ON CONFLICT upsert semantics for all four repository types.
"""

from __future__ import annotations

import pathlib
import sys
import types
from importlib import util as importlib_util

import pytest

# ---------------------------------------------------------------------------
# Manual package bootstrap (same pattern as test_project_db.py)
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PLATFORM_DIR = REPO_ROOT / "anylabeling" / "platform"
INFRA_DIR = PLATFORM_DIR / "infrastructure"
DOMAIN_DIR = PLATFORM_DIR / "domain"
SQLITE_REPOS_DIR = INFRA_DIR / "sqlite_repositories"


def _ensure_package(name: str, path: pathlib.Path | None = None) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [] if path is None else [str(path)]
    return module


def _load_module(name: str, path: pathlib.Path) -> types.ModuleType:
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None) == str(path):
        return existing
    spec = importlib_util.spec_from_file_location(name, path)
    module = importlib_util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bootstrap() -> None:
    _ensure_package("anylabeling")
    _ensure_package("anylabeling.platform", PLATFORM_DIR)
    _ensure_package("anylabeling.platform.domain", DOMAIN_DIR)
    _ensure_package("anylabeling.platform.infrastructure", INFRA_DIR)
    _ensure_package("anylabeling.platform.infrastructure.sqlite_repositories", SQLITE_REPOS_DIR)

    _load_module(
        "anylabeling.platform.domain.records",
        DOMAIN_DIR / "records.py",
    )
    _load_module(
        "anylabeling.platform.domain.workflow_status",
        DOMAIN_DIR / "workflow_status.py",
    )
    _load_module(
        "anylabeling.platform.infrastructure.project_db",
        INFRA_DIR / "project_db.py",
    )
    _load_module(
        "anylabeling.platform.infrastructure.sqlite_repositories.runs",
        SQLITE_REPOS_DIR / "runs.py",
    )
    _load_module(
        "anylabeling.platform.infrastructure.sqlite_repositories.jobs",
        SQLITE_REPOS_DIR / "jobs.py",
    )
    _load_module(
        "anylabeling.platform.infrastructure.sqlite_repositories.models",
        SQLITE_REPOS_DIR / "models.py",
    )
    _load_module(
        "anylabeling.platform.infrastructure.sqlite_repositories.evaluations",
        SQLITE_REPOS_DIR / "evaluations.py",
    )


_bootstrap()

from anylabeling.platform.domain.records import (
    EvaluationRecord,
    JobRecord,
    ModelRecord,
    RunRecord,
)
from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.sqlite_repositories.evaluations import (
    SQLiteEvaluationRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.jobs import (
    SQLiteJobRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.models import (
    SQLiteModelRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.runs import (
    SQLiteRunRepository,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def db(tmp_path: pathlib.Path) -> ProjectDb:
    """Return an open ProjectDb backed by a temp-file database."""
    db_path = tmp_path / "test.db"
    database = ProjectDb(db_path)
    database.open()
    yield database
    database.close()


@pytest.fixture
def run_repo(db: ProjectDb) -> SQLiteRunRepository:
    return SQLiteRunRepository(db)


@pytest.fixture
def job_repo(db: ProjectDb) -> SQLiteJobRepository:
    return SQLiteJobRepository(db)


@pytest.fixture
def model_repo(db: ProjectDb) -> SQLiteModelRepository:
    return SQLiteModelRepository(db)


@pytest.fixture
def eval_repo(db: ProjectDb) -> SQLiteEvaluationRepository:
    return SQLiteEvaluationRepository(db)


# ===================================================================
# SQLiteRunRepository tests
# ===================================================================


class TestSQLiteRunRepository:
    """State-transition and query tests for SQLiteRunRepository."""

    def test_create_and_get(self, run_repo: SQLiteRunRepository) -> None:
        record = RunRecord(
            id="run-1",
            dataset_build_id="build-1",
            adapter_id="yolo-v8",
            task_family="detection",
        )
        created = run_repo.create(record)
        assert created.id == "run-1"
        assert created.status == "pending"
        assert created.updated_at is not None  # timestamp was set

        fetched = run_repo.get("run-1")
        assert fetched is not None
        assert fetched.dataset_build_id == "build-1"
        assert fetched.adapter_id == "yolo-v8"

    def test_get_returns_none_for_missing(self, run_repo: SQLiteRunRepository) -> None:
        assert run_repo.get("nonexistent") is None

    def test_state_transition_pending_to_running(
        self, run_repo: SQLiteRunRepository
    ) -> None:
        run_repo.create(RunRecord(
            id="run-2",
            dataset_build_id="build-1",
            adapter_id="yolo-v8",
            task_family="detection",
        ))
        run_repo.mark_running("run-2")
        fetched = run_repo.get("run-2")
        assert fetched is not None
        assert fetched.status == "running"
        assert fetched.started_at is not None

    def test_state_transition_running_to_completed(
        self, run_repo: SQLiteRunRepository
    ) -> None:
        run_repo.create(RunRecord(
            id="run-3",
            dataset_build_id="build-1",
            adapter_id="yolo-v8",
            task_family="detection",
        ))
        run_repo.mark_running("run-3")
        run_repo.mark_completed("run-3")
        fetched = run_repo.get("run-3")
        assert fetched is not None
        assert fetched.status == "completed"
        assert fetched.started_at is not None
        assert fetched.finished_at is not None

    def test_state_transition_running_to_failed(
        self, run_repo: SQLiteRunRepository
    ) -> None:
        run_repo.create(RunRecord(
            id="run-4",
            dataset_build_id="build-1",
            adapter_id="yolo-v8",
            task_family="detection",
        ))
        run_repo.mark_running("run-4")
        error_msg = "OOM during training"
        run_repo.mark_failed("run-4", error_msg)
        fetched = run_repo.get("run-4")
        assert fetched is not None
        assert fetched.status == "failed"
        assert fetched.error_message == error_msg
        assert fetched.finished_at is not None

    def test_list_completed_returns_only_completed(
        self, run_repo: SQLiteRunRepository
    ) -> None:
        run_repo.create(RunRecord(
            id="r1", dataset_build_id="b1", adapter_id="a1", task_family="detection",
        ))
        run_repo.create(RunRecord(
            id="r2", dataset_build_id="b1", adapter_id="a1", task_family="detection",
        ))
        run_repo.create(RunRecord(
            id="r3", dataset_build_id="b1", adapter_id="a1", task_family="detection",
        ))
        run_repo.mark_running("r1")
        run_repo.mark_completed("r1")
        run_repo.mark_running("r2")
        run_repo.mark_failed("r2", "error")
        # r3 stays pending

        completed = run_repo.list_completed()
        assert len(completed) == 1
        assert completed[0].id == "r1"

    def test_create_upserts_on_conflict(self, run_repo: SQLiteRunRepository) -> None:
        """INSERT … ON CONFLICT should update an existing row."""
        run_repo.create(RunRecord(
            id="run-upd",
            dataset_build_id="build-1",
            adapter_id="v1",
            task_family="detection",
            config_json='{"lr": 0.01}',
        ))
        # Re-create with same ID but different fields
        run_repo.create(RunRecord(
            id="run-upd",
            dataset_build_id="build-2",
            adapter_id="v2",
            task_family="detection",
        ))
        fetched = run_repo.get("run-upd")
        assert fetched is not None
        assert fetched.dataset_build_id == "build-2"
        assert fetched.adapter_id == "v2"
        # config_json was overwritten by the upsert
        assert fetched.config_json is None


# ===================================================================
# SQLiteJobRepository tests
# ===================================================================


class TestSQLiteJobRepository:
    """Progress-update and state-transition tests for SQLiteJobRepository."""

    def test_create_and_get(self, job_repo: SQLiteJobRepository) -> None:
        record = JobRecord(
            id="job-1",
            kind="training",
            state="pending",
        )
        created = job_repo.create(record)
        assert created.id == "job-1"
        assert created.created_at is not None

        fetched = job_repo.get("job-1")
        assert fetched is not None
        assert fetched.kind == "training"
        assert fetched.state == "pending"

    def test_get_returns_none_for_missing(self, job_repo: SQLiteJobRepository) -> None:
        assert job_repo.get("nonexistent") is None

    def test_update_progress(self, job_repo: SQLiteJobRepository) -> None:
        job_repo.create(JobRecord(id="job-2", kind="training", state="running"))
        job_repo.update_progress("job-2", 0.5)
        fetched = job_repo.get("job-2")
        assert fetched is not None
        assert fetched.progress == 0.5

    def test_update_progress_multiple_times(
        self, job_repo: SQLiteJobRepository
    ) -> None:
        job_repo.create(JobRecord(id="job-3", kind="training", state="running"))
        for pct in [0.0, 0.25, 0.5, 0.75, 1.0]:
            job_repo.update_progress("job-3", pct)
        fetched = job_repo.get("job-3")
        assert fetched is not None
        assert fetched.progress == 1.0

    def test_mark_completed(self, job_repo: SQLiteJobRepository) -> None:
        job_repo.create(JobRecord(id="job-4", kind="training", state="running"))
        job_repo.mark_completed("job-4")
        fetched = job_repo.get("job-4")
        assert fetched is not None
        assert fetched.state == "completed"
        assert fetched.finished_at is not None

    def test_mark_failed(self, job_repo: SQLiteJobRepository) -> None:
        job_repo.create(JobRecord(id="job-5", kind="training", state="running"))
        error_msg = "timeout"
        job_repo.mark_failed("job-5", error_msg)
        fetched = job_repo.get("job-5")
        assert fetched is not None
        assert fetched.state == "failed"
        assert fetched.error_message == error_msg
        assert fetched.finished_at is not None

    def test_list_active_returns_non_terminal_jobs(
        self, job_repo: SQLiteJobRepository
    ) -> None:
        job_repo.create(JobRecord(id="j1", kind="training", state="pending"))
        job_repo.create(JobRecord(id="j2", kind="training", state="running"))
        job_repo.create(JobRecord(id="j3", kind="training", state="running"))
        job_repo.create(JobRecord(id="j4", kind="training", state="running"))

        job_repo.mark_completed("j3")
        job_repo.mark_failed("j4", "error")

        active = job_repo.list_active()
        active_ids = {j.id for j in active}
        assert active_ids == {"j1", "j2"}

    def test_list_active_empty_when_all_terminal(
        self, job_repo: SQLiteJobRepository
    ) -> None:
        job_repo.create(JobRecord(id="j1", kind="training", state="running"))
        job_repo.mark_completed("j1")
        assert job_repo.list_active() == []


# ===================================================================
# SQLiteModelRepository tests
# ===================================================================


class TestSQLiteModelRepository:
    """Upsert and query tests for SQLiteModelRepository."""

    def test_upsert_and_get_by_run(self, model_repo: SQLiteModelRepository) -> None:
        record = ModelRecord(
            id="model-1",
            run_id="run-1",
            name="best_model",
            format="onnx",
            path="/models/best.onnx",
            task_family="detection",
        )
        created = model_repo.upsert(record)
        assert created.id == "model-1"

        fetched = model_repo.get_by_run("run-1")
        assert fetched is not None
        assert fetched.name == "best_model"
        assert fetched.format == "onnx"

    def test_get_by_run_returns_none_for_missing(
        self, model_repo: SQLiteModelRepository
    ) -> None:
        assert model_repo.get_by_run("nonexistent") is None

    def test_upsert_updates_existing(self, model_repo: SQLiteModelRepository) -> None:
        model_repo.upsert(ModelRecord(
            id="m1",
            run_id="run-1",
            name="epoch1",
            format="onnx",
            path="/models/epoch1.onnx",
            task_family="detection",
        ))
        model_repo.upsert(ModelRecord(
            id="m1",
            run_id="run-1",
            name="epoch2",
            format="onnx",
            path="/models/epoch2.onnx",
            task_family="detection",
        ))
        fetched = model_repo.get_by_run("run-1")
        assert fetched is not None
        assert fetched.name == "epoch2"
        assert fetched.path == "/models/epoch2.onnx"

    def test_list_ready_returns_only_ready_models(
        self, model_repo: SQLiteModelRepository
    ) -> None:
        model_repo.upsert(ModelRecord(
            id="m1", run_id="r1", name="m1", format="onnx",
            path="/m1.onnx", task_family="detection", ready=False,
        ))
        model_repo.upsert(ModelRecord(
            id="m2", run_id="r2", name="m2", format="onnx",
            path="/m2.onnx", task_family="detection", ready=True,
        ))
        model_repo.upsert(ModelRecord(
            id="m3", run_id="r3", name="m3", format="onnx",
            path="/m3.onnx", task_family="detection", ready=True,
        ))

        ready = model_repo.list_ready()
        ready_ids = {m.id for m in ready}
        assert ready_ids == {"m2", "m3"}

    def test_list_ready_empty_when_none_ready(
        self, model_repo: SQLiteModelRepository
    ) -> None:
        model_repo.upsert(ModelRecord(
            id="m1", run_id="r1", name="m1", format="onnx",
            path="/m1.onnx", task_family="detection", ready=False,
        ))
        assert model_repo.list_ready() == []

    def test_get_by_run_returns_most_recent_for_run(
        self, model_repo: SQLiteModelRepository
    ) -> None:
        """Multiple upserts for the same run_id should return the latest."""
        model_repo.upsert(ModelRecord(
            id="m1", run_id="run-x", name="v1", format="onnx",
            path="/v1.onnx", task_family="detection",
        ))
        model_repo.upsert(ModelRecord(
            id="m2", run_id="run-x", name="v2", format="onnx",
            path="/v2.onnx", task_family="detection",
        ))
        fetched = model_repo.get_by_run("run-x")
        assert fetched is not None
        # Both are associated with run-x; get_by_run returns one — the latest
        assert fetched.id == "m2"
        assert fetched.name == "v2"


# ===================================================================
# SQLiteEvaluationRepository tests
# ===================================================================


class TestSQLiteEvaluationRepository:
    """Creation and completion tests for SQLiteEvaluationRepository."""

    def test_create_and_list_by_run(self, eval_repo: SQLiteEvaluationRepository) -> None:
        record = EvaluationRecord(
            id="eval-1",
            run_id="run-1",
            dataset_build_id="build-1",
        )
        created = eval_repo.create(record)
        assert created.id == "eval-1"
        assert created.status == "pending"

        results = eval_repo.list_by_run("run-1")
        assert len(results) == 1
        assert results[0].id == "eval-1"

    def test_list_by_run_returns_empty_for_no_evals(
        self, eval_repo: SQLiteEvaluationRepository
    ) -> None:
        assert eval_repo.list_by_run("nonexistent") == []

    def test_mark_completed_sets_metrics(
        self, eval_repo: SQLiteEvaluationRepository
    ) -> None:
        eval_repo.create(EvaluationRecord(
            id="eval-2",
            run_id="run-1",
            dataset_build_id="build-1",
        ))
        metrics = '{"accuracy": 0.95, "f1": 0.93}'
        eval_repo.mark_completed("eval-2", metrics)

        results = eval_repo.list_by_run("run-1")
        assert len(results) == 1
        assert results[0].status == "completed"
        assert results[0].metrics_json == metrics
        assert results[0].completed_at is not None

    def test_mark_completed_without_metrics(
        self, eval_repo: SQLiteEvaluationRepository
    ) -> None:
        eval_repo.create(EvaluationRecord(
            id="eval-3",
            run_id="run-1",
            dataset_build_id="build-1",
        ))
        eval_repo.mark_completed("eval-3")
        results = eval_repo.list_by_run("run-1")
        assert len(results) == 1
        assert results[0].status == "completed"
        assert results[0].metrics_json is None

    def test_list_by_run_filters_by_run_id(
        self, eval_repo: SQLiteEvaluationRepository
    ) -> None:
        eval_repo.create(EvaluationRecord(
            id="e1", run_id="run-a", dataset_build_id="b1",
        ))
        eval_repo.create(EvaluationRecord(
            id="e2", run_id="run-b", dataset_build_id="b1",
        ))
        eval_repo.create(EvaluationRecord(
            id="e3", run_id="run-a", dataset_build_id="b1",
        ))

        for_run_a = eval_repo.list_by_run("run-a")
        assert len(for_run_a) == 2
        assert {e.id for e in for_run_a} == {"e1", "e3"}

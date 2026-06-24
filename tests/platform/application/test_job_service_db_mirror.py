"""Tests for JobService SQLite DB mirror (E2-3).

Verifies that JobService writes JobRecord to the SQLite database via
ProjectContext, while remaining backward-compatible when no context is
provided.

Coverage:
    1. Job creation mirrors to jobs table.
    2. Progress updates reflected in DB.
    3. Completed job has state=completed in DB.
    4. Failed job has state=failed with error_message in DB.
    5. Backward compat: service without context works as before.
"""

from __future__ import annotations

import pathlib
import sys
import types
from importlib import util as importlib_util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Manual package bootstrap for new domain.records module
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
DOMAIN_DIR = REPO_ROOT / "anylabeling" / "platform" / "domain"


def _bootstrap_domain_records() -> None:
    """Load new domain sub-modules into an already-installed package.

    Strategy: first import the real parent packages so their ``__path__``
    is set correctly by the installed distribution, then load new
    sub-modules that do not exist in the installed package yet.
    """
    import anylabeling  # noqa: F401
    import anylabeling.platform  # noqa: F401

    _ensure_package("anylabeling.platform.domain", DOMAIN_DIR)
    _load_module(
        "anylabeling.platform.domain.records",
        DOMAIN_DIR / "records.py",
    )


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


_bootstrap_domain_records()

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.domain.records import JobRecord
from anylabeling.platform.workers.protocol import JobRequest, JobState


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def jobs_root(tmp_path: Path) -> Path:
    """Temporary directory for job data."""
    return tmp_path / "jobs"


@pytest.fixture
def mock_context() -> MagicMock:
    """A mocked ProjectContext with jobs repository."""
    ctx = MagicMock()
    ctx.jobs = MagicMock()
    return ctx


# ============================================================================
# Tests
# ============================================================================


class TestJobServiceDbMirror:
    """JobService DB mirror: creation, progress, and completion."""

    def test_job_created_mirrors_to_db(
        self,
        jobs_root: Path,
        mock_context: MagicMock,
    ):
        """Job creation writes a JobRecord to the jobs table."""
        service = JobService(jobs_root, context=mock_context)
        request = JobRequest(job_kind="test", params={"msg": "hello"})
        job_id = service.create_job(request, ["python", "-c", "print('hello')"])

        mock_context.jobs.create.assert_called_once()
        args = mock_context.jobs.create.call_args[0][0]
        assert args.id == job_id
        assert args.kind == "test"
        assert args.state == "running"

    def test_job_progress_updates_in_db(
        self,
        jobs_root: Path,
        mock_context: MagicMock,
    ):
        """Progress updates are reflected in the DB."""
        service = JobService(jobs_root, context=mock_context)
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(request, ["python", "-c", "print('hi')"])

        service.update_job_progress(job_id, 0.5)

        mock_context.jobs.update_progress.assert_called_once_with(job_id, 0.5)

    def test_job_completed_marked_in_db(
        self,
        jobs_root: Path,
        mock_context: MagicMock,
    ):
        """A completed job has state=completed in the DB."""
        service = JobService(jobs_root, context=mock_context)
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(request, ["python", "-c", "print('hi')"])

        service.mark_job_completed(job_id)

        mock_context.jobs.mark_completed.assert_called_once_with(job_id)

    def test_job_failed_marked_in_db(
        self,
        jobs_root: Path,
        mock_context: MagicMock,
    ):
        """A failed job has state=failed and error_message in the DB."""
        service = JobService(jobs_root, context=mock_context)
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(request, ["python", "-c", "print('hi')"])

        error_msg = "Something went wrong"
        service.mark_job_failed(job_id, error_msg)

        mock_context.jobs.mark_failed.assert_called_once_with(job_id, error_msg)

    def test_job_without_context_does_not_crash(
        self,
        jobs_root: Path,
    ):
        """Backward compat: JobService without ProjectContext works as before."""
        service = JobService(jobs_root)
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(request, ["python", "-c", "print('hello')"])
        service.wait_job(job_id)
        state = service.get_job_state(job_id)
        assert state == JobState.COMPLETED


__all__: list[str] = []

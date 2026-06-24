"""Tests for ProjectContext integration with ProjectSession."""
from __future__ import annotations

import pytest
from pathlib import Path

from anylabeling.platform.application.project_context import ProjectContext
from anylabeling.platform.application.project_session import ProjectSession
from anylabeling.platform.infrastructure.project_db import ProjectDb


class TestProjectContextOpen:
    def test_open_creates_sqlite_file(self, tmp_path: Path):
        ctx = ProjectContext(tmp_path)
        ctx.open()
        assert (tmp_path / "project.sqlite").exists()
        ctx.close()

    def test_open_sets_all_repositories(self, tmp_path: Path):
        ctx = ProjectContext(tmp_path)
        ctx.open()
        assert ctx.assets is not None
        assert ctx.annotations is not None
        assert ctx.dataset_builds is not None
        assert ctx.runs is not None
        assert ctx.jobs is not None
        assert ctx.models is not None
        assert ctx.evaluations is not None
        assert ctx.workflow_query is not None
        assert ctx.job_service is not None
        assert ctx.workflow_state is not None
        ctx.close()

    def test_double_open_overwrites(self, tmp_path: Path):
        ctx = ProjectContext(tmp_path)
        ctx.open()
        old_db = ctx.db
        ctx.close()
        ctx.open()
        assert ctx.db is not old_db  # new connection
        ctx.close()

    def test_close_nulls_repos(self, tmp_path: Path):
        ctx = ProjectContext(tmp_path)
        ctx.open()
        ctx.close()
        assert ctx.is_open is False

    def test_not_open_raises(self, tmp_path: Path):
        ctx = ProjectContext(tmp_path)
        with pytest.raises(RuntimeError):
            _ = ctx.assets


class TestProjectSessionContext:
    def test_open_project_creates_context(self, tmp_path: Path):
        session = ProjectSession()
        session.open_project(tmp_path)
        ctx = session.context
        assert ctx is not None
        assert ctx.is_open
        assert (tmp_path / "project.sqlite").exists()
        session.close_project()

    def test_context_properties_mirror_session(self, tmp_path: Path):
        session = ProjectSession()
        session.open_project(tmp_path)
        ctx = session.context
        assert session.job_service is ctx.job_service
        assert session.workflow_state is ctx.workflow_state
        session.close_project()

    def test_close_project_closes_context(self, tmp_path: Path):
        session = ProjectSession()
        session.open_project(tmp_path)
        session.close_project()
        assert session.context is None
        assert session.job_service is None

    def test_reopen_project_new_context(self, tmp_path: Path):
        session = ProjectSession()
        session.open_project(tmp_path)
        ctx1 = session.context
        session.close_project()
        session.open_project(tmp_path)
        ctx2 = session.context
        assert ctx1 is not ctx2
        session.close_project()

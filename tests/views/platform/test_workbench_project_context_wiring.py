"""Tests for WorkbenchWindow ProjectContext wiring (F1-2)."""
from __future__ import annotations

import pytest
from pathlib import Path

from anylabeling.platform.application.project_session import ProjectSession


class TestWorkbenchProjectContextWiring:
    """Verify WorkbenchWindow receives ProjectContext after set_project."""

    def test_session_open_project_returns_context(self, tmp_path: Path):
        session = ProjectSession()
        session.open_project(str(tmp_path))
        ctx = session.context
        assert ctx is not None
        assert ctx.is_open
        assert (tmp_path / "project.sqlite").exists()
        session.close_project()

    def test_context_has_job_service(self, tmp_path: Path):
        session = ProjectSession()
        session.open_project(str(tmp_path))
        ctx = session.context
        assert ctx.job_service is not None
        assert session.job_service is ctx.job_service
        session.close_project()

    def test_context_has_workflow_state(self, tmp_path: Path):
        session = ProjectSession()
        session.open_project(str(tmp_path))
        ctx = session.context
        assert ctx.workflow_state is not None
        session.close_project()

    def test_context_has_all_repos(self, tmp_path: Path):
        session = ProjectSession()
        session.open_project(str(tmp_path))
        ctx = session.context
        assert ctx.assets is not None
        assert ctx.dataset_builds is not None
        assert ctx.runs is not None
        assert ctx.models is not None
        session.close_project()

    def test_session_close_nulls_context(self, tmp_path: Path):
        session = ProjectSession()
        session.open_project(str(tmp_path))
        session.close_project()
        assert session.context is None

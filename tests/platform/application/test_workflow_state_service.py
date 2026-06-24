"""Tests for WorkflowState with DB-backed queries (F1-1)."""
from __future__ import annotations

import pytest
from pathlib import Path

from anylabeling.platform.application.workflow_state import WorkflowState
from anylabeling.platform.application.project_context import ProjectContext


class TestWorkflowStateFilesystemFallback:
    def test_refresh_returns_5_domains(self, tmp_path: Path):
        ws = WorkflowState(str(tmp_path))
        assert len(ws.refresh()) == 5

    def test_project_domain_is_ready(self, tmp_path: Path):
        ws = WorkflowState(str(tmp_path))
        assert ws.get_domain_state(0).state == "ready"

    def test_data_prep_not_started_when_empty(self, tmp_path: Path):
        ws = WorkflowState(str(tmp_path))
        assert ws.get_domain_state(1).state == "not_started"


class TestWorkflowStateDbMode:
    @pytest.fixture
    def ctx(self, tmp_path: Path):
        c = ProjectContext(str(tmp_path))
        c.open()
        yield c
        c.close()

    def test_refresh_5_domains(self, ctx):
        ws = WorkflowState(str(ctx.project_root), workflow_query=ctx.workflow_query)
        assert len(ws.refresh()) == 5

    def test_empty_data_prep(self, ctx):
        ws = WorkflowState(str(ctx.project_root), workflow_query=ctx.workflow_query)
        assert ws.get_domain_state(1).state == "not_started"

    def test_empty_train_blocked(self, ctx):
        ws = WorkflowState(str(ctx.project_root), workflow_query=ctx.workflow_query)
        assert ws.get_domain_state(2).state in ("not_started", "needs_attention")

    def test_empty_eval(self, ctx):
        ws = WorkflowState(str(ctx.project_root), workflow_query=ctx.workflow_query)
        assert ws.get_domain_state(3).state == "not_started"

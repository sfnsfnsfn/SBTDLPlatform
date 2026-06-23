"""Tests for WorkflowState — per-domain navigation state computation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anylabeling.platform.application.workflow_state import (
    DomainState,
    WorkflowState,
)


# ============================================================================
# Empty / missing project
# ============================================================================


class TestWorkflowStateEmptyProject:
    @pytest.fixture
    def empty_project(self, tmp_path):
        return tmp_path / "empty_project"

    @pytest.fixture
    def missing_project(self):
        return Path("/nonexistent/path/12345")

    def test_all_domains_not_started_on_empty_dir(self, empty_project):
        empty_project.mkdir()
        ws = WorkflowState(empty_project)
        states = ws.refresh()
        assert states[0].state == "ready"  # PROJECT always ready
        assert states[1].state == "not_started"  # DATA_PREP — no assets
        assert states[2].state == "not_started"
        assert states[3].state == "not_started"
        assert states[4].state == "not_started"

    def test_data_prep_not_started_on_missing_dir(self, missing_project):
        ws = WorkflowState(missing_project)
        states = ws.refresh()
        assert states[1].state == "not_started"
        assert "No assets directory" in states[1].reason

    def test_return_type_is_domain_state(self, tmp_path):
        ws = WorkflowState(tmp_path)
        states = ws.refresh()
        for domain_val, ds in states.items():
            assert isinstance(ds, DomainState)
            assert ds.domain == domain_val
            assert isinstance(ds.state, str)
            assert isinstance(ds.reason, str)
            assert isinstance(ds.prerequisites, list)

    def test_get_single_domain_state(self, tmp_path):
        ws = WorkflowState(tmp_path)
        ds = ws.get_domain_state(0)
        assert ds.domain == 0
        assert ds.state == "ready"

    def test_unknown_domain_returns_not_started(self, tmp_path):
        ws = WorkflowState(tmp_path)
        ds = ws.get_domain_state(99)
        assert ds.state == "not_started"
        assert "Unknown domain" in ds.reason


# ============================================================================
# Project with assets
# ============================================================================


class TestWorkflowStateWithAssets:
    @pytest.fixture
    def project_with_assets(self, tmp_path):
        proj = tmp_path / "proj"
        assets_dir = proj / "assets"
        assets_dir.mkdir(parents=True)
        (assets_dir / "image1.jpg").write_text("fake")
        (assets_dir / "image2.png").write_text("fake")
        return proj

    def test_data_prep_ready_with_assets(self, project_with_assets):
        ws = WorkflowState(project_with_assets)
        states = ws.refresh()
        assert states[1].state == "ready"

    def test_data_prep_in_progress_with_labels(self, project_with_assets):
        (project_with_assets / "labels.json").write_text("[]")
        ws = WorkflowState(project_with_assets)
        states = ws.refresh()
        assert states[1].state == "in_progress"

    def test_data_prep_in_progress_with_annotations(self, project_with_assets):
        (project_with_assets / "labels.json").write_text("[]")
        ann_dir = project_with_assets / "annotations"
        ann_dir.mkdir()
        (ann_dir / "image1.json").write_text("{}")
        ws = WorkflowState(project_with_assets)
        states = ws.refresh()
        assert states[1].state == "in_progress"


# ============================================================================
# Project with builds and runs
# ============================================================================


class TestWorkflowStateWithBuilds:
    @pytest.fixture
    def project_with_build(self, tmp_path):
        proj = tmp_path / "proj"
        for d in ("assets", "annotations", "dataset_builds", "runs"):
            (proj / d).mkdir(parents=True)
        (proj / "assets" / "img.jpg").write_text("fake")
        (proj / "labels.json").write_text("[]")
        builds_dir = proj / "dataset_builds" / "build-001"
        builds_dir.mkdir()
        (builds_dir / "build.json").write_text("{}")
        return proj

    def test_train_ready_with_build(self, project_with_build):
        ws = WorkflowState(project_with_build)
        states = ws.refresh()
        assert states[2].state == "ready"

    def test_train_completed_with_run(self, project_with_build):
        run_dir = project_with_build / "runs" / "run-001"
        run_dir.mkdir()
        (run_dir / "run.json").write_text(
            json.dumps({"id": "run-001", "status": "completed"})
        )
        ws = WorkflowState(project_with_build)
        states = ws.refresh()
        assert states[2].state == "completed"

    def test_train_needs_attention_with_failed_run(self, project_with_build):
        run_dir = project_with_build / "runs" / "run-001"
        run_dir.mkdir()
        (run_dir / "run.json").write_text(
            json.dumps({"id": "run-001", "status": "failed"})
        )
        ws = WorkflowState(project_with_build)
        states = ws.refresh()
        assert states[2].state == "needs_attention"

    def test_eval_ready_with_completed_run(self, project_with_build):
        run_dir = project_with_build / "runs" / "run-001"
        run_dir.mkdir()
        (run_dir / "run.json").write_text(
            json.dumps({"id": "run-001", "status": "completed"})
        )
        ws = WorkflowState(project_with_build)
        states = ws.refresh()
        assert states[3].state == "ready"

    def test_eval_completed_with_evaluations(self, project_with_build):
        run_dir = project_with_build / "runs" / "run-001"
        run_dir.mkdir()
        (run_dir / "run.json").write_text(
            json.dumps({"id": "run-001", "status": "completed"})
        )
        evals_dir = project_with_build / "evaluations"
        evals_dir.mkdir()
        (evals_dir / "eval-001.json").write_text("{}")
        ws = WorkflowState(project_with_build)
        states = ws.refresh()
        assert states[3].state == "completed"


# ============================================================================
# Export domain
# ============================================================================


class TestWorkflowStateExport:
    @pytest.fixture
    def project_with_model(self, tmp_path):
        proj = tmp_path / "proj"
        for d in ("assets", "models"):
            (proj / d).mkdir(parents=True)
        (proj / "assets" / "img.jpg").write_text("fake")
        model_dir = proj / "models" / "model-001"
        model_dir.mkdir()
        (model_dir / "_READY").write_text("")
        return proj

    def test_export_ready_with_model(self, project_with_model):
        ws = WorkflowState(project_with_model)
        states = ws.refresh()
        assert states[4].state == "ready"

    def test_export_not_started_without_models_dir(self, tmp_path):
        ws = WorkflowState(tmp_path)
        states = ws.refresh()
        assert states[4].state == "not_started"


# ============================================================================
# Edge cases
# ============================================================================


class TestWorkflowStateEdgeCases:
    def test_domain_state_is_immutable(self):
        ds = DomainState(domain=0, state="ready", reason="t", prerequisites=[])
        with pytest.raises(Exception):
            ds.state = "changed"  # type: ignore[misc]

    def test_corrupted_run_json_skipped(self, tmp_path):
        proj = tmp_path / "proj"
        for d in ("assets", "dataset_builds", "runs"):
            (proj / d).mkdir(parents=True)
        (proj / "assets" / "img.jpg").write_text("fake")
        builds_dir = proj / "dataset_builds" / "build-001"
        builds_dir.mkdir()
        (builds_dir / "build.json").write_text("{}")
        run_dir = proj / "runs" / "run-bad"
        run_dir.mkdir()
        (run_dir / "run.json").write_text("not valid json{{{")
        ws = WorkflowState(proj)
        states = ws.refresh()
        assert states[2].state == "ready"  # falls back to READY

    def test_non_image_files_ignored_in_assets(self, tmp_path):
        proj = tmp_path / "proj"
        assets_dir = proj / "assets"
        assets_dir.mkdir(parents=True)
        (assets_dir / "notes.txt").write_text("hello")
        ws = WorkflowState(proj)
        states = ws.refresh()
        assert states[1].state == "not_started"  # txt files not counted as images

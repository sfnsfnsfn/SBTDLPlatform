"""Tests for TrainingService.validate_training_readiness() + find_orphaned_runs().

Phase 4a — Task 4a.2 / 4a.4.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anylabeling.platform.application.training_service import TrainingService
from anylabeling.platform.domain.training_readiness import (
    CheckResult,
    TrainReadinessReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service_with_empty_project(tmp_path: Path) -> TrainingService:
    """TrainingService pointing at a tmp_path with no assets."""
    job_service = MagicMock()
    return TrainingService(job_service, project_root=tmp_path)


@pytest.fixture
def service_with_assets(tmp_path: Path) -> TrainingService:
    """Project with 10 images (8 annotated)."""
    job_service = MagicMock()

    images_dir = tmp_path / "assets" / "images"
    images_dir.mkdir(parents=True)
    for i in range(10):
        (images_dir / f"img_{i:04d}.jpg").write_text("")

    annotations_dir = tmp_path / "annotations" / "documents"
    annotations_dir.mkdir(parents=True)
    for i in range(8):
        (annotations_dir / f"img_{i:04d}.json").write_text("{}")

    return TrainingService(job_service, project_root=tmp_path)


@pytest.fixture
def service_with_runs(tmp_path: Path) -> TrainingService:
    """Project with runs/ directory containing an orphaned run."""
    job_service = MagicMock()

    runs_dir = tmp_path / "runs" / "run_abc123"
    runs_dir.mkdir(parents=True)
    run_data = {
        "id": "run_abc123",
        "adapter_id": "ultralytics_yolo_detect",
        "task_family": "detection_hbb",
        "dataset_build_id": "build_1",
        "base_model": "yolov8n.pt",
        "base_model_sha256": "",
        "config": {},
        "environment": {},
        "status": "running",
        "metrics": [],
        "best_metric": None,
        "output_dir": str(runs_dir),
    }
    (runs_dir / "run.json").write_text(
        json.dumps(run_data), encoding="utf-8"
    )

    return TrainingService(job_service, project_root=tmp_path)


# ---------------------------------------------------------------------------
# validate_training_readiness tests (8 tests)
# ---------------------------------------------------------------------------


class TestTrainingReadiness:
    """Test validate_training_readiness() across various project states."""

    def test_empty_project_not_ready(self, service_with_empty_project):
        """Empty project (0 assets) → ready=False."""
        report = service_with_empty_project.validate_training_readiness()
        assert isinstance(report, TrainReadinessReport)
        assert report.ready is False
        assert any(
            c.name == "assets_exist" and not c.passed
            for c in report.checks
        )

    def test_assets_exist_check_passes(self, service_with_assets):
        """Project with 10 images → assets_exist check passes."""
        report = service_with_assets.validate_training_readiness()
        assets_check = next(
            c for c in report.checks if c.name == "assets_exist"
        )
        assert assets_check.passed is True

    def test_annotation_coverage_above_50_percent(
        self, service_with_assets,
    ):
        """8/10 annotated → coverage >= 50% → check passes."""
        report = service_with_assets.validate_training_readiness()
        coverage_check = next(
            c for c in report.checks
            if c.name == "annotations_coverage"
        )
        assert coverage_check.passed is True
        assert not coverage_check.blocking

    def test_annotation_coverage_below_50_percent(self, tmp_path):
        """2/10 annotated → coverage < 50% → check fails (non-blocking)."""
        job_service = MagicMock()

        images_dir = tmp_path / "assets" / "images"
        images_dir.mkdir(parents=True)
        for i in range(10):
            (images_dir / f"img_{i:04d}.jpg").write_text("")

        annotations_dir = tmp_path / "annotations" / "documents"
        annotations_dir.mkdir(parents=True)
        for i in range(2):
            (annotations_dir / f"img_{i:04d}.json").write_text("{}")

        service = TrainingService(job_service, project_root=tmp_path)
        report = service.validate_training_readiness()
        coverage_check = next(
            c for c in report.checks
            if c.name == "annotations_coverage"
        )
        assert coverage_check.passed is False
        assert not coverage_check.blocking
        assert len(report.warnings) >= 1

    def test_dataset_build_missing(self, service_with_assets):
        """No dataset_build provided → dataset_build check fails."""
        report = service_with_assets.validate_training_readiness(
            dataset_build=None,
        )
        build_check = next(
            c for c in report.checks if c.name == "dataset_build"
        )
        assert build_check.passed is False
        assert build_check.blocking is True

    def test_dataset_build_provided(self, service_with_assets):
        """DatasetBuild provided → dataset_build check passes."""
        mock_build = MagicMock()
        report = service_with_assets.validate_training_readiness(
            dataset_build=mock_build,
        )
        build_check = next(
            c for c in report.checks if c.name == "dataset_build"
        )
        assert build_check.passed is True

    def test_model_compatible_always_passes(self, service_with_empty_project):
        """Model compatibility check always passes (validated by adapter)."""
        report = service_with_empty_project.validate_training_readiness()
        compat_check = next(
            c for c in report.checks if c.name == "model_compatible"
        )
        assert compat_check.passed is True
        assert not compat_check.blocking

    def test_disk_space_check_runs(self, service_with_empty_project):
        """Disk space check runs and returns a result."""
        report = service_with_empty_project.validate_training_readiness()
        disk_check = next(
            c for c in report.checks if c.name == "disk_space"
        )
        assert disk_check is not None
        assert not disk_check.blocking
        assert len(disk_check.detail) > 0


# ---------------------------------------------------------------------------
# find_orphaned_runs tests (3 tests)
# ---------------------------------------------------------------------------


class TestOrphanedRuns:
    """Test find_orphaned_runs() for run recovery."""

    def test_finds_orphaned_running_run(self, service_with_runs):
        """Run with status='running' → found as orphaned."""
        orphaned = service_with_runs.find_orphaned_runs()
        assert len(orphaned) == 1
        assert orphaned[0].id == "run_abc123"
        assert orphaned[0].status == "running"

    def test_no_orphaned_when_clean(self, service_with_assets):
        """No runs/ directory → no orphaned."""
        orphaned = service_with_assets.find_orphaned_runs()
        assert len(orphaned) == 0

    def test_skips_non_running_runs(self, tmp_path):
        """Run with status='completed' → not orphaned."""
        job_service = MagicMock()

        runs_dir = tmp_path / "runs" / "run_completed"
        runs_dir.mkdir(parents=True)
        run_data = {
            "id": "run_completed",
            "adapter_id": "ultralytics_yolo_detect",
            "task_family": "detection_hbb",
            "dataset_build_id": "",
            "base_model": "",
            "base_model_sha256": "",
            "config": {},
            "environment": {},
            "status": "completed",
            "metrics": [],
            "best_metric": None,
            "output_dir": str(runs_dir),
        }
        (runs_dir / "run.json").write_text(
            json.dumps(run_data), encoding="utf-8"
        )

        service = TrainingService(job_service, project_root=tmp_path)
        orphaned = service.find_orphaned_runs()
        assert len(orphaned) == 0


# ---------------------------------------------------------------------------
# TrainReadinessReport / CheckResult domain contracts
# ---------------------------------------------------------------------------


class TestTrainReadinessReport:
    """Test the frozen dataclass contracts."""

    def test_check_result_is_immutable(self):
        """CheckResult is frozen — cannot mutate after creation."""
        cr = CheckResult(
            name="test", passed=True, detail="ok", blocking=True,
        )
        with pytest.raises(Exception):
            cr.name = "other"  # type: ignore[misc]

    def test_readiness_report_is_immutable(self):
        """TrainReadinessReport is frozen."""
        report = TrainReadinessReport(ready=True, checks=(), warnings=())
        with pytest.raises(Exception):
            report.ready = False  # type: ignore[misc]

    def test_report_defaults(self):
        """Default values are sensible."""
        report = TrainReadinessReport(ready=True)
        assert report.checks == ()
        assert report.warnings == ()

    def test_readiness_report_aggregation(self):
        """Ready is True only when all blocking checks pass."""
        checks = (
            CheckResult(name="a", passed=True, blocking=True),
            CheckResult(name="b", passed=False, blocking=False),
        )
        report = TrainReadinessReport(ready=True, checks=checks)
        assert report.ready is True
        assert len(report.checks) == 2

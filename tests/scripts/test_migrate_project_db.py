"""Tests for scripts/migrate_project_db.py -- CLI wrapper for ProjectDbBootstrap.

Covers:
  1. --dry-run does not create or modify the SQLite index.
  2. --rebuild-index creates/updates the index with correct counts.
  3. --check reports consistency information.
  4. Missing project path reports an error (exit code 1).
  5. --checkpoint runs without error.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import PIL
import PIL.Image
import pytest

from anylabeling.platform.infrastructure.project_db import ProjectDb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WIDTH = 640
_HEIGHT = 480
_SCRIPT = _REPO_ROOT / "scripts" / "migrate_project_db.py"


def _make_image(path: Path) -> None:
    img = PIL.Image.new("RGB", (_WIDTH, _HEIGHT), color="red")
    img.save(str(path))


def _create_test_project(tmp_path: Path) -> Path:
    """Create a synthetic legacy project directory and return its root."""
    root = tmp_path / "test_project"
    root.mkdir()

    # project.json
    (root / "project.json").write_text(
        json.dumps({"name": "test_project", "labels": ["cat", "dog"]}),
        encoding="utf-8",
    )

    # assets/
    assets_dir = root / "assets"
    assets_dir.mkdir()
    _make_image(assets_dir / "img001.jpg")
    _make_image(assets_dir / "img002.png")

    # assets/group_a/  (nested group)
    group_a = assets_dir / "group_a"
    group_a.mkdir()
    _make_image(group_a / "img003.jpg")

    # annotations/
    ann_dir = root / "annotations"
    ann_dir.mkdir()
    (ann_dir / "img001.xml").write_text(
        '<?xml version="1.0" ?>'
        "<annotation><object><name>cat</name></object></annotation>",
        encoding="utf-8",
    )

    # dataset_builds/
    builds_dir = root / "dataset_builds"
    builds_dir.mkdir()
    b1 = builds_dir / "build_001"
    b1.mkdir()
    (b1 / "build.json").write_text(
        json.dumps({
            "status": "completed",
            "task_family": "detection_hbb",
            "output_path": "outputs/build_001",
        }),
        encoding="utf-8",
    )

    # runs/
    runs_dir = root / "runs"
    runs_dir.mkdir()
    r1 = runs_dir / "run_001"
    r1.mkdir()
    (r1 / "metrics.json").write_text(
        json.dumps({"mAP": 0.85, "loss": 0.12}),
        encoding="utf-8",
    )

    # models/
    models_dir = root / "models"
    models_dir.mkdir()
    m1 = models_dir / "model_001"
    m1.mkdir()
    (m1 / "best.pt").write_bytes(b"dummy model data")
    (m1 / "metadata.json").write_text(
        json.dumps({
            "name": "yolo_v8",
            "format": "onnx",
            "task_family": "detection_hbb",
            "run_id": "run_001",
        }),
        encoding="utf-8",
    )

    return root


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Invoke the migrate_project_db.py CLI script in a subprocess."""
    cmd = [sys.executable, str(_SCRIPT), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or str(_REPO_ROOT),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMigrateProjectDb:
    """Test suite for the migrate_project_db CLI."""

    def test_dry_run_does_not_create_db(self, tmp_path: Path) -> None:
        project = _create_test_project(tmp_path)
        db_path = project / "project.sqlite"

        assert not db_path.exists(), "Sanity: DB should not exist yet"

        result = _run_cli(str(project), "--dry-run")

        assert result.returncode == 0, (
            f"Expected exit code 0, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # DB file must not be created
        assert not db_path.exists(), (
            "--dry-run should not create project.sqlite"
        )
        # Output should contain counts
        assert "DRY RUN" in result.stdout
        assert "Assets:" in result.stdout or "Assets" in result.stdout

    def test_rebuild_index_creates_db_with_correct_counts(
        self, tmp_path: Path,
    ) -> None:
        project = _create_test_project(tmp_path)
        db_path = project / "project.sqlite"

        result = _run_cli(str(project), "--rebuild-index")

        assert result.returncode == 0, (
            f"Expected exit code 0, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert db_path.exists(), "--rebuild-index should create project.sqlite"

        # Verify DB contents via ProjectDb
        db = ProjectDb(db_path)
        db.open()
        try:
            asset_count = db.query_one(
                "SELECT COUNT(*) AS c FROM assets",
            )["c"]
            ann_count = db.query_one(
                "SELECT COUNT(*) AS c FROM annotation_summaries",
            )["c"]
            build_count = db.query_one(
                "SELECT COUNT(*) AS c FROM dataset_builds",
            )["c"]
            run_count = db.query_one(
                "SELECT COUNT(*) AS c FROM runs",
            )["c"]
            model_count = db.query_one(
                "SELECT COUNT(*) AS c FROM models",
            )["c"]
        finally:
            db.close()

        assert asset_count == 3, f"Expected 3 assets, got {asset_count}"
        assert ann_count == 1, f"Expected 1 annotation, got {ann_count}"
        assert build_count == 1, f"Expected 1 build, got {build_count}"
        assert run_count == 1, f"Expected 1 run, got {run_count}"
        assert model_count == 1, f"Expected 1 model, got {model_count}"

        # Output should mention rebuild
        assert "Rebuilt index" in result.stdout

    def test_check_reports_consistency(self, tmp_path: Path) -> None:
        project = _create_test_project(tmp_path)

        # Build index first
        build_result = _run_cli(str(project), "--rebuild-index")
        assert build_result.returncode == 0

        # Now check consistency
        result = _run_cli(str(project), "--check")

        assert result.returncode == 0, (
            f"Expected exit code 0, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "Consistency check" in result.stdout
        # Both sides should match
        assert "consistent" in result.stdout.lower()

    def test_check_reports_mismatch(self, tmp_path: Path) -> None:
        project = _create_test_project(tmp_path)

        # Build index first
        build_result = _run_cli(str(project), "--rebuild-index")
        assert build_result.returncode == 0

        # Add a file after building index — should become a mismatch
        extra = project / "assets" / "extra.jpg"
        _make_image(extra)

        result = _run_cli(str(project), "--check")

        assert result.returncode == 0
        assert "In DB but not on disk" not in result.stdout
        assert "On disk but not in DB" in result.stdout

    def test_missing_project_path_shows_error(self) -> None:
        missing = str(_REPO_ROOT / "nonexistent_project_xyz123")
        result = _run_cli(missing, "--dry-run")

        assert result.returncode == 1, (
            f"Expected exit code 1 for missing path, got {result.returncode}"
        )
        assert "not a valid directory" in result.stderr.lower()

    def test_checkpoint_runs_without_error(self, tmp_path: Path) -> None:
        project = _create_test_project(tmp_path)

        # Build index first
        build_result = _run_cli(str(project), "--rebuild-index")
        assert build_result.returncode == 0

        # Run checkpoint
        result = _run_cli(str(project), "--checkpoint")

        assert result.returncode == 0, (
            f"Expected exit code 0, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "WAL checkpoint" in result.stdout

    def test_checkpoint_fails_without_db(self, tmp_path: Path) -> None:
        project = _create_test_project(tmp_path)
        db_path = project / "project.sqlite"

        assert not db_path.exists(), "Sanity: DB should not exist"

        result = _run_cli(str(project), "--checkpoint")

        assert result.returncode == 1, (
            f"Expected exit code 1, got {result.returncode}"
        )
        assert "No SQLite index found" in result.stderr

    def test_verbose_flag_enables_logging(self, tmp_path: Path) -> None:
        project = _create_test_project(tmp_path)

        result = _run_cli(str(project), "--dry-run", "--verbose")

        assert result.returncode == 0, (
            f"Expected exit code 0, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_no_command_shows_help(self, tmp_path: Path) -> None:
        result = _run_cli(str(tmp_path))

        assert result.returncode == 1, (
            f"Expected exit code 1 for no command, got {result.returncode}"
        )

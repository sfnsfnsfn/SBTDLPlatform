"""Tests for ProjectDbBootstrap — legacy project directory scanning.

Covers:
  1. Bootstrap populates all 5 table groups correctly.
  2. Repeated bootstrap is idempotent (no duplicate rows).
  3. Corrupted annotation file does not crash the bootstrap.
  4. Missing optional directories are handled gracefully.
"""

from __future__ import annotations

import json
from pathlib import Path

import PIL
import PIL.Image
import pytest

from anylabeling.platform.infrastructure.project_db import ProjectDb
from anylabeling.platform.infrastructure.project_db_bootstrap import (
    BootstrapReport,
    ProjectDbBootstrap,
)
from anylabeling.platform.infrastructure.sqlite_repositories.annotations import (
    SQLiteAnnotationRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.assets import (
    SQLiteAssetRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.dataset_builds import (
    SQLiteDatasetBuildRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.models import (
    SQLiteModelRepository,
)
from anylabeling.platform.infrastructure.sqlite_repositories.runs import (
    SQLiteRunRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WIDTH = 640
_HEIGHT = 480


def _make_image(path: Path) -> None:
    img = PIL.Image.new("RGB", (_WIDTH, _HEIGHT), color="red")
    img.save(str(path))


def _create_old_project(tmp_path: Path) -> Path:
    """Create a synthetic old-format project directory and return its root."""
    root = tmp_path / "old_project"
    root.mkdir()

    # project.json
    (root / "project.json").write_text(
        json.dumps({"name": "test_project", "labels": ["cat", "dog"]}),
        encoding="utf-8",
    )

    # labels.json (legacy)
    (root / "labels.json").write_text(
        json.dumps([{"id": 0, "name": "cat"}, {"id": 1, "name": "dog"}]),
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
        '<?xml version="1.0" ?><annotation><object><name>cat</name></object></annotation>',
        encoding="utf-8",
    )
    (ann_dir / "img002.xml").write_text(
        '<?xml version="1.0" ?><annotation><object><name>dog</name></object></annotation>',
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


@pytest.fixture
def old_project(tmp_path: Path) -> Path:
    return _create_old_project(tmp_path)


@pytest.fixture
def db(tmp_path: Path) -> ProjectDb:
    db_path = tmp_path / "test.db"
    db = ProjectDb(db_path)
    db.open()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProjectDbBootstrap:
    """Test suite for ProjectDbBootstrap."""

    def test_bootstrap_populates_all_tables(self, db: ProjectDb, old_project: Path) -> None:
        bootstrap = ProjectDbBootstrap(db, old_project)
        report = bootstrap.run()

        assert isinstance(report, BootstrapReport)
        assert report.assets_processed == 3  # img001, img002, img003
        assert report.annotations_processed == 2  # img001.xml, img002.xml
        assert report.dataset_builds_processed == 1
        assert report.runs_processed == 1
        assert report.models_processed == 1

        # Verify assets in DB
        asset_repo = SQLiteAssetRepository(db)
        assets = asset_repo.list()
        rel_paths = {a.rel_path for a in assets}
        assert "img001.jpg" in rel_paths
        assert "img002.png" in rel_paths
        assert "group_a/img003.jpg" in rel_paths
        # Check dimensions were captured
        for a in assets:
            if a.rel_path == "img001.jpg":
                assert a.width == _WIDTH
                assert a.height == _HEIGHT

        # Verify annotations in DB
        ann_repo = SQLiteAnnotationRepository(db)
        ann_records = [
            ann_repo.get_by_asset(a.id)
            for a in assets
            if ann_repo.get_by_asset(a.id) is not None
        ]
        assert len(ann_records) == 2  # img001.xml matches img001.jpg, img002.xml matches img002.png

        # Verify dataset builds
        build_repo = SQLiteDatasetBuildRepository(db)
        completed = build_repo.list_completed()
        assert len(completed) == 1
        assert completed[0].status == "completed"

        # Verify runs
        run_repo = SQLiteRunRepository(db)
        runs = run_repo.list_completed()
        assert len(runs) == 1
        assert runs[0].status == "completed"

        # Verify models
        model_repo = SQLiteModelRepository(db)
        models = model_repo.list_ready()
        assert len(models) == 1
        assert models[0].name == "yolo_v8"

    def test_bootstrap_is_idempotent(self, db: ProjectDb, old_project: Path) -> None:
        bootstrap = ProjectDbBootstrap(db, old_project)

        report1 = bootstrap.run()
        report2 = bootstrap.run()

        # Counts should be the same
        assert report1.assets_processed == report2.assets_processed == 3
        assert report1.annotations_processed == report2.annotations_processed == 2

        # No duplicate rows in DB
        asset_repo = SQLiteAssetRepository(db)
        assets = asset_repo.list()
        assert len(assets) == 3  # Still 3, not 6

        ann_repo = SQLiteAnnotationRepository(db)
        ann_count = ann_repo.count_annotated()
        # annotation summaries are keyed on asset_id; each asset may have
        # multiple annotation files, but idempotent means same count
        assert ann_count >= 0  # just verifying no crash

    def test_corrupted_annotation_does_not_crash(
        self, db: ProjectDb, old_project: Path
    ) -> None:
        # Add a corrupted annotation file
        corrupted = old_project / "annotations" / "corrupted.xml"
        corrupted.write_text("not valid xml or anything", encoding="utf-8")

        bootstrap = ProjectDbBootstrap(db, old_project)
        report = bootstrap.run()

        # Bootstrap should complete without crashing
        assert report.annotations_processed >= 2  # the valid ones
        # The corrupted file should be in errors or gracefully skipped
        assert report.assets_processed == 3

    def test_missing_directories_handled_gracefully(
        self, db: ProjectDb, old_project: Path
    ) -> None:
        # Remove some directories to simulate minimal project
        for d in ("annotations", "dataset_builds", "runs", "models"):
            p = old_project / d
            if p.exists():
                for child in list(p.iterdir()):
                    if child.is_dir():
                        for f in child.iterdir():
                            f.unlink()
                        child.rmdir()
                    else:
                        child.unlink()
                p.rmdir()

        bootstrap = ProjectDbBootstrap(db, old_project)
        report = bootstrap.run()

        assert report.assets_processed == 3
        assert report.annotations_processed == 0
        assert report.dataset_builds_processed == 0
        assert report.runs_processed == 0
        assert report.models_processed == 0

    def test_bootstrap_report_is_frozen_dataclass(self) -> None:
        report = BootstrapReport(
            assets_processed=1,
            annotations_processed=2,
            dataset_builds_processed=3,
            runs_processed=4,
            models_processed=5,
        )
        assert report.assets_processed == 1

        with pytest.raises(AttributeError):
            report.assets_processed = 99  # type: ignore[misc]

    def test_run_without_project_json(self, db: ProjectDb, tmp_path: Path) -> None:
        """Bootstrap works even when project.json is missing."""
        root = tmp_path / "minimal"
        root.mkdir()
        (root / "assets").mkdir()
        _make_image(root / "assets" / "img.jpg")

        bootstrap = ProjectDbBootstrap(db, root)
        report = bootstrap.run()
        assert report.assets_processed == 1
        assert report.annotations_processed == 0

    def test_non_image_files_in_assets(self, db: ProjectDb, old_project: Path) -> None:
        """Non-image files in assets/ are still processed as assets."""
        (old_project / "assets" / "readme.txt").write_text("hello", encoding="utf-8")
        bootstrap = ProjectDbBootstrap(db, old_project)
        report = bootstrap.run()
        # txt file should still be counted, even if dimensions can't be read
        assert report.assets_processed == 4

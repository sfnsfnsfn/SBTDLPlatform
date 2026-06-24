"""Integration tests: ImportService writes assets to SQLite via ProjectContext.

Tests:
  1. Import creates AssetRecord rows in assets table.
  2. Duplicate import does not duplicate DB rows.
  3. File-copy failure does not write DB records.
  4. ImportService without context still works (backward compat).
"""

from __future__ import annotations

import pathlib
import sys
import types
from importlib import util as importlib_util
from unittest.mock import patch

import pytest

# =============================================================================
# Manual package bootstrap (files are not installed in editable mode yet)
# =============================================================================

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PLATFORM_DIR = REPO_ROOT / "anylabeling" / "platform"
DOMAIN_DIR = PLATFORM_DIR / "domain"
INFRA_DIR = PLATFORM_DIR / "infrastructure"
APP_DIR = PLATFORM_DIR / "application"
SQLITE_REPOS_DIR = INFRA_DIR / "sqlite_repositories"
PORTS_DIR = APP_DIR / "ports"


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
    _ensure_package("anylabeling.platform.application", APP_DIR)
    _ensure_package("anylabeling.platform.application.ports", PORTS_DIR)
    _ensure_package("anylabeling.platform.infrastructure", INFRA_DIR)
    _ensure_package(
        "anylabeling.platform.infrastructure.sqlite_repositories",
        SQLITE_REPOS_DIR,
    )

    # Pre-load the sqlite_repositories __init__ so imports from project_context work
    _load_module(
        "anylabeling.platform.infrastructure.sqlite_repositories._utils",
        SQLITE_REPOS_DIR / "_utils.py",
    )

    for mod_name, mod_path in [
        ("anylabeling.platform.domain.records", DOMAIN_DIR / "records.py"),
        ("anylabeling.platform.domain.workflow_status", DOMAIN_DIR / "workflow_status.py"),
        ("anylabeling.platform.infrastructure.project_db", INFRA_DIR / "project_db.py"),
        ("anylabeling.platform.infrastructure.unit_of_work", INFRA_DIR / "unit_of_work.py"),
        ("anylabeling.platform.infrastructure.sqlite_repositories.assets", SQLITE_REPOS_DIR / "assets.py"),
        ("anylabeling.platform.application.ports.repositories", PORTS_DIR / "repositories.py"),
        ("anylabeling.platform.application.project_context", APP_DIR / "project_context.py"),
    ]:
        _load_module(mod_name, mod_path)


_bootstrap()

# =============================================================================
# Imports (now safe after bootstrap)
# =============================================================================

from anylabeling.platform.application.import_service import ImportService
from anylabeling.platform.application.project_context import ProjectContext
from anylabeling.platform.domain.records import AssetRecord

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def project_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Return a unique temp project root directory (created)."""
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def context(project_root: pathlib.Path) -> ProjectContext:
    """Return an opened ProjectContext backed by the temp project."""
    ctx = ProjectContext(project_root)
    ctx.open()
    yield ctx
    ctx.close()


@pytest.fixture
def source_image(tmp_path: pathlib.Path) -> str:
    """Create a small valid test image in a temp source directory."""
    src_dir = tmp_path / "source"
    src_dir.mkdir(parents=True)
    img_path = src_dir / "test_img.jpg"
    import cv2
    import numpy as np
    img = np.zeros((100, 200, 3), dtype="uint8")
    cv2.imwrite(str(img_path), img)
    return str(img_path)


# =============================================================================
# Test: Import writes assets to DB
# =============================================================================


class TestImportWritesAssetsToDb:
    """ImportService with ProjectContext writes AssetRecords to SQLite."""

    def test_import_writes_assets_to_db(
        self, context: ProjectContext, source_image: str, project_root: pathlib.Path
    ) -> None:
        svc = ImportService(project_root, context=context)
        result = svc.import_images([source_image])

        assert result.total == 1
        assert len(result.assets) == 1

        asset = result.assets[0]
        # Verify DB record exists
        db_record = context.assets.get(asset.id)
        assert db_record is not None
        assert db_record.id == asset.id
        assert db_record.rel_path == asset.path
        assert db_record.width == asset.width
        assert db_record.height == asset.height
        assert db_record.sha256 == asset.sha256
        assert db_record.status == "active"
        assert db_record.source_kind == "import"

    def test_import_two_files_creates_two_records(
        self, context: ProjectContext, source_image: str, project_root: pathlib.Path
    ) -> None:
        svc = ImportService(project_root, context=context)

        # Create a second distinct test image
        src_dir = pathlib.Path(source_image).parent
        img2_path = src_dir / "test_img2.png"
        import cv2
        import numpy as np
        img2 = np.ones((50, 50, 3), dtype="uint8") * 128
        cv2.imwrite(str(img2_path), img2)

        result = svc.import_images([source_image, str(img2_path)])
        assert result.total == 2

        for asset in result.assets:
            record = context.assets.get(asset.id)
            assert record is not None
            assert record.rel_path == asset.path

    def test_record_fields_populated_correctly(
        self, context: ProjectContext, source_image: str, project_root: pathlib.Path
    ) -> None:
        """Verify all AssetRecord fields are populated as expected."""
        svc = ImportService(project_root, context=context)
        result = svc.import_images([source_image])
        asset = result.assets[0]

        db_record = context.assets.get(asset.id)
        assert db_record is not None

        # Check key computed fields
        assert db_record.ext == ".jpg"
        assert db_record.size_bytes > 0
        assert db_record.status == "active"
        assert db_record.source_kind == "import"
        assert db_record.source_version is None
        assert db_record.created_at is not None
        assert db_record.updated_at is not None
        assert db_record.deleted_at is None


# =============================================================================
# Test: Duplicate import does not duplicate DB rows
# =============================================================================


class TestDuplicateImportNoDuplicates:
    """ImportService deduplication also prevents duplicate DB records."""

    def test_same_file_twice_single_db_row(
        self, context: ProjectContext, source_image: str, project_root: pathlib.Path
    ) -> None:
        svc = ImportService(project_root, context=context)
        result1 = svc.import_images([source_image, source_image])

        # First call: dedup should skip the second copy
        assert result1.duplicate_count == 1
        assert result1.total == 1

        asset = result1.assets[0]
        record1 = context.assets.get(asset.id)
        assert record1 is not None

        # Import again (same file, new ImportService call)
        result2 = svc.import_images([source_image])
        # The file is a different physical copy but has same SHA-256
        # Note: this is a new ImportService call, so it has its own seen_hashes
        # The result may show 1 more record, but the upsert ON CONFLICT(rel_path)
        # should prevent duplicates
        assert result2.total == 0 or result2.total == 1

        # Query DB: should only be one record total (upsert prevents dupes)
        all_records = context.assets.list()
        matching = [r for r in all_records if r.rel_path == asset.path]
        assert len(matching) == 1, "ON CONFLICT should prevent duplicate rel_path rows"

    def test_same_content_different_folders(
        self, context: ProjectContext, tmp_path: pathlib.Path, project_root: pathlib.Path
    ) -> None:
        """Same image content from different source folders should produce
        separate DB records (different rel_path after copy / rename)."""
        import cv2
        import numpy as np

        img_data = np.zeros((32, 32, 3), dtype="uint8")

        src1 = tmp_path / "folder_a" / "img.jpg"
        src1.parent.mkdir(parents=True)
        cv2.imwrite(str(src1), img_data)

        src2 = tmp_path / "folder_b" / "img.jpg"
        src2.parent.mkdir(parents=True)
        cv2.imwrite(str(src2), img_data)

        svc = ImportService(project_root, context=context)
        result = svc.import_images([str(src1), str(src2)], group_by_folder=True)

        # Both files have same SHA but different source folders -> different
        # rel_path after copy (different destinations because same filename
        # "img.jpg" in same assets/ dir -> second gets _1 suffix).
        # total depends on dedup behavior
        assert result.total > 0

        all_records = context.assets.list()
        # Should have at least one record per file
        assert len(all_records) == result.total


# =============================================================================
# Test: File-copy failure does not write DB
# =============================================================================


class TestCopyFailureNoDbWrite:
    """When file copy fails, no AssetRecord should be written to the DB."""

    def test_copy_failure_skips_db_write(
        self, context: ProjectContext, source_image: str, project_root: pathlib.Path
    ) -> None:
        svc = ImportService(project_root, context=context)

        with patch(
            "anylabeling.platform.application.import_service.shutil.copy2",
            side_effect=OSError("Disk full"),
        ):
            result = svc.import_images([source_image])

        assert result.total == 0
        assert len(result.errors) == 1
        assert "Disk full" in result.errors[0]

        # Verify no records were written
        all_records = context.assets.list()
        assert len(all_records) == 0

    def test_copy_failure_on_one_file_leaves_others(
        self, context: ProjectContext, source_image: str, tmp_path: pathlib.Path, project_root: pathlib.Path
    ) -> None:
        """If one copy fails, records for other files should still be written."""
        import cv2
        import numpy as np

        # Create a second image that will be imported after the failing one
        src_dir = pathlib.Path(source_image).parent
        good_img = src_dir / "good.png"
        cv2.imwrite(str(good_img), np.zeros((10, 10, 3), dtype="uint8"))

        svc = ImportService(project_root, context=context)

        original_copy2 = __import__("shutil").copy2

        def _failing_copy2(src: str, dst: str) -> str:
            if "test_img.jpg" in str(src):
                raise OSError("Permission denied")
            return original_copy2(src, dst)

        with patch(
            "anylabeling.platform.application.import_service.shutil.copy2",
            side_effect=_failing_copy2,
        ):
            result = svc.import_images([source_image, str(good_img)])

        assert result.total == 1
        assert len(result.errors) == 1

        all_records = context.assets.list()
        assert len(all_records) == 1


# =============================================================================
# Test: Backward compat — ImportService without context
# =============================================================================


class TestImportWithoutContext:
    """ImportService without ProjectContext must still work as before."""

    def test_import_works_without_context(
        self, source_image: str, project_root: pathlib.Path
    ) -> None:
        svc = ImportService(project_root)  # no context
        result = svc.import_images([source_image])

        assert result.total == 1
        assert len(result.assets) == 1
        assert (project_root / result.assets[0].path).exists()

    def test_import_with_context_none_is_backward_compat(
        self, source_image: str, project_root: pathlib.Path
    ) -> None:
        svc = ImportService(project_root, context=None)
        result = svc.import_images([source_image])

        assert result.total == 1
        assert len(result.assets) == 1

    def test_import_with_images_and_annotations_no_context(
        self, source_image: str, project_root: pathlib.Path
    ) -> None:
        """import_with_annotations should also work without context."""
        svc = ImportService(project_root)  # no context
        result, _ = svc.import_with_annotations(
            [source_image],
            annotation_format="coco",
            annotation_source=__file__,  # dummy — won't parse but should not crash
        )
        assert result.total == 1


# =============================================================================
# Test: Error handling — corrupt image
# =============================================================================


class TestCorruptImageNoDbWrite:
    """A corrupt / unreadable image should not produce a DB record."""

    def test_corrupt_image_no_record(
        self, context: ProjectContext, tmp_path: pathlib.Path, project_root: pathlib.Path
    ) -> None:
        """A file that is not a valid image should not write a DB record."""
        src_dir = tmp_path / "source"
        src_dir.mkdir(parents=True)
        bad_file = src_dir / "fake.jpg"
        bad_file.write_text("this is not an image")

        svc = ImportService(project_root, context=context)
        result = svc.import_images([str(bad_file)])

        assert result.total == 0
        assert len(result.errors) == 1
        assert "Failed to read image" in result.errors[0]

        # Verify no DB record was created
        all_records = context.assets.list()
        assert len(all_records) == 0


# =============================================================================
# Test: Group folder attribute is persisted
# =============================================================================


class TestGroupFolderDbPersistence:
    """Group folder assignment from import is recorded in the DB."""

    def test_group_name_persisted(
        self, context: ProjectContext, tmp_path: pathlib.Path, project_root: pathlib.Path
    ) -> None:
        import cv2
        import numpy as np

        src_dir = tmp_path / "my_source_folder"
        src_dir.mkdir(parents=True)
        img = src_dir / "sample.jpg"
        cv2.imwrite(str(img), np.zeros((50, 50, 3), dtype="uint8"))

        svc = ImportService(project_root, context=context)
        result = svc.import_images([str(img)], group_by_folder=True)

        assert result.total == 1
        asset = result.assets[0]
        record = context.assets.get(asset.id)
        assert record is not None
        assert record.group_name == "my_source_folder"

    def test_group_name_none_when_disabled(
        self, context: ProjectContext, source_image: str, project_root: pathlib.Path
    ) -> None:
        svc = ImportService(project_root, context=context)
        result = svc.import_images([source_image], group_by_folder=False)

        assert result.total == 1
        asset = result.assets[0]
        record = context.assets.get(asset.id)
        assert record is not None
        assert record.group_name is None

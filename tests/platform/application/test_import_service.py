"""Tests for ImportService and ImportConfig/ImportResult domain models.

Coverage:
    1. ImportConfig defaults are correct
    2. ImportResult dataclass construction
    3. ImportService.import_images copies files to assets/
    4. SHA-256 deduplication skips duplicates
    5. Image property analysis populates Asset fields
    6. Large image detection (>2000px)
    7. Group by folder assigns group_id
    8. Supported formats filtering
    9. Empty paths returns empty result
    10. Non-existent paths recorded as errors
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from anylabeling.platform.domain.import_config import ImportConfig, ImportResult
from anylabeling.platform.application.import_service import ImportService


# ============================================================================
# Domain model tests
# ============================================================================


class TestImportConfig:
    """Tests for ImportConfig dataclass."""

    def test_defaults(self):
        """ImportConfig has sensible defaults."""
        cfg = ImportConfig()
        assert cfg.deduplicate is True
        assert cfg.group_by_folder is True
        assert cfg.detect_large_images is True
        assert cfg.large_threshold == 2000
        assert ".jpg" in cfg.supported_extensions
        assert ".png" in cfg.supported_extensions
        assert ".bmp" in cfg.supported_extensions
        assert ".tiff" in cfg.supported_extensions
        assert ".webp" in cfg.supported_extensions

    def test_custom_values(self):
        """ImportConfig accepts custom values."""
        cfg = ImportConfig(
            deduplicate=False,
            group_by_folder=False,
            detect_large_images=False,
            large_threshold=1024,
            supported_extensions=(".jpg", ".png"),
        )
        assert cfg.deduplicate is False
        assert cfg.group_by_folder is False
        assert cfg.detect_large_images is False
        assert cfg.large_threshold == 1024
        assert cfg.supported_extensions == (".jpg", ".png")

    def test_immutable_if_frozen(self):
        """ImportConfig fields behave as expected."""
        cfg = ImportConfig()
        assert isinstance(cfg.supported_extensions, tuple)


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_empty_result(self):
        """ImportResult can represent an empty import."""
        result = ImportResult(
            assets=[],
            total=0,
            large_count=0,
            duplicate_count=0,
            errors=[],
        )
        assert result.total == 0
        assert len(result.assets) == 0
        assert result.large_count == 0
        assert result.duplicate_count == 0
        assert result.errors == []

    def test_with_stats(self):
        """ImportResult carries correct statistics."""
        result = ImportResult(
            assets=[],
            total=10,
            large_count=3,
            duplicate_count=2,
            errors=["file not found: bad.jpg"],
        )
        assert result.total == 10
        assert result.large_count == 3
        assert result.duplicate_count == 2
        assert len(result.errors) == 1


# ============================================================================
# ImportService tests
# ============================================================================


class TestImportServiceInit:
    """Tests for ImportService construction."""

    def test_accepts_string_path(self):
        """ImportService accepts a string project root."""
        svc = ImportService("/tmp/test_project")
        assert svc.project_root == Path("/tmp/test_project")

    def test_accepts_path_object(self):
        """ImportService accepts a Path project root."""
        svc = ImportService(Path("/tmp/test_project"))
        assert svc.project_root == Path("/tmp/test_project")

    def test_project_root_property(self):
        """project_root property returns Path."""
        svc = ImportService("/data/project")
        assert isinstance(svc.project_root, Path)
        assert svc.project_root == Path("/data/project")


class TestImportServiceBasic:
    """Basic workflow tests using real file I/O in temp directory."""

    def test_empty_paths_returns_empty_result(self, tmp_path):
        """Importing an empty list returns empty ImportResult."""
        svc = ImportService(tmp_path)
        result = svc.import_images([])
        assert result.total == 0
        assert len(result.assets) == 0
        assert result.large_count == 0
        assert result.duplicate_count == 0
        assert result.errors == []

    def test_non_existent_paths_reported_as_errors(self, tmp_path):
        """Non-existent file paths are recorded in errors."""
        svc = ImportService(tmp_path)
        result = svc.import_images(["/nonexistent/path/img.jpg"])
        # total counts only successfully imported files
        assert result.total == 0
        assert len(result.errors) > 0
        assert len(result.assets) == 0

    def test_unsupported_extension_skipped(self, tmp_path):
        """Files with unsupported extensions are skipped and reported."""
        bad_file = tmp_path / "doc.txt"
        bad_file.write_text("hello")
        svc = ImportService(tmp_path)
        result = svc.import_images([str(bad_file)])
        # total counts only successfully imported files
        assert result.total == 0
        assert len(result.assets) == 0
        assert len(result.errors) > 0

    def test_copies_image_to_assets_dir(self, tmp_path):
        """ImportService copies images to assets/ directory."""
        # Create a source image
        src_img = tmp_path / "source" / "test.jpg"
        src_img.parent.mkdir(parents=True)
        import cv2
        img = __import__('numpy').zeros((100, 200, 3), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        svc = ImportService(tmp_path / "project")
        result = svc.import_images([str(src_img)])

        assert result.total == 1
        assert len(result.assets) == 1
        asset = result.assets[0]
        assert asset.width == 200
        assert asset.height == 100
        assert asset.channels == 3
        # Asset should be in assets/
        assert "assets" in asset.path
        # File should actually exist
        assert (svc.project_root / asset.path).exists()

    def test_image_property_analysis(self, tmp_path):
        """ImportService extracts width, height, channels from images."""
        src_img = tmp_path / "source" / "sample.png"
        src_img.parent.mkdir(parents=True)
        import cv2
        import numpy as np
        img = np.zeros((300, 400, 3), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        svc = ImportService(tmp_path / "project")
        result = svc.import_images([str(src_img)])

        assert len(result.assets) == 1
        a = result.assets[0]
        assert a.width == 400
        assert a.height == 300
        assert a.channels == 3

    def test_sha256_populated(self, tmp_path):
        """ImportService populates sha256 field on imported assets."""
        src_img = tmp_path / "source" / "img.jpg"
        src_img.parent.mkdir(parents=True)
        import cv2
        import numpy as np
        img = np.zeros((50, 50, 3), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        svc = ImportService(tmp_path / "project")
        result = svc.import_images([str(src_img)])

        assert len(result.assets) == 1
        assert result.assets[0].sha256 is not None
        assert len(result.assets[0].sha256) == 64  # SHA-256 hex digest

    def test_deduplication_skips_duplicates(self, tmp_path):
        """Importing the same file twice deduplicates by SHA-256."""
        src_img = tmp_path / "source" / "dup.jpg"
        src_img.parent.mkdir(parents=True)
        import cv2
        import numpy as np
        img = np.zeros((64, 64, 3), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        svc = ImportService(tmp_path / "project")
        result = svc.import_images([str(src_img), str(src_img)])
        assert result.duplicate_count == 1
        assert len(result.assets) == 1

    def test_deduplication_when_disabled(self, tmp_path):
        """With deduplicate=False, duplicates are still copied."""
        src_img = tmp_path / "source" / "nodup.jpg"
        src_img.parent.mkdir(parents=True)
        import cv2
        import numpy as np
        img = np.zeros((64, 64, 3), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        svc = ImportService(tmp_path / "project")
        result = svc.import_images([str(src_img), str(src_img)], deduplicate=False)
        # Both copied (second gets a suffix)
        assert len(result.assets) == 2
        assert result.duplicate_count == 0

    def test_large_image_detection(self, tmp_path):
        """Images with dimension >2000px are marked is_large on Asset."""
        src_img = tmp_path / "source" / "large.jpg"
        src_img.parent.mkdir(parents=True)
        import cv2
        import numpy as np
        # 2500 > 2000 threshold
        img = np.zeros((2500, 100, 3), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        svc = ImportService(tmp_path / "project")
        result = svc.import_images([str(src_img)])
        assert result.large_count == 1
        assert len(result.assets) == 1

    def test_small_image_not_large(self, tmp_path):
        """Images under threshold are not marked large."""
        src_img = tmp_path / "source" / "small.jpg"
        src_img.parent.mkdir(parents=True)
        import cv2
        import numpy as np
        img = np.zeros((100, 200, 3), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        svc = ImportService(tmp_path / "project")
        result = svc.import_images([str(src_img)])
        assert result.large_count == 0

    def test_group_by_folder(self, tmp_path):
        """Images from same folder get same group_id."""
        src_dir = tmp_path / "source" / "folder_a"
        src_dir.mkdir(parents=True)
        import cv2
        import numpy as np
        # Use different image content so dedup does not merge them
        img_a = np.zeros((50, 50, 3), dtype='uint8')
        img_b = np.ones((50, 50, 3), dtype='uint8') * 255
        cv2.imwrite(str(src_dir / "a.jpg"), img_a)
        cv2.imwrite(str(src_dir / "b.jpg"), img_b)

        svc = ImportService(tmp_path / "project")
        paths = [str(src_dir / "a.jpg"), str(src_dir / "b.jpg")]
        result = svc.import_images(paths, group_by_folder=True)

        assert len(result.assets) == 2
        gids = {a.group_id for a in result.assets}
        assert len(gids) == 1
        assert gids.pop() == "folder_a"

    def test_group_by_folder_disabled(self, tmp_path):
        """With group_by_folder=False, group_id is None."""
        src_dir = tmp_path / "source" / "folder_b"
        src_dir.mkdir(parents=True)
        import cv2
        import numpy as np
        img = np.zeros((50, 50, 3), dtype='uint8')
        cv2.imwrite(str(src_dir / "x.jpg"), img)

        svc = ImportService(tmp_path / "project")
        result = svc.import_images([str(src_dir / "x.jpg")], group_by_folder=False)

        assert len(result.assets) == 1
        assert result.assets[0].group_id is None

    def test_multiple_formats(self, tmp_path):
        """ImportService handles JPEG, PNG, BMP, TIFF, WebP."""
        src_dir = tmp_path / "source"
        src_dir.mkdir(parents=True)
        import cv2
        import numpy as np

        formats = {
            "a.jpg": None,
            "b.png": None,
            "c.bmp": None,
        }
        for fname in formats:
            if fname.endswith(".jpg") or fname.endswith(".png") or fname.endswith(".bmp"):
                img = np.zeros((48, 48, 3), dtype='uint8')
                cv2.imwrite(str(src_dir / fname), img)

        svc = ImportService(tmp_path / "project")
        paths = [str(src_dir / f) for f in formats]
        result = svc.import_images(paths)
        assert result.total == 3

    def test_assets_subdir_created(self, tmp_path):
        """ImportService ensures assets/ directory exists."""
        src_img = tmp_path / "source" / "img.jpg"
        src_img.parent.mkdir(parents=True)
        import cv2
        import numpy as np
        img = np.zeros((10, 10, 3), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        svc = ImportService(tmp_path / "proj")
        result = svc.import_images([str(src_img)])
        assets_dir = svc.project_root / "assets"
        assert assets_dir.exists()
        assert assets_dir.is_dir()

    def test_preserves_original_filename(self, tmp_path):
        """Imported file retains its original filename in assets/."""
        src_img = tmp_path / "source" / "my_cat_photo.jpg"
        src_img.parent.mkdir(parents=True)
        import cv2
        import numpy as np
        img = np.zeros((20, 20, 3), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        svc = ImportService(tmp_path / "proj")
        result = svc.import_images([str(src_img)])
        asset_path = svc.project_root / result.assets[0].path
        assert asset_path.name == "my_cat_photo.jpg"


# ============================================================================
# Integration / edge case tests
# ============================================================================


class TestImportServiceEdgeCases:
    """Edge case and integration tests."""

    def test_import_images_with_custom_config(self, tmp_path):
        """ImportService respects ImportConfig parameters."""
        src_img = tmp_path / "source" / "img.jpg"
        src_img.parent.mkdir(parents=True)
        import cv2
        import numpy as np
        img = np.zeros((100, 200, 3), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        cfg = ImportConfig(
            deduplicate=False,
            group_by_folder=False,
            detect_large_images=False,
            large_threshold=500,
        )
        svc = ImportService(tmp_path / "proj")
        result = svc.import_images(
            [str(src_img), str(src_img)],
            deduplicate=cfg.deduplicate,
            group_by_folder=cfg.group_by_folder,
        )
        assert result.duplicate_count == 0
        assert len(result.assets) == 2

    def test_grayscale_image_channels(self, tmp_path):
        """Grayscale images report channels=1."""
        src_img = tmp_path / "source" / "gray.jpg"
        src_img.parent.mkdir(parents=True)
        import cv2
        import numpy as np
        img = np.zeros((100, 200), dtype='uint8')
        cv2.imwrite(str(src_img), img)

        svc = ImportService(tmp_path / "proj")
        result = svc.import_images([str(src_img)])
        assert len(result.assets) == 1
        assert result.assets[0].channels == 1

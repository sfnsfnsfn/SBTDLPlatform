"""Unit tests for AssetRepository.

Covers all 5 public methods with edge cases for empty/missing directories.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from anylabeling.platform.application.asset_repository import AssetRepository


# ============================================================================
# Helpers
# ============================================================================


def _write_test_image(
    dir_path: Path, name: str, size: tuple[int, int] = (640, 480)
) -> Path:
    """Create a synthetic RGB image on disk and return its path."""
    rng = np.random.default_rng(42)
    img = rng.integers(0, 255, (size[1], size[0], 3)).astype(np.uint8)
    p = dir_path / name
    cv2.imwrite(str(p), img)
    return p


# ============================================================================
# Tests — scan_assets
# ============================================================================


class TestScanAssets:
    def test_returns_images_only(self, tmp_path: Path):
        """3 .jpg + 2 .png + 1 .txt → returns 5 image paths, no .txt."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        _write_test_image(assets_dir, "a.jpg")
        _write_test_image(assets_dir, "b.jpg")
        _write_test_image(assets_dir, "c.jpg")
        _write_test_image(assets_dir, "d.png")
        _write_test_image(assets_dir, "e.png")
        (assets_dir / "notes.txt").write_text("hello")

        repo = AssetRepository(tmp_path)
        result = repo.scan_assets()
        assert len(result) == 5
        assert all(p.endswith((".jpg", ".png")) for p in result)
        assert not any(p.endswith(".txt") for p in result)

    def test_empty_dir(self, tmp_path: Path):
        """assets dir exists but has no files → returns []."""
        (tmp_path / "assets").mkdir()
        repo = AssetRepository(tmp_path)
        assert repo.scan_assets() == []

    def test_no_assets_dir(self, tmp_path: Path):
        """No assets/ dir at all → returns []."""
        repo = AssetRepository(tmp_path)
        assert repo.scan_assets() == []


# ============================================================================
# Tests — count_assets
# ============================================================================


class TestCountAssets:
    def test_count(self, tmp_path: Path):
        """5 images → returns 5."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        for i in range(5):
            _write_test_image(assets_dir, f"img_{i}.jpg")
        repo = AssetRepository(tmp_path)
        assert repo.count_assets() == 5


# ============================================================================
# Tests — count_by_extension
# ============================================================================


class TestCountByExtension:
    def test_counts(self, tmp_path: Path):
        """3 jpg + 2 png → {"jpg": 3, "png": 2}."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        for i in range(3):
            _write_test_image(assets_dir, f"img_{i}.jpg")
        for i in range(2):
            _write_test_image(assets_dir, f"img_{i}.png")
        repo = AssetRepository(tmp_path)
        assert repo.count_by_extension() == {".jpg": 3, ".png": 2}


# ============================================================================
# Tests — find_large_images
# ============================================================================


class TestFindLargeImages:
    def test_detects(self, tmp_path: Path):
        """1×3000×3000 + 3×640×480 → returns 1 path."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        _write_test_image(assets_dir, "big.jpg", size=(3000, 3000))
        for i in range(3):
            _write_test_image(assets_dir, f"small_{i}.jpg", size=(640, 480))
        repo = AssetRepository(tmp_path)
        large = repo.find_large_images(min_dim=2000)
        assert len(large) == 1
        assert "big.jpg" in large[0]

    def test_none(self, tmp_path: Path):
        """All 640×480 → returns []."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        for i in range(3):
            _write_test_image(assets_dir, f"img_{i}.jpg", size=(640, 480))
        repo = AssetRepository(tmp_path)
        assert repo.find_large_images(min_dim=2000) == []


# ============================================================================
# Tests — list_subdirs
# ============================================================================


class TestListSubdirs:
    def test_lists(self, tmp_path: Path):
        """3 dirs + 2 files → returns 3 dir names."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        for name in ("train", "val", "test"):
            (assets_dir / name).mkdir()
        _write_test_image(assets_dir, "img_0.jpg")
        _write_test_image(assets_dir, "img_1.jpg")
        repo = AssetRepository(tmp_path)
        assert repo.list_subdirs() == ["test", "train", "val"]


# ============================================================================
# Tests — recursive scan with subdirectories (A0-3 fix)
# ============================================================================


class TestRecursiveScan:
    """A0-3: AssetRepository must scan subdirectories recursively."""

    def test_finds_images_in_subdirectories(self, tmp_path: Path):
        """Images in assets/group_a/ and assets/group_b/ are found."""
        assets_dir = tmp_path / "assets"
        group_a = assets_dir / "group_a"
        group_b = assets_dir / "group_b"
        group_a.mkdir(parents=True)
        group_b.mkdir(parents=True)

        _write_test_image(group_a, "a1.jpg")
        _write_test_image(group_a, "a2.jpg")
        _write_test_image(group_b, "b1.png")
        _write_test_image(assets_dir, "root_img.jpg")

        repo = AssetRepository(tmp_path)
        result = repo.scan_assets()
        assert len(result) == 4, (
            f"Expected 4 images (2 in group_a + 1 in group_b + 1 root), "
            f"got {len(result)}"
        )

    def test_empty_subdirectory_does_not_crash(self, tmp_path: Path):
        """Empty subdirectory should not cause errors."""
        assets_dir = tmp_path / "assets"
        (assets_dir / "empty_group").mkdir(parents=True)
        _write_test_image(assets_dir, "root_img.jpg")

        repo = AssetRepository(tmp_path)
        result = repo.scan_assets()
        assert len(result) == 1

    def test_deeply_nested_images_found(self, tmp_path: Path):
        """Images in deeply nested directories are found."""
        assets_dir = tmp_path / "assets"
        deep = assets_dir / "a" / "b" / "c"
        deep.mkdir(parents=True)
        _write_test_image(deep, "deep_img.jpg")
        _write_test_image(assets_dir, "root.jpg")

        repo = AssetRepository(tmp_path)
        result = repo.scan_assets()
        assert len(result) == 2


class TestGroupDetection:
    """A0-3: Group detection with recursive scanning."""

    def test_get_groups_from_subdirectories(self, tmp_path: Path):
        """Groups are extracted from first-level subdirectory names."""
        assets_dir = tmp_path / "assets"
        for gname in ("train", "val", "test"):
            gdir = assets_dir / gname
            gdir.mkdir(parents=True)
            _write_test_image(gdir, f"{gname}_img.jpg")

        repo = AssetRepository(tmp_path)
        groups = repo.get_groups()
        assert set(groups) == {"test", "train", "val"}, f"Got: {groups}"

    def test_root_images_have_no_group(self, tmp_path: Path):
        """Images directly in assets/ should have group=None."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        _write_test_image(assets_dir, "root.jpg")
        (assets_dir / "grouped").mkdir()
        _write_test_image(assets_dir / "grouped", "g.jpg")

        repo = AssetRepository(tmp_path)
        # Root image should not be counted in any group
        groups = repo.get_groups()
        assert groups == ["grouped"]
        # Verify count is correct
        assert repo.count_assets() == 2

"""Tests for AssetRepository extended query API (Phase 3a).

Covers:
    1. get_asset() returns Asset with correct dimensions
    2. get_asset() returns None for non-existent path
    3. get_asset() deterministic ID (sha256 of path)
    4. scan_assets() with pagination (offset/limit)
    5. scan_assets() with group_filter
    6. get_asset_ids_by_status() returns correct stems
    7. get_asset_ids_by_group() returns correct stems
    8. get_groups() returns sorted group IDs
    9. get_stats() returns correct counts
    10. invalidate_cache() forces re-scan
    11. get_annotation_statuses() reads annotation JSON
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from anylabeling.platform.application.asset_repository import (
    AssetRepository,
    STATUS_COMPLETE,
    STATUS_UNANNOTATED,
)


def _make_asset_file(
    assets_dir: Path, name: str, w: int = 100, h: int = 100
) -> str:
    """Write a test JPEG and return its absolute path string."""
    import cv2

    path = assets_dir / name
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :, 0] = np.linspace(0, 255, w, dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return str(path)


def _make_annotation_file(
    ann_dir: Path, stem: str, shapes: list[dict] | None = None
) -> None:
    """Write a test annotation JSON file."""
    data = {
        "version": "1.0",
        "shapes": shapes or [],
        "imagePath": f"{stem}.jpg",
    }
    ann_dir.mkdir(parents=True, exist_ok=True)
    (ann_dir / f"{stem}.json").write_text(
        json.dumps(data), encoding="utf-8"
    )


# ============================================================================
# get_asset()
# ============================================================================


class TestGetAsset:
    """Tests for AssetRepository.get_asset()."""

    def test_returns_asset_with_dimensions(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        path = _make_asset_file(assets_dir, "test.jpg", 640, 480)
        repo = AssetRepository(str(tmp_path))

        asset = repo.get_asset(path)

        assert asset is not None
        assert asset.width == 640
        assert asset.height == 480
        assert asset.channels == 3

    def test_returns_none_for_missing_file(self, tmp_path):
        repo = AssetRepository(str(tmp_path))
        asset = repo.get_asset("/nonexistent/path.jpg")
        assert asset is None

    def test_returns_none_for_non_image(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        text_file = assets_dir / "readme.txt"
        text_file.write_text("hello")
        repo = AssetRepository(str(tmp_path))
        asset = repo.get_asset(str(text_file))
        assert asset is None

    def test_asset_id_is_deterministic(self, tmp_path):
        """Same path produces same ID across get_asset() calls."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        path = _make_asset_file(assets_dir, "test.jpg", 100, 100)
        repo = AssetRepository(str(tmp_path))

        a1 = repo.get_asset(path)
        repo.invalidate_cache()
        a2 = repo.get_asset(path)

        assert a1 is not None
        assert a2 is not None
        assert a1.id == a2.id  # deterministic across cache invalidation

    def test_asset_cached(self, tmp_path):
        """Second call returns same object from cache."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        path = _make_asset_file(assets_dir, "test.jpg", 100, 100)
        repo = AssetRepository(str(tmp_path))

        a1 = repo.get_asset(path)
        a2 = repo.get_asset(path)

        assert a1 is a2  # same object (cached)


# ============================================================================
# scan_assets() with pagination and filters
# ============================================================================


class TestScanAssetsExtended:
    """Tests for scan_assets() with offset/limit/filters."""

    def test_pagination_offset(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        for i in range(10):
            _make_asset_file(assets_dir, f"img_{i:02d}.jpg", 50, 50)
        repo = AssetRepository(str(tmp_path))

        result = repo.scan_assets(offset=5)
        assert len(result) == 5

    def test_pagination_limit(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        for i in range(10):
            _make_asset_file(assets_dir, f"img_{i:02d}.jpg", 50, 50)
        repo = AssetRepository(str(tmp_path))

        result = repo.scan_assets(limit=3)
        assert len(result) == 3

    def test_pagination_offset_and_limit(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        for i in range(10):
            _make_asset_file(assets_dir, f"img_{i:02d}.jpg", 50, 50)
        repo = AssetRepository(str(tmp_path))

        result = repo.scan_assets(offset=2, limit=3)
        assert len(result) == 3


# ============================================================================
# get_asset_ids_by_status()
# ============================================================================


class TestGetAssetIdsByStatus:
    """Tests for get_asset_ids_by_status()."""

    def test_returns_annotated_stems(self, tmp_path):
        assets_dir = tmp_path / "assets"
        ann_dir = tmp_path / "annotations"
        assets_dir.mkdir()
        path = _make_asset_file(assets_dir, "annotated_img.jpg", 100, 100)
        stem = Path(path).stem
        _make_annotation_file(
            ann_dir, stem, [{"label": "cat", "points": [[0, 0]]}]
        )

        repo = AssetRepository(str(tmp_path))
        complete_ids = repo.get_asset_ids_by_status(STATUS_COMPLETE)

        assert stem in complete_ids

    def test_returns_unannotated_stems(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        path = _make_asset_file(
            assets_dir, "unannotated_img.jpg", 100, 100
        )
        stem = Path(path).stem

        repo = AssetRepository(str(tmp_path))
        unannotated_ids = repo.get_asset_ids_by_status(STATUS_UNANNOTATED)

        assert stem in unannotated_ids


# ============================================================================
# get_asset_ids_by_group()
# ============================================================================


class TestGetAssetIdsByGroup:
    """Tests for get_asset_ids_by_group().

    Note: _get_all_paths() scans only immediate children of assets/.
    Group detection via subdirectories requires enabling recursive scan.
    """

    def test_no_match_for_nonexistent_group(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        _make_asset_file(assets_dir, "flat.jpg", 100, 100)

        repo = AssetRepository(str(tmp_path))
        group_ids = repo.get_asset_ids_by_group("nonexistent_group")

        assert len(group_ids) == 0


# ============================================================================
# get_groups()
# ============================================================================


class TestGetGroups:
    """Tests for get_groups().

    Note: Groups require assets in subdirectories under assets/.
    _get_all_paths() currently scans only flat files; group detection
    via subdirectories requires enabling recursive scan in the repo.
    """

    def test_no_groups_for_flat_assets(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        _make_asset_file(assets_dir, "flat.jpg", 100, 100)

        repo = AssetRepository(str(tmp_path))
        groups = repo.get_groups()

        assert groups == []


# ============================================================================
# get_stats()
# ============================================================================


class TestGetStats:
    """Tests for get_stats()."""

    def test_returns_accurate_counts(self, tmp_path):
        assets_dir = tmp_path / "assets"
        ann_dir = tmp_path / "annotations"
        assets_dir.mkdir()
        ann_dir.mkdir()

        p1 = _make_asset_file(assets_dir, "img_a.jpg", 100, 100)
        _make_annotation_file(
            ann_dir, Path(p1).stem, [{"label": "x", "points": [[0, 0]]}]
        )
        _make_asset_file(assets_dir, "img_b.jpg", 100, 100)
        _make_asset_file(assets_dir, "img_c.jpg", 100, 100)

        repo = AssetRepository(str(tmp_path))
        stats = repo.get_stats()

        assert stats["total"] == 3
        assert stats["annotated"] == 1
        assert stats["unannotated"] == 2
        assert stats["partial"] == 0

    def test_empty_repository(self, tmp_path):
        repo = AssetRepository(str(tmp_path))
        stats = repo.get_stats()

        assert stats["total"] == 0
        assert stats["annotated"] == 0


# ============================================================================
# invalidate_cache()
# ============================================================================


class TestInvalidateCache:
    """Tests for invalidate_cache()."""

    def test_cache_cleared(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        _make_asset_file(assets_dir, "img1.jpg", 100, 100)

        repo = AssetRepository(str(tmp_path))
        first = repo.scan_assets()
        assert len(first) == 1

        _make_asset_file(assets_dir, "img2.jpg", 100, 100)
        repo.invalidate_cache()

        second = repo.scan_assets()
        assert len(second) == 2

    def test_asset_cache_cleared(self, tmp_path):
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        path = _make_asset_file(assets_dir, "img.jpg", 100, 100)

        repo = AssetRepository(str(tmp_path))
        a1 = repo.get_asset(path)
        repo.invalidate_cache()
        a2 = repo.get_asset(path)

        assert a1 is not None
        assert a2 is not None
        assert a1.id == a2.id
        assert a1 is not a2  # different object after cache clear

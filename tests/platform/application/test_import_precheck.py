"""Tests for ImportService.precheck() and PrecheckResult domain model.

Covers:
    1. PrecheckResult dataclass construction and properties
    2. precheck() with valid images returns correct counts
    3. precheck() with damaged file populates damaged_files
    4. precheck() with unsupported extension populates unsupported_files
    5. precheck() with large image populates oversized_files
    6. precheck() with directory walks recursively
    7. precheck() with non-existent sources records errors
    8. ImportService.import_images() with progress_callback
    9. ImportService.import_images() with cancel_token
    10. ImportCancelledError exception
    11. ImportViewModel state machine transitions
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pytest

from anylabeling.platform.domain.import_config import (
    ImportCancelledError,
    PrecheckResult,
)
from anylabeling.platform.application.import_service import ImportService
from anylabeling.views.platform.view_models.import_vm import ImportViewModel


# ============================================================================
# PrecheckResult domain model
# ============================================================================


class TestPrecheckResult:
    """Tests for PrecheckResult frozen dataclass."""

    def test_empty_result(self):
        result = PrecheckResult(total_files=0)
        assert result.ok_count == 0
        assert result.damaged_count == 0
        assert result.unsupported_count == 0
        assert result.oversized_count == 0
        assert result.estimated_size_bytes == 0
        assert result.errors == []

    def test_with_valid_files(self):
        result = PrecheckResult(
            total_files=3,
            valid_files=["a.jpg", "b.jpg", "c.png"],
        )
        assert result.ok_count == 3
        assert result.damaged_count == 0

    def test_with_mixed_files(self):
        result = PrecheckResult(
            total_files=5,
            valid_files=["a.jpg", "b.png"],
            damaged_files=["c.jpg"],
            unsupported_files=["d.txt"],
            oversized_files=[("e.tif", 4000, 3000)],
        )
        assert result.ok_count == 2
        assert result.damaged_count == 1
        assert result.unsupported_count == 1
        assert result.oversized_count == 1

    def test_is_frozen(self):
        result = PrecheckResult(total_files=1)
        with pytest.raises(Exception):
            result.total_files = 5  # type: ignore[misc]


# ============================================================================
# ImportCancelledError
# ============================================================================


class TestImportCancelledError:
    def test_default_message(self):
        exc = ImportCancelledError()
        assert "Import cancelled" in str(exc)

    def test_custom_message(self):
        exc = ImportCancelledError("Cancelled after 5 files")
        assert "Cancelled after 5 files" in str(exc)

    def test_is_exception(self):
        exc = ImportCancelledError()
        assert isinstance(exc, Exception)


# ============================================================================
# ImportService.precheck()
# ============================================================================


class TestPrecheckWithValidImages:
    """precheck() with valid image files."""

    def test_single_valid_image(self, tmp_path):
        img_path = tmp_path / "test.jpg"
        _write_test_image(img_path, 640, 480)
        svc = ImportService(str(tmp_path))
        result = svc.precheck([str(img_path)])
        assert result.ok_count == 1
        assert result.damaged_count == 0
        assert result.unsupported_count == 0
        assert result.total_files == 1

    def test_multiple_valid_images(self, tmp_path):
        for i in range(3):
            _write_test_image(tmp_path / f"img_{i}.jpg", 100, 100)
        svc = ImportService(str(tmp_path))
        result = svc.precheck(
            [str(tmp_path / f"img_{i}.jpg") for i in range(3)]
        )
        assert result.ok_count == 3

    def test_directory_walks_recursively(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        _write_test_image(tmp_path / "a.jpg", 100, 100)
        _write_test_image(subdir / "b.jpg", 100, 100)
        svc = ImportService(str(tmp_path))
        result = svc.precheck([str(tmp_path)])
        assert result.ok_count == 2
        assert result.total_files == 2


class TestPrecheckWithDamagedFiles:
    """precheck() with damaged/unreadable files."""

    def test_corrupt_image_detected(self, tmp_path):
        corrupt = tmp_path / "corrupt.jpg"
        corrupt.write_bytes(b"not a valid image")
        svc = ImportService(str(tmp_path))
        result = svc.precheck([str(corrupt)])
        assert result.ok_count == 0
        assert result.damaged_count == 1

    def test_unsupported_extension(self, tmp_path):
        text_file = tmp_path / "readme.txt"
        text_file.write_text("hello")
        svc = ImportService(str(tmp_path))
        result = svc.precheck([str(text_file)])
        assert result.ok_count == 0
        assert result.unsupported_count == 1


class TestPrecheckWithLargeImages:
    """precheck() large image detection."""

    def test_large_image_detected(self, tmp_path):
        _write_test_image(tmp_path / "big.jpg", 3000, 2000)
        svc = ImportService(str(tmp_path))
        result = svc.precheck([str(tmp_path / "big.jpg")])
        assert result.oversized_count == 1

    def test_normal_image_not_oversized(self, tmp_path):
        _write_test_image(tmp_path / "small.jpg", 640, 480)
        svc = ImportService(str(tmp_path))
        result = svc.precheck([str(tmp_path / "small.jpg")])
        assert result.oversized_count == 0


class TestPrecheckEdgeCases:
    """precheck() edge cases."""

    def test_empty_sources(self, tmp_path):
        svc = ImportService(str(tmp_path))
        result = svc.precheck([])
        assert result.total_files == 0
        assert result.ok_count == 0

    def test_non_existent_source(self, tmp_path):
        svc = ImportService(str(tmp_path))
        result = svc.precheck([str(tmp_path / "nonexistent.jpg")])
        assert result.total_files == 0
        assert len(result.errors) > 0

    def test_estimated_size_computed(self, tmp_path):
        _write_test_image(tmp_path / "img.jpg", 100, 100)
        svc = ImportService(str(tmp_path))
        result = svc.precheck([str(tmp_path / "img.jpg")])
        assert result.estimated_size_bytes > 0

    def test_progress_callback_fired(self, tmp_path):
        for i in range(5):
            _write_test_image(tmp_path / f"img_{i}.jpg", 100, 100)
        svc = ImportService(str(tmp_path))
        progress_values: list[tuple[int, int]] = []

        def on_progress(current: int, total: int) -> None:
            progress_values.append((current, total))

        result = svc.precheck(
            [str(tmp_path)], progress_callback=on_progress
        )
        assert len(progress_values) == 5
        assert progress_values[-1] == (5, 5)


# ============================================================================
# ImportService.import_images() — progress and cancel (Phase 3a)
# ============================================================================


class TestImportWithProgress:
    """import_images() with progress_callback."""

    def test_progress_callback_fired(self, tmp_path):
        for i in range(3):
            _write_test_image(tmp_path / f"img_{i}.jpg", 50, 50, seed=i)
        svc = ImportService(str(tmp_path))
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        svc._project_root = tmp_path
        progress_values: list[tuple[int, int, str]] = []

        def on_progress(current: int, total: int, filename: str) -> None:
            progress_values.append((current, total, filename))

        result = svc.import_images(
            [str(tmp_path / f"img_{i}.jpg") for i in range(3)],
            progress_callback=on_progress,
        )
        assert len(progress_values) == 3
        assert progress_values[-1] == (3, 3, "img_2.jpg")
        assert result.total == 3


class TestImportWithCancel:
    """import_images() with cancel_token."""

    def test_cancel_stops_import(self, tmp_path):
        for i in range(10):
            _write_test_image(tmp_path / f"img_{i}.jpg", 50, 50, seed=i)
        svc = ImportService(str(tmp_path))
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        svc._project_root = tmp_path
        cancel_token = threading.Event()

        def on_progress(current, total, filename):
            if current >= 5:
                cancel_token.set()

        with pytest.raises(ImportCancelledError):
            svc.import_images(
                [str(tmp_path / f"img_{i}.jpg") for i in range(10)],
                progress_callback=on_progress,
                cancel_token=cancel_token,
            )

    def test_no_cancel_when_token_not_set(self, tmp_path):
        _write_test_image(tmp_path / "img.jpg", 50, 50)
        svc = ImportService(str(tmp_path))
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        svc._project_root = tmp_path

        result = svc.import_images(
            [str(tmp_path / "img.jpg")],
            cancel_token=threading.Event(),  # not set
        )
        assert result.total == 1


# ============================================================================
# ImportViewModel state machine
# ============================================================================


class TestImportViewModel:
    """ImportViewModel state transitions."""

    def test_initial_state_is_idle(self, tmp_path):
        svc = ImportService(str(tmp_path))
        vm = ImportViewModel(svc)
        assert vm.stage == ImportViewModel.STAGE_IDLE
        assert vm.source_count == 0
        assert vm.precheck_result is None

    def test_add_sources_updates_count(self, tmp_path):
        svc = ImportService(str(tmp_path))
        vm = ImportViewModel(svc)
        vm.add_sources([str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg")])
        assert vm.source_count == 2

    def test_clear_sources_resets(self, tmp_path):
        svc = ImportService(str(tmp_path))
        vm = ImportViewModel(svc)
        vm.add_sources([str(tmp_path / "a.jpg")])
        vm.clear_sources()
        assert vm.source_count == 0
        assert vm.stage == ImportViewModel.STAGE_IDLE

    def test_cannot_start_precheck_without_sources(self, tmp_path):
        svc = ImportService(str(tmp_path))
        vm = ImportViewModel(svc)
        assert not vm.can_start_precheck
        result = vm.start_precheck()
        assert result is None
        assert vm.stage == ImportViewModel.STAGE_IDLE

    def test_precheck_produces_result(self, tmp_path):
        _write_test_image(tmp_path / "img.jpg", 100, 100)
        svc = ImportService(str(tmp_path))
        vm = ImportViewModel(svc)
        vm.add_sources([str(tmp_path / "img.jpg")])
        result = vm.start_precheck()
        assert result is not None
        assert result.ok_count == 1
        assert vm.stage == ImportViewModel.STAGE_PRECHECK_DONE

    def test_cannot_start_import_without_precheck(self, tmp_path):
        svc = ImportService(str(tmp_path))
        vm = ImportViewModel(svc)
        assert not vm.can_start_import
        result = vm.start_import()
        assert result is None

    def test_reset_returns_to_idle(self, tmp_path):
        _write_test_image(tmp_path / "img.jpg", 100, 100)
        svc = ImportService(str(tmp_path))
        vm = ImportViewModel(svc)
        vm.add_sources([str(tmp_path / "img.jpg")])
        vm.start_precheck()
        vm.reset()
        assert vm.stage == ImportViewModel.STAGE_IDLE
        assert vm.precheck_result is None

    def test_can_cancel_during_busy_state(self, tmp_path):
        svc = ImportService(str(tmp_path))
        vm = ImportViewModel(svc)
        assert not vm.can_cancel
        assert not vm.is_busy


# ============================================================================
# Helpers
# ============================================================================


def _write_test_image(
    path: Path, width: int, height: int, seed: int = 0
) -> None:
    """Write a minimal valid JPEG to *path* with given dimensions.

    Use different *seed* values to produce images with unique SHA-256 hashes.
    """
    import cv2

    img = np.zeros((height, width, 3), dtype=np.uint8)
    # Unique seed creates unique image content → unique SHA-256
    img[:, :, 0] = np.linspace(seed, min(255, seed + 255), width, dtype=np.uint8)
    cv2.imwrite(str(path), img)

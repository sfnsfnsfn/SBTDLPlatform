"""Tests for ExportService.self_test_onnx() — Phase 4b Task 4b.5.

Covers:
    - Missing onnxruntime → failed report
    - Missing ONNX file → failed report
    - Valid ONNX model (mocked ort session) → all pass
    - Path outside project root → failed report
    - Not an .onnx file → failed report
    - Custom sample_count
    - SelfTestReport domain contract
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anylabeling.platform.application.export_service import ExportService
from anylabeling.platform.domain.export_config import SelfTestReport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def export_service(tmp_path: Path) -> ExportService:
    """ExportService pointing at a temporary project root."""
    job_service = MagicMock()
    return ExportService(job_service, project_root=tmp_path)


# ---------------------------------------------------------------------------
# self_test_onnx tests
# ---------------------------------------------------------------------------


class TestSelfTestOnnx:
    """Test self_test_onnx() across success and failure paths."""

    def test_missing_onnxruntime_returns_failed_report(
        self, export_service, tmp_path,
    ):
        """When onnxruntime is not available, report is failed."""
        import numpy as np  # noqa: F401 — ensure numpy available

        onnx_path = tmp_path / "model.onnx"
        onnx_path.write_text("dummy")

        missing = {"onnxruntime": None}
        with patch.dict(sys.modules, missing):
            report = export_service.self_test_onnx(str(onnx_path))
            assert isinstance(report, SelfTestReport)
            assert report.passed is False
            assert report.samples_tested == 0

    def test_missing_onnx_file_returns_failed_report(
        self, export_service,
    ):
        """When ONNX file doesn't exist, report is failed."""
        report = export_service.self_test_onnx(
            "/nonexistent/model.onnx"
        )
        assert report.passed is False
        assert "not found" in report.failures[0].lower()

    def test_all_samples_pass_with_mocked_ort(
        self, export_service, tmp_path,
    ):
        """Mocked onnxruntime session → all samples pass."""
        import numpy as np

        onnx_path = tmp_path / "model.onnx"
        onnx_path.write_text("dummy onnx content")

        mock_session = MagicMock()
        mock_session.get_inputs.return_value = [
            MagicMock(shape=[1, 3, 640, 640], name="images"),
        ]
        mock_session.run.return_value = [
            np.random.randn(1, 8400, 85).astype(np.float32),
        ]

        with patch(
            "onnxruntime.InferenceSession",
            return_value=mock_session,
        ):
            with patch(
                "onnx.checker.check_model", return_value=None,
            ):
                report = export_service.self_test_onnx(
                    str(onnx_path),
                )
                assert isinstance(report, SelfTestReport)
                assert report.passed is True
                assert report.samples_tested == 10

    def test_report_has_expected_shape(
        self, export_service, tmp_path,
    ):
        """SelfTestReport has expected fields and types."""
        import numpy as np

        onnx_path = tmp_path / "model.onnx"
        onnx_path.write_text("dummy")

        mock_session = MagicMock()
        mock_session.get_inputs.return_value = [
            MagicMock(shape=[1, 3, 640, 640], name="images"),
        ]
        mock_session.run.return_value = [
            np.random.randn(1, 8400, 85).astype(np.float32),
        ]

        with patch(
            "onnxruntime.InferenceSession",
            return_value=mock_session,
        ):
            with patch(
                "onnx.checker.check_model", return_value=None,
            ):
                report = export_service.self_test_onnx(
                    str(onnx_path),
                )
                assert report.passed is True
                assert report.samples_tested == 10
                assert isinstance(report.max_deviation, float)
                assert report.max_deviation >= 0.0
                assert report.failures == ()
                assert len(report.created_at) > 0

    def test_path_outside_project_root_fails(
        self, export_service, tmp_path,
    ):
        """ONNX path outside project_root is rejected."""
        # Use a file outside the tmp_path project root that actually exists
        outside_dir = tmp_path.parent / f"outside_{uuid.uuid4().hex}"
        outside_dir.mkdir(parents=True, exist_ok=True)
        outside_path = outside_dir / "model.onnx"
        outside_path.write_text("dummy onnx content")
        try:
            report = export_service.self_test_onnx(str(outside_path))
            assert report.passed is False
            assert "outside project root" in report.failures[0].lower()
        finally:
            # Cleanup — remove_dir equivalent
            import shutil
            shutil.rmtree(outside_dir, ignore_errors=True)

    def test_non_onnx_extension_fails(
        self, export_service, tmp_path,
    ):
        """File not ending in .onnx is rejected."""
        not_onnx = tmp_path / "model.pt"
        not_onnx.write_text("dummy")
        report = export_service.self_test_onnx(str(not_onnx))
        assert report.passed is False
        assert "not an onnx file" in report.failures[0].lower()

    def test_custom_sample_count(self, export_service, tmp_path):
        """sample_count=5 → 5 iterations."""
        import numpy as np

        onnx_path = tmp_path / "model.onnx"
        onnx_path.write_text("dummy")

        mock_session = MagicMock()
        mock_session.get_inputs.return_value = [
            MagicMock(shape=[1, 3, 640, 640], name="images"),
        ]
        mock_session.run.return_value = [
            np.random.randn(1, 8400, 85).astype(np.float32),
        ]

        with patch(
            "onnxruntime.InferenceSession",
            return_value=mock_session,
        ):
            with patch(
                "onnx.checker.check_model", return_value=None,
            ):
                report = export_service.self_test_onnx(
                    str(onnx_path), sample_count=5,
                )
                assert report.samples_tested == 5
                assert report.passed is True


# ---------------------------------------------------------------------------
# SelfTestReport domain contract
# ---------------------------------------------------------------------------


class TestSelfTestReport:
    """Test the SelfTestReport frozen dataclass."""

    def test_self_test_report_is_immutable(self):
        """Frozen dataclass — mutation raises."""
        report = SelfTestReport(passed=True)
        with pytest.raises(Exception):
            report.passed = False  # type: ignore[misc]

    def test_default_values(self):
        """Default values are sensible."""
        report = SelfTestReport(passed=True)
        assert report.samples_tested == 0
        assert report.max_deviation == 0.0
        assert report.failures == ()
        assert report.created_at == ""

    def test_with_failures(self):
        """Failure details are preserved."""
        failures = (
            "Sample 3: no output produced",
            "Sample 7: NaN in output",
        )
        report = SelfTestReport(
            passed=False,
            samples_tested=10,
            max_deviation=0.05,
            failures=tuple(failures),
            created_at="2025-01-01T00:00:00",
        )
        assert report.passed is False
        assert report.samples_tested == 10
        assert len(report.failures) == 2

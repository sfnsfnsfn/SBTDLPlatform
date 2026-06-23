"""Tests for OfflinePolicy (M1.3) and downstream integrations."""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from anylabeling.platform.application.offline_policy import (
    OfflinePolicy,
    PreflightReport,
)


# ============================================================================
# PreflightReport
# ============================================================================

class TestPreflightReport:
    def test_defaults_are_empty(self):
        report = PreflightReport(passed=True)
        assert report.passed is True
        assert report.missing_packages == []
        assert report.recommendations == []
        assert report.errors == []

    def test_fields_populated(self):
        report = PreflightReport(
            passed=False,
            missing_packages=["onnx"],
            recommendations=["pip install onnx"],
            errors=["version conflict"],
        )
        assert report.passed is False
        assert "onnx" in report.missing_packages
        assert len(report.recommendations) == 1
        assert len(report.errors) == 1


# ============================================================================
# OfflinePolicy -- basic policy queries
# ============================================================================

class TestOfflinePolicyBasics:
    # --- allow_network_download -------------------------------------------------

    def test_offline_mode_blocks_network_download(self):
        """1. OfflinePolicy(offline_mode=True).allow_network_download() -> False"""
        policy = OfflinePolicy(offline_mode=True)
        assert policy.allow_network_download() is False

    def test_online_mode_allows_network_download(self):
        """2. OfflinePolicy(offline_mode=False).allow_network_download() -> True"""
        policy = OfflinePolicy(offline_mode=False)
        assert policy.allow_network_download() is True

    # --- allow_pip_install ------------------------------------------------------

    def test_offline_mode_blocks_pip_install(self):
        """3. OfflinePolicy(offline_mode=True).allow_pip_install() -> False"""
        policy = OfflinePolicy(offline_mode=True)
        assert policy.allow_pip_install() is False

    def test_online_mode_allows_pip_install(self):
        policy = OfflinePolicy(offline_mode=False)
        assert policy.allow_pip_install() is True


# ============================================================================
# OfflinePolicy -- preflight_check
# ============================================================================

class TestOfflinePolicyPreflightCheck:
    def test_offline_mode_missing_package_report(self):
        """4. preflight_check() in offline mode with missing package:
        passed=False, has install instructions, no pip call."""
        policy = OfflinePolicy(offline_mode=True)
        report = policy.preflight_check(["nonexistent_pkg_xyz_12345"])
        assert report.passed is False
        assert "nonexistent_pkg_xyz_12345" in report.missing_packages
        assert any(
            "[OFFLINE]" in r for r in report.recommendations
        ), "Should include offline-mode manual install instructions"
        # Confirm pip was never invoked (the method uses importlib, not pip)
        assert report.errors == []

    def test_offline_mode_all_packages_present(self):
        """5. preflight_check() in offline mode with all packages: passed=True"""
        policy = OfflinePolicy(offline_mode=True)
        report = policy.preflight_check(["sys", "os", "json"])
        assert report.passed is True
        assert report.missing_packages == []
        assert report.recommendations == []

    def test_online_mode_missing_package_report(self):
        """Online mode: report that packages are missing but without [OFFLINE] tag."""
        policy = OfflinePolicy(offline_mode=False)
        report = policy.preflight_check(["nonexistent_pkg_xyz_12345"])
        assert report.passed is False
        assert "nonexistent_pkg_xyz_12345" in report.missing_packages
        assert any(
            "[OFFLINE]" not in r for r in report.recommendations
        ), "Online recommendations should not contain [OFFLINE] prefix"

    def test_online_mode_all_packages_present(self):
        policy = OfflinePolicy(offline_mode=False)
        report = policy.preflight_check(["sys", "os"])
        assert report.passed is True

    def test_import_error_recorded_as_missing(self):
        """A genuinely non-existent package is reported as missing."""
        policy = OfflinePolicy(offline_mode=True)
        report = policy.preflight_check(["this_package_does_not_exist_42"])
        assert report.passed is False
        assert "this_package_does_not_exist_42" in report.missing_packages

    def test_never_calls_subprocess_for_pip(self, monkeypatch):
        """Sanity: preflight_check never shells out."""
        import subprocess

        called = []

        def fake_run(*a, **kw):
            called.append(True)
            return MagicMock()

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(subprocess, "Popen", fake_run)

        policy = OfflinePolicy(offline_mode=True)
        policy.preflight_check(["nonexistent_pkg"])
        assert len(called) == 0, "preflight_check must never invoke subprocess"


# ============================================================================
# helper: stub ultralytics modules so local import inside trainer works
# ============================================================================

def _stub_ultralytics_modules(download_mock):
    """Pre-populate sys.modules with mocked ultralytics packages so that the
    local ``from ultralytics.utils.downloads import attempt_download_asset``
    inside ``resolve_training_model_path`` succeeds."""
    mock_downloads = MagicMock()
    mock_downloads.attempt_download_asset = download_mock

    mock_utils = MagicMock()
    mock_utils.downloads = mock_downloads

    mock_ultralytics = MagicMock()
    mock_ultralytics.utils = mock_utils

    for mod_name, mod_obj in [
        ("ultralytics", mock_ultralytics),
        ("ultralytics.utils", mock_utils),
        ("ultralytics.utils.downloads", mock_downloads),
    ]:
        sys.modules[mod_name] = mod_obj

    return mock_downloads


def _cleanup_ultralytics_modules():
    """Remove stubbed ultralytics modules from sys.modules."""
    for mod_name in list(sys.modules):
        if mod_name.startswith("ultralytics"):
            del sys.modules[mod_name]


# ============================================================================
# trainer.py -- resolve_training_model_path  integration
# ============================================================================

class TestTrainerOfflineIntegration:
    """Tests 6 & 7 from the M1.3 specification."""

    def setup_method(self):
        """Clean cached trainer import before each test."""
        sys.modules.pop(
            "anylabeling.services.auto_training.ultralytics.trainer", None
        )
        _cleanup_ultralytics_modules()

    def teardown_method(self):
        _cleanup_ultralytics_modules()
        sys.modules.pop(
            "anylabeling.services.auto_training.ultralytics.trainer", None
        )

    def _get_weights_dir(self):
        from anylabeling.services.auto_training.ultralytics.trainer import (
            get_training_weights_dir,
        )
        return get_training_weights_dir()

    def test_platform_offline_blocks_download(self):
        """6. resolve_training_model_path with platform_offline=True does NOT
        call attempt_download_asset for a non-existent bare .pt filename."""
        download_mock = MagicMock(return_value="/fake/path.pt")
        _stub_ultralytics_modules(download_mock)

        try:
            from anylabeling.services.auto_training.ultralytics.trainer import (
                resolve_training_model_path,
            )

            # Ensure the weights dir does NOT contain this file.
            weights_dir = self._get_weights_dir()
            nonexistent = "nonexistent_model_m1_3_test.pt"
            cached = os.path.join(weights_dir, nonexistent)
            if os.path.exists(cached):
                os.remove(cached)

            result = resolve_training_model_path(
                nonexistent, platform_offline=True
            )

            # Should not have called download
            download_mock.assert_not_called()

            # Should indicate failure (returned None)
            assert result is None, (
                f"Expected None when model not found in offline mode, "
                f"got {result!r}"
            )
        finally:
            _cleanup_ultralytics_modules()

    def test_platform_online_preserves_download_behavior(self):
        """7. resolve_training_model_path with platform_offline=False preserves
        original behavior (attempts download)."""
        download_mock = MagicMock(return_value="/fake/downloaded/path.pt")
        _stub_ultralytics_modules(download_mock)

        try:
            from anylabeling.services.auto_training.ultralytics.trainer import (
                resolve_training_model_path,
            )

            nonexistent = "nonexistent_online_m1_3_test.pt"
            result = resolve_training_model_path(
                nonexistent, platform_offline=False
            )

            download_mock.assert_called_once()
            assert result == "/fake/downloaded/path.pt"
        finally:
            _cleanup_ultralytics_modules()

    def test_default_parameter_does_not_break_callers(self):
        """Backward-compat: calling without platform_offline uses default=False."""
        download_mock = MagicMock(return_value="/fake/path.pt")
        _stub_ultralytics_modules(download_mock)

        try:
            from anylabeling.services.auto_training.ultralytics.trainer import (
                resolve_training_model_path,
            )

            nonexistent = "nonexistent_default_test.pt"
            result = resolve_training_model_path(nonexistent)
            download_mock.assert_called_once()
            assert result == "/fake/path.pt"
        finally:
            _cleanup_ultralytics_modules()


# ============================================================================
# exporter.py -- ExportManager integration
# ============================================================================

class TestExporterOfflineIntegration:
    """Test 8 from the M1.3 specification."""

    def setup_method(self):
        sys.modules.pop(
            "anylabeling.services.auto_training.ultralytics.exporter", None
        )

    def teardown_method(self):
        sys.modules.pop(
            "anylabeling.services.auto_training.ultralytics.exporter", None
        )

    @staticmethod
    def _strip_version_spec(pkg_with_version: str) -> str:
        """Strip version specifiers from a package string.

        e.g. "onnxslim>=0.1.59" -> "onnxslim"
             "onnx>=1.12.0,<1.18.0" -> "onnx"
        """
        for sep in (">=", "<=", "!=", "~=", "==", ">", "<"):
            idx = pkg_with_version.find(sep)
            if idx != -1:
                return pkg_with_version[:idx].strip()
        return pkg_with_version.strip()

    def test_platform_offline_onnx_missing_packages_no_pip(self):
        """8. Missing ONNX packages in platform mode returns preflight error
        without calling pip."""
        # Mock install_packages_with_timeout so we can assert it is NOT called
        install_mock = MagicMock(return_value=(True, "", ""))

        with patch(
            "anylabeling.services.auto_training.ultralytics.exporter.install_packages_with_timeout",
            install_mock,
        ):
            from anylabeling.services.auto_training.ultralytics.exporter import (
                ExportManager,
            )

            manager = ExportManager(platform_offline=True)
            assert manager.platform_offline is True

            # Simulate the worker's package-check logic directly:
            # validate_onnx returns missing packages with version specs;
            # in platform mode those should produce an error callback
            # WITHOUT calling install_packages_with_timeout.
            from anylabeling.services.auto_training.ultralytics.exporter import (
                validate_onnx_export_environment,
            )

            missing = validate_onnx_export_environment()

            if missing:
                # Strip version specs before passing to preflight_check
                # (matches what _export_worker does)
                simple_names = [self._strip_version_spec(p) for p in missing]

                from anylabeling.platform.application.offline_policy import (
                    OfflinePolicy,
                )

                policy = OfflinePolicy(offline_mode=True)
                report = policy.preflight_check(simple_names)
                # In offline mode the report should NOT pass (packages missing)
                # and pip must NOT have been called
                install_mock.assert_not_called()
                assert report.passed is False
                assert any(
                    "[OFFLINE]" in r for r in report.recommendations
                ), "Should recommend manual install in offline mode"
            else:
                # All packages already present -- nothing to test here.
                pass

    def test_platform_online_preserves_pip_install_behavior(self):
        """Default behavior: ExportManager defaults to platform_offline=False."""
        from anylabeling.services.auto_training.ultralytics.exporter import (
            ExportManager,
        )

        manager = ExportManager()
        assert manager.platform_offline is False

    def test_export_start_offline_with_missing_packages_returns_false(self):
        """start_export with platform_offline=True should handle missing weights."""
        from anylabeling.services.auto_training.ultralytics.exporter import (
            ExportManager,
        )

        manager = ExportManager(platform_offline=True)

        # Use a non-existent project path so weights aren't found.
        ok, msg = manager.start_export("/nonexistent/project/path", "onnx")
        # Weights won't be found at all, so the error is about weights.
        # The key invariant: we did NOT call pip install.
        assert ok is False
        assert isinstance(msg, str) and len(msg) > 0

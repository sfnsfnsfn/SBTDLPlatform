"""Offline policy for Vision Algorithm Platform V4.

Controls whether the platform is allowed to perform network downloads or
auto-install packages. In platform mode (offline_mode=True), these operations
are blocked and callers receive human-readable instructions for manual steps.
"""

import importlib.util
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PreflightReport:
    """Result of an environment preflight check.

    Attributes:
        passed: True if all requirements are satisfied.
        missing_packages: List of packages that are not installed.
        recommendations: Human-readable install instructions.
        errors: Error messages encountered during the check.
    """

    passed: bool
    missing_packages: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class OfflinePolicy:
    """Governs whether network-access operations are permitted.

    When offline_mode is True:
        - Network downloads are forbidden.
        - Automatic pip install is forbidden.
        - preflight_check() reports missing packages without calling pip.

    When offline_mode is False (default):
        - All operations are permitted (legacy behavior preserved).
    """

    offline_mode: bool = False

    # ------------------------------------------------------------------
    # Policy queries
    # ------------------------------------------------------------------

    def allow_network_download(self) -> bool:
        """Return False if offline mode is active."""
        return not self.offline_mode

    def allow_pip_install(self) -> bool:
        """Return False if offline mode is active."""
        return not self.offline_mode

    # ------------------------------------------------------------------
    # Preflight check
    # ------------------------------------------------------------------

    def preflight_check(self, required_packages: list[str]) -> PreflightReport:
        """Check whether *required_packages* are importable.

        In offline mode, if any package is missing the report includes manual
        installation instructions.  **pip is never invoked** by this method in
        either mode.

        Args:
            required_packages: Simple package names (e.g. ``["onnx"]``).

        Returns:
            PreflightReport summarising the check result.
        """
        missing: list[str] = []
        errors: list[str] = []
        recommendations: list[str] = []

        for package_name in required_packages:
            spec = importlib.util.find_spec(package_name)
            if spec is not None:
                continue

            # Could not find the package
            missing.append(package_name)
            if self.offline_mode:
                recommendations.append(
                    f"[OFFLINE] Package '{package_name}' is not installed. "
                    f"Please manually run:  pip install {package_name}"
                )
            else:
                recommendations.append(
                    f"Package '{package_name}' is not installed. "
                    f"It will be auto-installed if required."
                )

        if errors:
            return PreflightReport(
                passed=False,
                missing_packages=missing,
                recommendations=recommendations,
                errors=errors,
            )

        passed = len(missing) == 0
        return PreflightReport(
            passed=passed,
            missing_packages=missing,
            recommendations=recommendations,
            errors=errors,
        )

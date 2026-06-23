"""Training readiness domain contracts — pure dataclass DTOs.

Provides the result types for the pre-training readiness validation
pipeline (Phase 4).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    """Single training readiness check.

    Attributes:
        name: Check identifier (e.g. "assets_exist",
            "annotations_coverage").
        passed: Whether the check passed.
        detail: Human-readable detail message.
        blocking: Whether this check blocks training start.
    """

    name: str
    passed: bool
    detail: str = ""
    blocking: bool = True


@dataclass(frozen=True)
class TrainReadinessReport:
    """Pre-training readiness validation report.

    Attributes:
        ready: Whether all blocking checks passed.
        checks: List of individual check results.
        warnings: Non-blocking warning messages.
    """

    ready: bool
    checks: tuple[CheckResult, ...] = ()
    warnings: tuple[str, ...] = ()

__all__ = [
    "CheckResult",
    "TrainReadinessReport",
]

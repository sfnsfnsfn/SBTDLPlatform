"""TrainValidationViewModel— pre-training readiness state.

Pure state machine— no PyQt6 imports.  Wraps TrainReadinessReport
and exposes per-check properties for the readiness checklist widget.
"""

from __future__ import annotations

import logging

from anylabeling.platform.domain.training_readiness import (
    CheckResult,
    TrainReadinessReport,
)

logger = logging.getLogger(__name__)


class TrainValidationViewModel:
    """ViewModel for pre-training readiness validation.

    Pure state machine— no PyQt6 imports.
    Wraps TrainReadinessReport and exposes per-check properties.

    Usage::

        vm = TrainValidationViewModel()
        report = training_service.validate_training_readiness(
            task_spec, dataset_build
        )
        vm.set_report(report)
        if vm.ready:
            print("Training can proceed")
    """

    def __init__(self) -> None:
        self._report: TrainReadinessReport | None = None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def set_report(self, report: TrainReadinessReport) -> None:
        """Set the readiness report."""
        self._report = report

    def clear(self) -> None:
        """Clear current report."""
        self._report = None

    # ------------------------------------------------------------------
    # read-only properties
    # ------------------------------------------------------------------

    @property
    def report(self) -> TrainReadinessReport | None:
        """The current readiness report, or None if not yet validated."""
        return self._report

    @property
    def ready(self) -> bool:
        """Whether all blocking checks passed."""
        if self._report is None:
            return False
        return self._report.ready

    @property
    def checks(self) -> tuple[CheckResult, ...]:
        """All check results."""
        if self._report is None:
            return ()
        return self._report.checks

    @property
    def warnings(self) -> tuple[str, ...]:
        """Non-blocking warning messages."""
        if self._report is None:
            return ()
        return self._report.warnings

    @property
    def passed_count(self) -> int:
        """Number of passed checks."""
        return sum(1 for c in self.checks if c.passed)

    @property
    def total_count(self) -> int:
        """Total number of checks."""
        return len(self.checks)

    @property
    def failed_blocking(self) -> tuple[CheckResult, ...]:
        """Failed blocking checks that prevent training."""
        return tuple(c for c in self.checks if c.blocking and not c.passed)

    @property
    def has_report(self) -> bool:
        """Whether a report has been set."""
        return self._report is not None


__all__ = ["TrainValidationViewModel"]

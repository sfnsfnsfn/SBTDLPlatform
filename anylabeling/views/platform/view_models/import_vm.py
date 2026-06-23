"""ImportViewModel — state management for import workflow.

No PyQt6 imports. Pure state machine with service delegation.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from anylabeling.platform.application.import_service import (
    ImportCancelledError,
    ImportService,
)
from anylabeling.platform.domain.import_config import ImportResult, PrecheckResult

logger = logging.getLogger(__name__)


class ImportViewModel:
    """ViewModel for import workflow — source management, precheck, execution.

    Lifecycle: IDLE → PRECHECKING → PRECHECK_DONE → IMPORTING → COMPLETE
    """

    STAGE_IDLE = "idle"
    STAGE_PRECHECKING = "prechecking"
    STAGE_PRECHECK_DONE = "precheck_done"
    STAGE_IMPORTING = "importing"
    STAGE_COMPLETE = "complete"

    def __init__(self, import_service: ImportService) -> None:
        self._service = import_service
        self._sources: list[str] = []
        self._precheck_result: PrecheckResult | None = None
        self._import_result: ImportResult | None = None
        self._stage: str = self.STAGE_IDLE
        self._progress_current: int = 0
        self._progress_total: int = 0
        self._progress_file: str = ""
        self._cancel_token: threading.Event | None = None
        self._error_message: str = ""

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def stage(self) -> str:
        return self._stage

    @property
    def sources(self) -> list[str]:
        return list(self._sources)

    @property
    def source_count(self) -> int:
        return len(self._sources)

    @property
    def precheck_result(self) -> PrecheckResult | None:
        return self._precheck_result

    @property
    def import_result(self) -> ImportResult | None:
        return self._import_result

    @property
    def progress_current(self) -> int:
        return self._progress_current

    @property
    def progress_total(self) -> int:
        return self._progress_total

    @property
    def progress_file(self) -> str:
        return self._progress_file

    @property
    def error_message(self) -> str:
        return self._error_message

    @property
    def can_start_precheck(self) -> bool:
        return self._stage in (self.STAGE_IDLE,) and len(self._sources) > 0

    @property
    def can_start_import(self) -> bool:
        return (
            self._stage == self.STAGE_PRECHECK_DONE
            and self._precheck_result is not None
            and self._precheck_result.ok_count > 0
        )

    @property
    def can_cancel(self) -> bool:
        return self._stage in (self.STAGE_PRECHECKING, self.STAGE_IMPORTING)

    @property
    def is_busy(self) -> bool:
        return self._stage in (self.STAGE_PRECHECKING, self.STAGE_IMPORTING)

    # ------------------------------------------------------------------
    # Source management
    # ------------------------------------------------------------------

    def add_sources(self, paths: list[str]) -> None:
        """Add file or directory paths to the source list (deduplicated)."""
        for p in paths:
            abs_path = str(Path(p).resolve())
            if abs_path not in self._sources:
                self._sources.append(abs_path)
        if self._stage == self.STAGE_PRECHECK_DONE:
            self._precheck_result = None
            self._stage = self.STAGE_IDLE

    def remove_source(self, path: str) -> None:
        """Remove a source from the list."""
        abs_path = str(Path(path).resolve())
        if abs_path in self._sources:
            self._sources.remove(abs_path)
        if not self._sources:
            self._precheck_result = None
            self._stage = self.STAGE_IDLE

    def clear_sources(self) -> None:
        """Clear all sources."""
        self._sources.clear()
        self._precheck_result = None
        self._stage = self.STAGE_IDLE

    # ------------------------------------------------------------------
    # Precheck
    # ------------------------------------------------------------------

    def start_precheck(
        self,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> PrecheckResult | None:
        """Run precheck synchronously. Call from a QThread.

        Returns:
            PrecheckResult, or None if precheck cannot start.
        """
        if not self.can_start_precheck:
            return None

        self._stage = self.STAGE_PRECHECKING
        self._cancel_token = threading.Event()
        self._error_message = ""

        def _on_progress(current: int, total: int) -> None:
            self._progress_current = current
            self._progress_total = total
            if progress_callback:
                progress_callback(current, total)

        try:
            self._precheck_result = self._service.precheck(
                self._sources,
                progress_callback=_on_progress,
                cancel_token=self._cancel_token,
            )
            self._stage = self.STAGE_PRECHECK_DONE
            return self._precheck_result
        except ImportCancelledError:
            self._error_message = "Precheck cancelled"
            self._stage = self.STAGE_IDLE
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            self._error_message = str(exc)
            self._stage = self.STAGE_IDLE
            raise
        finally:
            self._cancel_token = None

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def start_import(
        self,
        deduplicate: bool = True,
        group_by_folder: bool = True,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> ImportResult | None:
        """Run import synchronously. Call from a QThread.

        Only imports files that passed precheck (PrecheckResult.valid_files).

        Returns:
            ImportResult, or None if import cannot start.
        """
        if not self.can_start_import:
            return None

        assert self._precheck_result is not None
        self._stage = self.STAGE_IMPORTING
        self._cancel_token = threading.Event()
        self._error_message = ""

        def _on_progress(current: int, total: int, filename: str) -> None:
            self._progress_current = current
            self._progress_total = total
            self._progress_file = filename
            if progress_callback:
                progress_callback(current, total, filename)

        try:
            self._import_result = self._service.import_images(
                self._precheck_result.valid_files,
                deduplicate=deduplicate,
                group_by_folder=group_by_folder,
                progress_callback=_on_progress,
                cancel_token=self._cancel_token,
            )
            self._stage = self.STAGE_COMPLETE
            return self._import_result
        except ImportCancelledError:
            self._error_message = "Import cancelled"
            self._stage = self.STAGE_PRECHECK_DONE
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            self._error_message = str(exc)
            self._stage = self.STAGE_PRECHECK_DONE
            raise
        finally:
            self._cancel_token = None

    def cancel(self) -> None:
        """Request cancellation of the running precheck or import."""
        if self._cancel_token is not None:
            self._cancel_token.set()

    def reset(self) -> None:
        """Reset to IDLE, clearing all state."""
        self._cancel_token = None
        self._precheck_result = None
        self._import_result = None
        self._stage = self.STAGE_IDLE
        self._progress_current = 0
        self._progress_total = 0
        self._progress_file = ""
        self._error_message = ""


__all__ = ["ImportViewModel"]

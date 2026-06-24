"""ProjectSession — encapsulated project lifecycle and service wiring.

Provides a single entry point for opening and closing projects,
owning the JobService and WorkflowState instances.

Architecture constraints:
    - No PyQt6 imports (safe for worker processes).
    - No Ultralytics imports.
    - All paths are pathlib.Path.
    - All file I/O is UTF-8.
"""

from __future__ import annotations

import logging
from pathlib import Path

from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.application.project_context import ProjectContext
from anylabeling.platform.application.workflow_state import (
    DomainState,
    WorkflowState,
)

logger = logging.getLogger(__name__)


class ProjectSession:
    """Encapsulated project lifecycle — service wiring and cleanup.

    Usage::

        session = ProjectSession()
        session.open_project("/path/to/project")
        jobs = session.job_service.list_jobs()
        nav_states = session.workflow_state.refresh()
        session.close_project()
    """

    def __init__(self) -> None:
        self._project_root: Path | None = None
        self._context: ProjectContext | None = None
        self._job_service: JobService | None = None
        self._workflow_state: WorkflowState | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def project_root(self) -> Path | None:
        """The current project root path, or None if no project open."""
        return self._project_root

    @property
    def context(self) -> ProjectContext | None:
        """The current ProjectContext, or None if no project open."""
        return self._context

    @property
    def job_service(self) -> JobService | None:
        """The current JobService, or None if no project open."""
        return self._job_service

    @property
    def workflow_state(self) -> WorkflowState | None:
        """The current WorkflowState, or None if no project open."""
        return self._workflow_state

    @property
    def is_open(self) -> bool:
        """True if a project is currently open."""
        return self._project_root is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open_project(self, project_path: str | Path) -> None:
        """Open a project: create JobService and WorkflowState.

        If a project is already open, close it first to ensure clean
        state before opening the new project.

        Args:
            project_path: Path to the project root directory.

        Raises:
            FileNotFoundError: If ``project_path`` does not exist.
            NotADirectoryError: If ``project_path`` is not a directory.
        """
        path = Path(project_path).resolve()

        if not path.exists():
            raise FileNotFoundError(
                f"Project path does not exist: {path}"
            )
        if not path.is_dir():
            raise NotADirectoryError(
                f"Project path is not a directory: {path}"
            )

        # Close existing project first
        if self.is_open:
            logger.info(
                "Closing existing project '%s' before opening '%s'",
                self._project_root,
                path,
            )
            self.close_project()

        self._project_root = path

        self._context = ProjectContext(path)
        self._context.open()
        self._job_service = self._context.job_service
        self._workflow_state = self._context.workflow_state

        logger.info("Project opened: %s", path)

    def close_project(self) -> None:
        """Close the current project and nullify all services.

        Services are garbage-collected. No explicit resource cleanup
        is needed since JobService and WorkflowState have no open
        file handles or persistent connections.

        Safe to call when no project is open (no-op).
        """
        if not self.is_open:
            return

        logger.info("Closing project: %s", self._project_root)

        if self._context is not None:
            self._context.close()
        self._context = None
        self._workflow_state = None
        self._job_service = None
        self._project_root = None

    def refresh_navigation_state(self) -> dict[int, DomainState]:
        """Refresh and return per-domain navigation state.

        Returns:
            Dict mapping ``Domain.value`` → ``DomainState``.
            Empty dict if no project is open.
        """
        if self._workflow_state is None:
            logger.warning(
                "refresh_navigation_state called with no project open"
            )
            return {}
        return self._workflow_state.refresh()


__all__ = [
    "ProjectSession",
]

"""Application service for job lifecycle management.

JobService is the primary API that UI ViewModels interact with for
creating, monitoring, and cancelling long-running platform operations
(training, export, inference, dataset build).

Architecture constraints:
    - Does NOT import PyQt6 (safe for worker processes).
    - Does NOT import Ultralytics.
    - Does NOT import views.*.
    - All paths are pathlib.Path.
    - All file I/O is UTF-8.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Dict, List

from anylabeling.platform.infrastructure.process_job_runner import ProcessJobRunner
from anylabeling.platform.workers.protocol import (
    JobEvent,
    JobRequest,
    JobState,
    TERMINAL_STATES,
)

logger = logging.getLogger(__name__)


class JobService:
    """Application service for job lifecycle management.

    Wraps :class:`ProcessJobRunner` with a higher-level API that tracks
    job requests and provides query methods suitable for UI binding.

    Usage::

        service = JobService(Path("./jobs"))
        job_id = service.create_job(
            JobRequest(job_kind="training", params={"epochs": 10}),
            command=["python", "-m", "train", "--epochs", "10"],
        )
        state = service.get_job_state(job_id)
        events = service.get_job_events(job_id)
    """

    def __init__(self, jobs_root: str | Path) -> None:
        self._runner = ProcessJobRunner(jobs_root)
        self._jobs: Dict[str, JobRequest] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create_job(self, request: JobRequest, command: list[str]) -> str:
        """Create and start a job.

        Persists ``request.json`` and ``state.json`` in the job directory,
        starts the process via :class:`ProcessJobRunner`, and returns the
        *job_id* for tracking.

        If the subprocess fails to start (e.g. command not found) the job
        is still registered in ``_jobs`` and will appear in :meth:`list_jobs`
        with ``FAILED`` state.  The original exception is re-raised.

        Args:
            request: The job request describing what work to perform.
            command: The command line to execute (as a list of strings).

        Returns:
            The job ID string (available as ``request.job_id``).
        """
        with self._lock:
            try:
                self._runner.start(request, command)
            except Exception:
                self._jobs[request.job_id] = request
                logger.exception(
                    "Job %s (%s) failed to start", request.job_id, request.job_kind
                )
                raise
            self._jobs[request.job_id] = request
            logger.info("Job %s (%s) started", request.job_id, request.job_kind)
            return request.job_id

    def cancel_job(self, job_id: str) -> None:
        """Cancel a running job.

        Writes ``stop.flag``, waits for graceful shutdown, then force-kills
        if necessary.  Idempotent — safe to call on already-cancelled jobs.
        """
        with self._lock:
            self._runner.cancel(job_id)
        logger.info("Job %s cancelled", job_id)

    def wait_job(self, job_id: str, timeout: float | None = None) -> int:
        """Wait for *job_id* to complete.

        Returns the process exit code (0 = success, non-zero = failure).
        """
        with self._lock:
            return self._runner.wait(job_id, timeout=timeout)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_job_state(self, job_id: str) -> JobState:
        """Get the current state of *job_id*."""
        return self._runner.get_state(job_id)

    def get_job_events(self, job_id: str) -> list[JobEvent]:
        """Get all events emitted by *job_id*."""
        return self._runner.get_events(job_id)

    def get_job_logs(self, job_id: str) -> tuple[str, str]:
        """Get (stdout, stderr) log contents for *job_id*.

        Log files are written by the subprocess in whatever encoding the child
        process chooses (system locale on Windows, typically UTF-8 elsewhere).
        We read raw bytes and try UTF-8 first, falling back to the system's
        preferred encoding with surrogate escapes.

        Returns:
            A tuple of ``(stdout_text, stderr_text)``.
        """
        job_dir = self._runner._job_dir(job_id)
        stdout_path = job_dir / "stdout.log"
        stderr_path = job_dir / "stderr.log"

        def _read_log(path: Path) -> str:
            if not path.exists():
                return ""
            raw = path.read_bytes()
            # Try common encodings; order matters — single-byte fallbacks
            # like cp1252 can decode any byte sequence, so try multi-byte
            # encodings (utf-8, gbk) first.
            for enc in ("utf-8", "utf-16", "gbk", "cp1252"):
                try:
                    return raw.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue
            return raw.decode("utf-8", errors="replace")

        return _read_log(stdout_path), _read_log(stderr_path)

    def list_jobs(self) -> list[dict]:
        """List all jobs with their current state.

        Returns:
            A list of dicts with keys ``job_id``, ``job_kind``, ``state``.
        """
        with self._lock:
            result: list[dict] = []
            for job_id, request in self._jobs.items():
                try:
                    state = self.get_job_state(job_id)
                except FileNotFoundError:
                    state = JobState.FAILED
                result.append(
                    {
                        "job_id": job_id,
                        "job_kind": request.job_kind,
                        "state": state.value,
                    }
                )
            return result

    def is_terminal(self, job_id: str) -> bool:
        """Return True if *job_id* is in a terminal state."""
        try:
            return self.get_job_state(job_id) in TERMINAL_STATES
        except FileNotFoundError:
            return True

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def jobs_root(self) -> Path:
        """The root directory where all job directories live."""
        return self._runner.jobs_root


__all__ = [
    "JobService",
]

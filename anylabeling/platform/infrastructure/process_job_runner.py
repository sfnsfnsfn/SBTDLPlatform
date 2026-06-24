"""Process-based job runner.

Runs platform jobs as subprocesses, capturing stdout/stderr to log files
and tracking state transitions through a state.json file in the job's
working directory.

Architecture constraints:
    - No PyQt6 imports (runs in worker processes).
    - All paths are pathlib.Path.
    - All file I/O is UTF-8.
"""

from __future__ import annotations

import logging
import os
import platform
import signal
import subprocess
import sys
from pathlib import Path
from typing import Dict

from anylabeling.platform.workers.protocol import (
    JobEvent,
    JobRequest,
    JobState,
    append_event,
    read_events,
    read_state,
    write_state,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform-specific process termination
# ---------------------------------------------------------------------------

_IS_WINDOWS = platform.system() == "Windows"


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    """Kill *proc* and all of its child processes.

    On Windows this uses ``taskkill /F /T /PID``.
    On POSIX this sends SIGKILL to the process group.
    """
    if proc.poll() is not None:
        return  # already exited

    pid = proc.pid
    if pid is None:
        return

    if _IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Fallback: terminate just the parent
            try:
                proc.kill()
            except OSError:
                pass
    else:
        # POSIX: kill the entire process group
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            try:
                proc.kill()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# ProcessJobRunner
# ---------------------------------------------------------------------------


class ProcessJobRunner:
    """Runs a platform job as a subprocess with log capture and cancellation.

    Each job lives in a dedicated directory under *jobs_root*::

        jobs_root/
          <job_id>/
            request.json    — serialized JobRequest
            state.json      — current JobState (JSON)
            events.jsonl    — newline-delimited JobEvent records
            stdout.log      — subprocess stdout
            stderr.log      — subprocess stderr
            stop.flag       — cancellation signal (created on demand)

    Usage::

        runner = ProcessJobRunner(Path("./jobs"))
        proc = runner.start(request, ["python", "-c", "print('hello')"])
        exit_code = runner.wait(request.job_id)
        state = runner.get_state(request.job_id)

    .. warning::

        This class is **not thread-safe** on its own.  The internal
        ``_processes`` dict is mutated without locks.  It should be
        managed through :class:`JobService` which provides a threading.Lock.
    """

    def __init__(self, jobs_root: str | Path) -> None:
        self.jobs_root = Path(jobs_root)
        self._processes: Dict[str, subprocess.Popen] = {}

    # ------------------------------------------------------------------
    # Job directory helpers
    # ------------------------------------------------------------------

    def _job_dir(self, job_id: str) -> Path:
        """Return the job's working directory path."""
        return self.jobs_root / job_id

    def _ensure_job_dir(self, job_id: str) -> Path:
        """Create (if needed) and return the job's working directory."""
        d = self._job_dir(job_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, request: JobRequest, command: list[str]) -> subprocess.Popen:
        """Start a subprocess for *request* with the given *command*.

        1. Creates the job directory: ``jobs_root/<job_id>/``
        2. Writes ``request.json``
        3. Writes ``state.json`` with ``QUEUED``
        4. Opens ``stdout.log`` and ``stderr.log`` for capture
        5. Starts the subprocess
        6. Only if Popen succeeds: writes "started" event and advances
           state to RUNNING.

        On Popen failure the file handles are closed, ``state.json`` is
        set to ``FAILED``, a "failed" event is appended, and the original
        exception is re-raised so the caller (:class:`JobService`) can
        register the job as failed.

        Returns:
            The :class:`subprocess.Popen` handle for the launched process.
        """
        job_dir = self._ensure_job_dir(request.job_id)

        # Persist the request
        (job_dir / "request.json").write_text(
            request.to_json(), encoding="utf-8"
        )

        # Initial state: QUEUED
        write_state(job_dir / "state.json", JobState.QUEUED)

        # Open log files in binary mode — subprocesses write raw bytes
        # whose encoding is determined by their own environment, not ours.
        stdout_path = job_dir / "stdout.log"
        stderr_path = job_dir / "stderr.log"
        stdout_fh = stdout_path.open("wb")
        stderr_fh = stderr_path.open("wb")

        try:
            # Launch the subprocess
            popen_kwargs: dict = {
                "stdout": stdout_fh,
                "stderr": stderr_fh,
                "cwd": str(job_dir),
            }
            # On POSIX, create a new process group for clean tree termination
            if not _IS_WINDOWS:
                popen_kwargs["start_new_session"] = True

            proc = subprocess.Popen(command, **popen_kwargs)

            # Only write "started" event AFTER Popen succeeds (C2 fix)
            import datetime

            append_event(
                job_dir / "events.jsonl",
                JobEvent(
                    seq=0,
                    type="started",
                    payload={
                        "job_id": request.job_id,
                        "job_kind": request.job_kind,
                        "command": command,
                    },
                    timestamp=datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                ),
            )

            # Advance state to STARTING → RUNNING
            write_state(job_dir / "state.json", JobState.STARTING)
            write_state(job_dir / "state.json", JobState.RUNNING)

            self._processes[request.job_id] = proc
            return proc

        except Exception:
            # C1 fix: Clean up on Popen failure
            import datetime

            # Close file handles
            try:
                stdout_fh.close()
            except OSError:
                pass
            try:
                stderr_fh.close()
            except OSError:
                pass

            # Write FAILED state so the job is visible via list_jobs()
            try:
                write_state(job_dir / "state.json", JobState.FAILED)
            except Exception:
                logger.exception(
                    "Failed to write FAILED state for job %s",
                    request.job_id,
                )

            # Append "failed" event with error details
            try:
                append_event(
                    job_dir / "events.jsonl",
                    JobEvent(
                        seq=0,
                        type="failed",
                        payload={
                            "error": str(sys.exc_info()[1]),
                            "command": command,
                        },
                        timestamp=datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                    ),
                )
            except Exception:
                logger.exception(
                    "Failed to write failed event for job %s",
                    request.job_id,
                )

            raise

    def wait(self, job_id: str, timeout: float | None = None) -> int:
        """Wait for *job_id* to complete and return its exit code.

        When the process exits:
            - exit code 0  → state = COMPLETED
            - exit code != 0 → state = FAILED

        If *timeout* is given, :exc:`subprocess.TimeoutExpired` is raised
        when the deadline is exceeded (the process continues running).

        After the process exits the entry is removed from the internal
        process registry (reaping).

        Returns:
            The process exit code.
        """
        proc = self._processes.get(job_id)
        if proc is None:
            raise ValueError(f"No running process for job '{job_id}'")

        try:
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise

        # Close log file handles
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()

        # Persist terminal state
        job_dir = self._job_dir(job_id)
        state = JobState.COMPLETED if exit_code == 0 else JobState.FAILED
        write_state(job_dir / "state.json", state)

        import datetime

        append_event(
            job_dir / "events.jsonl",
            JobEvent(
                seq=9999,
                type=state.value,
                payload={"exit_code": exit_code},
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        )

        # Reap the process entry (I4 fix)
        self._processes.pop(job_id, None)

        return exit_code

    def cancel(self, job_id: str) -> None:
        """Cancel a running job.

        1. Writes ``stop.flag`` to the job directory (cooperative signal).
        2. Waits briefly for graceful shutdown (2 seconds).
        3. Force-terminates the process tree if still running.
        4. Updates ``state.json`` to ``CANCELLED``.

        Raises:
            FileNotFoundError: If the job directory does not exist
                (the job was never created).
        """
        job_dir = self._job_dir(job_id)
        if not job_dir.exists():
            raise FileNotFoundError(
                f"No job directory found for job '{job_id}'"
            )

        # Mark as cancelling
        write_state(job_dir / "state.json", JobState.CANCELLING)
        import datetime

        append_event(
            job_dir / "events.jsonl",
            JobEvent(
                seq=9998,
                type="log",
                payload={"message": "Cancellation requested"},
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        )

        # Write the stop flag
        (job_dir / "stop.flag").write_text("1", encoding="utf-8")

        # Graceful wait
        proc = self._processes.get(job_id)
        if proc is not None:
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                _terminate_process_tree(proc)

        # Close handles
        if proc is not None:
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()

        write_state(job_dir / "state.json", JobState.CANCELLED)

        append_event(
            job_dir / "events.jsonl",
            JobEvent(
                seq=9999,
                type="cancelled",
                payload={"message": "Job cancelled"},
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        )

        # Reap the process entry (I4 fix)
        self._processes.pop(job_id, None)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_state(self, job_id: str) -> JobState:
        """Read the current state of *job_id* from its ``state.json``.

        Raises:
            FileNotFoundError: If no state file exists for this job.
        """
        return read_state(self._job_dir(job_id) / "state.json")

    def get_events(self, job_id: str) -> list[JobEvent]:
        """Read all events for *job_id* from its ``events.jsonl``."""
        return read_events(self._job_dir(job_id) / "events.jsonl")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self, job_id: str) -> None:
        """Remove process tracking for *job_id* (does not delete files)."""
        self._processes.pop(job_id, None)


__all__ = [
    "ProcessJobRunner",
]

"""Job protocol — core types for the platform job system.

Defines the Job state machine, request/event data types, and the
CancellationToken mechanism used for cooperative job cancellation.

All types in this module are lightweight dataclasses with no framework
dependencies — safe to import in any process.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Set


# ============================================================================
# Job State Machine
# ============================================================================


class JobState(str, Enum):
    """Discrete states a job can occupy.

    Valid transitions::

        QUEUED ──► STARTING ──► RUNNING ──► COMPLETED
          │                                    ▲
          │                         ┌─────────┘
          ▼                         ▼
        CANCELLING ──► CANCELLED   FAILED

    Terminal states: COMPLETED, FAILED, CANCELLED
    """

    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


#: Valid state transitions.
#: Transitioning to an unlisted state raises :class:`InvalidStateTransition`.
VALID_TRANSITIONS: Dict[JobState, Set[JobState]] = {
    JobState.QUEUED: {JobState.STARTING, JobState.CANCELLING},
    JobState.STARTING: {JobState.RUNNING, JobState.FAILED, JobState.CANCELLING},
    JobState.RUNNING: {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLING},
    JobState.CANCELLING: {JobState.CANCELLED, JobState.FAILED},
    # Terminal states — no outgoing transitions
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}

#: Terminal states that will never transition again.
TERMINAL_STATES: Set[JobState] = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}


def try_transition_state(current: JobState, next_state: JobState) -> bool:
    """Return True if *current* → *next_state* is a valid transition."""
    return next_state in VALID_TRANSITIONS.get(current, set())


def transition_state(current: JobState, next_state: JobState) -> JobState:
    """Validate and apply a state transition.

    Returns *next_state* if the transition is valid.

    Raises:
        InvalidStateTransition: If the transition is not allowed.
    """
    if not try_transition_state(current, next_state):
        raise InvalidStateTransition(current, next_state)
    return next_state


class InvalidStateTransition(ValueError):
    """Raised when a state transition is not allowed."""

    def __init__(self, current: JobState, attempted: JobState) -> None:
        self.current = current
        self.attempted = attempted
        allowed = ", ".join(s.value for s in VALID_TRANSITIONS.get(current, set()))
        super().__init__(
            f"Invalid state transition: {current.value} → {attempted.value}. "
            f"Allowed from {current.value}: [{allowed or 'none (terminal state)'}]"
        )


# ============================================================================
# Job Request / Event Types
# ============================================================================


@dataclass
class JobRequest:
    """Immutable request to create a new job.

    Attributes:
        job_kind: Category of work, e.g. ``"training"``, ``"export"``,
            ``"dataset_build"``, ``"inference"``.
        params: Job-specific parameters (must be JSON-serializable).
        job_id: Unique identifier. Auto-generated if not supplied.
    """

    job_kind: str
    params: dict
    job_id: str = field(default_factory=lambda: f"job_{uuid.uuid4().hex[:12]}")

    def to_json(self) -> str:
        """Serialize the request to a JSON string."""
        return json.dumps(
            {"job_id": self.job_id, "job_kind": self.job_kind, "params": self.params},
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, data: str) -> "JobRequest":
        """Deserialize a JobRequest from a JSON string."""
        obj = json.loads(data)
        return cls(job_kind=obj["job_kind"], params=obj["params"], job_id=obj["job_id"])


@dataclass
class JobEvent:
    """A single event emitted during job execution.

    Events are persisted as newline-delimited JSON (JSONL) so that
    progress can be reconstructed incrementally without holding the
    entire event list in memory.

    Attributes:
        seq: Monotonically-increasing sequence number.
        type: Event category.
        payload: Free-form dict (must be JSON-serializable).
        timestamp: ISO-8601 timestamp populated by the writer.
    """

    seq: int
    type: Literal[
        "started", "progress", "metric", "artifact", "completed", "failed", "log"
    ]
    payload: dict
    timestamp: str = ""

    def to_json_line(self) -> str:
        """Serialize as a single JSONL line (no trailing newline)."""
        return json.dumps(
            {
                "seq": self.seq,
                "type": self.type,
                "payload": self.payload,
                "timestamp": self.timestamp,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json_line(cls, line: str) -> "JobEvent":
        """Deserialize from a single JSONL line."""
        obj = json.loads(line)
        return cls(
            seq=obj["seq"],
            type=obj["type"],
            payload=obj["payload"],
            timestamp=obj.get("timestamp", ""),
        )


# ============================================================================
# Cancellation Token
# ============================================================================


@dataclass
class CancellationToken:
    """Cooperative cancellation token backed by a ``stop.flag`` file.

    The runner writes ``stop.flag`` to the job directory to signal that
    the job should exit gracefully.  The job process checks for this file
    periodically and exits with a known code when it is detected.

    Attributes:
        job_dir: Path to the job's working directory.
    """

    job_dir: str
    _cancelled: bool = field(default=False, repr=False)

    @property
    def flag_path(self) -> Path:
        """Absolute path to the ``stop.flag`` file."""
        return Path(self.job_dir) / "stop.flag"

    @property
    def is_cancelled(self) -> bool:
        """Return True if ``stop.flag`` exists.

        This property is re-evaluated every access so that callers can
        poll it inside long-running loops.
        """
        return self._cancelled or self.flag_path.exists()

    def cancel(self) -> None:
        """Create the ``stop.flag`` file to signal cancellation."""
        self._cancelled = True
        self.flag_path.parent.mkdir(parents=True, exist_ok=True)
        self.flag_path.write_text("1", encoding="utf-8")


# ============================================================================
# State Persistence Helpers
# ============================================================================


def write_state(state_path: Path, state: JobState) -> None:
    """Atomically write the current job state to a JSON file.

    Uses a tmp→replace strategy so that readers never see a partial write.
    """
    content = json.dumps({"state": state.value}, ensure_ascii=False, indent=2)
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(state_path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def read_state(state_path: Path) -> JobState:
    """Read the current job state from a JSON file.

    Returns:
        JobState parsed from the file.

    Raises:
        FileNotFoundError: If the state file does not exist.
        ValueError: If the file contains an unrecognized state value.
    """
    data = json.loads(state_path.read_text(encoding="utf-8"))
    return JobState(data["state"])


def read_events(events_path: Path) -> List[JobEvent]:
    """Read all events from a JSONL file.

    Returns an empty list if the file does not exist.
    """
    if not events_path.exists():
        return []
    events: List[JobEvent] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(JobEvent.from_json_line(line))
    return events


def append_event(events_path: Path, event: JobEvent) -> None:
    """Append a single event to a JSONL file."""
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as f:
        f.write(event.to_json_line() + "\n")


__all__ = [
    "CancellationToken",
    "InvalidStateTransition",
    "JobEvent",
    "JobRequest",
    "JobState",
    "TERMINAL_STATES",
    "VALID_TRANSITIONS",
    "append_event",
    "read_events",
    "read_state",
    "transition_state",
    "try_transition_state",
    "write_state",
]

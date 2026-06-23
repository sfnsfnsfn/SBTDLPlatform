"""Platform workers — job protocol and runner infrastructure.

This package defines the core types for job management (protocol.py)
and will host worker-level handler implementations in the future.
"""

from anylabeling.platform.workers.protocol import (
    CancellationToken,
    InvalidStateTransition,
    JobEvent,
    JobRequest,
    JobState,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    append_event,
    read_events,
    read_state,
    transition_state,
    try_transition_state,
    write_state,
)

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

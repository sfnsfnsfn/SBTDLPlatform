"""Tests for JobService and ProcessJobRunner (M1.4).

Coverage:
    1. Create and start a simple job, verify COMPLETED
    2. Job that fails (exit code != 0), verify FAILED
    3. Cancel a long-running job, verify CANCELLED
    4. Verify stdout/stderr capture
    5. Verify events written to events.jsonl
    6. Verify stop.flag triggers cancellation
    7. State transition validation (invalid transitions raise error)
    8. Verify request.json contains correct params
    9. List jobs returns correct states
    10. CancellationToken behaviour
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from anylabeling.platform.application.job_service import JobService
from anylabeling.platform.workers.protocol import (
    CancellationToken,
    InvalidStateTransition,
    JobEvent,
    JobRequest,
    JobState,
    append_event,
    read_events,
    read_state,
    transition_state,
    try_transition_state,
    write_state,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def jobs_root(tmp_path: Path) -> Path:
    """Temporary directory for job data."""
    return tmp_path / "jobs"


@pytest.fixture
def service(jobs_root: Path) -> JobService:
    """JobService backed by a temp directory."""
    return JobService(jobs_root)


@pytest.fixture
def simple_request() -> JobRequest:
    """A simple job that prints hello and exits successfully."""
    return JobRequest(job_kind="test", params={"message": "hello"})


# ============================================================================
# 1. Simple job → COMPLETED
# ============================================================================


class TestSimpleJobCompletion:
    def test_simple_job_completes(self, service: JobService):
        """Submit a job that prints 'hello' and exits 0. Verify COMPLETED."""
        request = JobRequest(job_kind="test", params={"msg": "hello"})
        job_id = service.create_job(request, ["python", "-c", "print('hello')"])

        exit_code = service.wait_job(job_id)
        assert exit_code == 0

        state = service.get_job_state(job_id)
        assert state == JobState.COMPLETED


    def test_multiple_jobs_in_parallel(self, service: JobService):
        """Multiple jobs can run concurrently."""
        ids = []
        for i in range(3):
            req = JobRequest(job_kind="test", params={"n": i})
            jid = service.create_job(req, ["python", "-c", f"print({i})"])
            ids.append(jid)

        for jid in ids:
            service.wait_job(jid)
            assert service.get_job_state(jid) == JobState.COMPLETED


# ============================================================================
# 2. Failing job → FAILED
# ============================================================================


class TestFailingJob:
    def test_nonzero_exit_marks_failed(self, service: JobService):
        """A job that exits with code 1 should be FAILED."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request,
            ["python", "-c", "import sys; sys.exit(1)"],
        )

        exit_code = service.wait_job(job_id)
        assert exit_code != 0

        state = service.get_job_state(job_id)
        assert state == JobState.FAILED


    def test_failed_job_logs_stderr(self, service: JobService):
        """A failing job should capture stderr output."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request,
            [
                "python", "-c",
                "import sys; print('ERROR: something broke', file=sys.stderr); sys.exit(2)",
            ],
        )

        service.wait_job(job_id)
        stdout, stderr = service.get_job_logs(job_id)
        assert "ERROR: something broke" in stderr
        assert service.get_job_state(job_id) == JobState.FAILED


# ============================================================================
# 3. Cancel a long-running job
# ============================================================================


class TestJobCancellation:
    def test_cancel_long_running_job(self, service: JobService):
        """Start a long-running job, cancel it, verify CANCELLED."""
        request = JobRequest(job_kind="test", params={})
        # A script that sleeps for 60 seconds — we'll cancel it quickly
        command = [
            "python", "-c",
            """
import time, sys
try:
    time.sleep(60)
except KeyboardInterrupt:
    sys.exit(0)
""",
        ]
        job_id = service.create_job(request, command)

        # Give it a moment to start
        time.sleep(0.3)

        service.cancel_job(job_id)

        # Allow cancellation to complete
        time.sleep(0.5)

        state = service.get_job_state(job_id)
        assert state == JobState.CANCELLED


    def test_cancel_is_idempotent(self, service: JobService):
        """Cancelling an already-cancelled job should not raise."""
        request = JobRequest(job_kind="test", params={})
        command = [
            "python", "-c",
            "import time; time.sleep(30)",
        ]
        job_id = service.create_job(request, command)
        time.sleep(0.3)
        service.cancel_job(job_id)
        # Second cancel should not raise
        service.cancel_job(job_id)

        state = service.get_job_state(job_id)
        assert state == JobState.CANCELLED


# ============================================================================
# 4. Stdout / stderr capture
# ============================================================================


class TestLogCapture:
    def test_stdout_captured(self, service: JobService):
        """stdout from the subprocess should be written to stdout.log."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request,
            ["python", "-c", "print('line1'); print('line2')"],
        )
        service.wait_job(job_id)

        stdout, stderr = service.get_job_logs(job_id)
        assert "line1" in stdout
        assert "line2" in stdout
        assert stderr == ""  # No stderr expected


    def test_stderr_captured(self, service: JobService):
        """stderr from the subprocess should be written to stderr.log."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request,
            [
                "python", "-c",
                "import sys; print('warning', file=sys.stderr)",
            ],
        )
        service.wait_job(job_id)

        stdout, stderr = service.get_job_logs(job_id)
        assert "warning" in stderr


    def test_log_files_utf8(self, service: JobService):
        """Log files should be decoded correctly (multi-byte characters).

        On Windows, subprocess stdout uses the system locale encoding (e.g. GBK).
        get_job_logs must handle this via encoding fallback.
        """
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request,
            ["python", "-c", "print('hello')"],
        )
        service.wait_job(job_id)
        stdout, _ = service.get_job_logs(job_id)
        assert "hello" in stdout


# ============================================================================
# 5. Events (events.jsonl)
# ============================================================================


class TestEvents:
    def test_started_event_written(self, service: JobService):
        """A 'started' event should be written when the job starts."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(request, ["python", "-c", "print('hi')"])
        service.wait_job(job_id)

        events = service.get_job_events(job_id)
        types = [e.type for e in events]
        assert "started" in types


    def test_completed_event_written(self, service: JobService):
        """A 'completed' event should be written on successful exit."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(request, ["python", "-c", "print('hi')"])
        service.wait_job(job_id)

        events = service.get_job_events(job_id)
        types = [e.type for e in events]
        assert "completed" in types


    def test_failed_event_written(self, service: JobService):
        """A 'failed' event should be written on non-zero exit."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request,
            ["python", "-c", "import sys; sys.exit(3)"],
        )
        service.wait_job(job_id)

        events = service.get_job_events(job_id)
        types = [e.type for e in events]
        assert "failed" in types


    def test_cancelled_event_written(self, service: JobService):
        """A 'cancelled' event should be written on cancellation."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request,
            ["python", "-c", "import time; time.sleep(30)"],
        )
        time.sleep(0.3)
        service.cancel_job(job_id)

        events = service.get_job_events(job_id)
        types = [e.type for e in events]
        assert "cancelled" in types


    def test_events_jsonl_format(self, service: JobService, jobs_root: Path):
        """Events should be valid JSONL (one JSON object per line)."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(request, ["python", "-c", "print('hi')"])
        service.wait_job(job_id)

        events_path = jobs_root / job_id / "events.jsonl"
        assert events_path.exists()

        raw = events_path.read_text(encoding="utf-8")
        for line in raw.splitlines():
            line = line.strip()
            if line:
                # Each line must be valid JSON
                parsed = json.loads(line)
                assert "seq" in parsed
                assert "type" in parsed
                assert "payload" in parsed


# ============================================================================
# 6. Stop flag mechanism
# ============================================================================


class TestStopFlag:
    def test_stop_flag_created_on_cancel(self, service: JobService):
        """Cancelling a job should create a stop.flag file."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request,
            ["python", "-c", "import time; time.sleep(30)"],
        )
        time.sleep(0.3)
        service.cancel_job(job_id)

        flag_path = service.jobs_root / job_id / "stop.flag"
        assert flag_path.exists()


    def test_cancellation_token_detects_flag(self, tmp_path: Path):
        """CancellationToken should detect when stop.flag exists."""
        job_dir = tmp_path / "test_job"
        job_dir.mkdir(parents=True)

        token = CancellationToken(str(job_dir))
        assert not token.is_cancelled

        # Create the flag
        token.cancel()
        assert token.is_cancelled
        assert (job_dir / "stop.flag").exists()


    def test_cancellation_token_initial_state(self, tmp_path: Path):
        """CancellationToken should return False when no flag exists."""
        job_dir = tmp_path / "noflag_job"
        job_dir.mkdir(parents=True)
        token = CancellationToken(str(job_dir))
        assert not token.is_cancelled


# ============================================================================
# 7. State transition validation
# ============================================================================


class TestStateTransitions:
    def test_valid_transitions(self):
        """All documented valid transitions should be permitted."""
        valid_pairs = [
            (JobState.QUEUED, JobState.STARTING),
            (JobState.QUEUED, JobState.CANCELLING),
            (JobState.STARTING, JobState.RUNNING),
            (JobState.STARTING, JobState.FAILED),
            (JobState.STARTING, JobState.CANCELLING),
            (JobState.RUNNING, JobState.COMPLETED),
            (JobState.RUNNING, JobState.FAILED),
            (JobState.RUNNING, JobState.CANCELLING),
            (JobState.CANCELLING, JobState.CANCELLED),
            (JobState.CANCELLING, JobState.FAILED),
        ]
        for current, next_state in valid_pairs:
            assert try_transition_state(current, next_state), (
                f"Expected {current.value} → {next_state.value} to be valid"
            )


    def test_invalid_transitions_raise_error(self):
        """Invalid transitions should raise InvalidStateTransition."""
        invalid_pairs = [
            (JobState.COMPLETED, JobState.RUNNING),
            (JobState.FAILED, JobState.RUNNING),
            (JobState.CANCELLED, JobState.RUNNING),
            (JobState.RUNNING, JobState.QUEUED),
            (JobState.QUEUED, JobState.COMPLETED),
            (JobState.COMPLETED, JobState.CANCELLING),
        ]
        for current, next_state in invalid_pairs:
            with pytest.raises(InvalidStateTransition):
                transition_state(current, next_state)


    def test_terminal_states_have_no_outgoing(self):
        """Terminal states should have no valid transitions."""
        for state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
            for target in JobState:
                assert not try_transition_state(state, target), (
                    f"Terminal state {state.value} should not allow → {target.value}"
                )


    def test_transition_returns_next_state(self):
        """transition_state should return the next state on success."""
        result = transition_state(JobState.QUEUED, JobState.STARTING)
        assert result == JobState.STARTING


    def test_invalid_transition_error_message(self):
        """The error message should name the current and attempted states."""
        with pytest.raises(InvalidStateTransition) as exc_info:
            transition_state(JobState.COMPLETED, JobState.RUNNING)
        msg = str(exc_info.value)
        assert "completed" in msg
        assert "running" in msg


# ============================================================================
# 8. Request.json persistence
# ============================================================================


class TestRequestPersistence:
    def test_request_json_written(self, service: JobService):
        """request.json should be written with correct fields."""
        request = JobRequest(
            job_kind="training",
            params={"epochs": 10, "lr": 0.001},
        )
        job_id = service.create_job(request, ["python", "-c", "print('train')"])
        service.wait_job(job_id)

        req_path = service.jobs_root / job_id / "request.json"
        assert req_path.exists()

        data = json.loads(req_path.read_text(encoding="utf-8"))
        assert data["job_id"] == job_id
        assert data["job_kind"] == "training"
        assert data["params"]["epochs"] == 10
        assert data["params"]["lr"] == 0.001


    def test_request_serialization_roundtrip(self):
        """JobRequest JSON serialization should roundtrip correctly."""
        original = JobRequest(job_kind="export", params={"format": "onnx"})
        serialized = original.to_json()
        deserialized = JobRequest.from_json(serialized)
        assert deserialized.job_id == original.job_id
        assert deserialized.job_kind == original.job_kind
        assert deserialized.params == original.params


    def test_job_request_unique_ids(self):
        """Each JobRequest should get a unique job_id."""
        r1 = JobRequest(job_kind="test", params={})
        r2 = JobRequest(job_kind="test", params={})
        assert r1.job_id != r2.job_id
        assert r1.job_id.startswith("job_")


# ============================================================================
# 9. List jobs
# ============================================================================


class TestListJobs:
    def test_list_jobs_returns_all(self, service: JobService):
        """list_jobs should return all created jobs."""
        ids = []
        for i in range(3):
            req = JobRequest(job_kind="test", params={"n": i})
            jid = service.create_job(req, ["python", "-c", f"print({i})"])
            ids.append(jid)

        for jid in ids:
            service.wait_job(jid)

        jobs = service.list_jobs()
        assert len(jobs) == 3

        returned_ids = {j["job_id"] for j in jobs}
        assert returned_ids == set(ids)


    def test_list_jobs_returns_states(self, service: JobService):
        """Each entry in list_jobs should include the current state."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(request, ["python", "-c", "print('hi')"])
        service.wait_job(job_id)

        jobs = service.list_jobs()
        job_info = next(j for j in jobs if j["job_id"] == job_id)
        assert job_info["job_kind"] == "test"
        assert job_info["state"] == "completed"


    def test_list_jobs_empty(self, service: JobService):
        """list_jobs should return an empty list when no jobs exist."""
        assert service.list_jobs() == []


# ============================================================================
# 10. is_terminal helper
# ============================================================================


class TestIsTerminal:
    def test_completed_is_terminal(self, service: JobService):
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(request, ["python", "-c", "print('hi')"])
        service.wait_job(job_id)
        assert service.is_terminal(job_id) is True


    def test_cancelled_is_terminal(self, service: JobService):
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request,
            ["python", "-c", "import time; time.sleep(30)"],
        )
        time.sleep(0.3)
        service.cancel_job(job_id)
        assert service.is_terminal(job_id) is True


# ============================================================================
# 11. write_state / read_state helpers
# ============================================================================


class TestStatePersistenceHelpers:
    def test_write_and_read_state(self, tmp_path: Path):
        state_path = tmp_path / "state.json"
        write_state(state_path, JobState.RUNNING)
        assert read_state(state_path) == JobState.RUNNING


    def test_write_state_overwrite(self, tmp_path: Path):
        state_path = tmp_path / "state.json"
        write_state(state_path, JobState.QUEUED)
        write_state(state_path, JobState.RUNNING)
        assert read_state(state_path) == JobState.RUNNING


    def test_read_state_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_state(tmp_path / "nonexistent.json")


# ============================================================================
# 12. append_event / read_events helpers
# ============================================================================


class TestEventPersistenceHelpers:
    def test_append_and_read_events(self, tmp_path: Path):
        events_path = tmp_path / "events.jsonl"
        e1 = JobEvent(seq=1, type="log", payload={"msg": "hello"})
        e2 = JobEvent(seq=2, type="progress", payload={"pct": 50})

        append_event(events_path, e1)
        append_event(events_path, e2)

        events = read_events(events_path)
        assert len(events) == 2
        assert events[0].seq == 1
        assert events[0].type == "log"
        assert events[1].type == "progress"


    def test_read_events_empty_file(self, tmp_path: Path):
        events_path = tmp_path / "nonexistent.jsonl"
        events = read_events(events_path)
        assert events == []


# ============================================================================
# 13. JobService unknown job
# ============================================================================


class TestJobServiceEdgeCases:
    def test_get_logs_nonexistent_job(self, service: JobService):
        """get_job_logs for an unknown job should return empty strings."""
        stdout, stderr = service.get_job_logs("nonexistent_job")
        assert stdout == ""
        assert stderr == ""

    def test_is_terminal_unknown_job(self, service: JobService):
        """An unknown job should be considered terminal."""
        assert service.is_terminal("nonexistent_job") is True


# ============================================================================
# 14. Popen failure → job listed as FAILED (C1 + C2 regression test)
# ============================================================================


class TestPopenFailure:
    def test_command_not_found_job_listed_as_failed(self, service: JobService):
        """If Popen fails, the job should appear in list_jobs with FAILED state."""
        request = JobRequest(job_kind="test", params={"case": "bad_cmd"})
        with pytest.raises(Exception):
            service.create_job(request, ["__nonexistent_command_xyz__"])

        jobs = service.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == request.job_id
        assert jobs[0]["state"] == "failed"

    def test_command_not_found_state_json_is_failed(
        self, service: JobService
    ):
        """Popen failure should write FAILED to state.json."""
        request = JobRequest(job_kind="test", params={"case": "bad_cmd"})
        with pytest.raises(Exception):
            service.create_job(request, ["__nonexistent_command_xyz__"])

        state = service.get_job_state(request.job_id)
        assert state == JobState.FAILED

    def test_command_not_found_writes_failed_event(
        self, service: JobService
    ):
        """Popen failure should write a 'failed' event (not 'started')."""
        request = JobRequest(job_kind="test", params={"case": "bad_cmd"})
        with pytest.raises(Exception):
            service.create_job(request, ["__nonexistent_command_xyz__"])

        events = service.get_job_events(request.job_id)
        types = [e.type for e in events]
        assert "failed" in types
        assert "started" not in types
        # Verify the error payload was captured
        failed_event = next(e for e in events if e.type == "failed")
        assert "error" in failed_event.payload
        assert "command" in failed_event.payload


# ============================================================================
# 15. Cancel non-existent job must raise (I5 regression test)
# ============================================================================


class TestCancelNonExistentJob:
    def test_cancel_nonexistent_job_raises(self, service: JobService):
        """Cancelling a job that was never created should raise."""
        with pytest.raises(FileNotFoundError, match="No job directory"):
            service.cancel_job("nonexistent_job_id")

    def test_cancel_nonexistent_job_does_not_create_dirs(
        self, service: JobService, jobs_root: Path
    ):
        """Cancelling a non-existent job must NOT create directories."""
        fake_id = "nonexistent_job_abc"
        try:
            service.cancel_job(fake_id)
        except FileNotFoundError:
            pass

        assert not (jobs_root / fake_id).exists()


# ============================================================================
# 16. Process reaping after wait (I4 regression test)
# ============================================================================


class TestProcessReaping:
    def test_wait_reaps_process_entry(self, service: JobService):
        """After wait, the process should be reaped — subsequent wait raises."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request, ["python", "-c", "print('hi')"]
        )
        service.wait_job(job_id)

        # Second wait should raise because the process entry was reaped
        with pytest.raises(ValueError, match="No running process"):
            service.wait_job(job_id)

    def test_cancel_reaps_process_entry(self, service: JobService):
        """After cancel, the process should be reaped — subsequent cancel
        is still idempotent (directory still exists)."""
        request = JobRequest(job_kind="test", params={})
        job_id = service.create_job(
            request,
            ["python", "-c", "import time; time.sleep(30)"],
        )
        time.sleep(0.3)
        service.cancel_job(job_id)

        # Second cancel should not raise — directory still exists on disk
        service.cancel_job(job_id)
        state = service.get_job_state(job_id)
        assert state == JobState.CANCELLED

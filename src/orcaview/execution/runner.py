"""Background execution of a single frozen ORCA job on macOS or Linux."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
import os
from pathlib import Path
import re
from shutil import which
import subprocess
from threading import Condition, Event, Thread
from time import monotonic
from typing import Callable, Optional, Tuple

from ..core.provenance import ArtifactRef, new_id
from ..core.tasks import ErrorInfo, ResourceBudget, TaskEvent
from ..orca.input import InputSnapshot
from ._journal import JOURNAL, OUTPUT_LOG, recover_attempts, write_journal
from ._process import POLL_SECONDS, group_active, terminate_group
from ._workspace import ATTEMPT_METADATA, stage_attempt, verify_attempt_inputs
from .records import AttemptRecord, JobRecord
from .traversal import OrcaPreflight, probe_orca


_NORMAL_TERMINATION = re.compile(rb"[ \t*]*ORCA TERMINATED NORMALLY[ \t*]*")
_THREAD_LIMITS = (
    "OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _positive_seconds(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")


@dataclass
class _Attempt:
    record: AttemptRecord
    snapshot: InputSnapshot
    executable: Optional[Path]
    cancel_requested: Event = field(default_factory=Event)
    events: list = field(default_factory=list)
    interruptible: bool = True
    staged: bool = False
    process: Optional[subprocess.Popen] = None
    log_size: int = 0


class LocalOrcaRunner:
    """Explicit start, ordered event polling, and process-group cancellation."""

    def __init__(
        self,
        root: Path,
        *,
        budget: ResourceBudget,
        preflight: Callable[..., OrcaPreflight] = probe_orca,
        terminate_grace_seconds: float = 0.5,
    ):
        if os.name != "posix":
            raise OSError("Local ORCA execution requires POSIX process groups")
        if not isinstance(budget, ResourceBudget) or not callable(preflight):
            raise ValueError("A ResourceBudget and an ORCA preflight callable are required")
        _positive_seconds(terminate_grace_seconds, "terminate_grace_seconds")
        self.root = Path(root).expanduser().resolve()
        self.budget = budget
        self._preflight = preflight
        self._grace = terminate_grace_seconds
        self._condition = Condition()
        self._attempts = {}
        self._jobs = {}
        self._active = None
        self._unconfirmed = None
        self._closed = False

    def start(
        self,
        snapshot: InputSnapshot,
        executable: Optional[Path],
        *,
        timeout_seconds: Optional[float] = None,
        job_id: Optional[str] = None,
    ) -> AttemptRecord:
        if not isinstance(snapshot, InputSnapshot):
            raise ValueError("A frozen InputSnapshot is required")
        if timeout_seconds is not None:
            _positive_seconds(timeout_seconds, "timeout_seconds")
        if job_id is not None and (not isinstance(job_id, str) or not job_id.strip()):
            raise ValueError("job_id must be a nonempty string")
        job_id = new_id() if job_id is None else job_id
        executable = None if executable is None else Path(executable)
        with self._condition:
            if job_id in self._jobs:
                raise ValueError("Job already exists")
            return self._start(JobRecord(job_id, snapshot, ()), executable, timeout_seconds)

    def retry(self, attempt_id: str, *, timeout_seconds: Optional[float] = None) -> AttemptRecord:
        if timeout_seconds is not None:
            _positive_seconds(timeout_seconds, "timeout_seconds")
        with self._condition:
            source = self._attempts[attempt_id]
            job = self._jobs[source.record.job_id]
            if source.record.state not in ("failed", "cancelled") or attempt_id != job.attempt_ids[-1]:
                raise ValueError("Retry requires the latest failed or cancelled attempt of a job")
            if source.record.error is not None and source.record.error.retryable is False:
                raise ValueError("The recorded error requires a new job configuration")
            timeout = source.record.timeout_seconds if timeout_seconds is None else timeout_seconds
            return self._start(job, source.executable, timeout)

    def _start(
        self, job: JobRecord, executable: Optional[Path], timeout: Optional[float],
    ) -> AttemptRecord:
        if self._closed:
            raise RuntimeError("Runner is closed")
        if self._active is not None:
            raise RuntimeError("This runner already has an active attempt")
        if self._unconfirmed is not None:
            raise RuntimeError(f"Process shutdown is unconfirmed for attempt {self._unconfirmed}")
        attempt_id = new_id()
        record = AttemptRecord(
            job.job_id, attempt_id, self.root / attempt_id, job.snapshot.snapshot_digest,
            self.budget, _now(), timeout_seconds=timeout,
        )
        attempt = _Attempt(record, job.snapshot, executable)
        self._attempts[attempt_id] = attempt
        self._jobs[job.job_id] = replace(job, attempt_ids=job.attempt_ids + (attempt_id,))
        self._active = attempt_id
        self._emit(attempt, "state")
        worker = Thread(target=self._run, args=(attempt,), name=f"orca-{attempt_id[:8]}", daemon=True)
        try:
            worker.start()
        except RuntimeError as exc:
            self._finish(attempt, "failed", ErrorInfo("worker_start_failed", str(exc), True))
            return attempt.record
        return record

    def get(self, attempt_id: str) -> AttemptRecord:
        with self._condition:
            return self._attempts[attempt_id].record

    def get_job(self, job_id: str) -> JobRecord:
        with self._condition:
            return self._jobs[job_id]

    def wait(self, attempt_id: str, timeout: Optional[float] = None) -> AttemptRecord:
        with self._condition:
            attempt = self._attempts[attempt_id]
            if not self._condition.wait_for(lambda: attempt.record.terminal, timeout=timeout):
                raise TimeoutError("Attempt is still active")
            return attempt.record

    def events(
        self, attempt_id: str, *, after_sequence: int = -1, timeout: float = 0,
    ) -> Tuple[TaskEvent, ...]:
        with self._condition:
            attempt = self._attempts[attempt_id]
            offset = max(0, after_sequence + 1)
            if timeout:
                self._condition.wait_for(
                    lambda: len(attempt.events) > offset or attempt.record.terminal, timeout=timeout,
                )
            return tuple(attempt.events[offset:])

    def cancel(self, attempt_id: str) -> bool:
        with self._condition:
            attempt = self._attempts[attempt_id]
            if not attempt.interruptible or attempt.cancel_requested.is_set():
                return False
            attempt.cancel_requested.set()
            attempt.record = replace(attempt.record, state="cancelling")
            self._emit(attempt, "state")
            return True

    def recover(self) -> Tuple[dict, ...]:
        """Read prior evidence without signaling or resubmitting any recorded process."""
        return recover_attempts(self.root)

    def close(self) -> None:
        """Stop accepting work and wait for any active attempt to settle."""
        with self._condition:
            self._closed = True
            active = self._active
            if active is not None:
                self.cancel(active)
        if active is not None:
            self.wait(active)

    def _emit(self, attempt: _Attempt, kind: str) -> None:
        record = attempt.record
        attempt.events.append(TaskEvent(
            record.job_id, record.attempt_id, len(attempt.events), _now(),
            kind, record.state, log=record.output, error=record.error,
        ))
        self._condition.notify_all()

    def _checkpoint(self, attempt: _Attempt, *, running: bool = False, **changes) -> None:
        with self._condition:
            if running and attempt.record.state != "cancelling":
                changes["state"] = "running"
            attempt.record = record = replace(attempt.record, **changes)
            if running and record.state == "running":
                self._emit(attempt, "state")
        write_journal(record)

    def _finish(
        self, attempt: _Attempt, state: str, error: Optional[ErrorInfo] = None, **evidence,
    ) -> None:
        with self._condition:
            if attempt.interruptible and attempt.cancel_requested.is_set():
                state, error = "cancelled", None
            attempt.interruptible = False
            if error is not None and error.code in ("stop_unconfirmed", "orca_version_stop_unconfirmed"):
                self._unconfirmed = attempt.record.attempt_id
            record = replace(attempt.record, state=state, error=error, finished_at=_now(), **evidence)
        if attempt.staged:
            try:
                write_journal(record)
            except OSError as exc:
                refs = (record.output,) if record.output is not None else ()
                record = replace(record, state="needs_review", error=ErrorInfo(
                    "journal_failed", f"Could not retain the final attempt record: {exc}", False, refs,
                ))
        with self._condition:
            attempt.record = record
            self._active = None
            self._emit(attempt, "state")

    def _run(self, attempt: _Attempt) -> None:
        phase = "staging_failed"
        try:
            stage_attempt(self.root, attempt.record.attempt_id, attempt.snapshot)
            attempt.staged = True
            write_journal(attempt.record)
            if attempt.cancel_requested.is_set():
                self._finish(attempt, "cancelled")
                return

            phase = "preflight_failed"
            error, probe = self._check(attempt)
            if error is not None:
                if error.code == "orca_version_stop_unconfirmed":
                    with self._condition:
                        attempt.interruptible = False
                    self._finish(attempt, "needs_review", error)
                else:
                    self._finish(attempt, "failed", error)
                return
            if attempt.cancel_requested.is_set():
                self._finish(attempt, "cancelled")
                return

            phase = "input_integrity"
            verify_attempt_inputs(attempt.record.directory, attempt.snapshot, allowed_metadata=(JOURNAL,))
            if probe.executable_fingerprint is not None and not probe.matches_executable():
                self._finish(attempt, "failed", ErrorInfo(
                    "orca_executable_changed", "ORCA executable changed after preflight", True,
                ))
                return
            phase = "launch_failed"
            if not self._launch(attempt, probe.executable):
                self._finish(attempt, "cancelled")
                return
            phase = "monitor_failed"
            self._monitor(attempt)
        except Exception as exc:
            self._fail_worker(attempt, phase, exc)

    def _check(self, attempt: _Attempt) -> Tuple[Optional[ErrorInfo], Optional[OrcaPreflight]]:
        snapshot = attempt.snapshot
        if (snapshot.spec.cores > self.budget.processes
                or snapshot.estimated_maxcore_mb > self.budget.total_memory_mb):
            return ErrorInfo("resource_budget", "Frozen ORCA settings exceed the resource budget", False), None
        if snapshot.spec.cores > 1 and which("mpirun") is None:
            return ErrorInfo("mpi_missing", "Parallel ORCA requires mpirun on PATH", True), None
        probe = self._preflight(attempt.executable)
        self._checkpoint(attempt, executable=probe.executable, tool_version=probe.version,
                         executable_fingerprint=probe.executable_fingerprint,
                         version_output=probe.version_output)
        if not probe.ready:
            return probe.error or ErrorInfo("preflight_failed", "ORCA preflight did not succeed", True), None
        executable = probe.executable
        if (executable is None or not executable.is_absolute()
                or not executable.is_file() or not os.access(executable, os.X_OK)):
            return ErrorInfo("invalid_executable", "Preflight must resolve an executable absolute path", True), None
        target = snapshot.target_orca_version
        if probe.version is None or not re.fullmatch(re.escape(target) + r"(?:\.[0-9]+)*", probe.version):
            return ErrorInfo("version_mismatch", f"ORCA {target} required, found {probe.version}", True), None
        return None, probe

    def _launch(self, attempt: _Attempt, executable: Path) -> bool:
        directory = attempt.record.directory
        log_path = directory / ATTEMPT_METADATA / OUTPUT_LOG
        env = os.environ.copy()
        env.update(dict.fromkeys(_THREAD_LIMITS, str(self.budget.threads_per_process)))
        with self._condition:
            if attempt.cancel_requested.is_set():
                return False
            with log_path.open("xb") as log:
                output = ArtifactRef(format="orca-output", path_hint=str(log_path))
                attempt.record = replace(attempt.record, output=output)
                process = subprocess.Popen(
                    [str(executable), attempt.snapshot.main_input_path], cwd=directory, env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                attempt.process = process
        self._checkpoint(attempt, running=True, pid=process.pid, process_group=process.pid, started_at=_now())
        return True

    def _log_event(self, attempt: _Attempt) -> None:
        size = Path(attempt.record.output.path_hint).stat().st_size
        if size > attempt.log_size:
            attempt.log_size = size
            with self._condition:
                self._emit(attempt, "log")

    def _monitor(self, attempt: _Attempt) -> None:
        process = attempt.process
        timeout = attempt.record.timeout_seconds
        deadline = None if timeout is None else monotonic() + timeout
        while True:
            self._log_event(attempt)
            code = process.poll()
            with self._condition:
                cancelled = attempt.cancel_requested.is_set()
                timed_out = code is None and deadline is not None and monotonic() >= deadline
                if cancelled or timed_out or code is not None:
                    attempt.interruptible = False
                    break
            attempt.cancel_requested.wait(POLL_SECONDS)

        unfinished_group = code is not None and group_active(process.pid)
        if cancelled or timed_out or unfinished_group:
            if not terminate_group(process, self._grace):
                self._finish(attempt, "needs_review", ErrorInfo(
                    "stop_unconfirmed", "Could not confirm that the process group stopped", False,
                    (attempt.record.output,),
                ), exit_code=process.returncode)
                return

        self._log_event(attempt)
        output, normal = self._final_output(attempt.record.output)
        code = process.returncode
        state, error = self._outcome(cancelled, timed_out, unfinished_group, code, normal, output)
        self._finish(attempt, state, error, output=output, exit_code=code, normal_termination=normal)

    @staticmethod
    def _final_output(output: ArtifactRef) -> Tuple[ArtifactRef, bool]:
        digest = sha256()
        normal = False
        at_line_start = True
        with Path(output.path_hint).open("rb") as log:
            for part in iter(lambda: log.readline(65536), b""):
                digest.update(part)
                complete = part.endswith(b"\n") or len(part) < 65536
                if not normal and at_line_start and complete and _NORMAL_TERMINATION.fullmatch(part.rstrip(b"\r\n")):
                    normal = True
                at_line_start = complete
        return replace(output, sha256=digest.hexdigest()), normal

    @staticmethod
    def _outcome(cancelled, timed_out, unfinished_group, code, normal, output):
        if cancelled:
            return "cancelled", None
        if timed_out:
            return "failed", ErrorInfo("timeout", "ORCA exceeded its execution timeout", True, (output,))
        if unfinished_group:
            return "needs_review", ErrorInfo(
                "lingering_processes", "The driver exited while its process group was still active", False, (output,),
            )
        if code != 0:
            return "failed", ErrorInfo("nonzero_exit", f"ORCA exited with status {code}", True, (output,))
        if not normal:
            return "needs_review", ErrorInfo(
                "missing_termination", "Exit zero with no ORCA normal-termination marker", False, (output,),
            )
        return "succeeded", None

    def _fail_worker(self, attempt: _Attempt, phase: str, exc: Exception) -> None:
        with self._condition:
            cancelled = attempt.cancel_requested.is_set()
            attempt.interruptible = False
        process = attempt.process
        stopped = process is None or terminate_group(process, self._grace)
        output = attempt.record.output
        normal = None
        if stopped and output is not None:
            try:
                output, observed = self._final_output(output)
                normal = observed if process is not None else None
            except OSError:
                pass
        refs = (output,) if output is not None else ()
        if not stopped:
            error = ErrorInfo("stop_unconfirmed", f"Could not confirm shutdown after {phase}: {exc}", False, refs)
            state = "needs_review"
        elif cancelled:
            state, error = "cancelled", None
        else:
            state, error = "failed", ErrorInfo(phase, str(exc) or type(exc).__name__, True, refs)
        self._finish(attempt, state, error, output=output, normal_termination=normal,
                     exit_code=process.returncode if process is not None else None)

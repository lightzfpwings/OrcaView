"""Common envelopes for M4 and M6. Task-specific state belongs to the producer."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from ._validation import Versioned, finite_number, integer, nonempty, require_tuple
from .provenance import ArtifactRef


@dataclass(frozen=True)
class ResourceBudget(Versioned):
    processes: int
    threads_per_process: int
    total_memory_mb: int

    def __post_init__(self):
        for field in ("processes", "threads_per_process", "total_memory_mb"):
            integer(getattr(self, field), field, 1)

    @property
    def total_threads(self) -> int:
        return self.processes * self.threads_per_process


@dataclass(frozen=True)
class ErrorInfo(Versioned):
    code: str
    reason: str
    retryable: Optional[bool] = None
    evidence: Tuple[ArtifactRef, ...] = ()

    def __post_init__(self):
        nonempty(self.code, "Error code")
        nonempty(self.reason, "Error reason")
        if self.retryable is not None and type(self.retryable) is not bool:
            raise ValueError("retryable must be a boolean or None")
        require_tuple(self.evidence, "Error evidence")
        if any(not isinstance(item, ArtifactRef) for item in self.evidence):
            raise ValueError("Error evidence must use an ArtifactRef")


@dataclass(frozen=True)
class TaskEvent(Versioned):
    task_id: str
    attempt_id: Optional[str]
    sequence: int
    timestamp: datetime
    kind: str
    stage: str
    progress: Optional[float] = None
    log: Optional[ArtifactRef] = None
    error: Optional[ErrorInfo] = None

    def __post_init__(self):
        for label in ("task_id", "kind", "stage"):
            nonempty(getattr(self, label), label)
        if self.attempt_id is not None:
            nonempty(self.attempt_id, "attempt_id")
        integer(self.sequence, "Event sequence number", 0)
        if not isinstance(self.timestamp, datetime) or self.timestamp.utcoffset() is None:
            raise ValueError("The event timestamp must include a time zone")
        if self.progress is not None and not 0 <= finite_number(self.progress, "Progress") <= 1:
            raise ValueError("Progress must be in [0, 1]")
        if self.log is not None and not isinstance(self.log, ArtifactRef):
            raise ValueError("The log reference must be an ArtifactRef")
        if self.error is not None and not isinstance(self.error, ErrorInfo):
            raise ValueError("Errors must use ErrorInfo")

    def check_after(self, previous: "TaskEvent") -> None:
        if ((self.task_id, self.attempt_id) != (previous.task_id, previous.attempt_id)
                or self.sequence <= previous.sequence):
            raise ValueError("Event sequence numbers must increase strictly within a task attempt")

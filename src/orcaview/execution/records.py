"""Versioned records consumed by the workspace and result importer."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from ..core._validation import Versioned
from ..core.provenance import ArtifactRef
from ..core.tasks import ErrorInfo, ResourceBudget
from ..orca.input import InputSnapshot


TERMINAL_STATES = frozenset(("succeeded", "failed", "cancelled", "needs_review"))


@dataclass(frozen=True)
class JobRecord(Versioned):
    job_id: str
    snapshot: InputSnapshot
    attempt_ids: Tuple[str, ...]


@dataclass(frozen=True)
class AttemptRecord(Versioned):
    job_id: str
    attempt_id: str
    directory: Path
    snapshot_digest: str
    budget: ResourceBudget
    created_at: datetime
    timeout_seconds: Optional[float] = None
    state: str = "preparing"
    executable: Optional[Path] = None
    executable_fingerprint: Optional[Tuple[int, int, int, int, int]] = None
    tool_version: Optional[str] = None
    version_output: Optional[str] = None
    pid: Optional[int] = None
    process_group: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    normal_termination: Optional[bool] = None
    output: Optional[ArtifactRef] = None
    error: Optional[ErrorInfo] = None

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

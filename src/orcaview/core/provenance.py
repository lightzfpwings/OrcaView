"""Immutable source records. Paths are hints and never trigger implicit I/O."""

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import re
from typing import Optional, Tuple
from uuid import uuid4

from ._validation import Versioned, nonempty, require_tuple


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class ArtifactRef(Versioned):
    format: str
    path_hint: Optional[str] = None
    sha256: Optional[str] = None
    artifact_id: str = field(default_factory=new_id)

    def __post_init__(self):
        nonempty(self.artifact_id, "artifact_id")
        nonempty(self.format, "format")
        if self.path_hint is not None:
            nonempty(self.path_hint, "path_hint")
        if self.sha256 is not None and (
            not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.sha256)
        ):
            raise ValueError("sha256 must be a 64-character lowercase hexadecimal digest")

    @classmethod
    def from_bytes(cls, data: bytes, format: str, path_hint: Optional[str] = None):
        return cls(format=format, path_hint=path_hint, sha256=sha256(data).hexdigest())

    @classmethod
    def from_file(cls, path: Path, format: str):
        path = Path(path)
        digest = sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return cls(format=format, path_hint=str(path.resolve()), sha256=digest.hexdigest())


@dataclass(frozen=True)
class Provenance(Versioned):
    kind: str
    producer: Optional[str] = None
    producer_version: Optional[str] = None
    parents: Tuple[ArtifactRef, ...] = ()
    parameters: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self):
        nonempty(self.kind, "Source type")
        for label in ("producer", "producer_version"):
            if getattr(self, label) is not None:
                nonempty(getattr(self, label), label)
        require_tuple(self.parents, "Source files")
        for parent in self.parents:
            if not isinstance(parent, ArtifactRef):
                raise ValueError("Source files must be ArtifactRef objects")
        if len({p.artifact_id for p in self.parents}) != len(self.parents):
            raise ValueError("Source file IDs must be unique")
        require_tuple(self.parameters, "Source parameters")
        keys = set()
        for pair in self.parameters:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("Source parameters must be (name, value) pairs")
            key, value = pair
            nonempty(key, "Parameter name")
            if key in keys or not isinstance(value, str):
                raise ValueError("Source parameters require unique names and string values")
            keys.add(key)

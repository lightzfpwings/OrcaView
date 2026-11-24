"""Versioned scalar and array payloads shared by import, analysis and display."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
import math
import mmap
import os
from pathlib import Path
import struct
import tempfile
from typing import Optional, Tuple, Union

from ._validation import Versioned, finite_number, identifiers, integer, nonempty, require_tuple
from .provenance import ArtifactRef, Provenance, new_id
from .snapshots import GeometryRef, GeometrySnapshot


Number = Union[float, int]


@dataclass(frozen=True)
class DatasetAxis(Versioned):
    kind: str
    ids: Optional[Tuple[str, ...]] = None

    def __post_init__(self):
        nonempty(self.kind, "Axis type")
        if self.ids is not None:
            identifiers(self.ids, "Axis ID")
        elif self.kind in ("atom", "orbital", "mode", "state", "spin"):
            raise ValueError(f"The {self.kind} axis requires ordered identities")


@dataclass(frozen=True)
class ResultDataset(Versioned):
    kind: str
    geometry: GeometryRef
    provenance: Provenance
    dtype: str
    shape: Tuple[int, ...]
    unit: str
    values: Optional[Tuple[Optional[Number], ...]] = None
    axes: Tuple[DatasetAxis, ...] = ()
    array_ref: Optional[ArtifactRef] = None
    missing_reason: Optional[str] = None
    method: Optional[str] = None
    density: Optional[str] = None
    spin: Optional[str] = None
    state_id: Optional[str] = None
    quality: Tuple[str, ...] = ()
    data_version: int = 1
    dataset_id: str = field(default_factory=new_id)

    def __post_init__(self):
        nonempty(self.dataset_id, "dataset_id")
        nonempty(self.kind, "Data type")
        integer(self.data_version, "Data type version", 1)
        if not isinstance(self.geometry, GeometryRef) or not isinstance(self.provenance, Provenance):
            raise ValueError("The result must reference a geometry and provenance")
        nonempty(self.unit, "Unit")
        if self.dtype not in ("float64", "int64"):
            raise ValueError("Supported result dtypes are float64 and int64")
        require_tuple(self.shape, "shape")
        require_tuple(self.axes, "Axis")
        if len(self.axes) != len(self.shape):
            raise ValueError("The number of axes must match the rank of the shape")
        for size, axis in zip(self.shape, self.axes):
            integer(size, "Dimension", 1)
            if not isinstance(axis, DatasetAxis) or (axis.ids is not None and len(axis.ids) != size):
                raise ValueError("Axis identities do not match the shape")
        for label in ("method", "density", "spin", "state_id", "missing_reason"):
            if getattr(self, label) is not None:
                nonempty(getattr(self, label), label)
        identifiers(self.quality, "Quality notes")

        if self.array_ref is not None:
            if (not isinstance(self.array_ref, ArtifactRef) or self.array_ref.format != "raw-le"
                    or self.array_ref.sha256 is None):
                raise ValueError("An external array requires a raw-le file and a SHA-256 digest")
            if self.values is not None or self.missing_reason is not None:
                raise ValueError("An external array cannot also declare inline values or missing data")
        elif self.values is None:
            if self.missing_reason is None:
                raise ValueError("A missing result payload must include a reason")
        else:
            require_tuple(self.values, "Result values")
            if len(self.values) != math.prod(self.shape):
                raise ValueError("The number of result values does not match the shape")
            if (None in self.values) != (self.missing_reason is not None):
                raise ValueError("Missing values and their reasons must be declared together")
            if self.dtype == "float64":
                values = tuple(None if v is None else finite_number(v, "Result values") for v in self.values)
                object.__setattr__(self, "values", values)
            else:
                for value in self.values:
                    if value is not None and (type(value) is not int or not -2**63 <= value < 2**63):
                        raise ValueError("The result is outside the int64 range or has an incompatible type")

    @property
    def valid_mask(self) -> Optional[Tuple[bool, ...]]:
        """Row-major mask for inline values. Whole missing and external payloads have no inline mask."""
        if self.values is None:
            return None
        return tuple(value is not None for value in self.values)

    def validate_geometry(self, snapshot: GeometrySnapshot) -> None:
        if self.geometry != snapshot.ref:
            raise ValueError("The result refers to a different geometry")
        if not snapshot.atom_ids:
            raise ValueError("A molecule requires at least one atom")
        atoms = set(snapshot.atom_ids)
        for axis in self.axes:
            if axis.kind == "atom" and not atoms.issuperset(axis.ids):
                raise ValueError("The result axis contains atom IDs absent from this geometry")

    @contextmanager
    def open_array(self, path: Path):
        """Yield a verified, read-only mapping. Release borrowed buffers before leaving the block."""
        if self.array_ref is None:
            raise ValueError("The dataset has no external array")
        size = math.prod(self.shape) * 8
        digest = sha256()
        # A private copy stays immutable even if the source is edited or replaced.
        with Path(path).open("rb") as source, tempfile.TemporaryFile() as owned:
            if os.fstat(source.fileno()).st_size != size:
                raise ValueError("The external array byte count does not match its dtype and shape")
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                if owned.tell() + len(chunk) > size or len(chunk) % 8:
                    raise ValueError("The external array length has changed")
                if self.dtype == "float64" and any(not math.isfinite(v) for (v,) in struct.iter_unpack("<d", chunk)):
                    raise ValueError("The external array contains nonfinite numbers")
                digest.update(chunk)
                owned.write(chunk)
            if owned.tell() != size or digest.hexdigest() != self.array_ref.sha256:
                raise ValueError("The external array differs from its recorded SHA-256 digest or size")
            owned.flush()
            with mmap.mmap(owned.fileno(), size, access=mmap.ACCESS_READ) as mapping:
                yield mapping

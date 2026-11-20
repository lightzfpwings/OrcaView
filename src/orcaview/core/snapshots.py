"""Immutable geometries, atom ordering and selection for a single document."""

from dataclasses import dataclass, field
from hashlib import sha256
from struct import pack
from typing import Optional, Tuple

from ._validation import Versioned, identifiers, integer, nonempty
from .elements import ATOMIC_NUMBERS
from .models import Molecule
from .provenance import Provenance, new_id
from .units import LENGTH_UNITS, convert_length


@dataclass(frozen=True)
class GeometryRef(Versioned):
    document_id: str
    revision: int
    frame_id: Optional[str] = None
    snapshot_id: str = field(default_factory=new_id)

    def __post_init__(self):
        nonempty(self.document_id, "document_id")
        nonempty(self.snapshot_id, "snapshot_id")
        integer(self.revision, "revision", 1)
        if self.frame_id is not None:
            nonempty(self.frame_id, "frame_id")


@dataclass(frozen=True)
class GeometrySnapshot(Versioned):
    ref: GeometryRef
    molecule: Molecule
    atom_ids: Tuple[str, ...]
    provenance: Provenance
    parent: Optional[GeometryRef] = None
    source_unit: str = "angstrom"
    content_hash: str = field(init=False)

    def __post_init__(self):
        if not isinstance(self.ref, GeometryRef) or not isinstance(self.molecule, Molecule):
            raise ValueError("几何快照需要 GeometryRef 和 Molecule")
        if self.parent is not None and not isinstance(self.parent, GeometryRef):
            raise ValueError("父几何必须是 GeometryRef")
        if not isinstance(self.provenance, Provenance) or self.source_unit not in LENGTH_UNITS:
            raise ValueError("需要有效的几何来源和源长度单位")
        self.molecule.validate_structure()
        integer(self.molecule.charge, "总电荷")
        integer(self.molecule.multiplicity, "自旋多重度", 1)
        identifiers(self.atom_ids, "原子 ID")
        if len(self.atom_ids) != len(self.molecule.atoms):
            raise ValueError("原子 ID 数目必须与坐标行数相同")
        digest = sha256(b"orcaview/geometry/1/angstrom\0")
        for atom in self.molecule.atoms:
            # Canonical binary64, big endian. Normalize the two IEEE zeroes.
            digest.update(pack(">Bddd", ATOMIC_NUMBERS[atom.element],
                               atom.x or 0.0, atom.y or 0.0, atom.z or 0.0))
        object.__setattr__(self, "content_hash", digest.hexdigest())

    def id_at(self, index: int) -> str:
        integer(index, "原子索引", 0)
        if index >= len(self.atom_ids):
            raise ValueError("原子索引越界")
        return self.atom_ids[index]

    def index_of(self, atom_id: str) -> int:
        try:
            return self.atom_ids.index(atom_id)
        except ValueError as exc:
            raise ValueError("当前快照不存在该原子 ID") from exc

    def coordinates(self, unit: str = "angstrom") -> Tuple[Tuple[float, ...], ...]:
        return tuple(tuple(convert_length(v, "angstrom", unit) for v in (a.x, a.y, a.z))
                     for a in self.molecule.atoms)


@dataclass(frozen=True)
class SelectionContext(Versioned):
    geometry: GeometryRef
    atom_ids: Tuple[str, ...]
    mode: str = "atom"

    def __post_init__(self):
        if not isinstance(self.geometry, GeometryRef):
            raise ValueError("选择必须绑定实际几何")
        identifiers(self.atom_ids, "选择的原子 ID")
        nonempty(self.mode, "选择模式")

    @property
    def atom_set(self):
        return frozenset(self.atom_ids)

    def indices(self, snapshot: GeometrySnapshot) -> Tuple[int, ...]:
        if snapshot.ref != self.geometry:
            raise ValueError("选择与快照的几何引用不一致")
        lookup = {atom_id: i for i, atom_id in enumerate(snapshot.atom_ids)}
        try:
            return tuple(lookup[atom_id] for atom_id in self.atom_ids)
        except KeyError as exc:
            raise ValueError("选择包含未知原子 ID") from exc

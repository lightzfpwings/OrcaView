"""Immutable geometries, atom ordering and selection for a single document."""

from dataclasses import dataclass, field, replace
from hashlib import sha256
from struct import pack
from typing import Optional, Tuple

from ._validation import Versioned, finite_number, identifiers, integer, nonempty, require_tuple
from .elements import ATOMIC_NUMBERS
from .geometry import display_bonds
from .models import Molecule
from .provenance import Provenance, new_id
from .units import LENGTH_UNITS, convert_length


SketchCoordinates = Tuple[Tuple[float, float], ...]


def validate_sketch_xy(points: SketchCoordinates) -> None:
    require_tuple(points, "2D sketch coordinates")
    for point in points:
        require_tuple(point, "2D sketch coordinates")
        if len(point) != 2:
            raise ValueError("Each atom in the sketch needs two coordinates.")
        for value in point:
            finite_number(value, "2D sketch coordinates")


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
    sketch_xy: Optional[SketchCoordinates] = None
    content_hash: str = field(init=False)

    def __post_init__(self):
        if not isinstance(self.ref, GeometryRef) or not isinstance(self.molecule, Molecule):
            raise ValueError("A geometry snapshot requires a GeometryRef and a Molecule")
        if self.parent is not None and not isinstance(self.parent, GeometryRef):
            raise ValueError("The parent geometry must be a GeometryRef")
        if not isinstance(self.provenance, Provenance) or self.source_unit not in LENGTH_UNITS:
            raise ValueError("A valid geometry source and source length unit are required")
        self.molecule.validate_structure(allow_empty=self.ref.frame_id is None)
        integer(self.molecule.charge, "Total charge")
        integer(self.molecule.multiplicity, "Spin multiplicity", 1)
        identifiers(self.atom_ids, "Atom ID")
        if len(self.atom_ids) != len(self.molecule.atoms):
            raise ValueError("The number of atom IDs must equal the number of coordinate rows")
        if self.sketch_xy is not None:
            validate_sketch_xy(self.sketch_xy)
            if len(self.sketch_xy) != len(self.atom_ids) or self.ref.frame_id is not None:
                raise ValueError("Sketch positions must match the atoms in an editable revision, in order.")
        digest = sha256(b"orcaview/geometry/1/angstrom\0")
        for atom in self.molecule.atoms:
            # Canonical binary64, big endian. Normalize the two IEEE zeroes.
            digest.update(pack(">Bddd", ATOMIC_NUMBERS[atom.element],
                               atom.x or 0.0, atom.y or 0.0, atom.z or 0.0))
        object.__setattr__(self, "content_hash", digest.hexdigest())

    def id_at(self, index: int) -> str:
        integer(index, "Atom index", 0)
        if index >= len(self.atom_ids):
            raise ValueError("Atom index out of range")
        return self.atom_ids[index]

    def index_of(self, atom_id: str) -> int:
        try:
            return self.atom_ids.index(atom_id)
        except ValueError as exc:
            raise ValueError("This snapshot does not contain the atom ID") from exc

    def coordinates(self, unit: str = "angstrom") -> Tuple[Tuple[float, ...], ...]:
        return tuple(tuple(convert_length(v, "angstrom", unit) for v in (a.x, a.y, a.z))
                     for a in self.molecule.atoms)

    def sketch_molecule(self) -> Molecule:
        """Draw the depiction with connectivity from the physical geometry."""
        if self.sketch_xy is None:
            return self.molecule
        atoms = tuple(replace(atom, x=x, y=y) for atom, (x, y) in zip(self.molecule.atoms, self.sketch_xy))
        return replace(self.molecule, atoms=atoms, bonds=display_bonds(self.molecule), bonds_explicit=True)

    def remap_sketch(self, molecule: Molecule, atom_ids: Tuple[Optional[str], ...]) -> Optional[SketchCoordinates]:
        """Keep drawing positions by identity; new rows start at their own XY."""
        if self.sketch_xy is None or not any(atom_id is not None for atom_id in atom_ids):
            return None
        by_id = dict(zip(self.atom_ids, self.sketch_xy))
        return tuple(by_id.get(atom_id, (atom.x, atom.y)) for atom_id, atom in zip(atom_ids, molecule.atoms))


@dataclass(frozen=True)
class SelectionContext(Versioned):
    geometry: GeometryRef
    atom_ids: Tuple[str, ...]
    mode: str = "atom"

    def __post_init__(self):
        if not isinstance(self.geometry, GeometryRef):
            raise ValueError("The selection must reference an actual geometry")
        identifiers(self.atom_ids, "Selected atom IDs")
        nonempty(self.mode, "Selection mode")

    @property
    def atom_set(self):
        return frozenset(self.atom_ids)

    def indices(self, snapshot: GeometrySnapshot) -> Tuple[int, ...]:
        if snapshot.ref != self.geometry:
            raise ValueError("The selection and snapshot reference different geometries")
        lookup = {atom_id: i for i, atom_id in enumerate(snapshot.atom_ids)}
        try:
            return tuple(lookup[atom_id] for atom_id in self.atom_ids)
        except KeyError as exc:
            raise ValueError("The selection contains unknown atom IDs") from exc

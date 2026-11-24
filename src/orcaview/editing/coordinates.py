"""Ordered internal coordinates and explicit-set distance edits, without Qt.

Lengths use Å and angles use degrees.  For a dihedral A-B-C-D, project B→A
and C→D onto the plane normal to B→C.  Its signed angle is
atan2((B→C unit × first projection) · second projection,
      first projection · second projection), normalized to [-180, 180).
Collinear angle arms give 0/180 degrees; a dihedral with a collinear defining
plane (sine <= 1e-12) is undefined and rejected.
"""

from dataclasses import dataclass, replace
import math
from typing import Optional, Tuple

from orcaview.core._validation import Versioned, finite_number, identifiers
from orcaview.core.models import Atom, Molecule
from orcaview.core.snapshots import GeometryRef, GeometrySnapshot


_ARITY = {"distance": 2, "angle": 3, "dihedral": 4}


@dataclass(frozen=True)
class CoordinateDefinition(Versioned):
    """A versioned coordinate tied to one exact geometry and ordered stable IDs.

    ``unit=None`` chooses ``angstrom`` for distance and ``degree`` for angles.
    The IDs are interpreted only in ``geometry``; the same row numbers or
    document/revision numbers in a different snapshot never imply identity.
    """

    geometry: GeometryRef
    kind: str
    atom_ids: Tuple[str, ...]
    unit: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.geometry, GeometryRef):
            raise ValueError("The coordinate definition must reference a complete GeometryRef")
        if not isinstance(self.kind, str) or self.kind not in _ARITY:
            raise ValueError("Supported coordinate types are distance, angle and dihedral")
        identifiers(self.atom_ids, "Coordinate definition atom IDs")
        if len(self.atom_ids) != _ARITY[self.kind]:
            raise ValueError("The number of ordered atom IDs does not match the coordinate type")
        expected = "angstrom" if self.kind == "distance" else "degree"
        if self.unit is None:
            object.__setattr__(self, "unit", expected)
        elif self.unit != expected:
            raise ValueError("Distances must use angstrom and angles must use degree")


def _points(snapshot: GeometrySnapshot, definition: CoordinateDefinition):
    if not isinstance(snapshot, GeometrySnapshot) or not isinstance(definition, CoordinateDefinition):
        raise ValueError("Coordinate operations require a GeometrySnapshot and CoordinateDefinition")
    if snapshot.ref != definition.geometry:
        raise ValueError("The coordinate definition refers to a different geometry")
    return tuple(snapshot.molecule.atoms[snapshot.index_of(i)] for i in definition.atom_ids)


def _vector(first: Atom, second: Atom):
    return tuple(finite_number(b - a, "Coordinate difference")
                 for a, b in zip((first.x, first.y, first.z), (second.x, second.y, second.z)))


def _dot(first, second):
    return sum(a * b for a, b in zip(first, second))


def _cross(first, second):
    a, b, c = first
    d, e, f = second
    return b * f - c * e, c * d - a * f, a * e - b * d


def _unit(vector, label):
    scale = finite_number(max(abs(v) for v in vector), label)
    if scale == 0:
        raise ValueError(label + " is zero. Coincident atoms cannot define this coordinate")
    # Scaling first keeps normalization accurate for subnormal components and
    # avoids an overflowing norm for large, individually finite components.
    scaled = tuple(v / scale for v in vector)
    length = math.hypot(*scaled)
    return tuple(v / length for v in scaled)


def measure(snapshot: GeometrySnapshot, definition: CoordinateDefinition) -> float:
    """Measure in the definition's unit; reject missing IDs or degenerate planes."""
    points = _points(snapshot, definition)
    if definition.kind == "distance":
        # Zero distance is a defined measurement, but not a direction for editing.
        return finite_number(math.hypot(*_vector(points[0], points[1])), "Distance")
    if definition.kind == "angle":
        first = _unit(_vector(points[1], points[0]), "First angle arm")
        second = _unit(_vector(points[1], points[2]), "Second angle arm")
        return math.degrees(math.atan2(math.hypot(*_cross(first, second)), _dot(first, second)))
    axis = _unit(_vector(points[1], points[2]), "Central dihedral bond")
    first = _unit(_vector(points[1], points[0]), "First dihedral arm")
    second = _unit(_vector(points[2], points[3]), "Last dihedral arm")
    first_normal = _cross(axis, first)
    second_normal = _cross(axis, second)
    if min(math.hypot(*first_normal), math.hypot(*second_normal)) <= 1e-12:
        raise ValueError("Collinear or nearly collinear atoms do not define a dihedral plane")
    first_normal = _unit(first_normal, "First dihedral plane")
    second_normal = _unit(second_normal, "Second dihedral plane")
    value = math.degrees(math.atan2(_dot(_cross(axis, first_normal), second_normal),
                                    _dot(first_normal, second_normal)))
    return (value + 180.0) % 360.0 - 180.0


def edit_distance(snapshot: GeometrySnapshot, definition: CoordinateDefinition,
                  target: float, moving_atom_ids: Tuple[str, ...],
                  fixed_atom_ids: Tuple[str, ...] = ()) -> Molecule:
    """Translate exactly the supplied moving set, holding all other atoms fixed.

    For ordered A-B, A must be outside and B inside the moving set.  No bonds,
    rings or disconnected fragments are traversed to guess that set. Explicit
    fixed IDs assert that those atoms cannot move; they must be disjoint from
    the moving set. Bonds and the electronic state are retained, with no claim
    that the resulting structure satisfies chemical constraints or is relaxed.
    """
    points = _points(snapshot, definition)
    if definition.kind != "distance":
        raise ValueError("This edit requires a distance definition")
    target = finite_number(target, "Target distance")
    if target <= 0:
        raise ValueError("The target distance must be greater than zero.")
    identifiers(moving_atom_ids, "Moving atom IDs")
    identifiers(fixed_atom_ids, "Fixed atom IDs")
    known = set(snapshot.atom_ids)
    moving, fixed = set(moving_atom_ids), set(fixed_atom_ids)
    if not moving.issubset(known) or not fixed.issubset(known):
        raise ValueError("The moving or fixed set contains unknown atom IDs")
    if moving.intersection(fixed):
        raise ValueError("The fixed and moving sets must be disjoint")
    if definition.atom_ids[0] in moving or definition.atom_ids[1] not in moving:
        raise ValueError("For an ordered distance, the first atom must be fixed and the second must be in the moving set")
    vector = _vector(points[0], points[1])
    direction = _unit(vector, "Original distance")
    original = math.hypot(*vector)
    delta = tuple((target - original) * v for v in direction)
    atoms = tuple(
        Atom(atom.element, *(finite_number(c + d, "Edited coordinates")
                             for c, d in zip((atom.x, atom.y, atom.z), delta)))
        if atom_id in moving else atom
        for atom_id, atom in zip(snapshot.atom_ids, snapshot.molecule.atoms)
    )
    actual = math.hypot(*_vector(atoms[snapshot.index_of(definition.atom_ids[0])],
                                 atoms[snapshot.index_of(definition.atom_ids[1])]))
    if not math.isclose(actual, target, rel_tol=1e-10, abs_tol=0.0):
        raise ValueError("The coordinate precision does not allow this distance. The edit was not applied.")
    molecule = replace(snapshot.molecule, atoms=atoms)
    molecule.validate_structure()
    return molecule


def bond_moving_atoms(snapshot, definition, bonds):
    """Return the moving component after cutting the selected bridge bond."""
    fixed, moving = (snapshot.index_of(i) for i in definition.atom_ids)
    neighbors = [set() for _ in snapshot.atom_ids]
    for bond in bonds:
        neighbors[bond.a].add(bond.b)
        neighbors[bond.b].add(bond.a)
    if moving not in neighbors[fixed]:
        raise ValueError("The selected atoms are not directly bonded. Their distance is shown for measurement only.")
    neighbors[moving].remove(fixed)
    neighbors[fixed].remove(moving)
    component = {moving}
    pending = [moving]
    while pending:
        i = pending.pop()
        for neighbor in neighbors[i] - component:
            if neighbor == fixed:
                raise ValueError("You can only measure the length of a bond within a ring.")
            component.add(neighbor)
            pending.append(neighbor)
    return tuple(snapshot.atom_ids[i] for i in sorted(component))

"""Immutable M2 edit requests. Coordinates are in angstrom, angles in degrees."""

from dataclasses import dataclass
from typing import ClassVar, Optional, Tuple, Union

from orcaview.core._validation import Versioned, identifiers, integer, nonempty, require_tuple, finite_number
from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.models import Atom, Bond, validate_bond_style
from orcaview.core.snapshots import GeometryRef, SketchCoordinates, validate_sketch_xy

from .coordinates import CoordinateDefinition


@dataclass(frozen=True)
class AddHydrogen(Versioned):
    """Attach one explicit hydrogen by a single bond to the named atom."""

    anchor_id: str
    kind: ClassVar[str] = "add-hydrogen"

    def __post_init__(self):
        nonempty(self.anchor_id, "Atom ID")


@dataclass(frozen=True)
class AddHydrogens(Versioned):
    """Append a complete set of missing hydrogens prepared for this revision."""

    attachments: Tuple[Tuple[str, Atom], ...]
    perceived_bonds: Optional[Tuple[Bond, ...]] = None
    kind: ClassVar[str] = "add-hydrogens"

    def __post_init__(self):
        require_tuple(self.attachments, "Added hydrogen atoms")
        if not self.attachments:
            raise ValueError("No hydrogens could be added automatically to this structure.")
        for parent, atom in self.attachments:
            nonempty(parent, "Atom ID")
            if not isinstance(atom, Atom) or atom.element != "H":
                raise ValueError("Automatic hydrogen addition can only append H atoms.")
            atom.validate()
        if self.perceived_bonds is not None:
            require_tuple(self.perceived_bonds, "Perceived bond orders")
            if any(not isinstance(bond, Bond) for bond in self.perceived_bonds):
                raise ValueError("Open Babel could not construct this bond graph.")


@dataclass(frozen=True)
class SetSketchLayout(Versioned):
    """Replace only the drawing positions, in the base revision's atom order."""

    xy: SketchCoordinates
    kind: ClassVar[str] = "set-sketch-layout"

    def __post_init__(self):
        validate_sketch_xy(self.xy)


@dataclass(frozen=True)
class MoveSketchAtom(Versioned):
    atom_id: str
    x: float
    y: float
    kind: ClassVar[str] = "move-sketch-atom"

    def __post_init__(self):
        nonempty(self.atom_id, "Atom ID")
        finite_number(self.x, "2D sketch coordinates")
        finite_number(self.y, "2D sketch coordinates")


@dataclass(frozen=True)
class OptimizeCoordinates(Versioned):
    """Apply a force-field conformer calculated for the exact base revision."""

    method: str
    coordinates: Tuple[Tuple[float, float, float], ...]
    perceived_bonds: Optional[Tuple[Bond, ...]] = None
    kind: ClassVar[str] = "optimize-coordinates"

    def __post_init__(self):
        if self.method not in ("MMFF94", "UFF"):
            raise ValueError("Unknown structure optimization method.")
        if self.perceived_bonds is not None:
            require_tuple(self.perceived_bonds, "Perceived bond orders")
            if any(not isinstance(b, Bond) for b in self.perceived_bonds):
                raise ValueError("The optimization returned an invalid bond graph.")
        require_tuple(self.coordinates, "Optimized coordinates")
        for xyz in self.coordinates:
            require_tuple(xyz, "Atomic coordinates")
            if len(xyz) != 3:
                raise ValueError("Each atom requires three coordinates.")
            for value in xyz:
                finite_number(value, "Atomic coordinates")


@dataclass(frozen=True)
class AddAtoms(Versioned):
    """Append atoms; existing explicit bonds stay unchanged, no bonds are guessed."""

    atoms: Tuple[Atom, ...]
    kind: ClassVar[str] = "add-atoms"

    def __post_init__(self):
        require_tuple(self.atoms, "Added atoms")
        if not self.atoms:
            raise ValueError("At least one new atom is required")
        for atom in self.atoms:
            if not isinstance(atom, Atom):
                raise ValueError("New atoms must be Atom objects")
            atom.validate()


@dataclass(frozen=True)
class AttachAtom(Versioned):
    """Place a new atom and connect it to an existing atom in one revision."""

    anchor_id: str
    atom: Atom
    order: int
    style: str = "plain"
    kind: ClassVar[str] = "attach-atom"

    def __post_init__(self):
        nonempty(self.anchor_id, "Atom ID")
        if not isinstance(self.atom, Atom):
            raise ValueError("New atoms must be Atom objects")
        self.atom.validate()
        validate_bond_style(self.order, self.style)


@dataclass(frozen=True)
class InsertRing(Versioned):
    """Place a planar carbon-ring sketch, detached at a center or bonded to one atom."""

    size: int
    benzene: bool
    plane: str
    center: Optional[Tuple[float, float, float]] = None
    anchor_id: Optional[str] = None
    kind: ClassVar[str] = "insert-ring"

    def __post_init__(self):
        integer(self.size, "Ring size", 3)
        if self.size > 8 or type(self.benzene) is not bool or (self.benzene and self.size != 6):
            raise ValueError("Choose a 3- to 8-membered carbon ring or a benzene ring.")
        if self.plane not in ("XY", "XZ", "YZ"):
            raise ValueError("Choose the XY, XZ or YZ projection plane.")
        if (self.anchor_id is None) == (self.center is None):
            raise ValueError("Choose a ring center or an attachment atom.")
        if self.anchor_id is not None:
            nonempty(self.anchor_id, "Atom ID")
        else:
            require_tuple(self.center, "Ring center")
            if len(self.center) != 3:
                raise ValueError("The ring center requires three coordinates.")
            for value in self.center:
                finite_number(value, "Atomic coordinates")


@dataclass(frozen=True)
class DeleteAtoms(Versioned):
    atom_ids: Tuple[str, ...]
    kind: ClassVar[str] = "delete-atoms"

    def __post_init__(self):
        identifiers(self.atom_ids, "Deleted atom IDs")
        if not self.atom_ids:
            raise ValueError("Select at least one atom to delete")


@dataclass(frozen=True)
class ReplaceElement(Versioned):
    """Change one nucleus's element while retaining its editing identity."""

    atom_id: str
    element: str
    kind: ClassVar[str] = "replace-element"

    def __post_init__(self):
        nonempty(self.atom_id, "Atom ID")
        if not isinstance(self.element, str) or self.element not in ATOMIC_NUMBERS:
            raise ValueError("Unsupported element symbol")


@dataclass(frozen=True)
class MoveAtom(Versioned):
    atom_id: str
    x: float
    y: float
    z: float
    kind: ClassVar[str] = "move-atom"

    def __post_init__(self):
        nonempty(self.atom_id, "Atom ID")
        for coordinate in (self.x, self.y, self.z):
            finite_number(coordinate, "Atomic coordinates")


@dataclass(frozen=True)
class SetBond(Versioned):
    """Set the bond order between two stable atom IDs, or remove it with zero."""

    atom_a: str
    atom_b: str
    order: int
    style: str = "plain"
    kind: ClassVar[str] = "set-bond"

    def __post_init__(self):
        identifiers((self.atom_a, self.atom_b), "Bond endpoint")
        integer(self.order, "Bond order", 0)
        if self.order > 3:
            raise ValueError("Bond order must be 0, 1, 2 or 3.")
        if self.order:
            validate_bond_style(self.order, self.style)
        elif self.style != "plain":
            raise ValueError("The bond style does not match the selected bond order.")


@dataclass(frozen=True)
class ReorderAtoms(Versioned):
    atom_ids: Tuple[str, ...]
    kind: ClassVar[str] = "reorder-atoms"

    def __post_init__(self):
        identifiers(self.atom_ids, "Reordered atom IDs")


@dataclass(frozen=True)
class SetElectronicState(Versioned):
    """Explicitly supplied state; an incompatible state remains a flagged draft."""

    charge: int
    multiplicity: int
    kind: ClassVar[str] = "set-electronic-state"

    def __post_init__(self):
        integer(self.charge, "Total charge")
        integer(self.multiplicity, "Spin multiplicity", 1)


@dataclass(frozen=True)
class SetDistance(Versioned):
    coordinate: CoordinateDefinition
    target: float
    moving_atom_ids: Tuple[str, ...]
    fixed_atom_ids: Tuple[str, ...] = ()
    kind: ClassVar[str] = "set-distance"

    def __post_init__(self):
        if not isinstance(self.coordinate, CoordinateDefinition) or self.coordinate.kind != "distance":
            raise ValueError("A distance edit requires a distance coordinate definition")
        if finite_number(self.target, "Target distance") <= 0:
            raise ValueError("The target distance must be greater than zero.")
        identifiers(self.moving_atom_ids, "Moving atom IDs")
        identifiers(self.fixed_atom_ids, "Fixed atom IDs")


@dataclass(frozen=True)
class SetBondLength(SetDistance):
    """Rigidly translate one side of a bridge bond and retain its connectivity."""

    kind: ClassVar[str] = "set-bond-length"


@dataclass(frozen=True)
class UseResultGeometry(Versioned):
    source: GeometryRef
    kind: ClassVar[str] = "use-result-geometry"

    def __post_init__(self):
        if not isinstance(self.source, GeometryRef):
            raise ValueError("The restore target must be a complete GeometryRef")


EditOperation = Union[AddAtoms, AddHydrogen, AddHydrogens, AttachAtom, DeleteAtoms, InsertRing, MoveAtom,
                      MoveSketchAtom, SetSketchLayout, OptimizeCoordinates,
                      ReorderAtoms, ReplaceElement, SetBond, SetDistance, SetElectronicState, UseResultGeometry]


@dataclass(frozen=True)
class GeometryEditCommand(Versioned):
    expected: GeometryRef
    operation: EditOperation

    def __post_init__(self):
        if not isinstance(self.expected, GeometryRef) or self.expected.frame_id is not None:
            raise ValueError("The edit command must reference the complete editable revision")
        if type(self.operation) not in (AddAtoms, AddHydrogen, AddHydrogens, AttachAtom, DeleteAtoms, InsertRing, MoveAtom,
                                       MoveSketchAtom, SetSketchLayout, OptimizeCoordinates, ReorderAtoms, ReplaceElement, SetBond, SetBondLength,
                                       SetDistance, SetElectronicState, UseResultGeometry):
            raise ValueError("Unsupported edit operation")
        if isinstance(self.operation, SetDistance) and self.operation.coordinate.geometry != self.expected:
            raise ValueError("The coordinate definition must reference the command's base revision")

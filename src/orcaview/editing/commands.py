"""Immutable M2 edit requests. Coordinates are in angstrom, angles in degrees."""

from dataclasses import dataclass
from typing import ClassVar, Tuple, Union

from orcaview.core._validation import Versioned, identifiers, integer, nonempty, require_tuple, finite_number
from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.models import Atom
from orcaview.core.snapshots import GeometryRef

from .coordinates import CoordinateDefinition


@dataclass(frozen=True)
class AddAtoms(Versioned):
    """Append atoms; existing explicit bonds stay unchanged, no bonds are guessed."""

    atoms: Tuple[Atom, ...]
    kind: ClassVar[str] = "add-atoms"

    def __post_init__(self):
        require_tuple(self.atoms, "新增原子")
        if not self.atoms:
            raise ValueError("至少需要一个新增原子")
        for atom in self.atoms:
            if not isinstance(atom, Atom):
                raise ValueError("新增原子必须是 Atom")
            atom.validate()


@dataclass(frozen=True)
class DeleteAtoms(Versioned):
    atom_ids: Tuple[str, ...]
    kind: ClassVar[str] = "delete-atoms"

    def __post_init__(self):
        identifiers(self.atom_ids, "删除的原子 ID")
        if not self.atom_ids:
            raise ValueError("至少选择一个待删除原子")


@dataclass(frozen=True)
class ReplaceElement(Versioned):
    """Change one nucleus's element while retaining its editing identity."""

    atom_id: str
    element: str
    kind: ClassVar[str] = "replace-element"

    def __post_init__(self):
        nonempty(self.atom_id, "原子 ID")
        if not isinstance(self.element, str) or self.element not in ATOMIC_NUMBERS:
            raise ValueError("不支持的元素符号")


@dataclass(frozen=True)
class ReorderAtoms(Versioned):
    atom_ids: Tuple[str, ...]
    kind: ClassVar[str] = "reorder-atoms"

    def __post_init__(self):
        identifiers(self.atom_ids, "重排的原子 ID")


@dataclass(frozen=True)
class SetElectronicState(Versioned):
    """Explicitly supplied state; an incompatible state remains a flagged draft."""

    charge: int
    multiplicity: int
    kind: ClassVar[str] = "set-electronic-state"

    def __post_init__(self):
        integer(self.charge, "总电荷")
        integer(self.multiplicity, "自旋多重度", 1)


@dataclass(frozen=True)
class SetDistance(Versioned):
    coordinate: CoordinateDefinition
    target: float
    moving_atom_ids: Tuple[str, ...]
    fixed_atom_ids: Tuple[str, ...] = ()
    kind: ClassVar[str] = "set-distance"

    def __post_init__(self):
        if not isinstance(self.coordinate, CoordinateDefinition) or self.coordinate.kind != "distance":
            raise ValueError("距离编辑需要 distance 坐标定义")
        if finite_number(self.target, "目标距离") <= 0:
            raise ValueError("目标距离必须大于零")
        identifiers(self.moving_atom_ids, "移动原子 ID")
        identifiers(self.fixed_atom_ids, "固定原子 ID")


EditOperation = Union[AddAtoms, DeleteAtoms, ReplaceElement, ReorderAtoms,
                      SetElectronicState, SetDistance]


@dataclass(frozen=True)
class GeometryEditCommand(Versioned):
    expected: GeometryRef
    operation: EditOperation

    def __post_init__(self):
        if not isinstance(self.expected, GeometryRef) or self.expected.frame_id is not None:
            raise ValueError("编辑命令必须绑定可编辑修订的完整引用")
        if type(self.operation) not in (AddAtoms, DeleteAtoms, ReplaceElement, ReorderAtoms,
                                       SetElectronicState, SetDistance):
            raise ValueError("不支持的编辑操作")
        if isinstance(self.operation, SetDistance) and self.operation.coordinate.geometry != self.expected:
            raise ValueError("坐标定义必须绑定命令的基准修订")

"""Immutable M2 edit requests. Coordinates are in angstrom, angles in degrees."""

from dataclasses import dataclass
from typing import ClassVar, Optional, Tuple, Union

from orcaview.core._validation import Versioned, identifiers, integer, nonempty, require_tuple, finite_number
from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.models import Atom, Bond, validate_bond_style
from orcaview.core.snapshots import GeometryRef

from .coordinates import CoordinateDefinition


@dataclass(frozen=True)
class AddHydrogen(Versioned):
    """Attach one explicit hydrogen by a single bond to the named atom."""

    anchor_id: str
    kind: ClassVar[str] = "add-hydrogen"

    def __post_init__(self):
        nonempty(self.anchor_id, "原子 ID")


@dataclass(frozen=True)
class AddHydrogens(Versioned):
    """Append a complete set of missing hydrogens prepared for this revision."""

    attachments: Tuple[Tuple[str, Atom], ...]
    perceived_bonds: Optional[Tuple[Bond, ...]] = None
    kind: ClassVar[str] = "add-hydrogens"

    def __post_init__(self):
        require_tuple(self.attachments, "新增氢原子")
        if not self.attachments:
            raise ValueError("当前结构没有可自动补加的氢原子。")
        for parent, atom in self.attachments:
            nonempty(parent, "原子 ID")
            if not isinstance(atom, Atom) or atom.element != "H":
                raise ValueError("补氢操作只能添加氢原子")
            atom.validate()
        if self.perceived_bonds is not None:
            require_tuple(self.perceived_bonds, "感知键级")
            if any(not isinstance(bond, Bond) for bond in self.perceived_bonds):
                raise ValueError("Open Babel 无法建立当前连接表")


@dataclass(frozen=True)
class OptimizeCoordinates(Versioned):
    """Apply coordinates calculated for the command's exact base revision."""

    method: str
    coordinates: Tuple[Tuple[float, float, float], ...]
    perceived_bonds: Optional[Tuple[Bond, ...]] = None
    kind: ClassVar[str] = "optimize-coordinates"

    def __post_init__(self):
        if self.method not in ("gen2D", "MMFF94", "UFF"):
            raise ValueError("未知的结构优化方法")
        if self.perceived_bonds is not None:
            require_tuple(self.perceived_bonds, "感知键级")
            if any(not isinstance(b, Bond) for b in self.perceived_bonds):
                raise ValueError("优化返回的连接表无效")
        require_tuple(self.coordinates, "优化坐标")
        for xyz in self.coordinates:
            require_tuple(xyz, "原子坐标")
            if len(xyz) != 3:
                raise ValueError("每个原子需要三个坐标")
            for value in xyz:
                finite_number(value, "原子坐标")


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
class AttachAtom(Versioned):
    """Place a new atom and connect it to an existing atom in one revision."""

    anchor_id: str
    atom: Atom
    order: int
    style: str = "plain"
    kind: ClassVar[str] = "attach-atom"

    def __post_init__(self):
        nonempty(self.anchor_id, "原子 ID")
        if not isinstance(self.atom, Atom):
            raise ValueError("新增原子必须是 Atom")
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
        integer(self.size, "环大小", 3)
        if self.size > 8 or type(self.benzene) is not bool or (self.benzene and self.size != 6):
            raise ValueError("请选择 3 至 8 元碳环或苯环")
        if self.plane not in ("XY", "XZ", "YZ"):
            raise ValueError("请选择 XY、XZ 或 YZ 投影平面")
        if (self.anchor_id is None) == (self.center is None):
            raise ValueError("请选择环中心或连接原子")
        if self.anchor_id is not None:
            nonempty(self.anchor_id, "原子 ID")
        else:
            require_tuple(self.center, "环中心")
            if len(self.center) != 3:
                raise ValueError("环中心需要三个坐标")
            for value in self.center:
                finite_number(value, "原子坐标")


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
class MoveAtom(Versioned):
    atom_id: str
    x: float
    y: float
    z: float
    kind: ClassVar[str] = "move-atom"

    def __post_init__(self):
        nonempty(self.atom_id, "原子 ID")
        for coordinate in (self.x, self.y, self.z):
            finite_number(coordinate, "原子坐标")


@dataclass(frozen=True)
class SetBond(Versioned):
    """Set the bond order between two stable atom IDs, or remove it with zero."""

    atom_a: str
    atom_b: str
    order: int
    style: str = "plain"
    kind: ClassVar[str] = "set-bond"

    def __post_init__(self):
        identifiers((self.atom_a, self.atom_b), "键端点")
        integer(self.order, "键级", 0)
        if self.order > 3:
            raise ValueError("键级必须为 0、1、2 或 3")
        if self.order:
            validate_bond_style(self.order, self.style)
        elif self.style != "plain":
            raise ValueError("键型与所选键级不匹配")


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
            raise ValueError("恢复目标必须是完整的 GeometryRef")


EditOperation = Union[AddAtoms, AddHydrogen, AddHydrogens, AttachAtom, DeleteAtoms, InsertRing, MoveAtom, OptimizeCoordinates,
                      ReorderAtoms, ReplaceElement, SetBond, SetDistance, SetElectronicState, UseResultGeometry]


@dataclass(frozen=True)
class GeometryEditCommand(Versioned):
    expected: GeometryRef
    operation: EditOperation

    def __post_init__(self):
        if not isinstance(self.expected, GeometryRef) or self.expected.frame_id is not None:
            raise ValueError("编辑命令必须绑定可编辑修订的完整引用")
        if type(self.operation) not in (AddAtoms, AddHydrogen, AddHydrogens, AttachAtom, DeleteAtoms, InsertRing, MoveAtom,
                                       OptimizeCoordinates, ReorderAtoms, ReplaceElement, SetBond, SetBondLength,
                                       SetDistance, SetElectronicState, UseResultGeometry):
            raise ValueError("不支持的编辑操作")
        if isinstance(self.operation, SetDistance) and self.operation.coordinate.geometry != self.expected:
            raise ValueError("坐标定义必须绑定命令的基准修订")

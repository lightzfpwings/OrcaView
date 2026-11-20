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
            raise ValueError("坐标定义必须绑定完整 GeometryRef")
        if not isinstance(self.kind, str) or self.kind not in _ARITY:
            raise ValueError("坐标类型只支持 distance、angle、dihedral")
        identifiers(self.atom_ids, "坐标定义的原子 ID")
        if len(self.atom_ids) != _ARITY[self.kind]:
            raise ValueError("坐标类型与有序原子 ID 数目不符")
        expected = "angstrom" if self.kind == "distance" else "degree"
        if self.unit is None:
            object.__setattr__(self, "unit", expected)
        elif self.unit != expected:
            raise ValueError("距离单位必须为 angstrom，角度单位必须为 degree")


def _points(snapshot: GeometrySnapshot, definition: CoordinateDefinition):
    if not isinstance(snapshot, GeometrySnapshot) or not isinstance(definition, CoordinateDefinition):
        raise ValueError("坐标操作需要 GeometrySnapshot 和 CoordinateDefinition")
    if snapshot.ref != definition.geometry:
        raise ValueError("坐标定义与实际快照的几何引用不一致")
    return tuple(snapshot.molecule.atoms[snapshot.index_of(i)] for i in definition.atom_ids)


def _vector(first: Atom, second: Atom):
    return tuple(finite_number(b - a, "坐标差")
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
        raise ValueError(label + "为零；重合原子无法定义此坐标")
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
        return finite_number(math.hypot(*_vector(points[0], points[1])), "距离")
    if definition.kind == "angle":
        first = _unit(_vector(points[1], points[0]), "角的第一条边")
        second = _unit(_vector(points[1], points[2]), "角的第二条边")
        return math.degrees(math.atan2(math.hypot(*_cross(first, second)), _dot(first, second)))
    axis = _unit(_vector(points[1], points[2]), "二面角中心键")
    first = _unit(_vector(points[1], points[0]), "二面角第一条边")
    second = _unit(_vector(points[2], points[3]), "二面角最后一条边")
    first_normal = _cross(axis, first)
    second_normal = _cross(axis, second)
    if min(math.hypot(*first_normal), math.hypot(*second_normal)) <= 1e-12:
        raise ValueError("二面角存在共线或近共线原子，无法定义平面")
    first_normal = _unit(first_normal, "二面角第一平面")
    second_normal = _unit(second_normal, "二面角第二平面")
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
        raise ValueError("此编辑操作只接受 distance 定义")
    target = finite_number(target, "目标距离")
    if target <= 0:
        raise ValueError("目标距离必须大于零")
    identifiers(moving_atom_ids, "移动原子 ID")
    identifiers(fixed_atom_ids, "固定原子 ID")
    known = set(snapshot.atom_ids)
    moving, fixed = set(moving_atom_ids), set(fixed_atom_ids)
    if not moving.issubset(known) or not fixed.issubset(known):
        raise ValueError("移动或固定集合包含未知原子 ID")
    if moving.intersection(fixed):
        raise ValueError("固定与移动集合不能重叠")
    if definition.atom_ids[0] in moving or definition.atom_ids[1] not in moving:
        raise ValueError("有序距离的第一端必须固定，第二端必须属于移动集合")
    vector = _vector(points[0], points[1])
    direction = _unit(vector, "原始距离")
    original = math.hypot(*vector)
    delta = tuple((target - original) * v for v in direction)
    atoms = tuple(
        Atom(atom.element, *(finite_number(c + d, "编辑后的坐标")
                             for c, d in zip((atom.x, atom.y, atom.z), delta)))
        if atom_id in moving else atom
        for atom_id, atom in zip(snapshot.atom_ids, snapshot.molecule.atoms)
    )
    actual = math.hypot(*_vector(atoms[snapshot.index_of(definition.atom_ids[0])],
                                 atoms[snapshot.index_of(definition.atom_ids[1])]))
    if not math.isclose(actual, target, rel_tol=1e-10, abs_tol=0.0):
        raise ValueError("浮点坐标无法满足目标距离；未生成编辑结果")
    molecule = replace(snapshot.molecule, atoms=atoms)
    molecule.validate_structure()
    return molecule

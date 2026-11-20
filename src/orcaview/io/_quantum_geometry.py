"""Shared geometry conversions for quantum inputs and text wavefunctions."""

from ..core.elements import ATOMIC_NUMBERS
from ..core.models import Atom, Molecule
from ..core.units import convert_length
from .structure_record import PeriodicStructureError, StructureRecord


_ELEMENT_BY_NUMBER = {number: symbol for symbol, number in ATOMIC_NUMBERS.items()}


def number(value):
    return float(value.replace("D", "E").replace("d", "e"))


def whole(value, field):
    numeric = number(value)
    if not numeric.is_integer():
        raise ValueError(f"{field} 无法用整数表示：{value}")
    return int(numeric)


def atom(label, xyz, unit):
    symbol = _ELEMENT_BY_NUMBER.get(int(label)) if label.lstrip("+-").isdigit() else label.capitalize()
    if symbol not in ATOMIC_NUMBERS or len(xyz) != 3:
        raise ValueError(f"无法识别实原子及三个笛卡尔坐标：{label} {' '.join(xyz)}")
    return Atom(symbol, *(convert_length(number(value), unit, "angstrom") for value in xyz))


def check_periodic(periodic, remove_periodicity):
    if periodic and not remove_periodicity:
        raise PeriodicStructureError("检测到晶胞或平移矢量")


def geometry(name, atoms, unit, charge=0, multiplicity=1, periodic=False):
    if not isinstance(charge, int) or not isinstance(multiplicity, int) or multiplicity < 1:
        raise ValueError("自旋多重度必须大于零")
    molecule = Molecule(name, tuple(atoms), charge=charge, multiplicity=multiplicity)
    molecule.validate_structure()
    return StructureRecord(molecule, source_unit=unit, removed_periodicity=periodic)

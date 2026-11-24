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
        raise ValueError(f"{field} cannot be represented as an integer: {value}")
    return int(numeric)


def atom(label, xyz, unit):
    symbol = _ELEMENT_BY_NUMBER.get(int(label)) if label.lstrip("+-").isdigit() else label.capitalize()
    if symbol not in ATOMIC_NUMBERS or len(xyz) != 3:
        raise ValueError(f"Expected a real atom and three Cartesian coordinates: {label} {' '.join(xyz)}")
    return Atom(symbol, *(convert_length(number(value), unit, "angstrom") for value in xyz))


def check_periodic(periodic, remove_periodicity):
    if periodic and not remove_periodicity:
        raise PeriodicStructureError("Unit cell or translation vectors detected")


def geometry(name, atoms, unit, charge=0, multiplicity=1, periodic=False):
    if not isinstance(charge, int) or not isinstance(multiplicity, int) or multiplicity < 1:
        raise ValueError("Spin multiplicity must be positive.")
    molecule = Molecule(name, tuple(atoms), charge=charge, multiplicity=multiplicity)
    molecule.validate_structure()
    return StructureRecord(molecule, source_unit=unit, removed_periodicity=periodic)

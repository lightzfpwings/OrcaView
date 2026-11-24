"""Read a single XYZ frame without inferring charge or spin from comments."""

import json
from pathlib import Path
import re
from typing import NamedTuple, Tuple, Union

from ..core.models import Atom, Molecule
from ..core.units import convert_length


_METADATA = re.compile(
    r"""(?:^|\s)(?:([\w-]+)\s*=\s*|(?=["']))("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\S*)"""
)
_UNITS = {"angstrom": "angstrom", "angstroms": "angstrom", "å": "angstrom",
          "bohr": "bohr", "a0": "bohr"}


class XYZRecord(NamedTuple):
    molecule: Molecule
    source_unit: str
    unit_source: str


def _source_unit(comment: str) -> Tuple[str, str]:
    unit = None
    for key, raw in _METADATA.findall(comment):
        key, value = key.lower(), raw.strip("'\"").lower()
        if key == "pbc":
            flags = value.split()
            if len(flags) not in (1, 3) or any(flag not in ("f", "false", "0") for flag in flags):
                raise ValueError("The XYZ file contains periodic boundaries or an unrecognized PBC declaration.")
        elif key in ("unit", "units"):
            declared = _UNITS.get(value)
            if declared is None or (unit is not None and unit != declared):
                raise ValueError("Unknown or conflicting XYZ length units")
            unit = declared
        elif key == "lattice" or re.fullmatch(r"k[-_]?points?", key):
            raise ValueError("Molecular XYZ does not support unit cell or k-point metadata.")
    return (unit, "xyz-comment") if unit is not None else ("angstrom", "xyz-default")


def parse_xyz(text: str, name: str = "Molecule") -> Molecule:
    return parse_xyz_record(text, name).molecule


def parse_xyz_record(text: str, name: str = "Molecule") -> XYZRecord:
    """Keep whether the length unit was declared or supplied by the XYZ default."""
    lines = text.splitlines()
    if len(lines) < 2:
        raise ValueError("XYZ must include the atom count and a comment line.")
    try:
        count = int(lines[0].strip())
    except ValueError as exc:
        raise ValueError("The first XYZ line must contain a positive integer atom count.") from exc
    if count <= 0:
        raise ValueError("XYZ atom count must be positive.")
    if len(lines) < count + 2:
        raise ValueError(f"XYZ declares {count} atoms but contains too few coordinate rows.")
    if any(line.strip() for line in lines[count + 2:]):
        raise ValueError("Only a single XYZ frame is supported. Extra content or multiple frames detected.")
    unit, unit_source = _source_unit(lines[1])
    atoms = []
    for index, line in enumerate(lines[2:count + 2], start=3):
        fields = line.split()
        if len(fields) != 4:
            raise ValueError(f"XYZ line {index} must contain an element and three coordinates.")
        try:
            atom = Atom(fields[0], *(convert_length(float(value), unit, "angstrom") for value in fields[1:]))
            atom.validate()
        except ValueError as exc:
            raise ValueError(f"Invalid XYZ line {index}: {exc}") from exc
        atoms.append(atom)
    molecule = Molecule(name=name, atoms=tuple(atoms))
    molecule.validate_structure()
    return XYZRecord(molecule, unit, unit_source)


def load_xyz(path: Union[str, Path]) -> Molecule:
    source = Path(path)
    return parse_xyz(source.read_text(encoding="utf-8"), name=source.stem)


def write_xyz(molecule: Molecule) -> str:
    molecule.validate_structure()
    # Embedded newlines in comments must not change the XYZ frame layout.
    comment = " ".join(molecule.name.splitlines())
    if _METADATA.search(comment):
        comment = "name=" + json.dumps(comment, ensure_ascii=False)
    coordinates = [f"{a.element:<2} {a.x: .10f} {a.y: .10f} {a.z: .10f}" for a in molecule.atoms]
    return "\n".join([str(len(molecule.atoms)), comment, *coordinates]) + "\n"

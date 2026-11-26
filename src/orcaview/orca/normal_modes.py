"""ORCA normal modes in printed atom order, paired with their equilibrium geometry."""

from dataclasses import dataclass
from typing import Tuple

from orcaview.core._validation import finite_number, integer, nonempty
from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.models import Atom
from orcaview.core.units import BOHR_IN_ANGSTROM
from ._native_output import (_AU_ROW, _COORDINATE_HEADING, _XYZ_ROW, _finite, _table,
                             bohr_nuclear_charges)
from .log_spectra import _frequencies, _next_content


@dataclass(frozen=True)
class NormalMode:
    index: int
    frequency: float
    displacements: Tuple[Tuple[float, float, float], ...]
    source_line: int

    def __post_init__(self):
        integer(self.index, "Normal mode number", 0)
        finite_number(self.frequency, "Normal mode frequency")
        integer(self.source_line, "Displacement column heading line", 1)
        for vector in self.displacements:
            if len(vector) != 3:
                raise ValueError("A normal mode requires three displacement components per atom")
            for component in vector:
                finite_number(component, "Normal mode displacement")
        if not any(any(vector) for vector in self.displacements):
            raise ValueError("An animated normal mode needs a nonzero displacement")


@dataclass(frozen=True)
class NormalModeGroup:
    title: str
    atoms: Tuple[Atom, ...]
    modes: Tuple[NormalMode, ...]
    geometry_line: int
    frequency_line: int
    source_line: int

    def __post_init__(self):
        nonempty(self.title, "Normal mode group title")
        for line in (self.geometry_line, self.frequency_line, self.source_line):
            integer(line, "Normal mode source line", 1)
        if not self.geometry_line < self.frequency_line < self.source_line:
            raise ValueError("Invalid normal mode source line order")
        for atom in self.atoms:
            atom.validate()
        if not self.modes or len({m.index for m in self.modes}) != len(self.modes):
            raise ValueError("Normal modes require distinct printed mode numbers")
        if any(len(m.displacements) != len(self.atoms) or m.index >= 3 * len(self.atoms)
               or m.source_line <= self.source_line for m in self.modes):
            raise ValueError("Normal modes do not match their reference geometry or source")


def _reference_atoms(lines, angstrom, bohr):
    """Read the adjacent printed coordinate tables, checking indexed Bohr rows when available."""
    atoms = []
    if angstrom:
        for _, row in _table(lines, angstrom):
            match = _XYZ_ROW.fullmatch(row)
            if not match or match[1] not in ATOMIC_NUMBERS:
                raise ValueError
            atoms.append(Atom(match[1], *map(_finite, match.groups()[1:])))
    elif bohr:
        rows = iter(_table(lines, bohr))
        next(rows, None)  # The shared cross-check below validates the column names.
        for _, row in rows:
            if row.startswith("*"):
                break
            match = _AU_ROW.fullmatch(row)
            if not match or match[2] not in ATOMIC_NUMBERS:
                raise ValueError
            atoms.append(Atom(match[2], *(_finite(v) * BOHR_IN_ANGSTROM for v in match.groups()[4:])))
    if not atoms:
        raise ValueError
    if bohr:
        bohr_nuclear_charges(lines, bohr, atoms)
    return tuple(atoms)


def _read_vectors(lines, header, frequencies, atom_count, offset):
    # Rows are consecutive x/y/z components; column labels are ORCA's mode IDs.
    # ORCA has already applied the mass factor to these Cartesian displacements.
    i = header + 1
    while i < len(lines) and (not lines[i].strip("-= ") or
                              lines[i].startswith(("These modes", "M(i,i)", "Thus,"))):
        i += 1
    dimension = 3 * atom_count
    seen = set()
    modes = []
    while i < len(lines):
        fields = lines[i].split()
        if not fields or not all(field.isascii() and field.isdigit() for field in fields):
            if fields and fields[0].isdigit():  # An extra component row disagrees with atom count.
                raise ValueError
            break
        columns = tuple(map(int, fields))
        if (len(set(columns)) != len(columns) or seen.intersection(columns)
                or any(col >= dimension or col not in frequencies for col in columns)):
            raise ValueError
        seen.update(columns)
        source_line = i + offset + 1
        values = []
        for component in range(dimension):
            i += 1
            fields = lines[i].split() if i < len(lines) else ()
            if len(fields) != len(columns) + 1 or fields[0] != str(component):
                raise ValueError
            values.append(tuple(map(_finite, fields[1:])))
        for col, series in zip(columns, zip(*values)):
            if any(series):
                vectors = tuple(series[j:j + 3] for j in range(0, dimension, 3))
                modes.append(NormalMode(col, frequencies[col], vectors, source_line))
        i += 1
        while i < len(lines) and not lines[i]:
            i += 1
    return tuple(modes)


def parse_normal_modes(section, offset, context):
    """Read one job section without borrowing coordinates or frequencies across jobs."""
    if not any(line.strip().upper() == "NORMAL MODES" for line in section):
        return ()
    lines = [line.strip() for line in section]
    groups = []
    angstrom = bohr = 0
    numerical_reference = frequency_table = None
    for i, line in enumerate(lines):
        heading = _COORDINATE_HEADING.fullmatch(line)
        if heading:
            frequency_table = None
            if heading.lastgroup == "angstrom":
                angstrom, bohr = i + 1, 0
            elif heading.lastgroup == "bohr":
                bohr = i + 1
            else:
                angstrom = bohr = 0
        elif line.upper() == "ORCA NUMERICAL FREQUENCIES":
            # Verbose finite-difference runs may subsequently print displaced structures.
            numerical_reference = (angstrom, bohr) if angstrom or bohr else None
        elif line.upper() == "VIBRATIONAL FREQUENCIES":
            equilibrium = numerical_reference or (angstrom, bohr)
            numerical_reference = None
            start = _next_content(lines, i + 1)
            frequency_table = _frequencies(lines, i, start) if start < len(lines) else None
        elif line.upper() == "NORMAL MODES" and frequency_table and equilibrium:
            try:
                atoms = _reference_atoms(lines, *equilibrium)
                frequencies = dict(frequency_table.rows)
                if len(frequencies) != len(frequency_table.rows):
                    raise ValueError
                modes = _read_vectors(lines, i, frequencies, len(atoms), offset)
                if modes:
                    title = " · ".join(filter(None, (context, "Vibrational frequencies")))
                    groups.append(NormalModeGroup(title, atoms, modes, (equilibrium[0] or equilibrium[1]) + offset,
                                                  frequency_table.source_line + offset, i + offset + 1))
            except ValueError:
                # Keep the frequency and property tables usable on incomplete native outputs.
                pass
            frequency_table = None
    return tuple(groups)

"""Atom-resolved populations printed for one verified ORCA coordinate frame."""

from dataclasses import dataclass
from decimal import Decimal
from math import fsum, isclose
import re

from orcaview.core.elements import ATOMIC_NUMBERS
from ._native_output import (
    _COORDINATE_HEADING, _DASHES, _ELEMENT, _NUMBER, _finite, _table, bohr_nuclear_charges, population_tables,
)


@dataclass(frozen=True)
class PopulationColumn:
    kind: str
    method: str
    line: int
    values: tuple
    parameters: tuple = ()


_METHODS = {"Mulliken": "mulliken", "Löwdin": "loewdin", "Hirshfeld": "hirshfeld"}


def _atom_rows(lines, start, atoms, width):
    rows = []
    for index, atom in enumerate(atoms):
        fields = lines[start + index].split() if start + index < len(lines) else ()
        if len(fields) != width + 2 or fields[:2] != [str(index), atom.element]:
            raise ValueError
        rows.append(tuple(_finite(value) for value in fields[2:]))
    return tuple(zip(*rows))


def _mbis(lines, header, atoms):
    names = lines[header].upper().split()
    columns = _atom_rows(lines, header + 1, atoms, len(names) - 1)
    end = header + 1 + len(atoms)
    while end < len(lines) and not lines[end]:
        end += 1
    totals = lines[end].split() if end < len(lines) else ()
    if len(totals) != len(names) or totals[0].upper() != "TOTAL":
        raise ValueError
    for column, total in zip(columns, totals[1:]):
        if not isclose(fsum(column), _finite(total), abs_tol=(len(atoms) + 1) * 0.5e-6 + 1e-9, rel_tol=0):
            raise ValueError
    return columns


def _chelpg(lines, heading, molecule):
    values = []
    for _, row in _table(lines, heading):
        match = re.fullmatch(rf"(\d+)\s+({_ELEMENT})\s*:\s*({_NUMBER})", row)
        i = len(values)
        if not match or i >= len(molecule.atoms) or int(match[1]) != i or match[2] != molecule.atoms[i].element:
            raise ValueError
        values.append(_finite(match[3]))
    if len(values) != len(molecule.atoms):
        raise ValueError
    end = heading + 1 + len(values)
    if end < len(lines) and _DASHES.fullmatch(lines[end]):
        end += 1
    total = re.fullmatch(rf"Total charge:\s*({_NUMBER})", lines[end], re.I) if end < len(lines) else None
    if not total or not isclose(_finite(total[1]), molecule.charge, rel_tol=0, abs_tol=1e-6):
        raise ValueError
    if not isclose(fsum(values), _finite(total[1]), rel_tol=0, abs_tol=(len(values) + 1) * 0.5e-6 + 1e-9):
        raise ValueError
    return tuple(values)


def population_columns(lines, geometry_line, molecule):
    lines = tuple(line.strip() for line in lines)
    end = next((i for i in range(geometry_line, len(lines))
                if (m := _COORDINATE_HEADING.fullmatch(lines[i])) and m.lastgroup == "angstrom"), len(lines))
    lines = lines[:end]
    tables = list(population_tables(lines, geometry_line, molecule))
    atoms = molecule.atoms
    nuclear = ()
    nuclear_line = None
    mayer = []
    results = []
    mbis_heading = None
    for i in range(geometry_line, len(lines)):
        line = lines[i]
        try:
            if (match := _COORDINATE_HEADING.fullmatch(line)) and match.lastgroup == "bohr":
                nuclear = bohr_nuclear_charges(lines, i + 1, atoms)
                nuclear_line = i + 1
            elif line.split() == ["ATOM", "NA", "ZA", "QA", "VA", "BVA", "FA"]:
                electrons, charges_z, charges_q, *_ = _atom_rows(lines, i + 1, atoms, 6)
                end_row = i + 1 + len(atoms)
                if end_row < len(lines) and re.match(r"\d+\s+[A-Z]", lines[end_row]):
                    continue
                if not all(isclose(z - q, n, rel_tol=0, abs_tol=0.00016)
                           for z, q, n in zip(charges_z, charges_q, electrons)):
                    continue
                if not all(z.is_integer() and 0 < z <= ATOMIC_NUMBERS[a.element] for z, a in zip(charges_z, atoms)):
                    continue
                if nuclear and charges_z != nuclear:
                    continue
                if not isclose(fsum(charges_q), molecule.charge, rel_tol=0, abs_tol=len(atoms) * 0.5e-4 + 1e-9):
                    continue
                mayer.append((i + 1, electrons, charges_q, charges_z))
            elif line == "MBIS ANALYSIS":
                mbis_heading = i + 1
            elif mbis_heading and line.split() in (["ATOM", "CHARGE", "POPULATION", "SPIN"],
                                                    ["ATOM", "CHARGE", "POPULATION"]):
                for kind, values in zip(("charge", "electrons", "spin"), _mbis(lines, i, atoms)):
                    results.append(PopulationColumn("mbis-" + kind, "MBIS", mbis_heading, values))
                mbis_heading = None
            elif line.upper() == "CHELPG CHARGES":
                results.append(PopulationColumn("chelpg-charge", "CHELPG", i + 1, _chelpg(lines, i + 1, molecule)))
        except (ValueError, OverflowError):
            continue

    # Mayer NA is the printed gross Mulliken population. Match its QA to the
    # charge table at the precision actually printed before suppressing a duplicate.
    if not nuclear and mayer and all(row[3] == mayer[0][3] for row in mayer):
        nuclear_line, nuclear = mayer[0][0], mayer[0][3]
    mulliken = [q for method, _, q, _ in tables if method == "Mulliken"]
    def matches(q, other):
        return all(abs(a - b) <= 0.000051 for a, b in zip(q, other))

    for line, electrons, charge, _ in mayer:
        results.append(PopulationColumn("mulliken-electrons", "Mulliken", line, electrons,
                                        (("population_column", "Mayer NA"),)))
        if not any(matches(charge, other) for other in mulliken):
            results.append(PopulationColumn("mulliken-charge", "Mulliken", line, charge,
                                            (("population_column", "Mayer QA"),)))
    for method, line, charges, spins in tables:
        prefix = _METHODS[method]
        results.append(PopulationColumn(prefix + "-charge", method, line, charges))
        if spins:
            results.append(PopulationColumn(prefix + "-spin", method, line, spins))
        if nuclear and (method != "Mulliken" or not any(matches(charges, q) for _, _, q, _ in mayer)):
            electrons = tuple(float(Decimal(int(z)) - Decimal(str(q))) for z, q in zip(nuclear, charges))
            results.append(PopulationColumn(prefix + "-electrons", method, line, electrons,
                                            (("population_formula", "ZA - q"), ("nuclear_charge_line", str(nuclear_line)))))
    return sorted(results, key=lambda c: c.line)

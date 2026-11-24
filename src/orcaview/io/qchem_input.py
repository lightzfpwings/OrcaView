"""Read the explicit Cartesian molecule in a Q-Chem input file."""

import re

from ._quantum_geometry import atom, check_periodic, geometry


def read_qchem_input(path, raw, *, remove_periodicity=False):
    text = raw.decode("utf-8-sig")
    # Q-Chem accepts commas as coordinate separators and '=' in $rem.
    lines = [line.partition("!")[0].strip() for line in text.splitlines()]
    sections = {}
    section = None
    for line in lines:
        tag = line.lower()
        if tag == "@@@":
            raise ValueError("The Q-Chem input contains multiple jobs. Select a single-job file.")
        if tag == "$end":
            section = None
        elif tag.startswith("$"):
            if section is not None or tag in sections:
                raise ValueError("Unclosed or duplicate section in Q-Chem input.")
            sections[tag] = section = []
        elif section is not None and line:
            section.append(line)
    if section is not None or not sections.get("$molecule"):
        raise ValueError("No complete Q-Chem $molecule coordinate section found.")
    unit = "angstrom"
    periodic = any(line.lower().split()[0] in ("ewald", "box_length")
                   for line in sections.get("$forceman", ()))
    for line in sections.get("$rem", ()):
        tokens = line.lower().replace("=", " ").split()
        if tokens and tokens[0] == "ewald_on" and tokens[1:] in (["true"], ["1"]):
            periodic = True
        if tokens and tokens[0] == "input_bohr":
            if len(tokens) != 2 or tokens[1] not in ("true", "false", "1", "0"):
                raise ValueError("Unknown Q-Chem INPUT_BOHR unit setting.")
            unit = "bohr" if tokens[1] in ("true", "1") else "angstrom"
    check_periodic(periodic, remove_periodicity)
    rows = iter(sections["$molecule"])
    state = next(rows)
    if not re.fullmatch(r"[+-]?\d+[\s,]+\d+", state):
        raise ValueError("The Q-Chem file requires an explicit charge, multiplicity and Cartesian coordinates.")
    charge, mult = map(int, state.replace(",", " ").split())
    atoms = []
    for line in rows:
        if line.startswith("--"):
            fragment = next(rows, "")
            if not re.fullmatch(r"[+-]?\d+[\s,]+\d+", fragment):
                raise ValueError("Q-Chem fragment charge or multiplicity is missing.")
            continue
        fields = line.replace(",", " ").split()
        if len(fields) < 4 or any(not re.fullmatch(r"[+-]?\d+", field) for field in fields[4:]):
            raise ValueError("Q-Chem import requires an explicit element and three Cartesian coordinates.")
        atoms.append(atom(fields[0], fields[1:4], unit))
    return geometry(path.stem, atoms, unit, charge, mult, periodic=periodic)

"""Read the nuclear geometry sections of common text wavefunction files."""

import re

from ._quantum_geometry import atom, check_periodic, geometry, whole


def _array_atoms(numbers, coordinates, count, unit):
    if count <= 0 or len(numbers) != count or len(coordinates) != 3 * count:
        raise ValueError("The atom count, element list and number of 3D coordinates in the wavefunction do not match.")
    return [atom(label, coordinates[3*i:3*i + 3], unit) for i, label in enumerate(numbers)]


def _molden(name, text, remove_periodicity):
    if not re.search(r"(?im)^[ \t]*\[molden format\]", text):
        raise ValueError("Missing [Molden Format] header")
    periodic = bool(re.search(r"(?im)^[ \t]*\[(?:cell|unitcell|lattice|spacegroup|frac-coord)\]", text))
    check_periodic(periodic, remove_periodicity)
    section = re.search(r"(?im)^[ \t]*\[atoms\][ \t]*\(?([A-Za-z]+)\)?[ \t]*$", text)
    if section:
        unit = {"angs": "angstrom", "angstrom": "angstrom", "angstroms": "angstrom",
                "au": "bohr", "bohr": "bohr"}.get(section[1].lower())
        if unit is None:
            raise ValueError("Molden [Atoms] length units must be Angs or AU.")
    else:
        section = re.search(r"(?im)^[ \t]*\[fr-coord\][ \t]*$", text)
        if not section:
            raise ValueError("Missing Cartesian geometry in Molden [Atoms] with length units or [FR-COORD].")
        unit = "bohr"
    end = re.compile(r"(?m)^[ \t]*\[").search(text, section.end())
    body = text[section.end():end.start() if end else len(text)]
    atoms = []
    for line in body.splitlines():
        fields = line.split()
        if not fields:
            continue
        if section.lastindex:
            if len(fields) != 6 or int(fields[1]) != len(atoms) + 1:
                raise ValueError("Invalid fields or atom order in a Molden atom record")
            element = fields[2]
        else:
            if len(fields) != 4:
                raise ValueError("Molden vibration geometry requires an element and three coordinates in bohr.")
            element = fields[0]
        atoms.append(atom(element, fields[-3:], unit))
    return geometry(name, atoms, unit, periodic=periodic)


def _fchk_field(text, label, *, optional=False):
    header = re.search(r"(?im)^" + re.escape(label) + r"[ \t]+[IR][ \t]+(N=[ \t]*)?([-+]?\d+)[ \t]*$", text)
    if header is None:
        if optional:
            return None
        raise ValueError(f"Missing valid FCHK field: {label}")
    if not header[1]:
        return int(header[2])
    count = int(header[2])
    values = []
    pos = header.end() + 1
    while len(values) < count and pos < len(text):
        end = text.find("\n", pos)
        end = len(text) if end < 0 else end
        values.extend(text[pos:end].split())
        pos = end + 1
    if len(values) != count:
        raise ValueError(f"FCHK array length mismatch for {label}")
    return values


def _fchk(name, text, remove_periodicity):
    ndim = _fchk_field(text, "Number of translation vectors", optional=True)
    has_vectors = re.search(r"(?im)^Translation vectors[ \t]+R[ \t]+N=[ \t]*[1-9]\d*", text)
    periodic = bool(ndim or has_vectors)
    check_periodic(periodic, remove_periodicity)
    count = _fchk_field(text, "Number of atoms")
    numbers = _fchk_field(text, "Atomic numbers")
    coordinates = _fchk_field(text, "Current cartesian coordinates")
    if not isinstance(count, int) or not isinstance(numbers, list) or not isinstance(coordinates, list):
        raise ValueError("Invalid FCHK geometry field type")
    atoms = _array_atoms(numbers, coordinates, count, "bohr")
    charge = _fchk_field(text, "Charge", optional=True)
    mult = _fchk_field(text, "Multiplicity", optional=True)
    return geometry(name, atoms, "bohr", 0 if charge is None else charge,
                    1 if mult is None else mult, periodic)


def _wfx_tag(text, tag, *, optional=False):
    # WFX is tag-delimited, not XML: its tag names contain spaces.
    start = re.search(r"<" + re.escape(tag) + r">", text, re.I)
    if start is None:
        if optional:
            return None
        raise ValueError(f"Missing WFX element <{tag}>")
    end = re.compile(r"</" + re.escape(tag) + r">", re.I).search(text, start.end())
    if end is None:
        raise ValueError(f"Incomplete WFX element <{tag}>")
    return " ".join(line for line in text[start.end():end.start()].splitlines()
                    if not line.lstrip().startswith("#")).strip()


def _wfx(name, text, remove_periodicity):
    ndim = _wfx_tag(text, "Number of Translation Vectors", optional=True)
    periodic = bool(int(ndim or 0) or re.search(r"<Translation Vectors>", text, re.I))
    check_periodic(periodic, remove_periodicity)
    atoms = _array_atoms(_wfx_tag(text, "Atomic Numbers").split(),
                         _wfx_tag(text, "Nuclear Cartesian Coordinates").split(),
                         int(_wfx_tag(text, "Number of Nuclei")), "bohr")
    charge = whole(_wfx_tag(text, "Net Charge", optional=True) or "0", "WFX net charge")
    multiplicity = _wfx_tag(text, "Electronic Spin Multiplicity", optional=True)
    if multiplicity:
        mult = int(multiplicity)
    else:
        alpha = _wfx_tag(text, "Number of Alpha Electrons", optional=True)
        beta = _wfx_tag(text, "Number of Beta Electrons", optional=True)
        mult = abs(int(alpha) - int(beta)) + 1 if alpha is not None and beta is not None else 1
    return geometry(name, atoms, "bohr", charge, mult, periodic)


def _wfn(name, text):
    header = re.search(r"(?im)^[ \t]*(?:GAUSSIAN|GTO|SLATER|STO)[ \t]+\d+[ \t]+MOL ORBITALS"
                       r"[ \t]+\d+[ \t]+PRIMITIVES[ \t]+(\d+)[ \t]+NUCLEI\b[^\n]*$", text)
    if not header:
        raise ValueError("Missing WFN header with atom and orbital counts")
    count = int(header[1])
    row = re.compile(r"[ \t]*([A-Za-z]{1,2})[ \t]*\d+[ \t]*\([ \t]*CENT(?:RE|ER)[ \t]+(\d+)\)"
                     r"[ \t]*(.*?)[ \t]+CHARGE[ \t]*=[ \t]*\S+[ \t]*$", re.I)
    atoms = []
    pos = header.end() + 1
    for index in range(count):
        end = text.find("\n", pos)
        end = len(text) if end < 0 else end
        match = row.fullmatch(text, pos, end)
        if not match or int(match[2]) != index + 1:
            raise ValueError("Missing WFN nuclear coordinates or invalid center indices")
        # The printed charge may be an effective charge for ECP calculations.
        atoms.append(atom(match[1], match[3].split(), "bohr"))
        pos = end + 1
    return geometry(name, atoms, "bohr")


def _mwfn_field(text, key, default=None):
    match = re.search(r"(?im)^[ \t]*" + key + r"[ \t]*=[ \t]*([^\s#]+)", text)
    if match:
        return match[1]
    if default is not None:
        return default
    raise ValueError(f"Missing mwfn field: {key}")


def _mwfn(name, text, remove_periodicity):
    periodic = bool(int(_mwfn_field(text, "Ndim", "0")) or re.search(r"(?im)^[ \t]*cellv[123][ \t]*=", text))
    check_periodic(periodic, remove_periodicity)
    centers = list(re.finditer(r"(?im)^[ \t]*\$centers[ \t]*$", text))
    if len(centers) != 1:
        raise ValueError("Expected exactly one mwfn $Centers geometry section.")
    count = int(_mwfn_field(text, "Ncenter"))
    pos = centers[0].end() + 1
    atoms = []
    for index in range(count):
        end = text.find("\n", pos)
        end = len(text) if end < 0 else end
        fields = text[pos:end].split()
        if len(fields) != 7 or int(fields[0]) != index + 1:
            raise ValueError("Invalid mwfn center index or coordinates")
        atoms.append(atom(fields[2], fields[-3:], "angstrom"))
        pos = end + 1
    charge = whole(_mwfn_field(text, "Charge", "0"), "mwfn net charge")
    alpha = whole(_mwfn_field(text, "Naelec", "0"), "mwfn α electron count")
    beta = whole(_mwfn_field(text, "Nbelec", "0"), "mwfn β electron count")
    return geometry(name, atoms, "angstrom", charge, abs(alpha - beta) + 1, periodic)


def read_wavefunction(fmt, name, text, remove_periodicity):
    if fmt == "wfn":
        return _wfn(name, text)
    readers = {"molden": _molden, "gaussian-fchk": _fchk, "mwfn": _mwfn, "wfx": _wfx}
    return readers[fmt](name, text, remove_periodicity)

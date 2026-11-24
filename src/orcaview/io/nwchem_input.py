"""Read explicit NWChem geometries, including fractional primitive cells."""

from dataclasses import replace
import math
from pathlib import Path
import re

from ..core.symmetry import _cross, _dot
from ..core.units import convert_length
from ._quantum_geometry import atom, check_periodic, geometry, number, whole


_LENGTHS = {
    "angstrom": ("angstrom", 1.0), "angstroms": ("angstrom", 1.0), "an": ("angstrom", 1.0),
    "au": ("bohr", 1.0), "atomic": ("bohr", 1.0), "bohr": ("bohr", 1.0),
    "nm": ("angstrom", 10.0), "nanometers": ("angstrom", 10.0),
    "pm": ("angstrom", 0.01), "picometers": ("angstrom", 0.01),
}
_SPINS = {name: i for i, name in enumerate(
    ("singlet", "doublet", "triplet", "quartet", "quintet", "sextet", "septet", "octet"), 1
)}


def _input_rows(text):
    # Semicolons are statement separators, even within a physical line. A
    # quoted title or comment must not create a false GEOMETRY statement.
    text = re.sub(r"\\[ \t]*\r?\n", " ", text)
    statements = re.findall(r'''(?:"[^"\n]*"|'[^'\n]*'|[^;#\n'"]+)+|\#[^\n]*''', text)
    return [s.lower().split() for s in statements if s.strip() and not s.startswith("#")]


def _units(name):
    if name not in _LENGTHS:
        raise ValueError(f"Unknown NWChem length unit: {name}")
    return _LENGTHS[name]


def _cell_converter(kind, values):
    if "vectors" in values:
        if kind != "crystal" or len(values) != 1:
            raise ValueError("NWChem lattice_vectors requires exactly one 3D cell definition.")
        a, b, c = values["vectors"]
        volume = _dot(a, _cross(b, c))
        if not math.isfinite(volume) or volume == 0:
            raise ValueError("Invalid cell volume in NWChem lattice_vectors")
        return lambda x, y, z: tuple(x * a[i] + y * b[i] + z * c[i] for i in range(3))
    required = {"polymer": ("lat_c",), "surface": ("lat_a", "lat_b", "gamma"),
                "crystal": ("lat_a", "lat_b", "lat_c", "alpha", "beta", "gamma")}[kind]
    missing = [key for key in required if key not in values]
    if missing:
        raise ValueError("Missing explicit NWChem cell parameters: " + ", ".join(missing))
    for key in required:
        v = values[key]
        if not math.isfinite(v) or v <= 0 or (not key.startswith("lat_") and v >= 180):
            raise ValueError(f"Invalid NWChem cell parameter: {key}={v}")
    if kind == "polymer":
        return lambda x, y, z: (x, y, z * values["lat_c"])
    a, b = values["lat_a"], values["lat_b"]
    gamma = math.radians(values["gamma"])
    bx, by = b * math.cos(gamma), b * math.sin(gamma)
    if kind == "surface":
        return lambda x, y, z: (a * x + bx * y, by * y, z)
    c = values["lat_c"]
    cx = c * math.cos(math.radians(values["beta"]))
    cy = (c * math.cos(math.radians(values["alpha"])) - cx * math.cos(gamma)) / math.sin(gamma)
    cz2 = c * c - cx * cx - cy * cy
    if cz2 <= 0 or not math.isfinite(cz2):
        raise ValueError("NWChem cell angles do not define a nondegenerate 3D cell.")
    cz = math.sqrt(cz2)
    return lambda x, y, z: (a * x + bx * y + cx * z, by * y + cy * z, cz * z)


def _explicit_geometry(rows, unit, scale):
    """Collect atom rows and nested SYSTEM options in either input order."""
    atom_rows, cell = [], {}
    kind, in_system = None, False
    cell_factor = 1.0
    statements = iter(rows)
    for row in statements:
        key = row[0]
        if key == "end":
            if in_system:
                in_system = False
                continue
            return atom_rows, kind, cell
        if key == "system":
            if kind or len(row) not in (2, 4) or row[1] not in ("molecule", "crystal", "polymer", "surface"):
                raise ValueError("Unrecognized NWChem SYSTEM definition")
            kind, in_system = row[1], True
            if len(row) == 4:
                if row[2] != "units":
                    raise ValueError("Unrecognized length unit declaration in NWChem SYSTEM")
                cell_unit, cell_scale = _units(row[3])
                cell_factor = convert_length(cell_scale, cell_unit, unit) / scale
        elif in_system and row == ["lattice_vectors"]:
            vectors = [next(statements, []) for _ in range(3)]
            if "vectors" in cell or any(len(v) != 3 for v in vectors):
                raise ValueError("NWChem lattice_vectors requires three linearly independent 3D vectors.")
            cell["vectors"] = [tuple(number(x) * cell_factor for x in v) for v in vectors]
        elif in_system:
            if len(row) % 2:
                raise ValueError("Missing NWChem cell parameter value")
            for field, value in zip(row[::2], row[1::2]):
                if field not in ("lat_a", "lat_b", "lat_c", "alpha", "beta", "gamma") or field in cell:
                    raise ValueError(f"Unrecognized NWChem cell parameter: {field}")
                cell[field] = number(value) * (cell_factor if field.startswith("lat_") else 1.)
        elif key == "symmetry":
            if len(row) < 2 or row[1] not in ("c1", "p1"):
                raise ValueError("Expand the symmetry-unique NWChem atoms into full coordinates (C1/P1) first.")
        elif key in ("zmatrix", "zcoord", "load"):
            raise ValueError("NWChem requires explicit Cartesian or fractional cell coordinates for real atoms.")
        else:
            match = re.fullmatch(r"([a-z]{1,2})(?:[0-9_-].*)?", key)
            if not match or len(row) < 4:
                raise ValueError("Unrecognized NWChem atom or coordinate row: " + " ".join(row))
            atom_rows.append((match[1], [number(value) for value in row[1:4]]))
    raise ValueError("Missing end in an NWChem GEOMETRY or SYSTEM section")


def _electronic_state(rows):
    charges, spins = set(), set()
    block = None
    for row in rows:
        key = row[0]
        if key in ("scf", "dft", "nwpw"):
            block = key
        elif key == "end":
            block = None
        elif key == "charge" and len(row) == 2:
            charges.add(whole(row[1], "NWChem total charge"))
        elif block in ("dft", "nwpw") and key == "mult" and len(row) == 2:
            spins.add(whole(row[1], "NWChem spin multiplicity"))
        elif block == "scf" and key in _SPINS:
            spins.add(_SPINS[key])
        elif block == "scf" and key == "nopen" and len(row) == 2:
            spins.add(whole(row[1], "NWChem singly occupied orbital count") + 1)
    if len(charges) > 1 or len(spins) > 1:
        raise ValueError("The NWChem input declares multiple charges or spin states. Split the jobs first.")
    return next(iter(charges), 0), next(iter(spins), 1)


def read_nwchem_input(path, raw, *, remove_periodicity=False):
    if b"\0" in raw:
        raise ValueError("Expected a text NWChem input; binary data detected.")
    rows = _input_rows(raw.decode("utf-8-sig"))
    crystal = any(r[0] == "system" and len(r) > 1 and r[1] in ("crystal", "surface", "polymer") for r in rows)
    simulation = any(r[0] == "simulation_cell" for r in rows)
    boundaries = {r[1] for r in rows if r[0] == "boundary_conditions" and len(r) == 2}
    periodic = crystal or (simulation and boundaries != {"aperiodic"})
    check_periodic(periodic, remove_periodicity)
    if len(boundaries) > 1 or boundaries - {"periodic", "aperiodic"}:
        raise ValueError("Could not determine the NWChem simulation cell boundaries. Separate the cells first.")
    headers = [i for i, row in enumerate(rows) if row[0] == "geometry"]
    if len(headers) != 1:
        raise ValueError("The NWChem input requires one explicit GEOMETRY section.")
    header = rows[headers[0]]
    if "ang2au" in header or "angstrom_to_au" in header:
        raise ValueError("Custom NWChem angstrom_to_au conversion factors are unsupported.")
    if "units" in header:
        index = header.index("units") + 1
        unit, scale = _units(header[index] if index < len(header) else "")
    else:
        unit, scale = "angstrom", 1.0
    atom_rows, kind, cell = _explicit_geometry(rows[headers[0] + 1:], unit, scale)
    transform = _cell_converter(kind, cell) if kind in ("crystal", "surface", "polymer") else None
    atoms = []
    for symbol, values in atom_rows:
        xyz = transform(*values) if transform else values
        atoms.append(atom(symbol, [str(v * scale) for v in xyz], unit))
    charge, mult = _electronic_state(rows)
    record = geometry(Path(path).stem, atoms, unit, charge, mult, periodic)
    return replace(record, unit_source=f"nwchem-units-{header[index]}") if scale != 1 else record

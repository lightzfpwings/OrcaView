"""Read scalar and multi-field Gaussian Cube files, including ORCA MO cubes."""

from array import array
from concurrent.futures import CancelledError
from dataclasses import dataclass, replace
from io import BytesIO
import math
from pathlib import Path

from orcaview.core.models import Molecule
from orcaview.core.units import BOHR_IN_ANGSTROM
from orcaview.core.volume_grid import VolumeGrid
from orcaview.io._quantum_geometry import atom


_FORTRAN = bytes.maketrans(b"Dd", b"Ee")


@dataclass(frozen=True)
class CubeField:
    identifier: int
    values: memoryview
    minimum: float
    maximum: float

    def initial_isovalue(self):
        if self.minimum < .05 < self.maximum or self.minimum < -.05 < self.maximum:
            return .05
        # Use the middle of the larger signed range for small or offset scalar fields.
        low, high = ((-self.maximum, -self.minimum) if abs(self.minimum) > abs(self.maximum)
                     else (self.minimum, self.maximum))
        return ((max(0., low)*.5 + high*.5) or high) if high > 0 else .05


@dataclass(frozen=True)
class CubeData:
    molecule: Molecule
    grid: VolumeGrid
    fields: tuple
    comments: tuple
    source_unit: str


def _header(stream, lengths):
    fields = stream.readline().translate(_FORTRAN).split()
    if len(fields) not in lengths:
        raise ValueError("Incomplete Gaussian Cube header.")
    return fields


def _finite(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Cube coordinates and grid values must be finite.")
    return result


def read_cube(path, raw, cancel=None):
    stream = BytesIO(raw)
    comments = tuple(stream.readline().decode("utf-8", errors="replace").strip() for _ in range(2))
    header = _header(stream, (4, 5))
    natoms = int(header[0])
    nval = int(header[4]) if len(header) == 5 else 1
    axes = [_header(stream, (4,)) for _ in range(3)]
    counts = tuple(int(row[0]) for row in axes)
    # Formatted ORCA/Gaussian cubes use bohr. Some other writers use three
    # negative voxel counts to declare angstroms for all spatial coordinates.
    if not (all(n > 0 for n in counts) or all(n < 0 for n in counts)):
        raise ValueError("Cube grid counts must have a consistent sign and be nonzero.")
    unit = "bohr" if counts[0] > 0 else "angstrom"
    factor = BOHR_IN_ANGSTROM if unit == "bohr" else 1.
    origin = tuple(factor*_finite(v) for v in header[1:4])
    steps = tuple(tuple(factor*_finite(v) for v in row[1:]) for row in axes)
    grid = VolumeGrid(tuple(map(abs, counts)), origin, steps)
    atoms = []
    for _ in range(abs(natoms)):
        row = _header(stream, (5,))
        atomic_number = int(row[0])
        _finite(row[1])  # effective nuclear charge, distinct from the element
        if atomic_number == 0:  # dummy centers have no atom to display
            for coord in row[2:]:
                _finite(coord)
            continue
        atoms.append(atom(str(atomic_number), [v.decode("ascii") for v in row[2:]], unit))
    molecule = Molecule(Path(path).stem, tuple(atoms))
    # Cube supplies coordinates and nuclear charges, with no total charge or spin.
    # Use the same neutral input defaults as other structure-only imports.
    if molecule.electron_count % 2:
        molecule = replace(molecule, multiplicity=2)
    molecule.validate_structure(allow_empty=True)
    ids = None
    remainder = ()
    if natoms < 0:
        line = next((row.split() for row in stream if row.strip()), [])
        if not line:
            raise ValueError("Missing Cube dataset IDs.")
        count = int(line[0])
        if count < 1 or nval not in (1, count):
            raise ValueError("Invalid Cube dataset count.")
        tokens = line[1:]
        while len(tokens) < count:
            line = stream.readline()
            if not line:
                raise ValueError("Missing Cube dataset IDs.")
            tokens.extend(line.split())
        ids = tuple(int(v) for v in tokens[:count])
        if len(set(ids)) != count:
            raise ValueError("Cube dataset IDs must be unique.")
        remainder = tokens[count:]
        nval = count
    expected = math.prod(grid.shape)*nval
    if nval < 1 or expected > len(raw):
        raise ValueError("The number of Cube values does not match the declared grid.")
    data = array("d", (float(v.translate(_FORTRAN)) for v in remainder))
    for row, line in enumerate(stream):
        if not row % 256 and cancel is not None and cancel.is_set():
            raise CancelledError()
        data.extend(map(float, line.translate(_FORTRAN).split()))
        if len(data) > expected:
            break
    if len(data) != expected:
        raise ValueError("The number of Cube values does not match the declared grid.")
    if not all(map(math.isfinite, data)):
        raise ValueError("Cube coordinates and grid values must be finite.")
    view = memoryview(data).toreadonly()
    fields = []
    for i, identifier in enumerate(ids if ids is not None else range(1, nval+1)):
        values = view[i::nval]  # the innermost index is the dataset, followed by z
        fields.append(CubeField(identifier, values, min(values), max(values)))
    return CubeData(molecule, grid, tuple(fields), comments, unit)

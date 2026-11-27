"""Open structure files into independent molecular documents; no Qt dependencies."""

from dataclasses import dataclass, replace
from concurrent.futures import CancelledError
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
from tempfile import TemporaryDirectory
from typing import Optional

from orcaview import __version__
from orcaview.application.document import MoleculeDocument
from orcaview.application.session import Session
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.io.babel_structure import BABEL_FORMATS, read_babel_structure
from orcaview.io.cube import CubeData, read_cube
from orcaview.io.molden_orbitals import MoldenOrbitals, read_molden_orbitals
from orcaview.io.nwchem_input import read_nwchem_input
from orcaview.io.qchem_input import read_qchem_input
from orcaview.io.quantum_structure import QUANTUM_FORMATS, read_quantum_structure
from orcaview.io.structure_record import PeriodicStructureError, StructureRecord
from orcaview.orca.gbw import file_state, publish_molden, run_converter
from orcaview.orca.gbw_molden import has_builtin_layout
from orcaview.preferences import read_preferences


_EXTRA_FORMATS = {".qcin": "qchem-input", ".in": "qchem-input", ".input": "quantum-input", ".nw": "nwchem-input",
                  ".nwi": "nwchem-input", ".gbw": "orca-gbw", ".cube": "gaussian-cube", ".cub": "gaussian-cube"}
_FORMATS = {**BABEL_FORMATS, **QUANTUM_FORMATS, **_EXTRA_FORMATS}
_WAVEFUNCTION = {"molden", "gaussian-fchk", "wfn", "wfx", "mwfn", "orca-gbw"}


def structure_format(path, raw=None):
    name = path.name.lower()
    if name in _FORMATS:
        return _FORMATS[name]
    for suffix in sorted(_FORMATS, key=len, reverse=True):
        if suffix.startswith(".") and name.endswith(suffix):
            fmt = _FORMATS[suffix]
            if raw is not None and suffix in (".in", ".inp", ".input"):
                # These extensions are shared by several electronic structure packages.
                content = raw.removeprefix(b"\xef\xbb\xbf")
                for header, candidate in (
                    (rb"^[ \t]*\$molecule[ \t]*\r?$", "qchem-input"),
                    (rb"^[ \t]*(?:\*[ \t]*(?:xyz(?:file)?|int(?:ernal)?)\b|%coords\b)", "orca-input"),
                    (rb"^[ \t]*geometry\b[\s\S]*?(?:^|;)[ \t]*end\b", "nwchem-input"),
                    (rb"^[ \t]*#(?:[pnt]\b|[ \t]+\w)", "gaussian-input"),
                ):
                    if re.search(header, content, re.I | re.M):
                        return candidate
                if fmt == "quantum-input":
                    raise ValueError("Could not identify the quantum chemistry program or an explicit geometry section.")
            return fmt
    raise ValueError(f"Unsupported file type: {path.name}")


def open_file_filters(translate=str):
    def patterns(keys):
        return " ".join("*" + key if key.startswith(".") else f"{key.upper()} {key}" for key in keys)

    structure = patterns(BABEL_FORMATS)
    inputs = patterns(key for key, value in _FORMATS.items()
                      if key not in BABEL_FORMATS and value not in _WAVEFUNCTION and value != "gaussian-cube")
    waves = patterns(key for key, value in _FORMATS.items() if value in _WAVEFUNCTION)
    cubes = patterns(key for key, value in _FORMATS.items() if value == "gaussian-cube")
    groups = (("Supported files", f"{structure} {inputs} {waves} {cubes} *.out *.log *.oview.json"),
              ("Molecular and crystal structures", structure), ("Quantum chemistry input", inputs),
              ("ORCA output and logs", "*.out *.log"), ("Wavefunctions", waves), ("Cube grids", cubes),
              ("OrcaView projects", "*.oview.json"), ("All files", "*"))
    return ";;".join(f"{translate(label)} ({pattern})" for label, pattern in groups)


@dataclass(frozen=True)
class PeriodicFile:
    raw: bytes
    auxiliary: Optional[ArtifactRef] = None


@dataclass(frozen=True)
class OpenedStructure:
    record: StructureRecord
    source: ArtifactRef
    orbitals: Optional[MoldenOrbitals] = None
    orbital_error: str = ""
    cube_grid: Optional[CubeData] = None

    def session(self, calculation):
        record = self.record
        parameters = [("unit_source", record.unit_source)]
        if self.orbitals:
            parameters.append(("molecular_orbitals", str(len(self.orbitals.orbitals))))
        if self.cube_grid:
            parameters.append(("cube_fields", str(len(self.cube_grid.fields))))
            parameters.append(("input_electronic_state", "neutral parity default"))
        if record.polymer_roles:
            parameters.append(("polymer_roles", record.polymer_roles))
        if record.backbone_links is not None:
            parameters.append(("backbone_links", json.dumps(record.backbone_links, separators=(",", ":"))))
        if record.generated_3d:
            parameters.append(("geometry_generation", "Open Babel 3D"))
        if record.removed_periodicity:
            parameters.append(("periodicity", "removed"))
        origin = Provenance("import", "orcaview.structure-import", __version__,
                            (self.source, *record.auxiliary_sources), tuple(parameters))
        document = MoleculeDocument.from_molecule(record.molecule, origin, source_unit=record.source_unit)
        session = Session.from_document(document, calculation, self.source.path_hint)
        session.molden_orbitals = self.orbitals
        session.cube_grid = self.cube_grid
        return session


def find_converter(*, desktop=True):
    name = "orca_2mkl.exe" if os.name == "nt" else "orca_2mkl"
    saved = read_preferences("orca-tools", {"converter": ""})["converter"]
    candidates = [os.environ.get("ORCAVIEW_ORCA_2MKL"), saved]
    for variable in ("ORCADIR", "ORCA_PATH"):
        if os.environ.get(variable):
            directory = Path(os.environ[variable]).expanduser()
            candidates.append((directory.parent if directory.is_file() else directory) / name)
    candidates.append(shutil.which(name))
    orca = shutil.which("orca")
    if orca:
        candidates.append(Path(orca).resolve().with_name(name))
    if desktop:
        candidates.extend([Path.home() / "software/orca" / name, Path("/opt/orca") / name])
        if os.name == "nt":
            candidates.append(Path(os.environ.get("SystemDrive", "C:") + "/orca") / name)
        # A desktop launched outside a shell may not inherit the user's PATH.
        local = list((Path.home() / "software").glob("orca-*/" + name))
        if len(local) == 1:
            candidates.extend(local)
    for item in candidates:
        if item and Path(item).is_file() and os.access(item, os.X_OK):
            return Path(item).resolve()
    return None


def _opened_gbw(path, raw, *, remove_periodicity=False, cancel=None):
    with TemporaryDirectory(prefix="orcaview-gbw-") as directory:
        converter = None if has_builtin_layout(raw) else find_converter(desktop=False)
        output = run_converter(raw, Path(directory), converter, cancel)
        molden = output.read_bytes()
        record = read_quantum_structure(output, molden, remove_periodicity=remove_periodicity)
    record = replace(record, molecule=replace(record.molecule, name=path.stem))
    return _opened_molden(path, molden, record, source=ArtifactRef.from_bytes(raw, "orca-gbw", str(path)))


def _opened_molden(path, raw, record, *, source=None):
    source = source or ArtifactRef.from_bytes(raw, "molden", str(path))
    try:
        orbitals = read_molden_orbitals(raw, record.molecule) if not record.removed_periodicity else None
    except (ValueError, ArithmeticError) as exc:
        # A geometry-only import still works when the orbital dialect is unsupported.
        return OpenedStructure(record, source, orbital_error=str(exc))
    if orbitals:
        record = replace(record, molecule=orbitals.molecule)
    return OpenedStructure(record, source, orbitals)


@dataclass
class PreparedMolden:
    opened: OpenedStructure
    folder: TemporaryDirectory
    staged: Path
    destination: Path
    expected: Optional[tuple]
    gbw: Path
    gbw_state: tuple

    def publish(self):
        try:
            if file_state(self.gbw, follow_links=True) != self.gbw_state:
                raise ValueError("The GBW changed during conversion. Reopen it to convert the current file.")
            publish_molden(self.staged, self.destination, self.expected)
        finally:
            self.folder.cleanup()
        return self.opened


def prepare_gbw_open(path, converter, expected, cancel=None):
    """Stage and validate a sidecar. Only the accepted GUI open request publishes it."""
    path = Path(path).absolute()
    target = path.with_suffix(".molden.input")
    initial = file_state(path, follow_links=True)
    raw = path.read_bytes()
    gbw = ArtifactRef.from_bytes(raw, "orca-gbw", str(path))
    folder = TemporaryDirectory(prefix=".orcaview-gbw-", dir=target.parent)
    try:
        output = run_converter(raw, Path(folder.name), converter, cancel)
        if cancel is not None and cancel.is_set():
            raise CancelledError()
        molden = output.read_bytes()
        record = read_quantum_structure(target, molden)
        opened = _opened_molden(target, molden, replace(record, auxiliary_sources=(gbw,)))
        if opened.orbitals is None:
            raise ValueError(opened.orbital_error or "The converter output contains no molecular orbitals.")
        return PreparedMolden(opened, folder, output, target, expected, path, initial)
    except BaseException:
        folder.cleanup()
        raise


def read_linked_orbitals(source, project_path=None, cancel=None):
    original = Path(source.path_hint)
    candidates = [original]
    name = PureWindowsPath(source.path_hint).name if "\\" in source.path_hint else original.name
    if project_path:
        candidates.append(Path(project_path).parent / name)
    existing = [path for path in dict.fromkeys(candidates) if path.is_file()]
    if not existing:
        raise ValueError(f"Linked orbital file not found: {name}")
    for path in existing:
        if cancel is not None and cancel.is_set():
            raise CancelledError()
        raw = path.read_bytes()
        if ArtifactRef.from_bytes(raw, source.format).sha256 == source.sha256:
            break
    else:
        if source.format == "gaussian-cube":
            raise ValueError("The Cube file has changed since this project was saved. Open the file separately.")
        if source.format == "orca-gbw":
            raise ValueError("The GBW file has changed since this project was saved. Open the file separately.")
        raise ValueError("The Molden file has changed since this project was saved. Open the file separately.")
    if source.format == "gaussian-cube":
        return read_cube(path, raw, cancel)
    if source.format == "orca-gbw":
        opened = _opened_gbw(path, raw, cancel=cancel)
        if opened.orbitals is None:
            raise ValueError(opened.orbital_error or "The converter output contains no molecular orbitals.")
        return opened.orbitals
    molecule = read_quantum_structure(path, raw, format_id="molden").molecule
    wave = read_molden_orbitals(raw, molecule)
    if wave is None:
        raise ValueError("This Molden file contains no molecular orbitals.")
    return wave


def read_structure_file(path, confirmation=None, cancel=None):
    path = Path(path).resolve()
    if not path.is_file() and confirmation is None:
        raise ValueError("Select a regular file.")
    raw = path.read_bytes() if confirmation is None else confirmation.raw
    fmt = structure_format(path, raw)
    if fmt == "gaussian-cube":
        cube = read_cube(path, raw, cancel)
        record = StructureRecord(cube.molecule, source_unit=cube.source_unit)
        return OpenedStructure(record, ArtifactRef.from_bytes(raw, fmt, str(path)), cube_grid=cube)
    strip_cell = confirmation is not None
    try:
        if fmt in BABEL_FORMATS.values():
            record = read_babel_structure(raw, path.stem, fmt, remove_periodicity=strip_cell)
        elif fmt == "qchem-input":
            record = read_qchem_input(path, raw, remove_periodicity=strip_cell)
        elif fmt == "nwchem-input":
            record = read_nwchem_input(path, raw, remove_periodicity=strip_cell)
        elif fmt == "orca-gbw":
            return _opened_gbw(path, raw, remove_periodicity=strip_cell, cancel=cancel)
        else:
            record = read_quantum_structure(path, raw, remove_periodicity=strip_cell, format_id=fmt)
    except PeriodicStructureError as exc:
        if strip_cell:
            raise ValueError("Could not extract a nonperiodic structure from the file.") from exc
        return PeriodicFile(raw, getattr(exc, "source", None))
    if strip_cell and confirmation.auxiliary is not None:
        source = confirmation.auxiliary
        if not any(item.sha256 == source.sha256 and item.path_hint == source.path_hint
                   for item in record.auxiliary_sources):
            raise ValueError("The referenced coordinate file changed during confirmation. Reopen the input file.")
    if fmt == "molden":
        return _opened_molden(path, raw, record)
    return OpenedStructure(record, ArtifactRef.from_bytes(raw, fmt, str(path)))

"""Open structure files into independent molecular documents; no Qt dependencies."""

from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Optional

from orcaview import __version__
from orcaview.application.document import MoleculeDocument
from orcaview.application.session import Session
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.io.babel_structure import BABEL_FORMATS, read_babel_structure
from orcaview.io.nwchem_input import read_nwchem_input
from orcaview.io.qchem_input import read_qchem_input
from orcaview.io.quantum_structure import QUANTUM_FORMATS, read_quantum_structure
from orcaview.io.structure_record import PeriodicStructureError, StructureRecord


_EXTRA_FORMATS = {".qcin": "qchem-input", ".in": "qchem-input", ".input": "quantum-input", ".nw": "nwchem-input",
                  ".nwi": "nwchem-input", ".gbw": "orca-gbw"}
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
                      if key not in BABEL_FORMATS and value not in _WAVEFUNCTION)
    waves = patterns(key for key, value in _FORMATS.items() if value in _WAVEFUNCTION)
    groups = (("Supported files", f"{structure} {inputs} {waves} *.out *.log *.oview.json"),
              ("Molecular and crystal structures", structure), ("Quantum chemistry input", inputs),
              ("ORCA output and logs", "*.out *.log"), ("Wavefunctions", waves),
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

    def session(self, calculation):
        record = self.record
        parameters = [("unit_source", record.unit_source)]
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
        return Session.from_document(document, calculation, self.source.path_hint)


def _gbw_geometry(path, raw, *, remove_periodicity):
    converter = shutil.which("orca_2mkl")
    if not converter:
        orca = shutil.which("orca")
        if orca:
            sibling = Path(orca).resolve().with_name("orca_2mkl" + Path(orca).suffix)
            if sibling.is_file():
                converter = str(sibling)
    if not converter:
        raise ValueError("GBW files require orca_2mkl from a local ORCA installation. You can also open the exported .molden.input file.")
    with TemporaryDirectory(prefix="orcaview-gbw-") as directory:
        work = Path(directory)
        (work / "geometry.gbw").write_bytes(raw)
        try:
            converted = subprocess.run([converter, "geometry", "-molden"], cwd=work,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=120)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("orca_2mkl timed out while converting the GBW file.") from exc
        output = work / "geometry.molden.input"
        if converted.returncode or not output.is_file():
            raise ValueError("orca_2mkl could not convert this GBW file. Check that the ORCA version matches the file.")
        record = read_quantum_structure(output, output.read_bytes(), remove_periodicity=remove_periodicity)
        return replace(record, molecule=replace(record.molecule, name=path.stem))


def read_structure_file(path, confirmation=None):
    path = Path(path).resolve()
    if not path.is_file() and confirmation is None:
        raise ValueError("Select a regular file.")
    raw = path.read_bytes() if confirmation is None else confirmation.raw
    fmt = structure_format(path, raw)
    strip_cell = confirmation is not None
    try:
        if fmt in BABEL_FORMATS.values():
            record = read_babel_structure(raw, path.stem, fmt, remove_periodicity=strip_cell)
        elif fmt == "qchem-input":
            record = read_qchem_input(path, raw, remove_periodicity=strip_cell)
        elif fmt == "nwchem-input":
            record = read_nwchem_input(path, raw, remove_periodicity=strip_cell)
        elif fmt == "orca-gbw":
            record = _gbw_geometry(path, raw, remove_periodicity=strip_cell)
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
    return OpenedStructure(record, ArtifactRef.from_bytes(raw, fmt, str(path)))

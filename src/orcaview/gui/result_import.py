"""Read independent result files for the workspace without calling Qt."""

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from orcaview.i18n import tr

from orcaview.application.document import MoleculeDocument
from orcaview.application.session import Session
from orcaview.application.structure_import import OpenedStructure, PeriodicFile
from orcaview.core.models import CalculationSpec, Molecule
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.core.results import DatasetAxis, ResultDataset
from orcaview.io.structure_record import StructureRecord
from orcaview.orca._native_output import population_tables, reported_geometry
from orcaview.orca.log_report import LogReport, job_sections, parse_log_report
from orcaview.orca.output import parse_output
from orcaview.results import OrcaImportError, commit_orca_output
from orcaview.results.orca_native import inspect_orca_bytes


def _add_populations(lines, source, document, frame, geometry_line):
    existing = set()
    for dataset in document.records()[1]:
        if dataset.geometry == frame.ref and dataset.values is not None:
            locations = dict(dataset.provenance.parameters)
            existing.add((dataset.kind, locations.get("population_line") or locations.get("mulliken_line")))
    tables = tuple(population_tables(lines, geometry_line, frame.molecule))
    counts = Counter(method for method, _, _, _ in tables)
    for method, line, values, spins in tables:
        prefix = {"Mulliken": "mulliken", "Löwdin": "loewdin", "Hirshfeld": "hirshfeld"}[method]
        loc = (("population_line", str(line)),)
        if counts[method] > 1:
            loc += (("population_series", f"Line {line}"),)
        origin = Provenance("orca-native-import", "orcaview.orca.population", "1", (source,), loc)
        for kind, unit, series in ((prefix + "-charge", "e", values), (prefix + "-spin", "1", spins)):
            if series and (kind, str(line)) not in existing:
                document.add_dataset(ResultDataset(kind, frame.ref, origin, "float64", (len(series),),
                                                   unit, series, (DatasetAxis("atom", frame.atom_ids),), method=method))


def read_native_session(path: Path, confirmation=None):
    """Open the chosen file as a project if geometry is verified, otherwise as a log-only report."""
    path = path.resolve()
    if confirmation is None:
        if not path.is_file():
            raise OSError(tr("Select a readable regular file"))
        raw = path.read_bytes()
    else:
        raw = confirmation.raw
    periodic = re.search(rb"(?im)^\s*(?:periodic boundary conditions?|pbc)\s*[.:=]*\s*(?:true|on|yes|enabled|3d|2d|1d)\b", raw)
    if periodic and confirmation is None:
        return PeriodicFile(raw)
    if periodic:
        geometry = reported_geometry(raw.decode("utf-8-sig"))
        if geometry is None:
            raise ValueError(tr("No Cartesian coordinates could be identified in the log to display a finite structure."))
        atoms, charge, mult, _ = geometry
        mol = Molecule(path.stem, atoms, charge=charge, multiplicity=mult)
        return OpenedStructure(StructureRecord(mol, removed_periodicity=True),
                               ArtifactRef.from_bytes(raw, "orca-out", str(path)))
    inspection = inspect_orca_bytes(path, raw)
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    report = parse_log_report(lines, inspection.artifact)
    if inspection.importable:
        result = commit_orca_output(inspection)
        document, frame = result.document, result.frame
        line = inspection.evidence.geometry_line
    else:
        single = len(job_sections(lines)) == 1 and all(issue.code != "multiple_jobs" for issue in inspection.issues)
        geometry = reported_geometry(text) if single else None
        if geometry is None:
            if report.properties or report.spectra:
                return report
            raise OrcaImportError(inspection.issues)
        atoms, charge, mult, line = geometry
        molecule = Molecule(path.stem, atoms, charge=charge, multiplicity=mult)
        origin = Provenance("orca-log-geometry", parents=(report.source,), parameters=(("geometry_line", str(line)),))
        document = MoleculeDocument.from_molecule(molecule, origin)
        frame = document.add_frame(document.head.ref, f"orca-out:{report.source.sha256}:{line}",
                                   molecule, document.head.atom_ids, origin)
    _add_populations(lines, report.source, document, frame, line)
    session = Session.from_document(document, CalculationSpec(), str(path))
    session.log_report = report
    return session


@dataclass(frozen=True)
class SummaryView:
    text: str
    report: LogReport


def read_summary_view(path, job):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError(tr("The summary reader supports output files up to 64 MB."))
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    result = parse_output(text, job)
    fields = json.dumps(asdict(result), ensure_ascii=False, indent=2)
    summary = tr("Source: {path}\nJob type: {job}\nSeparate import, not linked to the current structure.", path=path, job=job) + "\n\n" + fields
    report = parse_log_report(text.splitlines(), ArtifactRef.from_bytes(raw, "orca-out", str(path.resolve())))
    return SummaryView(summary, report)


def read_output_summary(path: Path, job: str) -> str:
    return read_summary_view(path, job).text

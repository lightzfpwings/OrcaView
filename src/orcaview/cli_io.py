"""Shared desktop-format document loading and atomic command-line output."""

from pathlib import Path
import sys

from orcaview.application.document import MoleculeDocument
from orcaview.application.project import load_project
from orcaview.application.session import Session
from orcaview.application.structure_import import OpenedStructure, PeriodicFile, read_structure_file
from orcaview.core.models import CalculationSpec, Molecule
from orcaview.core.provenance import Provenance
from orcaview.gui.result_import import read_native_session
from orcaview.orca.log_report import LogReport
from orcaview.io.atomic_file import write_bytes


def load_session(path, *, finite=False, calculation=None):
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() == ".json":
        return load_project(source)
    reader = read_native_session if source.suffix.lower() in (".out", ".log") else read_structure_file
    result = reader(source)
    if isinstance(result, PeriodicFile):
        if not finite:
            raise ValueError("This file declares periodicity. Use --finite to import a finite structure.")
        result = reader(source, result)
    if isinstance(result, OpenedStructure):
        return result.session(calculation or CalculationSpec())
    if isinstance(result, LogReport):
        origin = Provenance("orca-log-report", parents=(result.source,))
        doc = MoleculeDocument.from_molecule(Molecule(source.stem, ()), origin)
        session = Session.from_document(doc, calculation or CalculationSpec(), str(source))
        session.log_report = result
        return session
    if calculation is not None:
        result.calculation = calculation
    return result


def check_output(input_path, output_path):
    if input_path is None or output_path is None or str(output_path) == "-":
        return
    first, second = Path(input_path), Path(output_path)
    if first.resolve() == second.resolve() or (first.exists() and second.exists() and first.samefile(second)):
        raise ValueError("Choose an output path distinct from the input file.")


def write_text(path, text):
    if path is None or str(path) == "-":
        sys.stdout.write(text)
    else:
        write_bytes(path, text.encode("utf-8"))

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orcaview.application.project import load_project, save_project
from orcaview.application.structure_import import (
    OpenedStructure, PeriodicFile, open_file_filters, read_structure_file, structure_format,
)
from orcaview.core.models import CalculationSpec
from orcaview.core.units import BOHR_IN_ANGSTROM
from orcaview.gui.result_display import source_file_details
from orcaview.gui.result_import import read_native_session


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
CELL_XYZ = b'1\nLattice="4 0 0 0 4 0 0 0 4" pbc="T T T"\nHe 1 2 3\n'


class StructureImportTests(unittest.TestCase):
    def setUp(self):
        work = TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)

    def test_open_formats_and_filters(self):
        for name, fmt in (("Wave.MOLDEN.INPUT", "molden"), ("POSCAR", "poscar"), ("CONTCAR", "poscar"),
                          ("test.NWI", "nwchem-input"), ("test.GBW", "orca-gbw"), ("water.GJF", "gaussian-input")):
            self.assertEqual(structure_format(Path(name)), fmt)
        filters = open_file_filters().split(";;")[0]
        for pattern in ("*.inp", "*.log", "*.gjf", "*.fchk", "*.cdxml", "POSCAR", "*.nw", "*.oview.json"):
            self.assertIn(pattern, filters)

    def test_periodic_confirmation_uses_selected_bytes_through_project_save(self):
        path = self.root / "cell.extxyz"
        path.write_bytes(CELL_XYZ)
        prompt = read_structure_file(path)
        self.assertIsInstance(prompt, PeriodicFile)
        path.write_text("1\nother\nNe 0 0 0\n")
        opened = read_structure_file(path, prompt)
        self.assertEqual(opened.source.sha256, hashlib.sha256(CELL_XYZ).hexdigest())
        self.assertEqual(opened.record.molecule.atoms[0].element, "He")
        self.assertTrue(opened.record.removed_periodicity)
        session = opened.session(CalculationSpec())
        project = self.root / "finite.oview.json"
        save_project(session, project)
        reopened = load_project(project)
        self.assertEqual(reopened.document.head, session.document.head)
        self.assertEqual(dict(reopened.document.head.provenance.parameters)["periodicity"], "removed")

    def test_shared_input_extensions_follow_program_headers(self):
        for name, contents, fmt in (
            ("water.in", (EXAMPLES / "native_methods/water-cpcm.inp").read_bytes(), "orca-input"),
            ("cell.inp", b"geometry units bohr\nHe 0 0 0\nend\n", "nwchem-input"),
            ("drawing.input", b"#p HF\n\nGeometry test\n\n0 1\nHe 0 0 0\n", "gaussian-input"),
            ("demo.inp", b"\xef\xbb\xbf$molecule\r\n0 1\r\nHe 0 0 0\r\n$end\r\n", "qchem-input"),
        ):
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(contents)
                self.assertEqual(read_structure_file(path).source.format, fmt)

    def test_external_coordinates_must_match_consent(self):
        path = self.root / "linked.inp"
        path.write_text('* xyzfile 0 1 "local cell.xyz"\n')
        sidecar = self.root / "local cell.xyz"
        sidecar.write_bytes(CELL_XYZ)
        prompt = read_structure_file(path)
        self.assertIsInstance(prompt, PeriodicFile)
        imported = read_structure_file(path, prompt).session(CalculationSpec())
        parents = imported.document.head.provenance.parents
        self.assertEqual([p.path_hint for p in parents], [str(p.resolve()) for p in (path, sidecar)])
        self.assertIn('ORCA input file', source_file_details(parents))
        sidecar.write_bytes(CELL_XYZ.replace(b"He 1", b"He 3"))
        with self.assertRaisesRegex(ValueError, '(?i)changed'):
            read_structure_file(path, prompt)

    def test_qchem_cartesian_fragments_bohr_and_ewald_cell(self):
        path = self.root / "fragment.qcin"
        content = ("$molecule\n0 1\n--\n0 1\nHe 0 0 0\n--\n0 1\nHe,2,0,0\n$end\n"
                   "$rem\nINPUT_BOHR = TRUE\n$end\n")
        path.write_text(content)
        record = read_structure_file(path).record
        self.assertEqual(record.molecule.atoms[1].x, 2 * BOHR_IN_ANGSTROM)
        self.assertFalse(record.removed_periodicity)
        path.write_text(content + "$forceman\newald\nbox_length 10\n$end\n")
        prompt = read_structure_file(path)
        self.assertIsInstance(prompt, PeriodicFile)
        record = read_structure_file(path, prompt).record
        self.assertEqual(record.molecule.atoms[1].x, 2 * BOHR_IN_ANGSTROM)
        self.assertTrue(record.removed_periodicity)
        path.write_text("$molecule\nread\n$end\n")
        with self.assertRaisesRegex(ValueError, 'explicit'):
            read_structure_file(path)

    def test_native_log_stays_bound_only_to_its_original_geometry(self):
        raw = (EXAMPLES / "m5_orca/water-sp.out").read_bytes()
        path = self.root / "water.log"
        path.write_bytes(raw)
        session = read_native_session(path)
        self.assertTrue(session.log_report.properties)
        path.write_bytes(raw + b"\nPeriodic boundary conditions: ON\n")
        prompt = read_native_session(path)
        self.assertIsInstance(prompt, PeriodicFile)
        opened = read_native_session(path, prompt)
        self.assertIsInstance(opened, OpenedStructure)
        self.assertEqual(opened.record.molecule.atoms, session.molecule.atoms)
        finite = opened.session(CalculationSpec())
        self.assertEqual(finite.document.records()[1], ())
        self.assertIsNone(finite.log_report)

    def test_gbw_explains_how_to_open_without_orca(self):
        path = self.root / "example.gbw"
        path.write_bytes(b"fixture")
        with patch("orcaview.application.structure_import.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, r"orca_2mkl.*\.molden\.input"):
                read_structure_file(path)

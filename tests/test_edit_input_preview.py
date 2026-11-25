import contextlib
from dataclasses import replace
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orcaview.application.project import load_project
from orcaview.application.session import Session
from orcaview.cli import main
from orcaview.core.block_options import BlockOverride
from orcaview.core.models import Atom, Bond, CalculationSpec, Molecule
from orcaview.orca.input import render_input


class PreviewTextTests(unittest.TestCase):
    def test_compact_input_syncs_and_survives_save_reload_and_cli(self):
        session = Session()
        raw = """! opt  PBE0  def2-tzvp TightSCF
! freq SMD(WATER) PAL8
%maxcore=3072
%scf MaxIter 220; # first note # TolE 1E-9 end
* XYZ 0 1
o 0 0 0
h .8 0 .6
H -.8 0 .6
*
"""
        text = session.apply_input_preview(raw)
        spec = session.calculation
        self.assertEqual((spec.method, spec.basis, spec.job_type, spec.cores, spec.maxcore_mb),
                         ("PBE0", "def2-TZVP", "OPT_FREQ", 8, 3072))
        self.assertEqual((spec.solvation_model, spec.solvent, spec.scf_convergence), ("SMD", "water", "TightSCF"))
        self.assertEqual(set(spec.block_options), {BlockOverride("scf", "MaxIter", 220), BlockOverride("scf", "TolE", 1e-9)})
        self.assertEqual(spec.input_comments, ("first note",))
        self.assertIn("  H   0.80000000  0.00000000  0.60000000\n", text)
        self.assertEqual(session.input_text(), text)
        with TemporaryDirectory() as tmp:
            project, out = Path(tmp, "edited.oview.json"), Path(tmp, "normalized.inp")
            with patch("sys.stdin", io.StringIO(raw)), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["project", "--edit-input", "-", "-o", str(project)]), 0)
            saved = load_project(project)
            self.assertEqual((saved.calculation, saved.input_text()), (spec, text))
            self.assertEqual(main(["preview", str(project), "-o", str(out)]), 0)
            self.assertEqual(out.read_text(), text)
            with patch("sys.stdin", io.StringIO(raw.replace("PBE0", "PBE0 mystery"))), contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(main(["preview", "--edit-input", "-", "-o", str(out)]), 0)
            self.assertEqual(out.read_text(), text)

    def test_coordinate_precision_and_atom_identity_survive_edits_and_reordering(self):
        atoms = (Atom("O", 0., 0., .123456789876), Atom("H", .76543210987, 0., .6), Atom("H", -.76, 0., .6))
        session = Session(molecule=Molecule("Water", atoms, (Bond(0, 1), Bond(0, 2)), bonds_explicit=True))
        initial = session.document.head
        text = session.apply_input_preview(session.input_text().replace("nprocs 16", "nprocs 24"))
        self.assertIs(session.document.head, initial)
        lines = text.splitlines()
        lines[-4:-1] = [lines[-2], lines[-4], lines[-3].replace("0.60000000", "0.68")]
        session.apply_input_preview("\n".join(lines))
        edited = session.document.head
        self.assertEqual(edited.atom_ids, tuple(initial.atom_ids[i] for i in (2, 0, 1)))
        self.assertEqual(edited.molecule.atoms, (atoms[2], atoms[0], replace(atoms[1], z=.68)))
        self.assertEqual(edited.molecule.bonds, (Bond(1, 2), Bond(1, 0)))
        self.assertEqual(edited.ref.revision, initial.ref.revision + 1)
        with self.assertRaises(ValueError):
            session.apply_input_preview(text, expected=initial.ref)

    def test_invalid_input_is_atomic_and_identifies_unsupported_text(self):
        session = Session()
        head, spec, original = session.document.head, session.calculation, session.input_text()
        for bad, reason in ((original.replace("B3LYP", "B3LYP UnknownSCF"), "unknownscf"),
                            (original.replace("nprocs 16", "nprocs 0"), "positive"),
                            (original.replace("* xyz", "%scf\n MaxIter 240\n* xyz"), "end"),
                            (original.replace("* xyz 0 1", "* xyz -1 1"), "multiplicity"),
                            (original.replace("SP", "Freq NumFreq"), "Conflicting")):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                session.apply_input_preview(bad)
            self.assertIs(session.document.head, head)
            self.assertIs(session.calculation, spec)

    def test_method_recipes_and_explicit_numeric_frequency_options_round_trip(self):
        specs = (CalculationSpec(method="TD-DFT", reference_functional="PBE0", nroots=3),
                 CalculationSpec(method="MR-EOM", active_electrons=2, active_orbitals=2, nroots=2),
                 CalculationSpec(job_type="OPT_FREQ", block_options=(BlockOverride("freq", "Increment", .003),)),
                 CalculationSpec(method="RI-MP2", job_type="OPT_FREQ"),
                 CalculationSpec(solvation_model="SMD", solvent="ethyl acetate"))
        for spec in specs:
            with self.subTest(spec=spec):
                session = Session()
                raw = render_input(session.molecule, spec)
                self.assertEqual(session.apply_input_preview(raw), raw)
                self.assertEqual(session.calculation, spec)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.main_window import MainWindow
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication, "Requires PySide6")
class PreviewWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.editor = self.window.input_preview

    def tearDown(self):
        with patch.object(self.window, "_guard_discard", return_value=True):
            self.window.close()

    def test_leave_updates_visible_controls_and_normalizes_once(self):
        w, editor = self.window, self.editor
        self.assertFalse(editor.isReadOnly())
        self.assertTrue(w.output_summary.isReadOnly())
        head = w.session.document.head
        editor.setFocus()
        inside = editor.viewport().mapTo(w, editor.viewport().rect().center())
        QTest.mouseMove(w.windowHandle(), inside)
        text = editor.toPlainText().replace("B3LYP", "pbe0").replace("Opt", "opt freq").replace("nprocs 16", "NPROCS   8")
        editor.setPlainText(text.replace("* xyz", "%scf MaxIter 240 end\n* xyz"))
        self.assertEqual(w.cores.value(), 16)
        QTest.mouseMove(w.windowHandle(), w.viewport.mapTo(w, w.viewport.rect().center()))
        self.app.processEvents()
        self.assertEqual((w.method.currentText(), w.job.currentData(), w.cores.value()), ("PBE0", "OPT_FREQ", 8))
        self.assertEqual(w.block_options.drafts["scf", "MaxIter"], "240")
        self.assertIs(w.session.document.head, head)
        self.assertEqual(editor.toPlainText(), w.session.input_text())
        self.assertFalse(editor.pending)
        w.maxcore.setValue(2048)
        self.assertIn("%maxcore 2048", editor.toPlainText())

    def test_tab_applies_geometry_and_can_correct_an_invalid_inspector(self):
        w, editor = self.window, self.editor
        source = editor.toPlainText()
        w.charge.setValue(-1)
        self.assertFalse(w.export_button.isEnabled())
        editor.setFocus()
        editor.setPlainText(source)
        QTest.keyClick(editor, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertTrue(w.export_button.isEnabled())
        self.assertEqual(w.charge.value(), 0)
        line = next(row for row in source.splitlines() if row.startswith("  C "))
        columns = line.split()
        columns[1] = "1.234567891"
        editor.setFocus()
        editor.setPlainText(source.replace(line, " ".join(columns), 1))
        QTest.keyClick(editor, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertEqual(w.session.molecule.atoms[0].x, 1.234567891)
        self.assertEqual(w.viewport.molecule, w.session.molecule)
        self.assertIn("1.23456789 ", editor.toPlainText())

    def test_invalid_draft_survives_export_and_can_be_fixed_or_reverted(self):
        w, editor = self.window, self.editor
        source = editor.toPlainText()
        draft = source.replace("nprocs 16", "nprocs ???")
        editor.setPlainText(draft)
        editor.setFocus()
        w.viewport.setFocus()
        self.app.processEvents()
        self.assertEqual(editor.toPlainText(), draft)
        self.assertFalse(w.export_button.isEnabled())
        self.assertEqual(w.cores.value(), 16)
        with patch.object(w, "_error"), patch("orcaview.gui.main_window.QFileDialog.getSaveFileName") as dialog:
            w.export_input()
            self.assertFalse(w.save_project_dialog())
            dialog.assert_not_called()
        editor.setFocus()
        QTest.keyClick(editor, Qt.Key.Key_Escape)
        self.assertEqual(editor.toPlainText(), source)
        self.assertTrue(w.export_button.isEnabled())
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "test.inp")
            editor.setPlainText(source.replace("%maxcore 4096", "%MAXCORE 3200"))
            with patch("orcaview.gui.main_window.QFileDialog.getSaveFileName", return_value=(str(path), "")):
                w.export_input()
            self.assertEqual(path.read_text(), w.session.input_text())
            self.assertEqual(w.maxcore.value(), 3200)

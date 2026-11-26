"""Exercise optimization and frequency viewers through the desktop result workspace."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import orcaview
from orcaview.application.session import Session
from orcaview.cli_io import load_session
from orcaview.core.models import Molecule
from orcaview.gui.result_import import read_native_session
from orcaview.orca.log_report import LogReport

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog
    from orcaview.gui.main_window import MainWindow
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


ROOT = Path(orcaview.__file__).resolve().parents[2]
VALIDATION = ROOT / "artifacts/public/validation"
OPTFREQ = VALIDATION / "ORCA-6.1.1-macOS-arm64/optfreq/job.out"
RAMAN = VALIDATION / "results-0.1.0a12/raman/water.out"
SINGLE_POINT = ROOT / "examples/m5_orca/water-sp.out"


def compound_modes(path):
    """Combine printed sections for two separately computed water geometries."""
    sections = []
    for job, source in enumerate((OPTFREQ, RAMAN), start=1):
        text = source.read_text(encoding="utf-8")
        xyz = text.rsplit("\nCARTESIAN COORDINATES (ANGSTROEM)\n", 1)[1].split("\n\n", 1)[0]
        vibrations = text.split("\nVIBRATIONAL FREQUENCIES\n", 1)[1].split("\nIR SPECTRUM\n", 1)[0]
        sections.append(f"COMPOUND JOB {job}\nCARTESIAN COORDINATES (ANGSTROEM)\n{xyz}\n\n"
                        f"VIBRATIONAL FREQUENCIES\n{vibrations}")
    path.write_text("\n".join(sections), encoding="utf-8")


@unittest.skipUnless(QApplication, "requires Qt")
class ResultPlotActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.panel = self.window.foundation_panel
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.dirty = False
        self.window.close()
        self.app.processEvents()

    def open_output(self, path):
        result = read_native_session(path)
        self.window._display_read_result(path, result)
        self.app.processEvents()
        self.assertIs(self.window.workspace_tabs.currentWidget(), self.panel)
        return result

    def open_player(self):
        self.assertTrue(self.panel.modes_button.isVisible())
        self.assertTrue(self.panel.modes_button.isEnabled())
        QTest.mouseClick(self.panel.modes_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        player = self.panel._mode_dialog
        self.assertTrue(player.isVisible())
        return player

    def test_open_optfreq_use_both_viewers_then_replace_with_single_point(self):
        session = self.open_output(OPTFREQ)
        records = session.document.records()
        self.assertTrue(self.panel.curve_button.isVisible())
        QTest.mouseClick(self.panel.curve_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        curve = self.panel._curve_dialog
        self.assertTrue(curve.isVisible())
        self.assertEqual(curve.table.rowCount(), 5)
        self.assertAlmostEqual(curve.plot.points[-1].energy, -76.321268537024)

        player = self.open_player()
        self.assertEqual(player.viewport.molecule.atoms, session.log_report.normal_modes[0].atoms)
        player.mode_table.setCurrentCell(2, 0)
        self.assertEqual(player.mode_table.item(2, 1).text(), "3882.00")
        QTest.qWait(50)
        self.assertEqual(session.document.records(), records)
        self.open_output(SINGLE_POINT)
        self.assertIsNone(self.panel._mode_dialog)
        self.assertIsNone(self.panel._curve_dialog)
        self.assertTrue(self.panel.modes_button.isHidden())
        self.assertTrue(self.panel.curve_button.isHidden())

    def test_blank_design_and_compound_raw_frequency_rows_use_their_own_geometry(self):
        design = Session(molecule=Molecule("Draft", (), bonds_explicit=True))
        self.window.open_result_session(design, mark_dirty=False)
        draft = design.document.head
        with TemporaryDirectory() as directory:
            source = Path(directory) / "two-jobs.out"
            compound_modes(source)
            report = self.open_output(source)
        self.assertIsInstance(report, LogReport)
        self.assertTrue(self.panel.showing_independent_log)
        self.assertTrue(self.panel.geometry_pane.isHidden())
        self.assertIs(self.window.session.document.head, draft)
        first, second = report.normal_modes
        self.assertNotEqual(first.atoms, second.atoms)
        player = self.open_player()
        self.assertEqual(player.viewport.molecule.atoms, first.atoms)
        player.close()

        self.panel.spectra.setCurrentItem(self.panel.spectra.topLevelItem(1))
        table = self.panel.log_table
        model = table.model()
        self.assertEqual(model.rowCount(), 9)

        def double_click_row(row):
            index = model.index(row, 0)
            table.scrollTo(index)
            self.app.processEvents()
            pos = table.visualRect(index).center()
            QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=pos)
            QTest.mouseDClick(table.viewport(), Qt.MouseButton.LeftButton, pos=pos)
            self.app.processEvents()

        double_click_row(1)
        self.assertFalse(player.isVisible())  # Projected, all-zero vector.
        double_click_row(8)
        self.assertTrue(player.isVisible())
        self.assertEqual(player.group_choice.currentIndex(), 1)
        self.assertEqual(player.mode_table.currentRow(), 2)
        self.assertEqual(player.mode_table.item(2, 1).text(), "4046.70")
        self.assertEqual(player.viewport.molecule.atoms, second.atoms)
        self.assertIs(self.window.session.document.head, draft)
        self.assertFalse(draft.molecule.atoms)

    def test_saved_standalone_report_reopens_with_both_mode_groups_without_source_file(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "two-jobs.out"
            project = Path(directory) / "report.oview.json"
            compound_modes(source)
            report_session = load_session(source)
            first, second = report_session.log_report.normal_modes
            self.window.open_result_session(report_session)
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(project), "")):
                self.assertTrue(self.window.save_project_dialog())
            self.assertTrue(self.panel.showing_independent_log)
            self.assertTrue(self.panel.modes_button.isVisible())
            self.assertTrue(self.panel.modes_button.isEnabled())
            source.unlink()
            self.open_output(SINGLE_POINT)
            self.window.dirty = False
            self.window._open_project_path(project)
            self.app.processEvents()

        self.assertIs(self.window.workspace_tabs.currentWidget(), self.panel)
        self.assertTrue(self.panel.showing_independent_log)
        self.assertFalse(self.window.session.molecule.atoms)
        player = self.open_player()
        self.assertEqual(player.groups, (first, second))
        player.group_choice.setCurrentIndex(1)
        self.assertEqual(player.viewport.molecule.atoms, second.atoms)

    def test_report_with_frequencies_only_keeps_table_and_disables_animation(self):
        text = OPTFREQ.read_text(encoding="utf-8")
        table = text.split("\nVIBRATIONAL FREQUENCIES\n", 1)[1].split("\nNORMAL MODES\n", 1)[0]
        with TemporaryDirectory() as directory:
            source = Path(directory) / "frequencies.out"
            source.write_text("VIBRATIONAL FREQUENCIES\n" + table, encoding="utf-8")
            self.open_output(source)
        self.assertTrue(self.panel.modes_button.isVisible())
        self.assertFalse(self.panel.modes_button.isEnabled())
        self.assertTrue(self.panel.curve_button.isHidden())
        self.assertEqual(self.panel.spectra.topLevelItemCount(), 1)
        self.panel.spectra.setCurrentItem(self.panel.spectra.topLevelItem(0))
        model = self.panel.log_table.model()
        self.assertEqual(model.rowCount(), 9)
        self.assertAlmostEqual(float(model.data(model.index(8, 1))), 3882.)
        self.assertIsNone(self.panel._mode_dialog)

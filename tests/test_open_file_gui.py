"""Drive the unified open-file action and the real periodicity choice dialog."""

import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from orcaview.gui.main_window import MainWindow
    HAS_QT = True
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "未安装可选 Qt 依赖")
class OpenFileWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.work = TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.addCleanup(self._close)
        self.app.processEvents()

    def _close(self):
        self.window.dirty = False
        self.window.close()
        self.app.processEvents()

    def _open(self, path):
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")) as dialog:
            self.window.open_file_action.trigger()
        self.assertEqual(dialog.call_args.args[1], "Open file")
        self.assertIn("*.sdf", dialog.call_args.args[3])

    def _wait(self, predicate):
        deadline = time.monotonic() + 30
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "文件读取未完成")

    def test_results_and_spectra_follow_open_file_and_saved_project(self):
        root = Path(__file__).resolve().parents[1]
        nmr = root / "artifacts/public/validation/results-0.1.0a12/nmr"
        project = Path(self.work.name) / "NMR.oview.json"
        panel = self.window.foundation_panel

        def check_file(path, has_data):
            previous = self.window.session
            self._open(path)
            self._wait(lambda: self.window.session is not previous)
            self.window.workspace_tabs.setCurrentWidget(panel)
            self.app.processEvents()
            if has_data:
                self.assertGreater(panel.datasets.rowCount(), 0)
                self.assertGreater(panel.spectra.topLevelItemCount(), 0)
                panel.spectra.setCurrentItem(panel.spectra.topLevelItem(0))
            else:
                self.assertEqual(panel.datasets.rowCount(), 0)
                self.assertEqual(panel.spectra.topLevelItemCount(), 0)
                self.assertGreater(panel.atoms.rowCount(), 0)
            self.assertEqual(panel.datasets.horizontalHeader().isVisible(), has_data)
            self.assertEqual(panel.spectrum_preview.isVisible(), has_data)

        check_file(root / "examples/water.xyz", False)
        check_file(nmr / "water-shield.out", True)
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(project), "")):
            self.assertTrue(self.window.save_project_dialog())
        check_file(nmr / "water-shield.inp", False)
        check_file(project, True)
        check_file(root / "examples/water.xyz", False)

    @unittest.skipUnless(importlib.util.find_spec("openbabel"), "需要 Open Babel")
    def test_open_drawing_builds_3d_and_keeps_file_source(self):
        raw = (b'<CDXML><page><fragment id="1"><n id="2" p="0 0"/>'
               b'<n id="3" p="20 0" Element="8"/><b id="4" B="2" E="3"/>'
               b'</fragment></page></CDXML>')
        path = Path(self.work.name, "二维甲醇.cdxml")
        path.write_bytes(raw)
        self.window.workspace_tabs.setCurrentWidget(self.window.foundation_panel)
        self._open(path)
        self._wait(lambda: self.window.session.source_path == str(path.resolve()))
        document = self.window.session.document
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 0)
        self.assertEqual(len(document.head.molecule.atoms), 6)
        self.assertTrue(any(abs(a.z) > 0.1 for a in document.head.molecule.atoms))
        self.assertIn("Open Babel", dict(document.head.provenance.parameters)["geometry_generation"])
        self.assertTrue(self.window.open_file_action.isEnabled())
        self.assertEqual(path.read_bytes(), raw)

    def test_periodic_dialog_decline_then_accept_retains_finite_cartesian_structure(self):
        raw = (b'2\nLattice="6 0 0 0 6 0 0 0 6" pbc="T T T"\n'
               b"He 0.1 2 3\nNe 5.9 4 5\n")
        path = Path(self.work.name, "periodic.xyz")
        path.write_bytes(raw)
        initial = self.window.session
        messages = []
        choice = QMessageBox.StandardButton.No
        unexpected = []

        def answer():
            box = self.app.activeModalWidget()
            if not isinstance(box, QMessageBox):
                return
            messages.append(box.text())
            if "Remove periodicity" in box.text():
                button = box.button(choice)
                if button is None:
                    role = QMessageBox.ButtonRole.YesRole if choice == QMessageBox.StandardButton.Yes else QMessageBox.ButtonRole.NoRole
                    button = next((b for b in box.buttons() if box.buttonRole(b) == role), None)
            else:
                button = box.button(QMessageBox.StandardButton.Ok)
            if button is None:
                unexpected.append(box.text())
                box.reject()
            else:
                button.click()

        timer = QTimer(self.window)
        timer.timeout.connect(answer)
        timer.start(20)
        self.addCleanup(timer.stop)
        self._open(path)
        self._wait(lambda: any("Periodic structures are unsupported" in msg for msg in messages))
        self.assertIs(self.window.session, initial)
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 0)
        choice = QMessageBox.StandardButton.Yes
        self._open(path)
        self._wait(lambda: self.window.session is not initial)
        head = self.window.session.document.head
        self.assertEqual([a.x for a in head.molecule.atoms], [0.1, 5.9])
        self.assertEqual(dict(head.provenance.parameters)["periodicity"], "removed")
        self.assertEqual(sum("Remove periodicity" in text for text in messages), 2)
        self.assertFalse(unexpected)
        self.assertEqual(path.read_bytes(), raw)

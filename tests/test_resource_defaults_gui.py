"""Resource defaults shared by new desktop jobs and explicit project settings."""

from dataclasses import replace
from argparse import ArgumentParser
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orcaview.application.project import save_project
from orcaview.core.resource_defaults import ResourceAssessment

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication, QFileDialog
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication, "Requires PySide6")
class DesktopResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from orcaview.gui.main_window import MainWindow

        self.host = ResourceAssessment(cpu_limit=8, memory_mb=32768)
        detector = patch("orcaview.gui.main_window.detect_resources", return_value=self.host)
        self.detect = detector.start()
        self.addCleanup(detector.stop)
        self.window = MainWindow()
        self.addCleanup(self._close)

    def _close(self):
        self.window.dirty = False
        self.window.close()

    def assert_resources(self, cores, memory):
        w = self.window
        self.assertEqual((w.cores.value(), w.maxcore.value()), (cores, memory))
        self.assertEqual((w.session.calculation.cores, w.session.calculation.maxcore_mb), (cores, memory))
        preview = w.input_preview.toPlainText().lower().splitlines()
        self.assertIn(f"  nprocs {cores}", preview)
        self.assertIn(f"%maxcore {memory}", preview)
        self.assertIn(f"{cores * memory:,}", w.memory_hint.text())

    def test_startup_and_new_design_use_one_snapshot_and_allow_overrides(self):
        w = self.window
        self.assert_resources(16, 4096)
        self.assertIn("6 × 4,096", w.resource_hint.text())
        self.assertEqual(w.statusBar().currentMessage(), w.resource_hint.text())
        self.assertIn("32,768", w.resource_hint.toolTip())
        w.cores.setValue(24)
        w.maxcore.setValue(8000)
        self.assert_resources(24, 8000)
        with patch.object(w, "_guard_discard", return_value=True):
            w._new_design()
        self.assert_resources(16, 4096)
        self.detect.assert_called_once_with()

    def test_project_and_structure_keep_explicit_settings_and_new_output_uses_defaults(self):
        w = self.window
        with TemporaryDirectory() as folder:
            project = Path(folder, "water.oview.json")
            saved = replace(w.session, calculation=replace(w.session.calculation, cores=320, maxcore_mb=512))
            save_project(saved, project)
            w._open_project_path(str(project))
        self.assert_resources(320, 512)
        with patch.object(QFileDialog, "getOpenFileName", return_value=("examples/water.xyz", "")):
            w.open_file()
        self.assert_resources(320, 512)
        with patch.object(QFileDialog, "getOpenFileName", return_value=("examples/m5_orca/water-sp.out", "")):
            w.import_native_output()
        w._read_future.result(10)
        w._finish_read()
        self.assertIsNotNone(w.session.log_report)
        self.assert_resources(16, 4096)
        self.detect.assert_called_once_with()

    def test_gui_command_uses_window_defaults_for_raw_files_and_saved_project_resources(self):
        from orcaview.cli_render import _configure_window, add_gui_options

        w = self.window
        parser = ArgumentParser()
        add_gui_options(parser)
        for path in ("examples/water.xyz", "examples/m5_orca/water-sp.out"):
            _configure_window(w, parser.parse_args([path]))
            self.assert_resources(16, 4096)
        with TemporaryDirectory() as folder:
            project = Path(folder, "custom.oview.json")
            w.cores.setValue(18)
            w.maxcore.setValue(2000)
            save_project(w.session, project)
            _configure_window(w, parser.parse_args([str(project)]))
            self.assert_resources(18, 2000)
        self.detect.assert_called_once_with()

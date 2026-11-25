import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.main_window import MainWindow
    from orcaview.gui.manual import ManualDialog
except ModuleNotFoundError as exc:
    if exc.name != "PySide6":
        raise
    QApplication = None


@unittest.skipUnless(QApplication, "Qt is optional")
class ManualGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_manual_results_open_correct_pdf_destination(self):
        dialog = ManualDialog()
        self.addCleanup(dialog.close)
        dialog.query.setText("3.18")
        self.assertEqual(dialog.results.currentItem().text(0), "3.18")
        with patch("orcaview.gui.manual.QDesktopServices.openUrl") as open_url:
            dialog.pdf.click()
            self.assertTrue(open_url.call_args.args[0].toString().endswith("#page=497"))
            dialog.web.click()
            self.assertTrue(open_url.call_args.args[0].toString().endswith("casdft.html"))
        dialog.query.setText("this is not a calculation topic")
        self.assertFalse(dialog.web.isEnabled())

    def test_model_and_job_switch_remove_incompatible_fields(self):
        win = MainWindow()
        try:
            win.job.setCurrentIndex(win.job.findData("IRC"))
            win.solvation_model.setCurrentIndex(win.solvation_model.findData("SMD"))
            self.assertEqual(win.solvent.currentData(), "water")
            self.assertNotIn("InitHess calc_numfreq", win.session.input_text())
            self.assertIn(("irc", "MaxIter"), win.block_options.options)
            win.job.setCurrentIndex(win.job.findData("SP"))
            self.assertNotIn(("irc", "MaxIter"), win.block_options.options)
            self.assertNotIn(("geom", "MaxIter"), win.block_options.options)
            self.assertIn("SMD(water)", win.session.input_text())
            win.solvation_model.setCurrentIndex(0)
            self.assertIsNone(win.solvent.currentData())
            self.assertNotIn(("cpcm", "SMD18"), win.block_options.options)
        finally:
            win.dirty = False
            win.close()

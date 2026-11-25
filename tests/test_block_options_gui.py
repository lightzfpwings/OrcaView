"""Desktop input-block edits, eligibility changes and project round trips."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orcaview.application.session import Session
from orcaview.core.methods import METHODS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtWidgets import QApplication, QFileDialog, QLabel
    from orcaview.gui.main_window import MainWindow
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False
else:
    HAS_QT = True


@unittest.skipUnless(HAS_QT, 'Optional Qt dependency is not installed')
class BlockOptionsGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.win = MainWindow()
        self.win.show()
        self.app.processEvents()
        self.panel = self.win.block_options
        self.addCleanup(self._close)

    def _close(self):
        self.win.dirty = False
        self.win.close()
        self.app.processEvents()

    def _group(self, block):
        self.panel.toggle.setChecked(True)
        group = self.panel.groups[block]
        group.toggle.setChecked(True)
        return group

    def _field(self, block, key):
        return next(field for name, field in self._group(block).fields.items() if name.casefold() == key.casefold())

    def _job(self, name):
        self.win.job.setCurrentIndex(self.win.job.findData(name))

    def _values(self):
        return {(entry.block, entry.key.casefold()): entry.value for entry in self.win.session.calculation.block_options}

    def test_expanded_blocks_share_the_inspector_columns(self):
        dock = self.win.inspector_dock
        scroll = dock.widget()
        content = scroll.widget()
        default_width = dock.width()
        groups = [self._group(name) for name in ("scf", "geom", "scf.trah")]
        fields = [self.win.method, self.win.cores]
        for group in groups:
            fields.extend(group.fields.values())
        labels = {label.buddy(): label for label in content.findChildren(QLabel) if label.buddy() is not None}

        def bounds(widget):
            return QRect(widget.mapTo(content, QPoint(0, 0)), widget.size())

        sizes = (("default", default_width), ("wide", default_width + 160),
                 ("narrow", dock.minimumWidth()))
        for mode, width in sizes:
            with self.subTest(mode=mode, width=width):
                if mode == "narrow":
                    self.win.resize(self.win.minimumWidth(), self.win.minimumHeight())
                dock.setFixedWidth(width)
                for _ in range(3):
                    self.app.processEvents()
                self.assertEqual(dock.width(), width)
                self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                reference = bounds(self.win.method)
                label_left = bounds(labels[self.win.method]).left()
                stacked = bounds(labels[self.win.method]).bottom() < reference.top()
                if mode != "narrow":
                    self.assertFalse(stacked)

                for field in [*fields, *(group.reset for group in groups)]:
                    box = bounds(field)
                    self.assertEqual((box.left(), box.right()), (reference.left(), reference.right()),
                                     field.accessibleName() or field.objectName())
                for field in fields:
                    self.assertIn(field, labels, field.accessibleName())
                    label = labels[field]
                    text = label.text()
                    label_box, editor_box = bounds(label), bounds(field)
                    self.assertEqual(label_box.left(), label_left, text)
                    if stacked:
                        self.assertLess(label_box.bottom(), editor_box.top(), text)
                        self.assertLessEqual(label_box.right(), editor_box.right(), text)
                    else:
                        self.assertLess(label_box.right(), editor_box.left(), text)
                        # Native spin/combo frames may differ by a pixel per edge.
                        self.assertLessEqual(abs(label_box.center().y() - editor_box.center().y()), 2, text)
                    if label.wordWrap():
                        self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()), text)
                        area = label.contentsRect()
                        painted = label.fontMetrics().boundingRect(area, Qt.TextFlag.TextWordWrap, text)
                        self.assertLessEqual(painted.width(), area.width() + 1, text)
                    else:
                        longest = max(label.fontMetrics().horizontalAdvance(line) for line in text.splitlines())
                        self.assertGreaterEqual(label.contentsRect().width(), longest - 1, text)
                if mode == "narrow":
                    self.panel.groups["geom"].fields["AddExtraBonds_MaxLength"].setText("invalid")
                    scroll.ensureWidgetVisible(self.win.validation)
                    for _ in range(3):
                        self.app.processEvents()
                    self.assertFalse(self.win.export_button.isEnabled())
                    self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)

    def test_default_disclosures_and_invalid_draft_stay_distinct(self):
        original = self.win.input_preview.toPlainText()
        self.assertFalse(self.panel.toggle.isChecked())
        self.assertFalse(self.panel.groups)
        self.panel.toggle.click()
        self.assertFalse(self.panel.groups["scf"].toggle.isChecked())
        self.assertFalse(self.panel.groups["scf"].fields)
        value = self._field("scf", "MaxIter")
        self.assertFalse(self.win.dirty)
        self.assertEqual(self.win.input_preview.toPlainText(), original)
        value.setText("180")
        self.assertTrue(self.win.dirty)
        self.assertEqual(self._values(), {("scf", "maxiter"): 180})
        self.assertIn("maxiter 180", self.win.input_preview.toPlainText().lower())
        self.panel.groups["scf"].toggle.click()
        self.panel.toggle.click()
        self.assertIn("1", self.panel.toggle.text())
        self.assertEqual(self._values(), {("scf", "maxiter"): 180})
        value = self._field("scf", "MaxIter")
        value.setText("oops")
        self.assertFalse(self.win.export_button.isEnabled())
        with patch.object(self.win, "_error"), patch.object(QFileDialog, "getSaveFileName") as picker:
            self.assertFalse(self.win.save_project_dialog())
            picker.assert_not_called()
        self.panel.groups["scf"].reset.click()
        self.assertTrue(self.win.export_button.isEnabled())
        self.assertEqual(self.win.input_preview.toPlainText(), original)
        self.assertEqual(self._values(), {})

    def test_switching_job_drops_only_incompatible_edits_and_reports_them(self):
        self._field("scf", "MaxIter").setText("211")
        self._field("geom", "MaxIter").setText("67")
        self.assertEqual(self._values(), {("scf", "maxiter"): 211, ("geom", "maxiter"): 67})
        self._job("SP")
        self.assertNotIn("geom", self.panel.groups)
        self.assertIn("%geom", self.win.statusBar().currentMessage())
        self.assertIn("%geom", self.win.log.toPlainText())
        self.assertNotIn("%geom", self.win.input_preview.toPlainText())
        self.assertTrue(self.win.export_button.isEnabled())
        self.assertEqual(self._values(), {("scf", "maxiter"): 211})
        self._job("OPT")
        self.assertEqual(self._field("geom", "MaxIter").text(), "")
        self.assertNotIn("%geom", self.win.input_preview.toPlainText())

    def test_boolean_default_and_false_are_distinct_and_conflicts_recover(self):
        switch = self._field("scf", "CNVDIIS")
        self.assertEqual(switch.currentData(), "")
        switch.setCurrentIndex(switch.findData("false"))
        self.assertIs(self._values()[("scf", "cnvdiis")], False)
        self.assertIn("cnvdiis false", self.win.input_preview.toPlainText().lower())
        dependent = self._field("scf", "DIISMaxEq")
        dependent.setText("12")
        self.assertFalse(self.win.export_button.isEnabled())
        self.assertIn("CNVDIIS", self.win.validation.text())
        switch.setCurrentIndex(0)
        self.assertTrue(self.win.export_button.isEnabled())
        self.assertEqual(self._values(), {("scf", "diismaxeq"): 12})
        self.assertNotIn("cnvdiis", self.win.input_preview.toPlainText().lower())

    def test_nested_subblock_and_local_memory_estimate(self):
        self.win.cores.setValue(4)
        self.win.maxcore.setValue(1000)
        self._field("scf.trah", "MaxRed").setText("24")
        self.assertIn("→", self.panel.groups["scf.trah"].toggle.text())
        self.assertIn("maxred 24", self.win.input_preview.toPlainText().lower())
        method = "RI-MP2"
        self.win.method_group.setCurrentText(METHODS[method].family)
        self.win.method.setCurrentText(method)
        self._field("mp2", "MaxCore").setText("2300")
        self.assertTrue(self.win.export_button.isEnabled(), self.win.validation.text())
        self.assertIn("9,200", self.win.memory_hint.text())
        self._field("mp2", "MaxCore").clear()
        self.assertIn("4,000", self.win.memory_hint.text())

    def test_solver_block_merges_with_primary_settings_and_loads_collapsed(self):
        method = "EOM-CCSD"
        self.win.method_group.setCurrentText(METHODS[method].family)
        self.win.method.setCurrentText(method)
        self.win.nroots.setValue(3)
        self._field("mdci", "NDav").setText("32")
        self._field("scf", "MaxIter").setText("230")
        preview = self.win.input_preview.toPlainText()
        self.assertEqual(preview.lower().count("%mdci"), 1)
        self.assertIn("ndav 32", preview.lower())
        self.assertIn("nroots 3", preview.lower())
        with TemporaryDirectory() as temp:
            path = str(Path(temp) / "advanced.oview.json")
            with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")):
                self.assertTrue(self.win.save_project_dialog())
            self.win.session = Session()
            self.win._load_controls()
            self.assertFalse(self.panel.toggle.isChecked())
            self.assertFalse(self.panel.drafts)
            with patch.object(QFileDialog, "getOpenFileName", return_value=(path, "")):
                self.win.open_project()
            self.assertFalse(self.win.dirty)
            self.assertFalse(self.panel.toggle.isChecked())
            self.assertEqual(self.win.input_preview.toPlainText(), preview)
            self.assertEqual(self._field("mdci", "NDav").text(), "32")

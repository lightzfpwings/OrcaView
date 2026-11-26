"""Check the calculation controls against the actual scroll viewport."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt, QVariantAnimation
    from PySide6.QtWidgets import QApplication, QLabel
    from orcaview.gui.main_window import MainWindow
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


@unittest.skipUnless(QApplication, "requires Qt")
class InspectorWidthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        for animation in self.window.columns.findChildren(QVariantAnimation):
            animation.setDuration(0)
        self.window.resize(self.window.minimumSize())
        self.window.show()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.dirty = False
        self.window.close()

    def settle(self):
        for _ in range(4):
            self.app.processEvents()

    def test_fields_and_text_fit_collapsed_and_expanded_in_both_workspaces(self):
        w = self.window
        scroll = w.inspector_dock.widget()
        panel = scroll.widget()
        for page in (w.input_page, w.foundation_panel):
            w.workspace_tabs.setCurrentWidget(page)
            for expanded in (False, True):
                with self.subTest(page=page.objectName(), expanded=expanded):
                    w.block_options.toggle.setChecked(expanded)
                    fields = [w.method, w.cores, w.maxcore, w.export_button, w.block_options.toggle]
                    if expanded:
                        group = w.block_options.groups["scf"]
                        group.toggle.setChecked(True)
                        fields.extend((group.toggle, *group.fields.values(), group.reset))
                    self.settle()
                    self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                    self.assertEqual(panel.width(), scroll.viewport().width())
                    for field in fields:
                        left = field.mapTo(panel, QPoint()).x()
                        self.assertGreater(field.width(), 0)
                        self.assertGreaterEqual(left, 0)
                        self.assertLessEqual(left + field.width(), panel.width())
                    for label in (panel.findChild(QLabel, "heading"), w.resource_hint, w.memory_hint, w.validation):
                        area = label.contentsRect()
                        metrics = label.fontMetrics()
                        bounds = metrics.boundingRect(area, Qt.TextFlag.TextWordWrap, label.text())
                        if bounds.width() > area.width():
                            bounds = metrics.boundingRect(area, Qt.TextFlag.TextWrapAnywhere, label.text())
                        self.assertLessEqual(bounds.width(), area.width() + 1, label.text())
                        self.assertLessEqual(bounds.height(), area.height() + 1, label.text())
                    self.assertEqual(w.block_options.toggle.toolTip(), w.block_options.toggle.text())

        bounds = w.validation.geometry(), w.export_button.geometry(), panel.size()
        w.charge.setValue(-1)
        self.settle()
        self.assertFalse(w.export_button.isEnabled())
        self.assertIn("multiplicity", w.validation.toolTip())
        self.assertEqual((w.validation.geometry(), w.export_button.geometry(), panel.size()), bounds)
        w.multiplicity.setValue(2)
        self.settle()
        self.assertTrue(w.export_button.isEnabled())
        self.assertEqual((w.validation.geometry(), w.export_button.geometry(), panel.size()), bounds)

    def test_compact_layout_wraps_a_long_translated_word(self):
        w = self.window
        scroll = w.inspector_dock.widget()
        heading = scroll.widget().findChild(QLabel, "heading")
        heading.setText("Recheneinstellungen")
        w.export_button.setText(".inp exportieren")
        w.workspace_tabs.setCurrentWidget(w.foundation_panel)
        self.settle()
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
        self.assertGreaterEqual(w.export_button.width(), w.export_button.minimumSizeHint().width())
        metrics = heading.fontMetrics()
        area = heading.contentsRect()
        self.assertGreater(metrics.horizontalAdvance(heading.text()), area.width())
        bounds = metrics.boundingRect(area, Qt.TextFlag.TextWrapAnywhere, heading.text())
        self.assertGreaterEqual(area.height(), bounds.height())

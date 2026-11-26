"""Check the Windows inspector's painted arrows and their actual click regions."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication, QComboBox, QDoubleSpinBox, QSpinBox, QStyle, QStyleOptionComboBox,
        QStyleOptionSpinBox, QVBoxLayout, QWidget,
    )
    from orcaview.gui import typography
    from orcaview.gui.inspector_controls import apply_inspector_control_style
    from orcaview.gui.main_window import STYLE
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


@unittest.skipUnless(QApplication, "requires Qt")
class InspectorControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QWidget()
        self.window.setStyleSheet(typography.stylesheet(STYLE))
        panel = QWidget()
        QVBoxLayout(self.window).addWidget(panel)
        with patch.object(typography, "WINDOWS", True):
            apply_inspector_control_style(panel)
        self.layout = QVBoxLayout(panel)
        self.addCleanup(self.window.close)

    def assert_arrow_visible(self, field, rect):
        image = field.grab().toImage()
        ratio = image.devicePixelRatio()
        # Sample the glyph inside the button, excluding borders and adjacent text.
        point = rect.center()
        ink = [image.pixelColor(x, y).lightness()
               for y in range(round((point.y() - 3) * ratio), round((point.y() + 4) * ratio))
               for x in range(round((point.x() - 5) * ratio), round((point.x() + 6) * ratio))]
        self.assertLess(min(ink), 145)

    def test_integer_and_decimal_steppers(self):
        for kind in (QSpinBox, QDoubleSpinBox):
            with self.subTest(kind=kind.__name__):
                field = kind()
                self.layout.addWidget(field)
                field.setValue(10)
                self.window.show()
                self.app.processEvents()
                option = QStyleOptionSpinBox()
                field.initStyleOption(option)
                style = field.style()
                up, down, edit = [style.subControlRect(QStyle.CC_SpinBox, option, part, field)
                                  for part in (QStyle.SC_SpinBoxUp, QStyle.SC_SpinBoxDown, QStyle.SC_SpinBoxEditField)]
                self.assertEqual(up.left(), down.left())
                self.assertLess(up.bottom(), down.top())
                for rect, value in ((up, 11), (down, 10)):
                    self.assertTrue(field.rect().contains(rect))
                    self.assertFalse(edit.intersects(rect))
                    self.assert_arrow_visible(field, rect)
                    QTest.mouseClick(field, Qt.LeftButton, Qt.NoModifier, rect.center())
                    self.assertEqual(field.value(), value)
                QTest.keyClick(field, Qt.Key_Up)
                self.assertEqual(field.value(), 11)

    def test_combo_arrow_opens_list(self):
        field = QComboBox()
        field.addItems(["Gas phase", "Water"])
        self.layout.addWidget(field)
        self.window.show()
        self.app.processEvents()
        option = QStyleOptionComboBox()
        field.initStyleOption(option)
        arrow = field.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxArrow, field)
        edit = field.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField, field)
        self.assertFalse(edit.intersects(arrow))
        self.assert_arrow_visible(field, arrow)
        QTest.mouseClick(field, Qt.LeftButton, Qt.NoModifier, arrow.center())
        self.assertTrue(field.view().isVisible())
        field.hidePopup()

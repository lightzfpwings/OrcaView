"""Exercise the design element popup through real pointer and keyboard events."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit, QTableWidget
    from orcaview.gui.main_window import MainWindow
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    MainWindow = None


@unittest.skipIf(MainWindow is None, "requires Qt")
class ElementPickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.resize(self.window.minimumSize())
        self.window.show()
        self.design = self.window.design_panel
        self.window.workspace_tabs.setCurrentWidget(self.design)
        self.combo = self.design.element
        self.app.processEvents()
        self.addCleanup(self.window.close)

    def open(self):
        QTest.mouseClick(self.combo, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        table = self.combo.findChild(QTableWidget, "periodicTable")
        self.assertTrue(table.isVisible())
        return table

    def test_all_elements_visible_in_period_and_group_positions(self):
        table = self.open()
        data = {}
        for row in range(table.rowCount()):
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
                    continue
                data[item.text()] = (item.data(Qt.ItemDataRole.UserRole), row, col)
                self.assertTrue(table.viewport().rect().contains(table.visualItemRect(item)), item.text())
        self.assertEqual(sorted(number for number, _, _ in data.values()), list(range(1, 119)))
        self.assertEqual(data["He"], (2, 0, 17))
        self.assertEqual(data["Fe"], (26, 3, 7))
        self.assertEqual(data["La"], (57, 7, 2))
        self.assertEqual(data["Lr"], (103, 8, 16))
        self.assertEqual(data["Og"], (118, 6, 17))
        self.assertTrue(self.combo.screen().availableGeometry().contains(table.window().frameGeometry()))
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton,
                         pos=table.visualItemRect(table.item(8, 16)).center())
        self.assertEqual(self.combo.currentText(), "Lr")
        self.assertEqual(self.design.canvas.tool, "atom")
        self.assertFalse(table.isVisible())

    def test_numeric_and_symbol_search_escape_and_bond_tool(self):
        self.design.findChild(type(self.design.atom_tool), "designBond2").click()
        for query, symbol in (("118", "Og"), ("cl", "Cl")):
            table = self.open()
            search = self.combo.findChild(QLineEdit, "elementSearch")
            QTest.keyClicks(search, query)
            QTest.keyClick(search, Qt.Key.Key_Return)
            self.assertEqual(self.combo.currentText(), symbol)
            self.assertEqual(self.design.canvas.tool, "bond")
            self.assertFalse(table.isVisible())
        table = self.open()
        search = self.combo.findChild(QLineEdit, "elementSearch")
        QTest.keyClicks(search, "999")
        QTest.keyClick(search, Qt.Key.Key_Return)
        self.assertTrue(table.isVisible())
        QTest.keyClick(search, Qt.Key.Key_Escape)
        self.assertFalse(table.isVisible())
        self.assertEqual(self.combo.currentText(), "Cl")

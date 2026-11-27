"""Selection, clipboard and read-only behavior of the result browser."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractItemView, QApplication, QStyleOptionViewItem, QTableWidgetSelectionRange
    from orcaview.core.provenance import ArtifactRef
    from orcaview.gui.foundation_panel import FoundationPanel
    from orcaview.orca.log_properties import LogProperty
    from orcaview.orca.log_report import LogReport
    from orcaview.orca.log_spectra import SpectrumTable
    HAS_QT = True
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'Optional Qt dependency is not installed')
class ResultGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = FoundationPanel()
        self.panel.resize(1030, 540)
        props = (LogProperty('Electronic energy', 'Final single-point energy', -76.1754831, "Eh", 18),
                 LogProperty('Electric properties', 'Dipole magnitude', 0.0, "Debye", 30, "SCF"),
                 LogProperty('Electronic energy', "HOMO", -7.81, "eV", 41))
        spectrum = SpectrumTable("nmr", 'NMR shielding', ('Atom', 'Shielding / ppm'), (("1 O", 0.0),), 53)
        report = LogReport(ArtifactRef.from_bytes(b"fixture", "orca-out", "/data/test.out"),
                           props, (spectrum,), 'Normal termination')
        self.panel.set_log_report(report, standalone=True)
        self.panel.show()
        self.panel.activateWindow()
        self.app.processEvents()
        self.addCleanup(self.panel.close)
        self.table = self.panel.datasets

    def test_tsv_selection_and_entire_table(self):
        table = self.table
        table.setFocus()
        table.setCurrentCell(0, 3)
        table.clearSelection()
        self.assertEqual(table.columnCount(), 4)
        table.setRangeSelected(QTableWidgetSelectionRange(0, 0, 0, 3), True)
        QTest.keySequence(table, QKeySequence.StandardKey.Copy)
        self.assertEqual(self.app.clipboard().text(), 'Final single-point energy\t-76.1754831 Eh\tDipole magnitude\t0.0 Debye')
        whole = next(a for a in table.actions() if 'entire table' in a.text())
        whole.trigger()
        self.assertEqual(self.app.clipboard().text().splitlines(), [
            'Name\tResult\tName\tResult', 'Final single-point energy\t-76.1754831 Eh\tDipole magnitude\t0.0 Debye',
            "HOMO\t-7.81 eV\t\t",
        ])
        self.assertEqual(self.panel.table_title.text(), 'Dipole magnitude')
        self.assertIn("SCF", table.item(0, 2).toolTip())
        self.assertIn("SCF", self.panel.details.text())

    def test_matching_labels_keep_temperature_in_each_row(self):
        temperatures = ("298.15 K · 1 atm", "350.0 K · 1 atm")
        properties = tuple(LogProperty('Thermochemistry', 'Enthalpy H', -70.0, "Eh", n + 1, temp)
                           for n, temp in enumerate(temperatures))
        report = LogReport(ArtifactRef.from_bytes(b"thermo", "orca-out", "/data/thermo.log"),
                           properties, (), 'Normal termination')
        self.panel.set_log_report(report, standalone=True)
        self.assertEqual(self.table.rowCount(), 1)
        self.assertEqual([self.table.item(0, col).text() for col in range(4)],
                         ['Enthalpy H (298.15 K)', "-70.0 Eh", 'Enthalpy H (350.0 K)', "-70.0 Eh"])
        for column, temp in zip((0, 2), temperatures):
            self.assertIn(temp, self.table.item(0, column).toolTip())

    def test_four_visible_columns_share_width_and_alignment(self):
        table = self.table
        self.assertEqual(table.horizontalHeader().defaultAlignment(), Qt.AlignmentFlag.AlignCenter)
        for width in (850, 1080):
            self.panel.resize(width, 530)
            self.app.processEvents()
            widths = [table.columnWidth(col) for col in range(4)]
            self.assertLessEqual(max(widths) - min(widths), 1)
            self.assertEqual(sum(widths), table.viewport().width())
            for row in range(table.rowCount()):
                for col in range(4):
                    item = table.item(row, col)
                    if item.text():
                        self.assertEqual(item.textAlignment(), Qt.AlignmentFlag.AlignCenter)
                    else:
                        self.assertEqual(item.flags(), Qt.ItemFlag.NoItemFlags)

    def test_compact_number_keeps_original_precision_for_copy(self):
        table = self.table
        option = QStyleOptionViewItem()
        option.initFrom(table)
        option.rect = QRect(0, 0, 62, 28)
        index = table.model().index(0, 1)
        table.itemDelegateForColumn(1).initStyleOption(option, index)
        self.assertNotEqual(option.text, index.data())
        shown_value, shown_unit = option.text.split()
        self.assertAlmostEqual(float(shown_value), -76.1754831, delta=0.01)
        self.assertEqual(shown_unit, "Eh")
        self.assertEqual(index.data(), "-76.1754831 Eh")
        self.assertIn(index.data(), index.data(Qt.ItemDataRole.ToolTipRole))

    def test_shift_navigation_preserves_multi_selection_and_data(self):
        table = self.table
        table.setFocus()
        table.setCurrentCell(0, 1)
        QTest.keyClick(table, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
        QTest.keySequence(table, QKeySequence.StandardKey.Copy)
        self.assertEqual(self.app.clipboard().text(), "-76.1754831 Eh\n-7.81 eV")
        self.assertFalse(table.item(1, 1).flags() & Qt.ItemFlag.ItemIsEditable)
        self.assertEqual(table.editTriggers(), QAbstractItemView.EditTrigger.NoEditTriggers)
        QTest.keyClick(table, Qt.Key.Key_F2)
        QTest.keyClicks(table, "123")
        self.assertEqual(table.item(1, 1).text(), "-7.81 eV")
        self.assertNotEqual(table.state(), QAbstractItemView.State.EditingState)
        self.panel.spectra.setCurrentItem(self.panel.spectra.topLevelItem(0))
        self.assertEqual(len(table.selectedIndexes()), 0)
        self.assertEqual(self.panel.table_title.text(), 'NMR shielding')
        next(a for a in self.panel.log_table.actions() if 'entire table' in a.text()).trigger()
        self.assertEqual(self.app.clipboard().text(), 'Atom\tShielding / ppm\n1 O\t0.0')

    def test_navigate_between_pairs_in_one_row_and_skip_empty_pair(self):
        table = self.table
        for col, label in ((1, 'Final single-point energy'), (2, 'Dipole magnitude'), (0, 'Final single-point energy'), (3, 'Dipole magnitude')):
            item = table.item(0, col)
            QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton,
                             pos=table.visualItemRect(item).center())
            self.assertEqual(table.currentItem(), item)
            self.assertEqual(self.panel.table_title.text(), label)
        QTest.keyClick(table, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClick(table, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
        QTest.keySequence(table, QKeySequence.StandardKey.Copy)
        self.assertEqual(self.app.clipboard().text(), '-76.1754831 Eh\tDipole magnitude\t0.0 Debye')
        self.assertEqual(self.panel.table_title.text(), 'Final single-point energy')
        unused = table.item(1, 2)
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualItemRect(unused).center())
        self.assertEqual(self.panel.table_title.text(), 'Final single-point energy')

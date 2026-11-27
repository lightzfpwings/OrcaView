"""Optional Qt checks for result binding, atom coordinates and visual selection."""

import math
import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel
    from orcaview.core.provenance import Provenance
    from orcaview.core.results import DatasetAxis, ResultDataset
    from orcaview.gui.main_window import MainWindow
    HAS_QT = True
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'Optional Qt dependency is not installed')
class FoundationGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self._close)
        self.panel = self.window.foundation_panel

    def _close(self):
        self.window.dirty = False
        self.window.close()
        self.app.processEvents()

    def _demo(self):
        self.window.load_foundation_demo()
        self.app.processEvents()
        document = self.window.session.document
        snapshots, datasets = document.records()
        charges = next(data for data in datasets if data.kind == "atomic_charge")
        return document, snapshots, charges

    def test_results_navigation_reuses_rows_and_picks_a_late_result_on_its_frame(self):
        tabs = self.window.workspace_tabs
        document = self.window.session.document
        head = document.head
        tabs.setCurrentWidget(self.panel)
        self.assertEqual(tabs.tabText(tabs.currentIndex()), 'Result')
        inspector = self.panel.inspector_tabs
        self.assertEqual([inspector.tabText(i) for i in range(inspector.count())], ['Overview', 'Source details'])
        first_atom = self.panel.atoms.item(0, 0)
        for _ in range(2):
            tabs.setCurrentIndex(0)
            tabs.setCurrentWidget(self.panel)
            self.assertIs(self.panel.atoms.item(0, 0), first_atom)

        tabs.setCurrentIndex(0)
        frame = document.add_frame(head.ref, "late-frame", head.molecule, head.atom_ids, Provenance("fixture"))
        result = ResultDataset("count", frame.ref, Provenance("fixture"), "int64", (), "1", (7,))
        document.add_dataset(result)
        tabs.setCurrentWidget(self.panel)
        self.assertEqual(document.head.ref, head.ref)
        self.assertEqual(self.panel.selected_snapshot.ref, head.ref)
        self.panel.datasets.setCurrentItem(self.panel._dataset_items[result.dataset_id])
        self.assertEqual(self.panel.selected_snapshot.ref, frame.ref)

    def test_dataset_displays_original_frame_and_missing_values_after_head_reorder(self):
        document, _, data = self._demo()
        head = document.head
        before = document.records()
        self.panel.view_dataset(data.dataset_id)
        self.app.processEvents()
        frame = document.resolve(data.geometry)
        self.assertEqual(self.panel.selected_snapshot, frame)
        self.assertNotEqual(frame.ref, head.ref)
        self.assertEqual(self.panel.viewport.molecule, frame.molecule)
        self.assertEqual(self.panel.atoms.rowCount(), len(frame.atom_ids))
        displayed_ids = tuple(self.panel.atoms.item(row, 0).data(Qt.ItemDataRole.UserRole)
                              for row in range(self.panel.atoms.rowCount()))
        self.assertEqual(displayed_ids, frame.atom_ids)
        by_id = dict(zip(data.axes[0].ids, data.values))
        for row, atom_id in enumerate(displayed_ids):
            shown = self.panel.atoms.item(row, 2).text()
            if by_id[atom_id] is None:
                self.assertIn('Missing', shown)
            else:
                self.assertAlmostEqual(float(shown.split()[0]), by_id[atom_id])
        self.assertEqual(document.records(), before)
        self.assertIs(document.head, head)
        self.assertIn('Synthetic', self.panel.details.text())

    def test_atom_table_and_viewport_share_identity_selection(self):
        document, _, data = self._demo()
        self.panel.view_dataset(data.dataset_id)
        self.app.processEvents()
        table = self.panel.atoms
        table.selectRow(0)
        self.app.processEvents()
        atom_id = table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        frame = document.resolve(data.geometry)
        self.assertEqual(self.panel.viewport.selected, [frame.index_of(atom_id)])

        self.panel.view_geometry(frame.ref)
        self.panel.viewport.repaint()
        self.app.processEvents()
        index = frame.atom_ids.index(atom_id)
        x, y, _, _ = self.panel.viewport._projected[index]
        QTest.mouseClick(self.panel.viewport, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, QPoint(round(x), round(y)))
        self.app.processEvents()
        selected_ids = {table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
                        for item in table.selectionModel().selectedRows()}
        self.assertEqual(selected_ids, {atom_id})

    def test_pair_measurement_follows_selection_and_only_appears_in_overview(self):
        document, _, data = self._demo()
        frame = document.resolve(data.geometry)
        self.panel.view_dataset(data.dataset_id)
        overview = self.panel.inspector_tabs.widget(0)
        measurement = self.panel.bond_length
        self.assertTrue(overview.isAncestorOf(measurement))
        table, viewport = self.panel.atoms, self.panel.viewport

        def check_pair(snapshot):
            self.assertTrue(measurement.isVisible())
            self.assertIs(self.panel.inspector_tabs.currentWidget(), overview)
            shown = measurement.text()
            self.assertIn('Bond length', shown)
            match = re.search(r"(\d+\.\d+)\s*Å", shown)
            self.assertIsNotNone(match, shown)
            first, second = snapshot.molecule.atoms[:2]
            expected = math.hypot(first.x - second.x, first.y - second.y, first.z - second.z)
            self.assertAlmostEqual(float(match[1]), expected, places=4)
            for label in self.window.findChildren(QLabel):
                if label.isVisible() and not overview.isAncestorOf(label):
                    self.assertNotIn(match[1], label.text())
            self.assertNotIn(match[1], self.panel.evidence.toPlainText())

        def click_atom(index):
            viewport.repaint()
            x, y, _, _ = viewport._projected[index]
            QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=QPoint(round(x), round(y)))
            self.app.processEvents()

        before = self.panel.details.text()
        evidence = self.panel.evidence.toPlainText()
        self.panel.inspector_tabs.setCurrentIndex(1)
        for row, modifier in enumerate((Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier)):
            item = table.item(row, 0)
            table.scrollToItem(item)
            QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, modifier, table.visualItemRect(item).center())
            if row == 0:
                self.assertFalse(measurement.isVisibleTo(overview))
        check_pair(frame)
        self.assertEqual(viewport.selected, [0, 1])
        self.assertEqual(self.panel.details.text(), before)
        self.assertEqual(self.panel.evidence.toPlainText(), evidence)

        click_atom(1)
        self.assertFalse(measurement.isVisible())
        click_atom(1)
        check_pair(frame)
        self.panel.inspector_tabs.setCurrentIndex(1)
        self.panel.view_dataset(data.dataset_id)
        self.assertEqual(self.panel.inspector_tabs.currentIndex(), 1)
        self.panel.view_geometry(document.head.ref)
        self.assertFalse(measurement.isVisibleTo(overview))
        geometry_details = self.panel.details.text()
        click_atom(0)
        click_atom(1)
        check_pair(document.head)
        self.assertEqual(self.panel.details.text(), geometry_details)
        table.clearSelection()
        self.assertFalse(measurement.isVisible())

    def test_coordinate_columns_keep_equal_widths_and_align_signed_values(self):
        document, _, data = self._demo()
        frame = document.resolve(data.geometry)
        table = self.panel.atoms
        for has_results in (False, True):
            if has_results:
                self.panel.view_dataset(data.dataset_id)
            else:
                self.panel.view_geometry(frame.ref)
            self.app.processEvents()
            self.assertEqual(table.isColumnHidden(2), not has_results)
            self.assertEqual(table.columnWidth(0), table.columnWidth(1))
            self.assertLess(table.columnWidth(0), table.columnWidth(3))
            self.assertEqual(table.columnWidth(3), table.columnWidth(4))
            self.assertEqual(table.columnWidth(4), table.columnWidth(5))
            for row, atom in enumerate(frame.molecule.atoms):
                for column in (0, 1):
                    self.assertEqual(table.item(row, column).textAlignment(), Qt.AlignmentFlag.AlignCenter)
                self.assertEqual([table.item(row, col).text() for col in (3, 4, 5)],
                                 [f"{value:.6f}" for value in (atom.x, atom.y, atom.z)])

        # These two hydrogen atoms have the same |X|. Compare the rendered
        # numerals so a leading minus cannot shift the decimal point.
        self.assertEqual(frame.molecule.atoms[1].x, -frame.molecule.atoms[2].x)
        table.clearSelection()
        table.scrollToItem(table.item(2, 3))
        self.panel.datasets.setFocus()
        self.app.processEvents()
        edges = []
        for row in (1, 2):
            rect = table.visualItemRect(table.item(row, 3)).adjusted(2, 2, -2, -2)
            self.assertTrue(table.viewport().rect().contains(rect))
            image = table.viewport().grab(rect).toImage()
            ink = [x for x in range(image.width()) if any(
                image.pixelColor(x, y).lightness() < 145 for y in range(image.height()))]
            self.assertTrue(ink)
            edges.append((ink[0], ink[-1]))
        positive, negative = edges
        self.assertLess(negative[0], positive[0])
        self.assertLessEqual(abs(negative[1] - positive[1]), 1)

    def test_default_workspace_and_demo_return_to_current_input_geometry(self):
        default_document = self.window.session.document
        self.assertEqual(default_document.records()[1], ())
        self.assertEqual(self.panel.selected_snapshot, default_document.head)
        document, _, data = self._demo()
        self.assertTrue(self.window.dirty)
        self.assertIs(self.window.workspace_tabs.currentWidget(), self.panel)
        self.panel.view_dataset(data.dataset_id)
        structure_index = next(index for index in range(self.window.workspace_tabs.count())
                               if self.window.workspace_tabs.widget(index) is not self.panel)
        self.window.workspace_tabs.setCurrentIndex(structure_index)
        self.app.processEvents()
        self.assertEqual(self.window.viewport.molecule, document.head.molecule)
        self.assertEqual(self.window.input_preview.toPlainText(), self.window.session.input_text())
        self.assertNotEqual(self.panel.selected_snapshot.ref, document.head.ref)
        for dock in (self.window.tree_dock, self.window.inspector_dock, self.window.bottom_dock):
            self.assertFalse(dock.isHidden())

    def test_reversed_integer_axis_preserves_large_integer_precision(self):
        document = self.window.session.document
        geometry = document.head
        values = tuple(2**60 + index for index in range(len(geometry.atom_ids)))
        vector = ResultDataset(
            "counts", geometry.ref, Provenance("fixture"), "int64", (len(values),), "1",
            values, (DatasetAxis("atom", geometry.atom_ids[::-1]),),
        )
        scalar = ResultDataset("count", geometry.ref, Provenance("fixture"), "int64", (), "1", (2**60 + 3,))
        document.add_dataset(vector)
        document.add_dataset(scalar)
        self.panel.set_document(document)
        self.panel.view_dataset(vector.dataset_id)
        by_id = dict(zip(vector.axes[0].ids, vector.values))
        for row in range(self.panel.atoms.rowCount()):
            atom_id = self.panel.atoms.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self.assertEqual(self.panel.atoms.item(row, 2).text(), str(by_id[atom_id]))
        self.panel.view_dataset(scalar.dataset_id)
        self.assertIn(str(2**60 + 3), self.panel.details.text())

if __name__ == "__main__":
    unittest.main()

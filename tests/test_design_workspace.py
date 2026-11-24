"""Exercise structure design through the same controls and file dialogs used at the desktop."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QSplitter
    from orcaview.gui.main_window import MainWindow
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    MainWindow = None


@unittest.skipIf(MainWindow is None, "requires Qt")
class DesignWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.close_window)
        self.tabs = self.window.workspace_tabs
        self.design = self.window.design_panel
        self.canvas = self.design.canvas

    def close_window(self):
        self.window.dirty = False
        self.window.close()
        self.app.processEvents()

    def activate(self, page):
        self.tabs.setCurrentWidget(page)
        self.app.processEvents()

    def click_tool(self, name):
        widget = self.design.findChild(QAbstractButton, name)
        self.assertIsNotNone(widget, name)
        self.assertTrue(widget.isVisible() and widget.isEnabled(), name)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        self.app.processEvents()

    def click_canvas(self, position):
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=position)
        self.app.processEvents()

    def click_atom(self, index):
        self.click_canvas(self.canvas.atom_position(index).toPoint())

    def drag_from_atom(self, index, delta):
        start = self.canvas.atom_position(index).toPoint()
        end = start + delta
        self.assertTrue(self.canvas.rect().contains(end))
        QTest.mousePress(self.canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(self.canvas, end)
        QTest.mouseRelease(self.canvas, Qt.MouseButton.LeftButton, pos=end)
        self.app.processEvents()

    def choose_element(self, symbol):
        self.design.findChild(QComboBox, "designElement").setCurrentText(symbol)
        self.click_tool("designAtom")

    def test_design_split_starts_equal_and_double_click_restores_only_the_layout(self):
        self.activate(self.design)
        splitter = self.design.findChild(QSplitter, "designSplitter")
        self.assertEqual(splitter.handleWidth(), 1)
        for width in (1120, 1441):
            self.window.resize(width, self.window.height())
            self.app.processEvents()
            left, right = splitter.sizes()
            self.assertLessEqual(abs(left - right), 1)
        splitter.moveSplitter(left + 85, 1)
        self.app.processEvents()
        self.assertGreater(splitter.sizes()[0] - splitter.sizes()[1], 60)
        self.activate(self.window.input_page)
        self.activate(self.design)
        self.assertGreater(splitter.sizes()[0] - splitter.sizes()[1], 60)
        view = self.design.viewport
        view.rotate_view("x", 25)
        orientation = view.camera_transform(0, 1, 0)
        head = self.window.session.document.head
        handle = splitter.handle(1)
        QTest.mouseDClick(handle, Qt.MouseButton.LeftButton, pos=handle.rect().center())
        self.app.processEvents()
        left, right = splitter.sizes()
        self.assertLessEqual(abs(left - right), 1)
        self.assertEqual(view.camera_transform(0, 1, 0), orientation)
        self.assertIs(self.window.session.document.head, head)

    def test_drawing_keeps_the_preview_camera_when_the_principal_axis_changes(self):
        self.activate(self.design)
        self.click_tool("designNew")
        view = self.design.viewport
        view.rotate_view("x", 28)
        view.zoom = 1.5
        axes = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        before = [view.transform(*axis) for axis in axes]
        self.click_tool("designBond1")
        self.drag_from_atom(0, QPoint(72, -40))
        self.assertIsNotNone(view.principal_axis.direction)
        self.assertEqual(view.zoom, 1.5)
        for axis, original in zip(axes, before):
            for actual, expected in zip(view.transform(*axis), original):
                self.assertAlmostEqual(actual, expected)

    def test_edit_loaded_3d_geometry_and_save_reopen(self):
        self.assertEqual([self.tabs.tabText(i) for i in range(self.tabs.count())], ["Input", "Design", "Result"])
        source = Path("examples/water.xyz").resolve()
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(source), "")):
            self.window.open_file()
        self.activate(self.design)
        document = self.window.session.document
        old = document.head
        self.assertEqual(old.molecule.atoms[1].z, 0.586541)
        self.choose_element("S")
        self.click_atom(0)
        edited = document.head
        self.assertEqual(edited.molecule.atoms[0].element, "S")
        self.assertEqual(edited.atom_ids, old.atom_ids)
        self.assertEqual(edited.molecule.atoms[1:], old.molecule.atoms[1:])
        self.assertTrue(self.window.dirty)
        self.assertEqual(self.design.viewport.molecule, edited.molecule)

        self.activate(self.window.input_page)
        self.assertEqual(self.window.viewport.molecule, edited.molecule)
        expected_input = self.window.session.input_text()
        self.assertEqual(self.window.input_preview.toPlainText(), expected_input)
        self.activate(self.window.foundation_panel)
        self.assertEqual(self.window.foundation_panel.viewport.molecule, edited.molecule)
        self.activate(self.design)
        self.click_tool("designUndo")
        self.assertEqual(document.head.molecule, old.molecule)
        self.click_tool("designRedo")
        self.assertEqual(document.head.molecule, edited.molecule)

        with TemporaryDirectory() as temp:
            project = Path(temp) / "design.oview.json"
            inp = Path(temp) / "design.inp"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(inp), "")):
                self.window.export_input()
            self.assertEqual(inp.read_text(), expected_input)
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(project), "")):
                self.assertTrue(self.window.save_project_dialog())
            self.assertFalse(self.window.dirty)
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(project), "")):
                self.window.open_project()
            self.activate(self.design)
            restored = self.window.session.document.head
            self.assertEqual(restored.molecule, edited.molecule)
            self.assertEqual(restored.atom_ids, edited.atom_ids)
            self.assertEqual(self.design.viewport.molecule, restored.molecule)

    def test_build_bonds_move_and_delete_atom(self):
        self.activate(self.design)
        self.click_tool("designNew")
        document = self.window.session.document
        first_id, = document.head.atom_ids
        self.choose_element("O")
        self.click_canvas(QPoint(self.canvas.width() // 4, self.canvas.height() // 3))
        self.assertEqual([a.element for a in document.head.molecule.atoms], ["C", "O"])
        atom_ids = document.head.atom_ids
        self.assertEqual(atom_ids[0], first_id)
        for order in (1, 2, 3, 0):
            with self.subTest(bond_order=order):
                self.click_tool("designBond" + str(order))
                self.click_atom(0)
                self.click_atom(1)
                bonds = document.head.molecule.bonds
                if order:
                    self.assertEqual([(bond.a, bond.b, bond.order) for bond in bonds], [(0, 1, order)])
                else:
                    self.assertEqual(bonds, ())

        self.click_tool("designUndo")
        self.assertEqual(document.head.molecule.bonds[0].order, 3)
        self.click_tool("designSelect")
        self.click_atom(1)
        before_move = document.head
        self.design.findChild(QDoubleSpinBox, "designZ").setValue(1.25)
        self.click_tool("designApplyPosition")
        self.assertEqual(document.head.molecule.atoms[1].z, 1.25)
        self.assertEqual(document.head.atom_ids, atom_ids)
        self.assertEqual(document.head.molecule.atoms[0], before_move.molecule.atoms[0])
        moved = document.head.molecule
        self.click_tool("designDelete")
        self.assertEqual(document.head.atom_ids, (first_id,))
        self.assertEqual(document.head.molecule.bonds, ())
        self.click_tool("designUndo")
        self.assertEqual(document.head.atom_ids, atom_ids)
        self.assertEqual(document.head.molecule, moved)

    def test_drag_in_xy_sketch_keeps_z_and_original_atom_identity(self):
        self.activate(self.design)
        self.click_tool("designNew")
        document = self.window.session.document
        self.assertIsNone(self.design.findChild(QComboBox, "designPlane"))
        self.click_tool("designSelect")
        self.click_atom(0)
        self.design.findChild(QDoubleSpinBox, "designZ").setValue(0.8)
        self.click_tool("designApplyPosition")
        before = document.head
        self.drag_from_atom(0, QPoint(19, -27))
        after = document.head
        self.assertEqual(after.atom_ids, before.atom_ids)
        self.assertEqual(after.molecule.atoms[0].z, 0.8)
        self.assertGreater(after.molecule.atoms[0].x, before.molecule.atoms[0].x)
        self.assertGreater(after.molecule.atoms[0].y, before.molecule.atoms[0].y)
        self.click_tool("designUndo")
        self.assertEqual(document.head.molecule, before.molecule)

    def test_draw_two_connected_segments_and_undo_one_gesture(self):
        self.activate(self.design)
        self.click_tool("designNew")
        document = self.window.session.document
        seed = document.head
        self.click_tool("designBond1")
        self.drag_from_atom(0, QPoint(60, -30))
        middle = document.head
        self.assertEqual(middle.parent, seed.ref)
        self.assertEqual([atom.element for atom in middle.molecule.atoms], ["C", "C"])
        self.assertEqual([(b.a, b.b, b.order) for b in middle.molecule.bonds], [(0, 1, 1)])
        self.design.findChild(QComboBox, "designElement").setCurrentText("O")
        self.click_tool("designBond2")
        self.drag_from_atom(1, QPoint(45, 35))
        end = document.head
        self.assertEqual(end.parent, middle.ref)
        self.assertEqual([atom.element for atom in end.molecule.atoms], ["C", "C", "O"])
        self.assertEqual([(b.a, b.b, b.order) for b in end.molecule.bonds], [(0, 1, 1), (1, 2, 2)])
        self.click_tool("designUndo")
        self.assertEqual(document.head.molecule, middle.molecule)
        self.assertEqual(document.head.atom_ids, middle.atom_ids)
        self.click_tool("designRedo")
        self.assertEqual(document.head.molecule, end.molecule)
        self.assertEqual(document.head.atom_ids, end.atom_ids)

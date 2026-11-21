"""Select atoms by dragging across the sketch and the 3D preview."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractButton, QApplication
    from orcaview.gui.design_panel import DesignPanel
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    DesignPanel = None

from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, Molecule


@unittest.skipIf(DesignPanel is None, "requires Qt")
class DesignMarqueeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        molecule = Molecule("selection",
                            (Atom("C", -2, -1, 0), Atom("O", 0, -1, 0), Atom("Si", 2, -1, 0),
                             Atom("S", 0, 1.5, 0), Atom("C", 2, 1.5, 0)),
                            (Bond(0, 1), Bond(1, 2), Bond(1, 3), Bond(3, 4)), bonds_explicit=True)
        self.document = Session(molecule).document
        self.panel = DesignPanel()
        self.addCleanup(self.panel.close)
        self.panel.resize(1200, 650)
        self.panel.set_document(self.document)
        self.panel.show()
        self.app.processEvents()
        self.canvas, self.view = self.panel.canvas, self.panel.viewport

    def drag(self, widget, start, end, *, shift=False, right=False):
        button = Qt.MouseButton.RightButton if right else Qt.MouseButton.LeftButton
        modifiers = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
        self.assertTrue(widget.rect().contains(start) and widget.rect().contains(end))
        QTest.mousePress(widget, button, modifiers, pos=start)
        QTest.mouseMove(widget, end)
        QTest.mouseRelease(widget, button, modifiers, pos=end)
        self.app.processEvents()

    def sketch_box(self, *indices):
        points = [self.canvas.atom_position(i).toPoint() for i in indices]
        # Keep the start of the gesture outside the atom hit target.
        return (QPoint(min(p.x() for p in points) - 21, min(p.y() for p in points) - 21),
                QPoint(max(p.x() for p in points) + 21, max(p.y() for p in points) + 21))

    def assert_selection(self, expected):
        self.assertEqual(self.canvas.selected, expected)
        self.assertEqual(self.view.selected, expected)
        self.assertEqual(self.panel.editor.selection.atom_ids,
                         tuple(self.document.head.atom_ids[i] for i in expected))

    def test_all_drag_directions_replace_selection_and_empty_boxes_follow_modifiers(self):
        low, high = self.sketch_box(0, 1)
        for left_to_right in (True, False):
            for top_to_bottom in (True, False):
                with self.subTest(left_to_right=left_to_right, top_to_bottom=top_to_bottom):
                    QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton,
                                     pos=self.canvas.atom_position(4).toPoint())
                    self.assert_selection([4])
                    start = QPoint(low.x() if left_to_right else high.x(), low.y() if top_to_bottom else high.y())
                    end = QPoint(high.x() if left_to_right else low.x(), high.y() if top_to_bottom else low.y())
                    self.drag(self.canvas, start, end)
                    self.assert_selection([0, 1])
        self.assertTrue(self.panel.bond_length.controls.isVisible())
        self.drag(self.canvas, QPoint(12, 15), QPoint(46, 42), shift=True)
        self.assert_selection([0, 1])
        self.drag(self.canvas, QPoint(12, 15), QPoint(46, 42))
        self.assert_selection([])
        self.assertEqual(self.document.head.ref.revision, 1)

    def test_add_to_selection_then_delete_and_undo_as_one_edit(self):
        original = self.document.head
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=self.canvas.atom_position(4).toPoint())
        self.assertTrue(all(field.isEnabled() for field in self.panel.coordinates))
        self.drag(self.canvas, *self.sketch_box(0, 1), shift=True)
        self.drag(self.canvas, *self.sketch_box(1), shift=True)
        self.assert_selection([4, 0, 1])
        self.assertFalse(any(field.isEnabled() for field in self.panel.coordinates))
        self.assertFalse(self.panel.bond_length.controls.isVisible())
        self.assertTrue(self.panel.delete_button.isEnabled())
        QTest.mouseClick(self.panel.delete_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.document.head.atom_ids, (original.atom_ids[2], original.atom_ids[3]))
        QTest.mouseClick(self.panel.undo_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.document.head.atom_ids, original.atom_ids)
        self.assertEqual(self.document.head.molecule, original.molecule)

    def test_delete_entire_selection_and_start_again_with_one_atom(self):
        original = self.document.head
        self.drag(self.canvas, *self.sketch_box(*range(len(original.atom_ids))))
        self.assertTrue(self.panel.delete_button.isEnabled())
        QTest.keyClick(self.canvas, Qt.Key.Key_Delete)
        self.app.processEvents()
        self.assertEqual(self.document.head.atom_ids, ())
        self.assert_selection([])
        self.assertIsNone(self.view.principal_axis)
        self.assertEqual(self.view.symmetry_label, "")
        self.assertEqual(self.view._projected, [])
        self.assertEqual(self.view.bonds, ())
        self.assertFalse(self.panel.problems.isVisible())
        for control in (self.panel.delete_button, self.panel.hydrogens, self.panel.atom_choice,
                        self.panel.clean_2d, self.panel.optimize_3d, *self.panel.coordinates):
            self.assertFalse(control.isEnabled())

        self.panel.element.setCurrentText("O")
        QTest.mouseClick(self.panel.atom_tool, Qt.MouseButton.LeftButton)
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=self.canvas.rect().center())
        first = self.document.head
        self.assertEqual([a.element for a in first.molecule.atoms], ["O"])
        self.assertEqual(first.molecule.atoms[0].z, 0.0)
        self.assert_selection([0])
        self.assertTrue(self.panel.hydrogens.isEnabled())
        self.assertTrue(self.panel.delete_button.isEnabled())
        self.panel.undo_button.click()
        self.assertEqual(self.document.head.atom_ids, ())
        self.panel.undo_button.click()
        self.assertEqual(self.document.head.molecule, original.molecule)
        self.assertEqual(self.document.head.atom_ids, original.atom_ids)
        self.panel.redo_button.click()
        self.assertEqual(self.document.head.atom_ids, ())
        self.panel.redo_button.click()
        self.assertEqual(self.document.head.atom_ids, first.atom_ids)

    def test_open_empty_design_and_start_with_a_benzene_ring(self):
        self.drag(self.canvas, *self.sketch_box(*range(len(self.document.head.atom_ids))))
        QTest.mouseClick(self.panel.delete_button, Qt.MouseButton.LeftButton)
        current = DesignPanel()
        self.addCleanup(current.close)
        current.set_document(self.document)
        current.resize(1000, 650)
        current.show()
        self.app.processEvents()
        current.canvas.fit()
        current.ring_menu.actions()[-1].trigger()
        QTest.mouseClick(current.canvas, Qt.MouseButton.LeftButton, pos=current.canvas.rect().center())
        ring = self.document.head
        self.assertEqual(len(ring.atom_ids), 6)
        self.assertEqual([bond.order for bond in ring.molecule.bonds], [2, 1, 2, 1, 2, 1])
        self.assertTrue(all(atom.z == 0. for atom in ring.molecule.atoms))
        current.undo_button.click()
        self.assertEqual(self.document.head.atom_ids, ())

    def test_editing_tools_do_not_treat_empty_space_drags_as_selection(self):
        head = self.document.head
        start, end = self.sketch_box(0, 1)
        QTest.mousePress(self.canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(self.canvas, end)
        self.panel.atom_tool.click()
        QTest.mouseRelease(self.canvas, Qt.MouseButton.LeftButton, pos=end)
        self.assert_selection([])
        self.assertIs(self.document.head, head)
        for tool in ("designAtom", "designBond1"):
            with self.subTest(tool=tool):
                QTest.mouseClick(self.panel.findChild(QAbstractButton, tool), Qt.MouseButton.LeftButton)
                self.drag(self.canvas, *self.sketch_box(0, 1))
                self.assert_selection([])
                self.assertIs(self.document.head, head)

    def test_3d_shift_drag_adds_projected_atoms_without_moving_the_camera(self):
        view = self.view
        head = self.document.head
        axes = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        def orientation():
            return tuple(view.camera_transform(*axis) for axis in axes)
        before = orientation()
        self.drag(view, QPoint(55, 60), QPoint(82, 74))
        rotated = orientation()
        self.assertNotEqual(rotated, before)
        before_pan = tuple(view._projected)
        self.drag(view, QPoint(45, 55), QPoint(72, 69), right=True)
        positions = tuple(view._projected)
        self.assertEqual(orientation(), rotated)
        for old, moved in zip(before_pan, positions):
            self.assertAlmostEqual(moved[0] - old[0], 27)
            self.assertAlmostEqual(moved[1] - old[1], 14)
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=self.canvas.atom_position(4).toPoint())
        QTest.mouseClick(self.panel.atom_tool, Qt.MouseButton.LeftButton)
        x0, y0 = positions[0][:2]
        x1, y1 = positions[1][:2]
        start = QPoint(round(max(x0, x1) + 23), round(max(y0, y1) + 23))
        end = QPoint(round(min(x0, x1) - 23), round(min(y0, y1) - 23))
        self.drag(view, start, end, shift=True)
        self.assert_selection([4, 0, 1])
        self.drag(view, QPoint(12, 15), QPoint(46, 42), shift=True)
        self.assert_selection([4, 0, 1])
        self.assertEqual(tuple(view._projected), positions)
        self.assertEqual(orientation(), rotated)
        self.assertIs(self.document.head, head)

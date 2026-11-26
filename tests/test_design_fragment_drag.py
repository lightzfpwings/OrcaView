"""Drag one disconnected molecule through the design workspace's two views."""

from itertools import combinations
import math
from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.design_panel import DesignPanel
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    DesignPanel = None

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.geometry import display_bonds, infer_bonds
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.editing import SetSketchLayout


@unittest.skipIf(DesignPanel is None, "requires Qt")
class FragmentDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Indices 0, 2, 4 are water; indices 1, 3 are hydrogen fluoride.
        self.atoms = (Atom("H", -2.5, .7, .3), Atom("F", 2.1, -.5, .6),
                      Atom("O", -1.9, 0, 0), Atom("H", 2.8, -.9, .2),
                      Atom("H", -1.2, .5, -.45))
        self.bonds = (Bond(0, 2), Bond(2, 4), Bond(1, 3))
        self.panel = DesignPanel()
        self.addCleanup(self.panel.close)
        self.panel.resize(1160, 680)
        self.use_molecule(self.bonds, explicit=True)
        self.panel.show()
        self.app.processEvents()
        self.canvas, self.view = self.panel.canvas, self.panel.viewport

    def use_molecule(self, bonds, *, explicit):
        self.session = Session(Molecule("Water and HF", self.atoms, bonds, bonds_explicit=explicit))
        self.doc = self.session.document
        self.panel.set_document(self.doc)
        self.app.processEvents()

    def drag(self, widget, start, delta, *, alt=True, cancel=False, button=None):
        if button is None:
            button = Qt.MouseButton.RightButton if alt else Qt.MouseButton.LeftButton
        start = start.toPoint()
        end = start + delta
        self.assertTrue(widget.rect().contains(start) and widget.rect().contains(end))
        modifier = Qt.KeyboardModifier.AltModifier if alt else Qt.KeyboardModifier.NoModifier
        before = self.doc.head
        QTest.mousePress(widget, button, modifier, start)
        QTest.mouseMove(widget, start + delta / 2)
        QTest.mouseMove(widget, end)
        self.app.processEvents()
        self.assertIs(self.doc.head, before)
        preview = tuple(widget._projected) if widget is self.view else None
        if cancel:
            QTest.keyClick(widget, Qt.Key.Key_Escape)
        QTest.mouseRelease(widget, button, modifier, end)
        self.app.processEvents()
        return preview

    def assert_translation(self, before, after, moving, delta):
        for index, (old, new) in enumerate(zip(before, after)):
            with self.subTest(atom=index):
                if index not in moving:
                    self.assertEqual(new, old)
                    continue
                for a, b, d in zip(old, new, delta):
                    self.assertAlmostEqual(b - a, d)

    def assert_history(self, before, after):
        self.assertEqual(after.ref.revision, before.ref.revision + 1)
        self.assertEqual(after.atom_ids, before.atom_ids)
        self.assertEqual(display_bonds(after.molecule), display_bonds(before.molecule))
        self.panel.undo_button.click()
        self.assertEqual(self.doc.head.molecule, before.molecule)
        self.assertEqual(self.doc.head.sketch_xy, before.sketch_xy)
        self.panel.redo_button.click()
        self.assertEqual(self.doc.head.molecule, after.molecule)
        self.assertEqual(self.doc.head.sketch_xy, after.sketch_xy)

    def test_sketch_bond_drag_moves_physical_xy_and_the_detached_drawing(self):
        xy = ((-2.7, 1.2), (1.8, -.8), (-1.5, .4), (2.8, -.3), (-.9, 1.2))
        self.panel._execute(SetSketchLayout(xy))
        before = self.doc.head
        midpoint = (self.canvas.atom_position(0) + self.canvas.atom_position(2)) / 2
        self.assertEqual(self.canvas._target_at(midpoint), (0, 2))
        delta = QPoint(-24, 19)
        scale = self.canvas._scale()
        self.drag(self.canvas, midpoint, delta)
        after = self.doc.head
        shift = (delta.x() / scale, -delta.y() / scale)
        self.assert_translation(before.coordinates(), after.coordinates(), (0, 2, 4), (*shift, 0.))
        self.assert_translation(before.sketch_xy, after.sketch_xy, (0, 2, 4), shift)
        self.assert_history(before, after)
        with TemporaryDirectory() as t:
            path = Path(t) / "mixture.oview.json"
            save_project(self.session, path)
            self.assertEqual(load_project(path).document.head, self.doc.head)

    def test_rotated_preview_drag_preserves_screen_depth_and_stationary_partner(self):
        self.use_molecule((), explicit=False)
        xy = ((-2.4, .8), (2., -.3), (-1.6, .2), (2.6, -.8), (-1., .7))
        self.panel._execute(SetSketchLayout(xy))
        self.view.rotate_view("y", 31)
        self.view.rotate_view("x", -17)
        self.app.processEvents()
        screen = tuple(QPointF(x, y) for x, y, _, _ in self.view._projected)
        self.assertEqual(self.view._target_at(screen[0]), (0,))
        delta = QPoint(-26, 22)
        before = self.doc.head
        scale = self.view._projection_scale()
        self.drag(self.view, screen[0], delta)
        after = self.doc.head
        offset = tuple(b - a for a, b in zip(before.coordinates()[0], after.coordinates()[0]))
        self.assert_translation(before.coordinates(), after.coordinates(), (0, 2, 4), offset)
        x, y, depth = self.view.transform(*offset)
        self.assertAlmostEqual(x * scale, delta.x())
        self.assertAlmostEqual(-y * scale, delta.y())
        self.assertAlmostEqual(depth, 0)
        self.assertEqual(after.sketch_xy, xy)
        for i, previous in enumerate(screen):
            target = previous + delta if i in (0, 2, 4) else previous
            x, y = self.view._projected[i][:2]
            self.assertAlmostEqual(x, target.x())
            self.assertAlmostEqual(y, target.y())
        self.assert_history(before, after)

    def test_explicitly_unbonded_atom_and_cancelled_drags(self):
        self.use_molecule((), explicit=True)
        before = self.doc.head
        delta = QPoint(28, -13)
        for widget, start in ((self.canvas, self.canvas.atom_position(0)),
                              (self.view, QPointF(*self.view._projected[0][:2]))):
            self.drag(widget, start, delta, cancel=True)
            self.assertIs(self.doc.head, before)
        scale = self.canvas._scale()
        self.drag(self.canvas, self.canvas.atom_position(0), delta)
        self.assert_translation(before.coordinates(), self.doc.head.coordinates(), (0,),
                                (delta.x() / scale, -delta.y() / scale, 0.))
        self.assert_history(before, self.doc.head)

    def assert_rigid_rotation(self, before, after, moving):
        for index in set(range(len(before))) - set(moving):
            self.assertEqual(before[index], after[index])
        for i, j in combinations(moving, 2):
            self.assertAlmostEqual(math.dist(before[i], before[j]), math.dist(after[i], after[j]))
        for axis in range(len(before[0])):
            self.assertAlmostEqual(sum(before[i][axis] for i in moving), sum(after[i][axis] for i in moving))
        self.assertTrue(any(math.dist(before[i], after[i]) > .001 for i in moving))

    def test_selected_molecule_orbits_in_screen_axes_from_over_its_neighbor(self):
        self.use_molecule((), explicit=False)
        sketch = tuple((atom.x, atom.y) for atom in self.atoms)
        self.panel._execute(SetSketchLayout(sketch))
        self.view.rotate_view("y", 35)
        self.view.rotate_view("x", -45)
        self.app.processEvents()
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=self.canvas.atom_position(2).toPoint())
        self.assertEqual(self.view.selected, [2])
        before = self.doc.head
        screen = tuple(self.view._projected)
        camera = tuple(self.view.transform(*axis) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
        delta = QPoint(39, -29)
        start = QPointF(*screen[1][:2])
        self.drag(self.view, start, delta, button=Qt.MouseButton.LeftButton, cancel=True)
        self.assertIs(self.doc.head, before)
        preview = self.drag(self.view, start, delta, button=Qt.MouseButton.LeftButton)
        after = self.doc.head
        self.assert_rigid_rotation(before.coordinates(), after.coordinates(), (0, 2, 4))
        self.assertEqual(after.sketch_xy, sketch)
        self.assertEqual(self.view.selected, [2])
        self.assertTrue(after.molecule.bonds_explicit)
        for prior, shown in zip(camera, (self.view.transform(*axis) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))):
            for a, b in zip(prior, shown):
                self.assertAlmostEqual(a, b)
        self.assertTrue(any(abs(preview[i][2] - screen[i][2]) > .02 for i in (0, 2, 4)))
        for i, final in enumerate(self.view._projected):
            for shown, committed in zip(preview[i], final):
                self.assertAlmostEqual(shown, committed)
            if i in (1, 3):
                for old, committed in zip(screen[i], final):
                    self.assertAlmostEqual(old, committed)
        self.assert_history(before, after)

    def test_sketch_rotation_works_away_from_selection_with_independent_layout(self):
        sketch = ((-2.7, 1.2), (1.8, -.8), (-1.5, .4), (2.8, -.3), (-.9, 1.2))
        self.panel._execute(SetSketchLayout(sketch))
        self.panel._select([2])
        before = self.doc.head
        start = QPointF(22, 40)
        self.assertFalse(self.canvas._target_at(start))
        self.drag(self.canvas, start, QPoint(75, 0), button=Qt.MouseButton.LeftButton)
        after = self.doc.head
        self.assert_rigid_rotation(before.coordinates(), after.coordinates(), (0, 2, 4))
        self.assert_rigid_rotation(before.sketch_xy, after.sketch_xy, (0, 2, 4))
        for a, b in zip(before.molecule.atoms, after.molecule.atoms):
            self.assertAlmostEqual(a.z, b.z)
        self.assert_history(before, after)

    def test_selected_molecule_translates_from_empty_space_across_a_hydrogen_bond(self):
        self.use_molecule(self.bonds + (Bond(0, 1, 1, "hydrogen_bond"),), explicit=True)
        self.panel._select([3])
        before = self.doc.head
        start = QPointF(40, 50)
        self.assertFalse(self.view._target_at(start))
        delta = QPoint(40, 25)
        self.drag(self.view, start, delta)
        after = self.doc.head
        offset = tuple(b - a for a, b in zip(before.coordinates()[3], after.coordinates()[3]))
        self.assert_translation(before.coordinates(), after.coordinates(), (1, 3), offset)
        self.assertGreater(math.hypot(*offset), .01)
        self.assert_history(before, after)

    def test_single_atom_rotation_and_empty_alt_drags_do_not_edit_or_move_camera(self):
        self.use_molecule((), explicit=True)
        before = self.doc.head
        camera = self.view.transform(0, 0, 1), QPointF(self.view._pan)
        for widget, atom in ((self.canvas, self.canvas.atom_position(2)),
                             (self.view, QPointF(*self.view._projected[2][:2]))):
            self.drag(widget, atom, QPoint(25, -26), button=Qt.MouseButton.LeftButton)
            for button in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
                self.drag(widget, QPointF(15, 15), QPoint(18, 14), button=button)
        self.assertIs(self.doc.head, before)
        self.assertEqual((self.view.transform(0, 0, 1), self.view._pan), camera)

    def test_xyz_fragments_can_be_brought_close_and_separated_again(self):
        self.use_molecule((), explicit=False)
        self.panel.atom_tool.click()
        original = self.doc.head
        start = self.canvas.atom_position(2)
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier,
                         start.toPoint())
        self.assertIs(self.doc.head, original)
        scale = self.canvas._scale()
        toward_hf = QPoint(round(3.2 * scale), round(.5 * scale))
        self.drag(self.canvas, start, toward_hf)
        close = self.doc.head
        self.assertNotEqual(infer_bonds(close.molecule), display_bonds(original.molecule))
        self.assertEqual(display_bonds(close.molecule), display_bonds(original.molecule))
        self.drag(self.canvas, self.canvas.atom_position(2), -toward_hf)
        self.assert_translation(original.coordinates(), self.doc.head.coordinates(), (0, 2, 4), (0., 0., 0.))

    def test_unmodified_drag_keeps_atom_editing_and_camera_orbit(self):
        before = self.doc.head
        delta = QPoint(24, -16)
        scale = self.canvas._scale()
        self.drag(self.canvas, self.canvas.atom_position(0), delta, alt=False)
        self.assert_translation(before.coordinates(), self.doc.head.coordinates(), (0,),
                                (delta.x() / scale, -delta.y() / scale, 0.))
        edited = self.doc.head
        orientation = self.view.transform(0, 0, 1)
        self.drag(self.view, QPointF(*self.view._projected[0][:2]), delta, alt=False)
        self.assertIs(self.doc.head, edited)
        self.assertNotEqual(self.view.transform(0, 0, 1), orientation)

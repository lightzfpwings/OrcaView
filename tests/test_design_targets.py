"""Editing the atom or bond highlighted under the pointer in either design view."""

from dataclasses import replace
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QImage, QPainter
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
class DesignTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        molecule = Molecule("Targets", (Atom("C", -1.35, .05, .2), Atom("O", .15, .1, 0),
                            Atom("N", 1.4, 1.05, .65), Atom("F", -.75, 1.55, -.4)),
                            (Bond(0, 1), Bond(1, 2), Bond(0, 3)), bonds_explicit=True)
        self.doc = Session(molecule).document
        self.panel = DesignPanel()
        self.addCleanup(self.panel.close)
        self.panel.resize(1160, 680)
        self.panel.set_document(self.doc)
        self.canvas, self.view = self.panel.canvas, self.panel.viewport
        self.panel.show()
        self.panel.activateWindow()
        self.app.processEvents()

    def atom(self, widget, i):
        if widget is self.canvas:
            return widget.atom_position(i)
        return QPointF(*widget._projected[i][:2])

    def hover(self, widget, point):
        # Route unpressed motion through the native window, including on Cocoa.
        QTest.mouseMove(self.panel.windowHandle(), widget.mapTo(self.panel, point.toPoint()))
        self.app.processEvents()

    def click(self, widget, point, modifier=Qt.KeyboardModifier.NoModifier):
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, modifier, point.toPoint())
        self.app.processEvents()

    def tool(self, name):
        self.panel.findChild(QAbstractButton, name).click()
        self.app.processEvents()

    @staticmethod
    def export_image(widget):
        image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        widget.paint_structure(painter)
        painter.end()
        return image

    def test_three_dimensional_delete_and_backspace_follow_keyboard_focus(self):
        original = self.doc.head
        for key, indices in ((Qt.Key.Key_Delete, (0,)), (Qt.Key.Key_Backspace, (1, 2))):
            with self.subTest(key=key):
                self.panel._select([])
                self.click(self.view, self.atom(self.view, indices[0]))
                for i in indices[1:]:
                    self.click(self.view, self.atom(self.view, i), Qt.KeyboardModifier.ShiftModifier)
                self.assertEqual(self.canvas.selected, list(indices))
                self.assertIs(self.app.focusWidget(), self.view)
                QTest.keyClick(self.app.focusWidget(), key)
                self.assertEqual(self.doc.head.atom_ids, tuple(uid for i, uid in enumerate(original.atom_ids)
                                                              if i not in indices))
                self.panel.undo_button.click()
                self.app.processEvents()
                self.assertEqual(self.doc.head.atom_ids, original.atom_ids)
                self.assertEqual(self.doc.head.molecule, original.molecule)
        self.panel._select([0])
        field = self.panel.coordinates[0]
        field.setFocus()
        head = self.doc.head
        QTest.keyClick(field, Qt.Key.Key_Backspace)
        self.assertIs(self.doc.head, head)

    def test_hover_changes_only_the_interactive_view_and_follows_the_active_tool(self):
        head = self.doc.head
        for widget in (self.canvas, self.view):
            for name, wanted in (("designAddHydrogens", (0,)), ("designAtom", (0,)),
                                 ("designBond2", (0, 1)), ("designBond0", (0, 1))):
                with self.subTest(view=widget.objectName(), tool=name):
                    self.tool(name)
                    self.hover(widget, QPointF(8, 8))
                    screen = widget.grab().toImage()
                    export = self.export_image(widget)
                    # Tool hints can wrap differently and resize the canvas.
                    point = self.atom(widget, wanted[0])
                    if len(wanted) == 2:
                        point = (point + self.atom(widget, wanted[1])) / 2
                    self.assertEqual(widget._target_at(point), wanted)
                    self.hover(widget, point)
                    self.assertEqual(widget._hover_target, wanted)
                    self.assertNotEqual(widget.grab().toImage(), screen)
                    self.assertEqual(self.export_image(widget), export)
                    self.assertIs(self.doc.head, head)
                    self.assertFalse(self.panel.editor.selection.atom_ids)
                    self.app.sendEvent(widget, QEvent(QEvent.Type.Leave))
                    self.assertEqual(widget._hover_target, ())
            self.tool("designAddHydrogens")
            self.hover(widget, (self.atom(widget, 0) + self.atom(widget, 1)) / 2)
            self.assertEqual(widget._hover_target, ())

    def test_three_dimensional_bond_clicks_edit_the_highlighted_edge(self):
        for tool, order in (("designBond2", 2), ("designBond0", 0)):
            self.tool(tool)
            midpoint = (self.atom(self.view, 0) + self.atom(self.view, 1)) / 2
            self.hover(self.view, midpoint)
            self.assertEqual(self.view._hover_target, (0, 1))
            self.click(self.view, midpoint)
            bonds = self.doc.head.molecule.bonds
            self.assertEqual([b.order for b in bonds if (b.a, b.b) == (0, 1)], [order] if order else [])
            self.assertEqual(self.canvas.selected, [0, 1])
        self.panel.undo_button.click()
        self.assertIn(Bond(0, 1, 2), self.doc.head.molecule.bonds)

    def test_bond_drag_targets_the_second_atom_only_in_the_sketch(self):
        self.tool("designBond1")
        window = self.panel.windowHandle()
        for widget in (self.canvas, self.view):
            start, end = (widget.mapTo(self.panel, self.atom(widget, i).toPoint()) for i in (0, 2))
            head = self.doc.head
            QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(window, end)
            self.app.processEvents()
            self.assertEqual(widget._hover_target, (2,) if widget is self.canvas else ())
            self.assertIs(self.doc.head, head)
            QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
            self.app.processEvents()
            if widget is self.canvas:
                self.assertIn(Bond(0, 2), self.doc.head.molecule.bonds)
            else:
                self.assertIs(self.doc.head, head)

    def test_three_dimensional_atom_tool_uses_the_selected_depth_after_rotation(self):
        view = self.view
        self.panel.element.setCurrentText("S")
        self.tool("designAtom")
        view.rotate_view("y", 23)
        self.app.processEvents()
        self.click(view, self.atom(view, 2))
        anchor = self.doc.head.molecule.atoms[2]
        self.assertEqual(anchor.element, "S")
        point = QPointF(round(view.width() * .21), round(view.height() * .2))
        displacement = (point - self.atom(view, 2)) / view._projection_scale()
        ids = self.doc.head.atom_ids
        self.click(view, point)
        self.assertEqual(self.doc.head.atom_ids[:-1], ids)
        atom = self.doc.head.molecule.atoms[-1]
        self.assertEqual(atom.element, "S")
        x, y, z = view.transform(atom.x - anchor.x, atom.y - anchor.y, atom.z - anchor.z)
        self.assertAlmostEqual(x, displacement.x())
        self.assertAlmostEqual(y, -displacement.y())
        self.assertAlmostEqual(z, 0.)

    def test_overlapping_spheres_pick_the_front_atom_and_hidden_bonds_are_not_targets(self):
        view = self.view
        self.tool("designAddHydrogens")
        near, far = (Atom("O", 0, 0, 1), Atom("C", 0, 0, -1))
        molecule = Molecule("Layers", (near, far, Atom("F", 1.4, .8, 0), Atom("N", -1., 1.2, -.3)),
                            (Bond(0, 2),), bonds_explicit=True)
        self.doc = Session(molecule).document
        self.panel.set_document(self.doc)
        self.app.processEvents()
        point = self.atom(view, 0)
        self.hover(view, point)
        self.assertEqual(view._hover_target, (0,))
        self.click(view, point)
        self.assertIn(Bond(0, 4), self.doc.head.molecule.bonds)
        self.tool("designBond0")
        view.set_appearance(replace(view.appearance, model="space-filling", atom_scale=.25), {})
        self.app.processEvents()
        self.hover(view, (self.atom(view, 0) + self.atom(view, 2)) / 2)
        self.assertEqual(view._hover_target, ())

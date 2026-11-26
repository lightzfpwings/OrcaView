"""Actual split-button choices, rendering and sketch gestures for bond variants."""

import math
import os
import unittest

from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, BOND_STYLES, Molecule

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton
    from orcaview.gui.design_panel import DesignPanel
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


@unittest.skipIf(QApplication is None, "requires Qt")
class BondPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = DesignPanel()
        self.addCleanup(self.panel.close)
        self.doc = Session(Molecule("pair", (Atom("H", -1, 0, 0), Atom("F", 1, 0, 0)),
                                    bonds_explicit=True)).document
        self.panel.set_document(self.doc)
        self.panel.resize(1100, 650)
        self.panel.show()
        self.app.processEvents()
        self.canvas = self.panel.canvas
        self.left = Qt.MouseButton.LeftButton

    def open_style(self, order, style):
        button = self.panel.findChild(QPushButton, f"designBond{order}")
        menu = button.options_menu
        QTest.mouseClick(button, self.left, pos=button.arrow_rect().center())
        self.app.processEvents()
        self.assertTrue(menu.isVisible())
        action = next(action for action in menu.actions() if action.data() == style)
        QTest.mouseClick(menu, self.left, pos=menu.actionGeometry(action).center())
        self.app.processEvents()
        self.assertFalse(menu.isVisible())
        self.assertTrue(button.isChecked())
        self.assertEqual(button.accessibleName(), action.text())
        self.assertEqual([a.data() for a in menu.actions() if a.isChecked()], [style])
        self.assertEqual((self.canvas.bond_order, self.canvas.bond_style), (order, style))
        return button

    def test_all_menu_variants_change_the_drawn_bond_and_both_views(self):
        view = self.panel.viewport
        view.rotate_view("y", 90)
        for order, styles in BOND_STYLES.items():
            button = self.panel.findChild(QPushButton, f"designBond{order}")
            self.assertEqual(button.size(), self.panel.element.size())
            self.assertCountEqual([a.data() for a in button.options_menu.actions()], styles)
            QTest.mouseClick(button, self.left)
            self.assertFalse(button.options_menu.isVisible())
            self.assertEqual((self.canvas.bond_order, self.canvas.bond_style), (order, "plain"))
            drawings = []
            projections = []
            for style in styles:
                with self.subTest(order=order, style=style):
                    self.open_style(order, style)
                    for i in (0, 1):
                        QTest.mouseClick(self.canvas, self.left, pos=self.canvas.atom_position(i).toPoint())
                    self.app.processEvents()
                    self.assertEqual(self.doc.head.molecule.bonds, (Bond(0, 1, order, style),))
                    self.assertEqual(view.bonds, self.doc.head.molecule.bonds)
                    drawing = self.canvas.grab().toImage()
                    projection = view.grab().toImage()
                    self.assertNotIn(drawing, drawings)
                    self.assertNotIn(projection, projections)
                    drawings.append(drawing)
                    projections.append(projection)

    def test_menu_cancel_main_face_reuse_and_directional_extension(self):
        button = self.open_style(1, "coordinate_arrow")
        self.panel.select_tool.click()
        QTest.keyClick(button, Qt.Key.Key_Down)
        self.assertTrue(button.options_menu.isVisible())
        QTest.keyClick(button.options_menu, Qt.Key.Key_Escape)
        self.assertEqual(self.canvas.tool, "select")
        QTest.mouseClick(button, self.left)
        self.assertEqual((self.canvas.tool, self.canvas.bond_style), ("bond", "coordinate_arrow"))
        start = self.canvas.atom_position(1).toPoint()
        end = start + QPoint(35, -45)
        QTest.mousePress(self.canvas, self.left, pos=start)
        QTest.mouseMove(self.canvas, end)
        QTest.mouseRelease(self.canvas, self.left, pos=end)
        self.assertEqual(self.doc.head.molecule.bonds, (Bond(1, 2, 1, "coordinate_arrow"),))
        self.panel.undo_button.click()
        self.assertEqual(len(self.doc.head.molecule.atoms), 2)

    def test_aromatic_dashes_face_the_ring_interior_with_reversed_edges(self):
        atoms = tuple(Atom("C", 1.4 * math.cos(i * math.pi / 3), 1.4 * math.sin(i * math.pi / 3), 0)
                      for i in range(6))
        bonds = tuple(Bond(*((i, (i+1) % 6) if i % 2 else ((i+1) % 6, i)), 2, "aromatic")
                      for i in range(6))
        self.panel.set_document(Session(Molecule("ring", atoms, bonds)).document)
        image = self.canvas.grab().toImage().scaled(self.canvas.size())
        positions = [self.canvas.atom_position(i) for i in range(6)]
        center = sum(positions, QPointF()) / 6
        for bond in bonds:
            start, end = positions[bond.a], positions[bond.b]
            inward = center - (start + end) / 2
            offset = inward * (2.1 / math.hypot(inward.x(), inward.y()))
            samples = [start + (end-start) * (fraction / 100.) for fraction in range(25, 76)]
            def ink_count(shift):
                return sum(image.pixelColor(math.floor(p.x()+shift.x()), math.floor(p.y()+shift.y())).lightness() < 200
                           for p in samples)
            inner, outer = ink_count(offset), ink_count(-offset)
            self.assertGreater(outer, 45, bond)
            self.assertTrue(10 < inner < outer-8, (bond, inner, outer))


if __name__ == "__main__":
    unittest.main()

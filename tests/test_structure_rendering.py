"""Molecule-only painting on an externally transformed transparent device."""

import os
import unittest

from orcaview.core.models import Atom, Bond, BOND_STYLES, Molecule

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPicture
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.design_canvas import DesignCanvas
    from orcaview.gui.viewport import MoleculeViewport
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


@unittest.skipIf(QApplication is None, "requires Qt")
class StructureRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def render(self, view, scale=1):
        image = QImage(view.size() * scale, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            painter.scale(scale, scale)
            transform = painter.transform()
            font, pen, brush, hints = painter.font(), painter.pen(), painter.brush(), painter.renderHints()
            view.paint_structure(painter)
            self.assertEqual(painter.transform(), transform)
            self.assertEqual((painter.font(), painter.pen(), painter.brush(), painter.renderHints()),
                             (font, pen, brush, hints))
        finally:
            painter.end()
        return image

    def test_empty_drafts_do_not_paint(self):
        for view in (DesignCanvas(), MoleculeViewport()):
            self.addCleanup(view.close)
            self.assertFalse(view.has_exportable_structure())
            blank = self.render(view)
            view.set_molecule(Molecule("empty draft", ()))
            self.assertFalse(view.has_exportable_structure())
            self.assertEqual(self.render(view), blank)
            view.set_molecule(Molecule("atom", (Atom("O", 0, 0, 0),)))
            self.assertTrue(view.has_exportable_structure())
            self.assertNotEqual(self.render(view), blank)

    def test_sketch_bonds_do_not_show_through_labels_on_transparent_paper(self):
        view = DesignCanvas()
        self.addCleanup(view.close)
        view.resize(480, 320)
        # The unbonded oxygen also lies over the C–C bond.
        atoms = (Atom("C", -1, 0, 0), Atom("C", 1, 0, 0), Atom("O", 0, 0, 0))
        view.set_molecule(Molecule("labels", atoms, bonds_explicit=True), fit=True)
        labels_only = self.render(view, 2)
        view.set_molecule(Molecule("crossing", atoms, (Bond(0, 1),), bonds_explicit=True))
        sketch = self.render(view, 2)
        self.assertNotEqual(labels_only, sketch)
        self.assertEqual(sketch.pixelColor(0, 0).alpha(), 0)
        for i in range(len(atoms)):
            point = (view.atom_position(i) * 2).toPoint()
            self.assertEqual(sketch.copy(point.x() - 19, point.y() - 12, 38, 24),
                             labels_only.copy(point.x() - 19, point.y() - 12, 38, 24))
            self.assertEqual(sketch.pixelColor(point.x() - 18, point.y()).alpha(), 0)
        midpoint = (view.atom_position(0) + view.atom_position(2)).toPoint()
        self.assertGreater(sketch.pixelColor(midpoint).alpha(), 0)
        view.selected = [0, 2]
        view._pressed = 1
        view._drag = QPointF(30, 45)
        view._bond_tip = QPointF(150, 210)
        view._box = QRectF(10, 10, 90, 90)
        self.assertEqual(sketch, self.render(view, 2))

    def test_recorded_sketch_preserves_background_and_callers_clip(self):
        view = DesignCanvas()
        self.addCleanup(view.close)
        view.resize(480, 320)
        atoms = (Atom("O", -1, 0, 0), Atom("C", 1, 0, 0))
        view.set_molecule(Molecule("pair", atoms, (Bond(0, 1),)), fit=True)
        picture = QPicture()
        recorder = QPainter(picture)
        view.paint_structure(recorder)
        recorder.end()

        image = QImage(view.size(), QImage.Format.Format_ARGB32_Premultiplied)
        backdrop = QColor("#2BCE9D")
        image.fill(backdrop)
        painter = QPainter(image)
        try:
            # Keep the snapshot's coordinates in viewport pixels at playback.
            painter.scale(picture.logicalDpiX() / image.logicalDpiX(),
                          picture.logicalDpiY() / image.logicalDpiY())
            painter.setClipRect(0, 0, view.width() // 2, view.height())
            painter.drawPicture(QPointF(), picture)
        finally:
            painter.end()
        left, right = (view.atom_position(i).toPoint() for i in (0, 1))
        self.assertEqual(image.pixelColor(left.x() + 9, left.y()), backdrop)
        self.assertNotEqual(image.pixelColor(left.x() + 30, left.y()), backdrop)
        self.assertEqual(image.pixelColor(right.x() - 30, right.y()), backdrop)

    def test_sketch_preserves_bond_styles(self):
        view = DesignCanvas()
        self.addCleanup(view.close)
        atoms = (Atom("C", -1, 0, 0), Atom("C", 1, 0, 0))
        for order, styles in BOND_STYLES.items():
            drawings = []
            for style in styles:
                with self.subTest(order=order, style=style):
                    view.set_molecule(Molecule("pair", atoms, (Bond(0, 1, order, style),),
                                               bonds_explicit=True), fit=True)
                    image = self.render(view)
                    self.assertNotIn(image, drawings)
                    drawings.append(image)

    def test_3d_keeps_camera_and_label_preference_independent_of_selection(self):
        molecule = Molecule("water", (Atom("O", 0, 0, 0), Atom("H", .96, 0, 0),
                                      Atom("H", -.24, .93, 0)), (Bond(0, 1), Bond(0, 2)),
                            bonds_explicit=True)
        for view in (MoleculeViewport(), MoleculeViewport(result_view=True),
                     MoleculeViewport(design_selection=True)):
            self.addCleanup(view.close)
            view.resize(500, 340)
            view.set_molecule(molecule)
            initial = self.render(view)
            self.assertEqual(initial.pixelColor(18, 26).alpha(), 0)
            self.assertEqual(initial.pixelColor(452, 288).alpha(), 0)
            view.selected = [0, 1]
            self.assertEqual(self.render(view), initial)
            view.labels = True
            labeled = self.render(view)
            self.assertNotEqual(labeled, initial)
            view.selected = []
            self.assertEqual(self.render(view), labeled)
            view.rotate_view("y", 35)
            rotated = self.render(view)
            self.assertNotEqual(rotated, labeled)
            view.zoom = 1.35
            zoomed = self.render(view)
            self.assertNotEqual(zoomed, rotated)
            view._pan = QPointF(11, 8)
            self.assertNotEqual(self.render(view), zoomed)
            self.assertEqual(view._projected, [])  # Export did not change mouse picking state.


if __name__ == "__main__":
    unittest.main()

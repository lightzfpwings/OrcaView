"""Molecule-only painting on an externally transformed transparent device."""

from dataclasses import replace
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orcaview.appearance import AppearanceSettings
from orcaview.application.structure_import import read_structure_file
from orcaview.core.elements import ELEMENT_COLORS, VDW_RADII
from orcaview.core.models import Atom, Bond, BOND_STYLES, Molecule

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPicture
    from PySide6.QtTest import QTest
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

    def test_four_models_render_distinctly_and_use_element_colors(self):
        view = MoleculeViewport()
        self.addCleanup(view.close)
        view.resize(520, 380)
        atoms = (Atom("C", -1, 0, 0), Atom("O", 1, 0, 0))
        view.set_molecule(Molecule("pair", atoms, (Bond(0, 1),)))
        view.rotate_view("y", 90)  # Put the internuclear axis in the image plane.
        colors = {"C": "#18A340", "O": "#AD38D5"}
        images = []
        for model in ("ball-and-stick", "space-filling", "stick", "wireframe"):
            with self.subTest(model=model):
                view.set_appearance(AppearanceSettings(model=model), colors)
                image = self.render(view)
                self.assertNotIn(image, images)
                images.append(image)
                scale, projected = view._project_atoms()
                a, b = (QPointF(x, y) for x, y, _, _ in projected)
                if model in ("stick", "wireframe"):
                    for fraction, element in ((.28, "C"), (.72, "O")):
                        midpoint = (a + (b - a) * fraction).toPoint()
                        color = image.pixelColor(midpoint)
                        self.assertGreater(color.alpha(), 180)
                        self.assertTrue(all(abs(x - y) <= 2 for x, y in zip(
                            color.getRgb()[:3], QColor(colors[element]).getRgb()[:3])))
                elif model == "space-filling":
                    self.assertAlmostEqual(projected[0][3], VDW_RADII["C"] * scale)
                    # Space-filling has no bond symbols, including explicit multiple bonds.
                    view.set_molecule(Molecule("pair", atoms, (Bond(0, 1, 3),)), keep_view=True)
                    self.assertEqual(image, self.render(view))
                    view.set_molecule(Molecule("pair", atoms, (Bond(0, 1),)), keep_view=True)
                else:
                    self.assertAlmostEqual(projected[0][3], .32 * scale)

    def test_ball_and_stick_sizing_and_visible_space_filling_pick(self):
        view = MoleculeViewport()
        self.addCleanup(view.close)
        view.resize(520, 380)
        atoms = (Atom("C", -1, 0, 0), Atom("C", 1, 0, 0))
        view.set_molecule(Molecule("pair", atoms, (Bond(0, 1),)))
        view.rotate_view("y", 90)
        settings = AppearanceSettings()
        original = self.render(view)
        _, projected = view._project_atoms()
        x, y, _, radius = projected[0]
        midpoint = QPointF((x + projected[1][0]) / 2, y).toPoint()

        def stroke_height(image):
            return sum(image.pixelColor(midpoint.x(), yy).alpha() > 127 for yy in range(image.height()))

        view.set_appearance(replace(settings, atom_scale=1.4), ELEMENT_COLORS)
        self.assertAlmostEqual(view._project_atoms()[1][0][3], radius * 1.4)
        self.assertEqual(stroke_height(self.render(view)), stroke_height(original))
        view.set_appearance(replace(settings, bond_scale=2), ELEMENT_COLORS)
        self.assertAlmostEqual(view._project_atoms()[1][0][3], radius)
        self.assertGreater(stroke_height(self.render(view)), stroke_height(original) * 1.7)

        view.set_molecule(Molecule("heavy atom", (Atom("Fr", 0, 0, 0),)))
        view.set_appearance(replace(settings, model="space-filling", atom_scale=3), ELEMENT_COLORS)
        view.fit()
        view.show()
        self.app.processEvents()
        x, y, _, radius = view._projected[0]
        self.assertLess(radius, min(view.width(), view.height()) / 2)
        point = QPointF(x + radius * .9, y).toPoint()
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(view.selected, [0])

    def test_inference_factor_only_changes_implicit_visual_bonds(self):
        view = MoleculeViewport()
        self.addCleanup(view.close)
        atoms = (Atom("H", 0, 0, 0), Atom("H", .8, 0, 0))
        implicit = Molecule("pair", atoms)
        view.set_molecule(implicit)
        self.assertEqual(view.visual_bonds, ())
        view.selected = [1]
        view.rotate_view("y", 15)
        orientation = view.camera_transform(1, 0, 0)
        view.set_appearance(AppearanceSettings(bond_distance_factor=1.5), ELEMENT_COLORS)
        self.assertEqual(view.visual_bonds, (Bond(0, 1),))
        self.assertEqual(view.bonds, ())
        self.assertIs(view.molecule, implicit)
        self.assertEqual(view.selected, [1])
        self.assertEqual(view.camera_transform(1, 0, 0), orientation)
        for authored in ((), (Bond(0, 1, 2),)):
            view.set_molecule(replace(implicit, bonds=authored, bonds_explicit=True))
            for factor in (.5, 2):
                view.set_appearance(AppearanceSettings(bond_distance_factor=factor), ELEMENT_COLORS)
                self.assertEqual(view.visual_bonds, authored)
                self.assertEqual(view.bonds, authored)

    @unittest.skipUnless(importlib.util.find_spec("openbabel"), "requires the native import worker")
    def test_real_import_preserves_declared_zero_bonds(self):
        mol = ("Pair\n  OrcaView          3D\n\n  2  0  0  0  0  0            999 V2000\n"
               "    0.0000    0.0000    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\n"
               "    0.7400    0.0000    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\nM  END\n")
        mol2 = ("@<TRIPOS>MOLECULE\nPair\n2 0 0 0 0\nSMALL\nNO_CHARGES\n@<TRIPOS>ATOM\n"
                "1 H1 0 0 0 H 1 PAIR 0\n2 H2 .74 0 0 H 1 PAIR 0\n@<TRIPOS>BOND\n")
        cml = ('<cml xmlns="http://www.xml-cml.org/schema"><molecule><atomArray>'
               '<atom id="a1" elementType="H" x3="0" y3="0" z3="0"/>'
               '<atom id="a2" elementType="H" x3=".74" y3="0" z3="0"/></atomArray>{}</molecule></cml>')
        cases = (("pair.mol", mol, True), ("pair.sdf", mol + "$$$$\n", True),
                 ("pair.mol2", mol2, True), ("empty.cml", cml.format("<bondArray/>"), True),
                 ("coordinates.cml", cml.format(""), False), ("pair.xyz", "2\npair\nH 0 0 0\nH .74 0 0\n", False))
        view = MoleculeViewport()
        self.addCleanup(view.close)
        with TemporaryDirectory() as tmp:
            for filename, source, explicit in cases:
                with self.subTest(filename=filename):
                    path = Path(tmp, filename)
                    path.write_text(source, encoding="utf-8")
                    molecule = read_structure_file(path).record.molecule
                    self.assertEqual(molecule.bonds_explicit, explicit)
                    view.set_molecule(molecule)
                    view.set_appearance(AppearanceSettings(bond_distance_factor=2), {})
                    self.assertEqual(view.visual_bonds, () if explicit else (Bond(0, 1),))
                    view.set_appearance(AppearanceSettings(bond_distance_factor=.5), {})
                    self.assertEqual(view.visual_bonds, ())

    def test_flat_models_keep_a_pale_hydrogen_visible_on_the_canvas(self):
        view = MoleculeViewport()
        self.addCleanup(view.close)
        view.resize(480, 300)
        view.set_molecule(Molecule("atom", (Atom("H", 0, 0, 0),)))
        for model in ("wireframe", "stick"):
            view.set_appearance(AppearanceSettings(model=model), {})
            pixel = self.render(view).pixelColor(view.width() // 2, view.height() // 2)
            self.assertGreater(pixel.alpha(), 245)
            self.assertLessEqual(max(pixel.red(), pixel.green(), pixel.blue()), 150)


if __name__ == "__main__":
    unittest.main()

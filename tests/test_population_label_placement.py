"""Check charge labels against pixels painted by the molecular renderer."""

from dataclasses import replace
import os
from pathlib import Path
import unittest

from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.core.provenance import Provenance
from orcaview.core.results import DatasetAxis, ResultDataset
from orcaview.gui.result_import import read_native_session

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPointF, QRect, QRectF, Qt
    from PySide6.QtGui import QImage, QPainter, QRegion
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None
else:
    from orcaview.gui.population_map import PopulationMap, PopulationStyle
    from orcaview.gui.viewport import MoleculeViewport

    class LabelPainter(QPainter):
        def drawText(self, *args):
            if isinstance(args[0], QRectF):
                self.labels.append((QRectF(args[0]), args[-1]))
            return super().drawText(*args)


@unittest.skipUnless(QApplication, "Requires PySide6")
class PopulationLabelPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.view = MoleculeViewport(result_view=True)
        self.view.resize(720, 420)
        self.addCleanup(self.view.close)

    def draw(self):
        image = QImage(self.view.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = LabelPainter(image)
        painter.labels = []
        try:
            self.view.paint_structure(painter)
        finally:
            painter.end()
        return image, painter.labels

    def assert_labels_clear(self, population, expected, *, element_labels=False):
        self.view.population_map = None
        self.view.labels = False
        molecule, _ = self.draw()
        self.view.population_map = population
        self.view.labels = element_labels
        annotated, labels = self.draw()
        self.assertCountEqual([text for _, text in labels], expected)
        for i, (box, text) in enumerate(labels):
            self.assertTrue(QRectF(self.view.rect()).contains(box), text)
            for other, other_text in labels[:i]:
                self.assertFalse(box.intersects(other), (text, other_text))
            # Count molecule pixels changed by the label background or the text.
            rect = box.toAlignedRect()
            covered = sum(
                molecule.pixelColor(x, y).alpha() > 32 and molecule.pixel(x, y) != annotated.pixel(x, y)
                for x in range(rect.left(), rect.right() + 1)
                for y in range(rect.top(), rect.bottom() + 1)
            )
            self.assertEqual(covered, 0, f"{text} covers {covered} molecule pixels")

    def test_water_charges_after_orbit_zoom_and_pan_to_edge(self):
        path = Path(__file__).resolve().parents[1] / "examples/m5_orca/water-sp.out"
        session = read_native_session(path)
        data = next(d for d in session.document.records()[1] if d.kind == "mulliken-charge")
        frame = session.document.resolve(data.geometry)
        self.view.set_molecule(frame.molecule)
        population = PopulationMap(data, frame, PopulationStyle(legend=False))
        self.view.rotate_view("x", 60)
        self.view.rotate_view("z", 30)
        self.view.zoom = 1.7
        with self.subTest(view="diagonal bonds"):
            self.assert_labels_clear(population, ["−0.420", "0.200", "0.220"])
        self.view.fit()
        self.view.rotate_view("x", 80)
        self.view.rotate_view("z", 28)
        self.view.zoom = 1.25
        rightmost = max(x for x, *_ in self.view._project_atoms()[1])
        self.view._pan += QPointF(self.view.width() - 9 - rightmost, 0)
        with self.subTest(view="rotated at right edge"):
            self.assert_labels_clear(population, ["O1  −0.420", "H2  0.200", "H3  0.220"],
                                     element_labels=True)

    def test_crowded_view_preserves_charge_with_and_without_a_distant_opening(self):
        molecule = Molecule("Chloride", (Atom("Cl", 0., 0., 0.),), charge=-1)
        frame = Session(molecule).document.head
        data = ResultDataset("mulliken-charge", frame.ref, Provenance("fixture"), "float64",
                             (1,), "e", (-1.,), (DatasetAxis("atom", frame.atom_ids),))
        population = PopulationMap(data, frame, PopulationStyle(legend=False))
        self.view.set_molecule(molecule)
        self.view.resize(360, 300)
        image = QImage(self.view.size(), QImage.Format.Format_ARGB32_Premultiplied)
        painter = LabelPainter(image)
        try:
            text = "Cl1  −1.000"
            width = painter.fontMetrics().horizontalAdvance(text) + 8
            height = painter.fontMetrics().height() + 2
            opening = QRect(230, 240, width, height)
            whole_view = QRegion(self.view.rect())
            for has_opening in (True, False):
                with self.subTest(has_opening=has_opening):
                    bonds = whole_view - QRegion(opening) if has_opening else whole_view
                    painter.labels = []
                    population.draw_annotations(painter, self.view, [(90., 90., 0., 8.)], True, (), bonds)
                    self.assertEqual([s for _, s in painter.labels], [text])
                    box = painter.labels[0][0]
                    self.assertTrue(QRectF(self.view.rect()).contains(box))
                    self.assertEqual((box.width(), box.height()), (width, height))
                    if has_opening:
                        self.assertEqual(box.toAlignedRect(), opening)
        finally:
            painter.end()

    def test_labels_near_other_fragments_and_multiple_bond_strokes(self):
        molecule = Molecule(
            "Multiple bonds in projection",
            (Atom("Na", -.7, .10, .35), Atom("C", 0., -.95, -.05), Atom("O", 0., .9, .10),
             Atom("N", 1.35, -1.1, .36), Atom("N", 1.35, .9, .40)),
            (Bond(1, 2, 2), Bond(3, 4, 3)), multiplicity=2, bonds_explicit=True,
        )
        frame = Session(molecule).document.head
        values = (.74, .37, -.51, -.20, -.40)
        data = ResultDataset("mulliken-charge", frame.ref, Provenance("fixture"), "float64",
                             (len(values),), "e", values, (DatasetAxis("atom", frame.atom_ids),))
        population = PopulationMap(data, frame, PopulationStyle(legend=False, digits=6))
        self.view.set_molecule(molecule)
        expected = ["Na1  0.740000", "C2  0.370000", "O3  −0.510000", "N4  −0.200000", "N5  −0.400000"]
        for model, turn in (("stick", 0), ("wireframe", 60)):
            with self.subTest(model=model):
                self.view.set_appearance(replace(self.view.appearance, model=model, bond_scale=1.4), {})
                self.view.rotate_view("z", turn)
                self.assert_labels_clear(population, expected, element_labels=True)

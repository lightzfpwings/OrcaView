"""A biochemical sketch exposes only the original indices on its backbone."""

import os
import unittest

from orcaview.core.models import Atom, Bond, Molecule

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.design_canvas import DesignCanvas
except ModuleNotFoundError as exc:
    if not exc.name.startswith("PySide6"):
        raise
    QApplication = None


@unittest.skipIf(QApplication is None, "requires Qt")
class DesignBackboneViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Two visible traces, their branches, and an independent oxygen.
        self.molecule = Molecule("mixed", (
            Atom("N", -2, -1, 0), Atom("C", 0, -1, 0), Atom("C", 0, 0, 1),
            Atom("C", 2, -1, 0), Atom("P", -2, 1, 0), Atom("O", 0, 1, 0),
            Atom("C", 2, 1, 0), Atom("O", 2, 0, 0), Atom("O", 4, 0, 0),
            Atom("H", 40, 20, 0),
        ), (Bond(0, 1), Bond(1, 2), Bond(1, 3), Bond(4, 5), Bond(5, 6),
            Bond(6, 7), Bond(7, 9)), bonds_explicit=True)
        self.visible = frozenset((0, 1, 3, 4, 5, 6, 8))
        self.canvas = DesignCanvas()
        self.addCleanup(self.canvas.close)
        self.canvas.resize(640, 400)
        self.canvas.set_molecule(self.molecule, polymer_roles="BBSBBBBS.S", fit=True)
        self.canvas.show()
        self.app.processEvents()

    def rendered(self):
        view = self.canvas
        image = QImage(view.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            view.paint_structure(painter)
        finally:
            painter.end()
        return image

    def set_trace(self, points, *, independent=False):
        atoms = tuple(Atom("C", x, y, .2 * i) for i, (x, y) in enumerate(points))
        bonds = tuple(Bond(i, i + 1) for i in range(len(atoms) - 1))
        molecule = Molecule("trace", atoms, bonds, bonds_explicit=True)
        self.canvas.set_molecule(molecule, fit=True, independent_sketch=independent, polymer_roles="B" * len(atoms))
        return molecule

    def projected(self, atom):
        view = self.canvas
        cx, cy = view._center
        return QPointF(view.width() / 2 + (atom.x - cx) * view._scale(),
                       view.height() / 2 - (atom.y - cy) * view._scale())

    def test_curved_stroke_exports_and_selects_the_same_chemical_bond(self):
        view = self.canvas
        molecule = self.set_trace(((-4, -1), (-2, -1), (-1, 1.5), (1, 1.5), (2, -1), (4, -1)),
                                  independent=True)
        self.assertEqual([view.atom_position(i) for i in range(len(molecule.atoms))],
                         [self.projected(atom) for atom in molecule.atoms])
        center = ((view.atom_position(2) + view.atom_position(3)) / 2).toPoint()
        image = self.rendered()
        # The curve bows away from this horizontal chord. Read its center from
        # the exported ink, independently of the painter and picking internals.
        ink = [y for y in range(center.y() - 35, center.y() + 36)
               if image.pixelColor(center.x(), y).alpha() > 190]
        self.assertTrue(ink)
        stroke = QPoint(center.x(), (min(ink) + max(ink)) // 2)
        self.assertGreater(abs(stroke.y() - center.y()), 5)
        self.assertEqual(view._target_at(QPointF(stroke)), (2, 3))
        clicked = []
        view.bond_clicked.connect(lambda a, b: clicked.append((a, b)))
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=stroke)
        self.assertEqual(clicked, [(2, 3)])
        view._track_hover(QPointF(stroke))
        view.selected = [2, 3]
        self.assertEqual(self.rendered(), image)

    def test_smoothed_site_picking_marquee_and_model_space_drag(self):
        view = self.canvas
        points = tuple((i - 4, (.9 if i % 2 else -.8) + .12 * i) for i in range(9))
        molecule = self.set_trace(points)
        index = 4
        atom = molecule.atoms[index]
        displayed = view.atom_position(index)
        self.assertGreater((displayed - self.projected(atom)).manhattanLength(), 10)
        self.assertEqual(view._target_at(displayed), (index,))
        center = displayed.toPoint()
        selected = []
        view.box_selected.connect(lambda indices, _: selected.append(indices))
        begin, end = center - QPoint(10, 13), center + QPoint(10, 13)
        self.assertFalse(view._target_at(QPointF(begin)))
        QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=begin)
        QTest.mouseMove(view, end)
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(selected, [[index]])

        moved = []
        view.atom_moved.connect(lambda *args: moved.append(args))
        delta = QPoint(20, -22)
        QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=center)
        QTest.mouseMove(view, center + delta)
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=center + delta)
        self.assertEqual(len(moved), 1)
        selected_id, x, y, z = moved[0]
        self.assertEqual(selected_id, index)
        self.assertAlmostEqual(x, atom.x + delta.x() / view._scale())
        self.assertAlmostEqual(y, atom.y - delta.y() / view._scale())
        self.assertEqual(z, atom.z)

        extensions = []
        view.bond_to_space.connect(lambda *args: extensions.append(args))
        view.tool = "bond"
        release = center + QPoint(18, -33)
        QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=center)
        QTest.mouseMove(view, release)
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=release)
        self.assertEqual(len(extensions), 1)
        anchor, x, y, z = extensions[0]
        self.assertEqual(anchor, index)
        offset = QPointF(release) - displayed
        self.assertAlmostEqual(x, atom.x + offset.x() / view._scale())
        self.assertAlmostEqual(y, atom.y - offset.y() / view._scale())
        self.assertEqual(z, atom.z)
        self.assertEqual([(a.x, a.y) for a in view.molecule.atoms], list(points))

    def test_crossing_draws_and_picks_the_front_strand(self):
        view = self.canvas
        for height, front in ((-1, (2, 3)), (1, (0, 1))):
            with self.subTest(height=height):
                atoms = (Atom("C", -2, -1, height), Atom("C", 2, 1, height),
                         Atom("C", -2, 1, -height), Atom("C", 2, -1, -height))
                molecule = Molecule("crossing", atoms, (Bond(0, 1), Bond(2, 3)), bonds_explicit=True)
                view.set_molecule(molecule, polymer_roles="BBBB", fit=True)
                midpoint = (view.atom_position(0) + view.atom_position(1)) / 2
                self.assertEqual(view._target_at(midpoint), front)
                image = self.rendered()
                crossing = image.pixelColor(midpoint.toPoint())
                def color_distance(index):
                    sample = (midpoint + view.atom_position(index)) / 2
                    rgb = image.pixelColor(sample.toPoint()).getRgb()[:3]
                    return sum(abs(a - b) for a, b in zip(crossing.getRgb()[:3], rgb))
                other = 2 if front[0] == 0 else 0
                self.assertLess(color_distance(front[0]), color_distance(other))

    def test_a_node_covered_by_a_front_strand_does_not_intercept_its_bond(self):
        view = self.canvas
        rear = (Atom("C", -2, 0, -1), Atom("C", 0, 0, -1), Atom("C", 2, 0, -1))
        for front in (((0, -2), (0, 2)), ((-1, 0), (1, 0))):
            with self.subTest(front=front):
                atoms = rear + tuple(Atom("C", x, y, 1) for x, y in front)
                molecule = Molecule("covered node", atoms, (Bond(0, 1), Bond(1, 2), Bond(3, 4)), bonds_explicit=True)
                view.set_molecule(molecule, polymer_roles="BBBBB", fit=True)
                self.assertEqual(view._target_at(view.atom_position(1)), (3, 4))
                self.assertEqual(view._target_at(view.atom_position(0)), (0,))

    def test_end_on_backbone_has_a_visible_pickable_point(self):
        view = self.canvas
        molecule = Molecule("end-on", (Atom("C", 1, 1, -1), Atom("C", 1, 1, 0), Atom("C", 1, 1, 1)),
                            (Bond(0, 1), Bond(1, 2)), bonds_explicit=True)
        view.set_molecule(molecule, polymer_roles="BBB", fit=True)
        center = view.atom_position(2)
        self.assertEqual(center, view.atom_position(0))
        self.assertGreater(self.rendered().pixelColor(center.toPoint()).alpha(), 0)
        self.assertEqual(view._target_at(center), (2,))

    def test_fit_visible_traces_only_while_export_and_picking_use_full_indices(self):
        view = self.canvas
        self.assertEqual(view.molecule, self.molecule)
        self.assertEqual(view._extent, (6., 2.))
        self.assertEqual(view._target_at(view.atom_position(2)), ())
        self.assertEqual(view._target_at(view.atom_position(7)), ())
        self.assertEqual(view._target_at(view.atom_position(8)), (8,))
        points = [view.atom_position(i) for i in range(len(self.molecule.atoms))]
        self.assertEqual(view._target_at((points[1] + points[3]) / 2), (1, 3))
        image = self.rendered()
        for i in (2, 7):
            self.assertEqual(image.pixelColor(points[i].toPoint()).alpha(), 0)
        self.assertGreater(image.pixelColor(points[1].toPoint()).alpha(), 0)
        self.assertNotEqual(image.pixelColor(points[1].toPoint()), image.pixelColor(points[5].toPoint()))
        # The separate atom keeps its ordinary element glyph.
        label = points[8].toPoint()
        self.assertTrue(any(image.pixelColor(label + QPoint(x, y)).alpha()
                            for x in range(-8, 9) for y in range(4, 9)))
        view._track_hover(points[2])
        self.assertEqual(view._hover_target, ())
        view.selected = [2]
        self.assertEqual(self.rendered(), image)
        # A short chain remains a trace even with ample space for full labels.
        view.resize(1000, 700)
        self.assertEqual(self.rendered().pixelColor(view.atom_position(2).toPoint()).alpha(), 0)

    def test_marquee_omits_hidden_atoms_and_alt_gesture_uses_the_complete_fragment(self):
        view = self.canvas
        selections = []
        view.box_selected.connect(lambda indices, _: selections.append(indices))
        start, end = QPoint(10, 10), QPoint(view.width() - 10, view.height() - 10)
        QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view, end)
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(selections, [sorted(self.visible)])
        moved = []
        view.fragment_moved.connect(lambda i, dx, dy: moved.append((i, dx, dy)))
        p = view.atom_position(5).toPoint()
        drag = QPoint(30, 20)
        QTest.mousePress(view, Qt.MouseButton.RightButton, Qt.KeyboardModifier.AltModifier, p)
        self.assertEqual(view._fragment, {4, 5, 6, 7, 9})
        QTest.mouseMove(view, p + drag)
        QTest.mouseRelease(view, Qt.MouseButton.RightButton, Qt.KeyboardModifier.AltModifier, p + drag)
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0][0], 5)
        self.assertAlmostEqual(moved[0][1], drag.x() / view._scale())
        self.assertAlmostEqual(moved[0][2], -drag.y() / view._scale())

    def test_named_roles_preserve_isolated_backbone_and_ordinary_ligand(self):
        view = self.canvas
        fragment = Molecule("partial deposited chain", (Atom("C", -2, 0, 0), Atom("O", 0, 0, 0),
                                                        Atom("H", 1, 0, 0)), (Bond(1, 2),), bonds_explicit=True)
        view.set_molecule(fragment, polymer_roles="B..", fit=True)
        self.assertEqual(view.polymer_roles, "B..")
        self.assertEqual(set(view._chain_colors), {0})
        image = self.rendered()
        carbon = view.atom_position(0).toPoint()
        self.assertGreater(image.pixelColor(carbon).alpha(), 0)
        self.assertEqual(image.pixelColor(carbon + QPoint(0, 5)).alpha(), 0)
        view.set_molecule(fragment, polymer_roles="...", fit=True)
        self.assertEqual(view.polymer_roles, "...")
        self.assertFalse(view._chain_colors)
        self.assertEqual(list(view._visible_indices), [0, 1, 2])
        self.assertNotEqual(self.rendered(), image)
        view.set_molecule(fragment, polymer_roles="S..", fit=True)
        self.assertEqual(list(view._visible_indices), [1, 2])
        self.assertEqual(view._target_at(view.atom_position(0)), ())

    def test_explicit_trace_edges_are_independent_of_chemical_topology(self):
        view = self.canvas
        fragment = Molecule("deposited trace and ligand", (
            Atom("C", -2, 1, 0), Atom("C", 0, 1, 0), Atom("C", 2, 1, 0), Atom("C", 2, -1, 0),
            Atom("O", -2, -1, 0), Atom("H", 0, -1, 0),
        ), (Bond(0, 1), Bond(1, 2), Bond(4, 5)), bonds_explicit=True)
        # 1–2 has an underlying bond omitted by the source; 2–3 has only a trace.
        view.set_molecule(fragment, polymer_roles="BBBB..", backbone_links=((3, 2), (0, 1)), fit=True)
        self.assertEqual(view.backbone_links, ((0, 1), (2, 3)))
        self.assertEqual(view._full_bonds, fragment.bonds)
        self.assertEqual(view._chain_colors[0], view._chain_colors[1])
        self.assertEqual(view._chain_colors[2], view._chain_colors[3])
        self.assertNotEqual(view._chain_colors[1], view._chain_colors[2])
        image = self.rendered()
        def center(a, b):
            return (view.atom_position(a) + view.atom_position(b)) / 2
        for a, b in ((0, 1), (2, 3), (4, 5)):
            self.assertGreater(image.pixelColor(center(a, b).toPoint()).alpha(), 0)
        self.assertEqual(image.pixelColor(center(1, 2).toPoint()).alpha(), 0)
        self.assertEqual(view._target_at(center(1, 2)), ())
        self.assertEqual(view._target_at(center(2, 3)), ())
        self.assertEqual(view._target_at(center(0, 1)), (0, 1))
        self.assertEqual(view._target_at(center(4, 5)), (4, 5))
        view.set_molecule(fragment, polymer_roles="BBBB..", backbone_links=())
        self.assertEqual(view.backbone_links, ())
        isolated = self.rendered()
        self.assertEqual(isolated.pixelColor(center(0, 1).toPoint()).alpha(), 0)
        self.assertGreater(isolated.pixelColor(view.atom_position(0).toPoint()).alpha(), 0)
        self.assertGreater(isolated.pixelColor(center(4, 5).toPoint()).alpha(), 0)
        view.set_molecule(fragment, polymer_roles="BBBB..")
        self.assertIsNone(view.backbone_links)
        self.assertEqual(view._target_at(center(1, 2)), (1, 2))

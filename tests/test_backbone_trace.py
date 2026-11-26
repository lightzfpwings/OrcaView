"""Graph and interpolation invariants behind the 2D backbone drawing."""

import itertools
import math
import os
import unittest

try:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from orcaview.gui.backbone_ink import prepare_ink
    from orcaview.gui.backbone_trace import chain_paths, project_trace
except ModuleNotFoundError as exc:
    if not exc.name.startswith("PySide6"):
        raise
    QPointF = None


@unittest.skipIf(QPointF is None, "requires Qt geometry")
class BackboneTraceTests(unittest.TestCase):
    def test_edge_viewed_end_on_is_drawn_at_the_original_site(self):
        from PySide6.QtWidgets import QApplication
        from orcaview.core.models import Atom, Bond, Molecule
        from orcaview.gui.design_canvas import DesignCanvas

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance() or QApplication([])
        view = DesignCanvas()
        self.addCleanup(view.close)
        view.resize(320, 240)
        molecule = Molecule("end-on edge", (Atom("C", 3, 4, 0), Atom("N", 3, 4, 1.4)),
                            (Bond(0, 1),), bonds_explicit=True)
        view.set_molecule(molecule, polymer_roles="BB", fit=True)
        view.show()
        app.processEvents()
        point = view.atom_position(0)
        self.assertEqual(point, view.atom_position(1))
        self.assertNotEqual(point, QPointF())
        paths = chain_paths(((0, 1),))
        _, segments = project_trace(paths, (point, point), [0, 1.4])
        self.assertTrue(segments[0].path.isEmpty())
        self.assertEqual(segments[0].path.currentPosition(), point)
        stroke, = prepare_ink(segments, {0: QColor("#267a80")}, paths)
        self.assertEqual(stroke.hit_distance(point + QPointF(3, 0)), 3.)
        self.assertIn(view._target_at(point), ((0,), (1,)))
        image = QImage(view.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        view.paint_structure(painter)
        painter.end()
        self.assertGreater(image.pixelColor(point.toPoint()).alpha(), 240)

    def test_paths_do_not_invent_links_at_gaps_junctions_or_cycles(self):
        edges = ((5, 3), (3, 2), (7, 6), (6, 8), (8, 7), (1, 3), (2, 0), (4, 1))
        paths = chain_paths(edges)
        found = sorted(tuple(sorted((a, b))) for p in paths for a, b in zip(p, p[1:]))
        self.assertEqual(found, sorted(tuple(sorted(edge)) for edge in edges))
        self.assertEqual(paths, chain_paths((b, a) for a, b in reversed(edges)))
        self.assertTrue(any(p[0] == p[-1] for p in paths))
        self.assertTrue(all(3 not in p[1:-1] for p in paths))

    def test_curve_removes_bond_scale_jaggedness_and_preserves_atom_indices(self):
        points = [QPointF(x, (-1.)**x * 2 + math.sin(x / 7) * 10) for x in range(32)]
        original = [QPointF(p) for p in points]
        paths = chain_paths(zip(range(30), range(1, 31)))
        shown, segments = project_trace(paths, points, list(range(len(points))))
        self.assertEqual(points, original)
        self.assertEqual((shown[0], shown[30], shown[31]), (points[0], points[30], points[31]))
        for i in range(5, 25):
            self.assertAlmostEqual(shown[i].x(), i, places=8)
            self.assertAlmostEqual(shown[i].y(), math.sin(i / 7) * 10, delta=.4)
        self.assertEqual(len(segments), 30)
        for seg in segments:
            self.assertEqual(seg.path.pointAtPercent(0), shown[seg.a])
            self.assertEqual(seg.path.pointAtPercent(1), shown[seg.b])
            self.assertEqual(seg.depth, (seg.a + seg.b) / 2)
        for first, second in zip(segments, segments[1:]):
            x1, y1 = first.path.elementAt(2).x, first.path.elementAt(2).y
            x2, y2 = second.path.elementAt(1).x, second.path.elementAt(1).y
            self.assertAlmostEqual((x1+x2) / 2, shown[first.b].x())
            self.assertAlmostEqual((y1+y2) / 2, shown[first.b].y())

    def test_junctions_and_authored_positions_stay_exact(self):
        # A ring touches the rest of the molecule only at atom zero.
        edges = [(i, (i+1) % 10) for i in range(10)] + [(0, 10), (10, 11)]
        paths = chain_paths(edges)
        points = [QPointF(i, (i % 3) * 4) for i in range(12)]
        shown, _ = project_trace(paths, points, [0.] * len(points))
        self.assertEqual(shown[0], points[0])
        self.assertEqual(shown[11], points[11])
        authored, _ = project_trace(paths, points, [0.] * len(points), independent_sketch=True)
        self.assertEqual(authored, tuple(points))

    def test_coincident_and_irregular_steps_have_bounded_cubic_handles(self):
        points = [QPointF(0, 0), QPointF(60, 1), QPointF(60, 1), QPointF(61, 8),
                  QPointF(61.00001, 8), QPointF(100, 0)]
        _, segments = project_trace(chain_paths(zip(range(5), range(1, 6))), points,
                                    [0.] * len(points), independent_sketch=True)
        for s in segments:
            p, q = points[s.a], points[s.b]
            dx, dy = q.x() - p.x(), q.y() - p.y()
            for i in range(s.path.elementCount()):
                element = s.path.elementAt(i)
                self.assertTrue(math.isfinite(element.x) and math.isfinite(element.y))
            if s.path.elementCount() == 4:
                for index, anchor in zip((1, 2), (p, q)):
                    control = s.path.elementAt(index)
                    self.assertLessEqual(math.hypot(control.x-anchor.x(), control.y-anchor.y()),
                                         math.hypot(dx, dy) / 3. + 1e-9)

    def test_closed_cycle_has_a_smooth_seam(self):
        points = [QPointF(6 * math.cos(i * math.tau / 10), 4 * math.sin(i * math.tau / 10)) for i in range(10)]
        paths = chain_paths(zip(range(10), itertools.chain(range(1, 10), [0])))
        shown, segments = project_trace(paths, points, [0.] * len(points))
        self.assertEqual(len(segments), len(points))
        a, b = segments[-1].path.elementAt(2), segments[0].path.elementAt(1)
        self.assertAlmostEqual(a.x + b.x, 2 * shown[0].x())
        self.assertAlmostEqual(a.y + b.y, 2 * shown[0].y())

    def test_crossing_leaves_transparent_gap_and_picks_the_top_strand(self):
        points = [QPointF(5, 32), QPointF(60, 32), QPointF(32, 5), QPointF(32, 60)]
        paths = chain_paths(((0, 1), (2, 3)))
        _, curves = project_trace(paths, points, [-2., -2., 3., 3.])
        colors = {0: QColor("#267a80"), 2: QColor("#98536a")}
        back, front = prepare_ink(curves, colors, paths)
        self.assertLess(back.width, front.width)
        self.assertLess(back.depth, front.depth)
        self.assertTrue(math.isinf(back.hit_distance(QPointF(32, 32))))
        self.assertEqual(front.hit_distance(QPointF(32, 32)), 0.)
        self.assertAlmostEqual(back.hit_distance(QPointF(12, 32)), 0.)
        image = QImage(65, 65, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        back.paint(painter)
        front.paint(painter)
        painter.end()
        self.assertEqual(image.pixelColor(32, 32).rgb(), front.color.rgb())
        self.assertEqual(image.pixelColor(27, 32).alpha(), 0)
        self.assertGreater(image.pixelColor(20, 32).alpha(), 245)

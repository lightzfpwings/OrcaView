import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.editing import EditorService, GeometryEditCommand, InsertRing
from orcaview.editing.hydrogens import missing_hydrogens
from orcaview.editing.rings import HETEROCYCLES

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPoint, QTimer, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.design_panel import DesignPanel
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


def apply(editor, operation):
    return editor.commit(editor.preview(GeometryEditCommand(editor.expected, operation))).snapshot


class RingPlacementTests(unittest.TestCase):
    def test_benzene_from_seed_preserves_identity_through_history_and_save(self):
        seed = Atom("C", .4, -.6, 1.1)
        session = Session(Molecule("seed", (seed,), bonds_explicit=True))
        editor = EditorService(session.document)
        initial = session.document.head
        ring = apply(editor, InsertRing(6, True, "XZ", anchor_id=initial.atom_ids[0]))
        self.assertEqual(ring.ref.revision, initial.ref.revision + 1)
        self.assertEqual(len(ring.atom_ids), 6)
        self.assertEqual(ring.atom_ids[0], initial.atom_ids[0])
        self.assertEqual(ring.molecule.atoms[0], seed)
        self.assertEqual(ring.molecule.bonds, tuple(Bond(i, (i + 1) % 6, 2 - i % 2) for i in range(6)))
        for i, atom in enumerate(ring.molecule.atoms):
            other = ring.molecule.atoms[(i + 1) % 6]
            self.assertEqual(atom.y, seed.y)
            self.assertAlmostEqual(math.hypot(atom.x - other.x, atom.z - other.z), 1.4)
        self.assertEqual(editor.undo().snapshot.atom_ids, initial.atom_ids)
        self.assertEqual(session.molecule, initial.molecule)
        self.assertEqual(editor.redo().snapshot.atom_ids, ring.atom_ids)
        self.assertEqual(session.molecule, ring.molecule)
        with TemporaryDirectory() as temp:
            path = Path(temp) / "ring.oview.json"
            save_project(session, path)
            loaded = load_project(path).document.head
            self.assertEqual((loaded.molecule, loaded.atom_ids), (ring.molecule, ring.atom_ids))

    def test_attachment_points_away_from_neighbour_and_detached_ring_keeps_depth(self):
        atoms = (Atom("C", -1.52, 0, 3), Atom("C", 0, 0, 3))
        session = Session(Molecule("chain", atoms, (Bond(0, 1),)))
        editor = EditorService(session.document)
        ring = apply(editor, InsertRing(5, False, "XY", anchor_id=session.document.head.atom_ids[1]))
        self.assertEqual(ring.molecule.atoms[:2], atoms)
        self.assertTrue(all(a.x > 1.5 and a.z == 3 for a in ring.molecule.atoms[2:]))
        self.assertEqual(len(ring.molecule.bonds), 7)
        self.assertIn(Bond(1, 2), ring.molecule.bonds)
        self.assertTrue(all(b.order == 1 for b in ring.molecule.bonds))
        detached = apply(editor, InsertRing(8, False, "YZ", center=(12., 3., -2.)))
        self.assertTrue(all(a.x == 12 for a in detached.molecule.atoms[7:]))
        self.assertEqual(detached.molecule.bonds[:7], ring.molecule.bonds)
        self.assertEqual(len(detached.molecule.bonds), 15)

    def test_overlapping_ring_without_clear_orientation_does_not_commit(self):
        atoms = tuple(Atom("C", 1.4 * math.cos(i * math.tau / 24),
                           1.4 * math.sin(i * math.tau / 24), 0.) for i in range(24))
        editor = EditorService(Session(Molecule("crowded", atoms, bonds_explicit=True)).document)
        initial = editor.expected
        with self.assertRaisesRegex(ValueError, "overlaps"):
            apply(editor, InsertRing(6, True, "XY", center=(0., 0., 0.)))
        self.assertEqual(editor.expected, initial)
        self.assertFalse(editor.can_undo)

    def test_named_rings_keep_seed_and_have_expected_neutral_valences(self):
        # The nitrogen positions distinguish the isomers with the same formula.
        expected = {"pyrrole": ("CCNCC", 5), "furan": ("CCOCC", 4),
                    "thiophene": ("CCSCC", 4), "imidazole": ("CNCCN", 4),
                    "pyrazole": ("CCNNC", 4), "pyridine": ("CNCCCC", 5),
                    "pyrimidine": ("CNCNCC", 4), "pyrazine": ("CNCCNC", 4)}
        seed = Atom("C", .4, -.6, 1.1)
        editor = EditorService(Session(Molecule("seed", (seed,), bonds_explicit=True)).document)
        initial = editor.document.head
        self.assertEqual(set(HETEROCYCLES), set(expected))
        for name, (symbols, hydrogen_count) in expected.items():
            with self.subTest(template=name):
                ring = apply(editor, InsertRing(len(symbols), False, "XY", anchor_id=initial.atom_ids[0],
                                                heterocycle=name))
                self.assertEqual(ring.atom_ids[0], initial.atom_ids[0])
                self.assertEqual(ring.molecule.atoms[0], seed)
                self.assertEqual("".join(a.element for a in ring.molecule.atoms), symbols)
                self.assertEqual(len(ring.molecule.bonds), len(symbols))
                self.assertEqual(sum(b.order == 2 for b in ring.molecule.bonds), len(symbols) // 2)
                hydrogen_atoms, _ = missing_hydrogens(ring.molecule)
                self.assertEqual(len(hydrogen_atoms), hydrogen_count)
                self.assertEqual(editor.undo().snapshot.atom_ids, initial.atom_ids)

    def test_heterocycle_attaches_at_carbon_without_changing_anchor(self):
        seed = Atom("O", 1., 2., -1.)
        editor = EditorService(Session(Molecule("oxygen", (seed,), bonds_explicit=True)).document)
        initial = editor.document.head
        ring = apply(editor, InsertRing(5, False, "YZ", anchor_id=initial.atom_ids[0], heterocycle="furan"))
        self.assertEqual(ring.atom_ids[0], initial.atom_ids[0])
        self.assertEqual(ring.molecule.atoms[0], seed)
        self.assertEqual("".join(atom.element for atom in ring.molecule.atoms[1:]), "CCOCC")
        self.assertIn(Bond(0, 1), ring.molecule.bonds)
        self.assertEqual(editor.undo().snapshot.molecule, initial.molecule)
        self.assertEqual(editor.redo().snapshot.molecule, ring.molecule)
        for size, benzene, heterocycle in ((5, False, "pyridine"), (6, True, "pyridine"),
                                         (7, False, "unknown"), (13, False, None)):
            with self.assertRaises(ValueError):
                InsertRing(size, benzene, "XY", center=(0., 0., 0.), heterocycle=heterocycle)


@unittest.skipIf(QApplication is None, "requires Qt")
class RingToolTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.panel = DesignPanel()
        self.addCleanup(self.panel.close)
        self.doc = Session(Molecule("seed", (Atom("C", 0., 0., 0.),), bonds_explicit=True)).document
        self.panel.set_document(self.doc)
        self.panel.resize(1100, 650)
        self.panel.show()
        self.app.processEvents()

    def test_menu_lists_all_templates_and_dismissal_preserves_current_tool(self):
        button = self.panel.ring_tool
        menu = self.panel.ring_menu
        self.assertEqual(button.text(), "")
        self.assertFalse(button.icon().isNull())
        self.assertTrue(button.accessibleName())
        self.assertLess(button.iconSize().height(), button.height())
        expected = [(size, "") for size in range(3, 13)] + [(6, "benzene")]
        expected.extend((len(elements), name) for name, (elements, _) in HETEROCYCLES.items())
        self.assertCountEqual([tuple(a.data()) for a in menu.actions() if a.isCheckable()], expected)
        self.assertEqual([tuple(a.data()) for a in menu.actions() if a.isChecked()], [(6, "")])

        visible_before_escape = []

        def dismiss():
            visible_before_escape.append(menu.isVisible())
            QTest.keyClick(menu, Qt.Key.Key_Escape)

        button.setFocus()
        QTimer.singleShot(0, dismiss)
        QTest.keyClick(button, Qt.Key.Key_Down)
        self.app.processEvents()
        self.assertEqual(visible_before_escape, [True])
        self.assertFalse(menu.isVisible())
        self.assertTrue(self.panel.select_tool.isChecked())
        self.assertEqual(self.panel.canvas.tool, "select")

    def test_ring_icon_and_arrow_open_templates_for_placement(self):
        panel = self.panel
        button = panel.ring_tool
        menu = panel.ring_menu
        face = button.icon().pixmap(button.iconSize()).toImage()
        size_before = button.size()
        actions = {tuple(action.data()): action for action in menu.actions() if action.isCheckable()}

        for x, template in ((button.width() // 3, (12, "")), (button.width() - 6, (6, "benzene")),
                            (button.width() // 3, (5, "imidazole"))):
            with self.subTest(template=template):
                QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=QPoint(x, button.height() // 2))
                self.app.processEvents()
                self.assertTrue(menu.isVisible())
                QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(actions[template]).center())
                self.app.processEvents()
                self.assertFalse(menu.isVisible())
                self.assertTrue(button.isChecked())
                self.assertEqual(panel.canvas.tool, "ring")
                self.assertEqual([key for key, action in actions.items() if action.isChecked()], [template])
                self.assertIn(actions[template].text(), button.toolTip())
                self.assertEqual(button.text(), "")
                self.assertEqual(button.icon().pixmap(button.iconSize()).toImage(), face)
                self.assertEqual(button.size(), size_before)
                QTest.mouseClick(panel.canvas, Qt.MouseButton.LeftButton, pos=panel.canvas.atom_position(0).toPoint())
                size, name = template
                self.assertEqual(len(self.doc.head.molecule.atoms), size)
                self.assertEqual(len(panel.viewport.bonds), size)
                self.assertEqual(sum(b.order == 2 for b in panel.viewport.bonds), size // 2 if name else 0)
                if name == "imidazole":
                    self.assertEqual(sum(a.element == "N" for a in self.doc.head.molecule.atoms), 2)
                QTest.mouseClick(panel.undo_button, Qt.MouseButton.LeftButton)
                self.assertEqual(len(self.doc.head.molecule.atoms), 1)
                QTest.mouseClick(panel.select_tool, Qt.MouseButton.LeftButton)
                self.assertFalse(button.isChecked())

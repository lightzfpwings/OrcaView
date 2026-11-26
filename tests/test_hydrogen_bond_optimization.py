"""Exercise marked contacts through the desktop's isolated Open Babel worker."""

from dataclasses import replace
from importlib.util import find_spec
import math
import os
import time
import unittest

from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.editing import EditorService, GeometryEditCommand, SetSketchLayout
from orcaview.editing.hydrogen_bonds import optimize_hydrogen_bonds


def water_cluster():
    atoms = (Atom("O", 0, 0, 0), Atom("H", .96, 0, 0), Atom("H", -.2, .9, 0),
             Atom("O", 4, .7, 0), Atom("H", 4.65, 1.4, 0), Atom("H", 4.5, -.12, 0),
             Atom("O", 7, 2.5, .2), Atom("H", 7.7, 3.2, .2), Atom("H", 7.55, 1.72, .2),
             Atom("He", 9, 6, -1))
    bonds = (Bond(0, 1), Bond(0, 2), Bond(3, 4), Bond(3, 5), Bond(6, 7), Bond(6, 8),
             Bond(1, 3, 1, "hydrogen_bond"), Bond(6, 4, 1, "hydrogen_bond"))
    return Molecule("Three waters and helium", atoms, bonds, bonds_explicit=True)


class HydrogenBondOptimizationTest(unittest.TestCase):
    def test_missing_donor_contact_and_invalid_restraints(self):
        m = water_cluster()
        for mol, args, error in ((replace(m, bonds=m.bonds[:-2]), (), "Mark a hydrogen bond"),
                                 (replace(m, bonds=m.bonds[1:]), (), "donor atom"),
                                 (replace(m, multiplicity=3), (), "neutral singlets"),
                                 (m, (float("nan"), 150), "distance"),
                                 (m, (2, 190), "angle")):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                optimize_hydrogen_bonds(Session(mol).document.head, *args)

    def assert_contact(self, coordinates, d, h, a, distance, angle):
        self.assertAlmostEqual(math.dist(coordinates[h], coordinates[a]), distance, delta=.05)
        ha = tuple(x-y for x, y in zip(coordinates[a], coordinates[h]))
        hd = tuple(x-y for x, y in zip(coordinates[d], coordinates[h]))
        cos = sum(x*y for x, y in zip(ha, hd)) / (math.hypot(*ha) * math.hypot(*hd))
        self.assertAlmostEqual(math.degrees(math.acos(cos)), angle, delta=5.)

    @unittest.skipUnless(find_spec("openbabel"), "requires desktop Open Babel")
    def test_simultaneous_contacts_undo_and_spectator(self):
        document = Session(water_cluster()).document
        editor = EditorService(document)
        sketch = tuple((n, n+.4) for n in range(len(document.head.atom_ids)))
        editor.commit(editor.preview(GeometryEditCommand(document.head.ref, SetSketchLayout(sketch))))
        before = document.head
        op = optimize_hydrogen_bonds(before, distance=2., angle=165.)
        editor.commit(editor.preview(GeometryEditCommand(before.ref, op)))
        after = document.head
        self.assertIn(op.method, ("MMFF94", "UFF"))
        self.assert_contact(after.coordinates(), 0, 1, 3, 2., 165.)
        self.assert_contact(after.coordinates(), 3, 4, 6, 2., 165.)
        self.assertEqual(after.molecule.atoms[-1], before.molecule.atoms[-1])
        self.assertEqual((after.atom_ids, after.molecule.bonds, after.sketch_xy),
                         (before.atom_ids, before.molecule.bonds, sketch))
        editor.undo()
        self.assertEqual(document.head.molecule, before.molecule)
        editor.redo()
        self.assertEqual(document.head.molecule, after.molecule)

    @unittest.skipUnless(find_spec("openbabel"), "requires desktop Open Babel")
    def test_intramolecular_contact(self):
        atoms = (Atom("O", 0, 0, 0), Atom("H", .96, 0, 0), Atom("C", -.35, -1.35, .15),
                 Atom("C", .8, -2.25, .35), Atom("C", 2.1, -1.8, -.1),
                 Atom("O", 2.62, -.65, .50), Atom("H", 3.50, -.9, .70))
        bonds = (Bond(0, 1), Bond(0, 2), Bond(2, 3), Bond(3, 4), Bond(4, 5), Bond(5, 6),
                 Bond(1, 5, 1, "hydrogen_bond"))
        head = Session(Molecule("1,3-propanediol", atoms, bonds)).document.head
        op = optimize_hydrogen_bonds(head, 2., 165.)
        self.assert_contact(op.coordinates, 0, 1, 5, 2., 165.)

    @unittest.skipUnless(find_spec("openbabel") and find_spec("PySide6"), "requires desktop dependencies")
    def test_desktop_dialog_applies_targets(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QDialog, QDoubleSpinBox
        from orcaview.gui.design_panel import DesignPanel
        app = QApplication.instance() or QApplication([])
        panel = DesignPanel()
        self.addCleanup(panel.close)
        document = Session(water_cluster()).document
        panel.set_document(document)
        panel.show()
        self.assertTrue(panel.optimize_hbonds.isVisible())
        def change_targets():
            dialog = panel.findChild(QDialog)
            distance, angle = dialog.findChildren(QDoubleSpinBox)
            distance.setValue(2.10)
            angle.setValue(160.)
            dialog.accept()
        QTimer.singleShot(0, change_targets)
        panel.optimize_hbonds.click()
        deadline = time.monotonic() + 15
        while panel._structure_job is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        self.assertIsNone(panel._structure_job, panel.status.text())
        self.assert_contact(document.head.coordinates(), 0, 1, 3, 2.10, 160.)

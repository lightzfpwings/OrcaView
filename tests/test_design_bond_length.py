"""Bond-length editing through the design canvas and its numeric controls."""

import os
import unittest
from unittest.mock import patch

from orcaview.application.document import MoleculeDocument
from orcaview.core.geometry import display_bonds, infer_bonds
from orcaview.core.models import Atom, Bond, Molecule

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.design_panel import DesignPanel
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    DesignPanel = None


@unittest.skipIf(DesignPanel is None, "requires Qt")
class BondLengthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def open_molecule(self, molecule):
        self.doc = MoleculeDocument.from_molecule(molecule)
        self.panel = DesignPanel()
        self.panel.resize(1050, 650)
        self.panel.set_document(self.doc)
        self.panel.show()
        self.app.processEvents()
        self.addCleanup(self.panel.close)
        self.canvas = self.panel.canvas
        self.length = self.panel.bond_length

    def click_bond(self, a, b):
        midpoint = (self.canvas.atom_position(a) + self.canvas.atom_position(b)) / 2
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=midpoint.toPoint())

    def test_click_bond_swap_ends_and_translate_only_the_selected_branch(self):
        original = Molecule("Branched", (
            Atom("C", -1.5, 0., 0.), Atom("C", 0., 0., 0.),
            Atom("N", 1., 1., .5), Atom("F", 1., -1., -.5), Atom("He", 5., 3., 1.),
        ), (Bond(0, 1), Bond(1, 2), Bond(1, 3)), bonds_explicit=True)
        self.open_molecule(original)
        ids = self.doc.head.atom_ids
        self.click_bond(0, 1)
        self.assertEqual(self.canvas.selected, [0, 1])
        self.assertEqual(self.length.target.value(), 1.5)
        self.assertEqual(self.length.moving_atoms, ids[1:4])
        self.length.target.setValue(2.)
        QTest.mouseClick(self.length.apply, Qt.MouseButton.LeftButton)
        head = self.doc.head
        self.assertEqual(head.ref.revision, 2)
        self.assertEqual(head.atom_ids, ids)
        self.assertEqual(head.molecule.bonds, original.bonds)
        for index, (old, new) in enumerate(zip(original.atoms, head.molecule.atoms)):
            self.assertEqual(new.x - old.x, .5 if index in (1, 2, 3) else 0.)
            self.assertEqual((old.y, old.z), (new.y, new.z))
        QTest.mouseClick(self.panel.undo_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.doc.head.molecule, original)
        QTest.mouseClick(self.length.swap, Qt.MouseButton.LeftButton)
        self.assertEqual(self.length.moving_atoms, ids[:1])
        self.assertEqual(self.canvas.selected, [1, 0])
        self.length.target.setValue(1.25)
        QTest.mouseClick(self.length.apply, Qt.MouseButton.LeftButton)
        self.assertEqual(self.doc.head.molecule.atoms[1:], original.atoms[1:])
        self.assertEqual(self.doc.head.molecule.atoms[0].x, -1.25)

    def test_ring_and_unbonded_pair_are_measured_without_changing_geometry(self):
        original = Molecule("Ring", (Atom("C", 0., 0., 0.), Atom("C", 1.4, 0., 0.),
                                     Atom("C", .7, 1.2, 0.), Atom("He", -2., 0., 0.)),
                            (Bond(0, 1), Bond(1, 2), Bond(2, 0)), bonds_explicit=True)
        self.open_molecule(original)
        self.click_bond(0, 1)
        self.assertFalse(self.length.controls.isVisible())
        self.assertIn("1.400000", self.length.summary.text())
        self.assertIn("ring", self.length.details.text())
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, pos=self.canvas.atom_position(0).toPoint())
        QTest.mouseClick(self.canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
                         pos=self.canvas.atom_position(3).toPoint())
        self.assertEqual(self.canvas.selected, [0, 3])
        self.assertFalse(self.length.controls.isVisible())
        self.assertIn("2.000000", self.length.summary.text())
        self.assertEqual(self.doc.head.ref.revision, 1)

    def test_editing_an_inferred_bond_preserves_it_past_the_distance_cutoff(self):
        original = Molecule("H2", (Atom("H", -.37, 0., 0.), Atom("H", .37, 0., 0.)))
        self.open_molecule(original)
        with patch("orcaview.core.geometry.infer_bonds", wraps=infer_bonds) as infer:
            self.click_bond(0, 1)
            infer.assert_not_called()
        self.length.target.setValue(2.5)
        QTest.mouseClick(self.length.apply, Qt.MouseButton.LeftButton)
        self.assertTrue(self.doc.head.molecule.bonds_explicit)
        self.assertEqual(display_bonds(self.doc.head.molecule), (Bond(0, 1),))
        self.assertAlmostEqual(self.doc.head.molecule.atoms[1].x, 2.13)
        QTest.mouseClick(self.panel.undo_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.doc.head.molecule, original)

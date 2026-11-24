"""Diagnostics for editable geometries with arbitrary explicit bond counts."""

from dataclasses import replace
import unittest

from orcaview.core.models import Atom, Bond, Molecule
from orcaview.editing.diagnostics import design_diagnostics


def bonded_hydrogens(element, count, **state):
    atoms = (Atom(element, 0, 0, 0),) + tuple(Atom("H", i, 1, 0) for i in range(count))
    return Molecule(element, atoms, tuple(Bond(0, i + 1) for i in range(count)), **state)


class DesignDiagnosticsTests(unittest.TestCase):
    def test_fifth_carbon_bond_coexists_with_electronic_state_error(self):
        methane = bonded_hydrogens("C", 4)
        self.assertEqual(design_diagnostics(methane), ())
        extra_h = bonded_hydrogens("C", 5)
        with self.assertRaises(ValueError) as mismatch:
            extra_h.validate()
        issues = design_diagnostics(extra_h)
        self.assertIn(str(mismatch.exception), issues)
        valence = "Check the bonds of C1: the total bond order (5) is outside the usual range."
        self.assertIn(valence, issues)
        self.assertEqual(design_diagnostics(replace(extra_h, multiplicity=2)), (valence,))

    def test_hydrogen_bridge_and_multiple_bonds_use_total_bond_order(self):
        bridge = Molecule("H3+", (Atom("H", -1, 0, 0), Atom("H", 0, 0, 0), Atom("H", 1, 0, 0)),
                          (Bond(0, 1), Bond(1, 2)), charge=1)
        self.assertEqual(design_diagnostics(bridge), ("Check the bonds of H2: the total bond order (2) is outside the usual range.",))
        alkynyl = Molecule("draft", (Atom("C", 0, 0, 0), Atom("N", 1, 0, 0), Atom("O", -1, 0, 0)),
                           (Bond(0, 1, 3), Bond(0, 2, 2)), multiplicity=2)
        self.assertEqual(design_diagnostics(alkynyl), ("Check the bonds of C1: the total bond order (5) is outside the usual range.",))

    def test_assigned_charge_and_metal_coordination_do_not_trigger_false_warnings(self):
        for molecule in (bonded_hydrogens("N", 4, charge=1),
                         bonded_hydrogens("O", 3, charge=1),
                         bonded_hydrogens("Fe", 8)):
            with self.subTest(element=molecule.name):
                self.assertEqual(design_diagnostics(molecule), ())
        # These close H contacts in an XYZ file have no assigned bond orders.
        unknown_graph = Molecule("H4", tuple(Atom("H", i * 0.3, 0, 0) for i in range(4)))
        self.assertEqual(design_diagnostics(unknown_graph), ())

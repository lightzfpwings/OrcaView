"""A +H click may exceed normal valence and always addresses one stable anchor."""

import math
import unittest

from orcaview.application.session import Session
from orcaview.core.geometry import display_bonds
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.core.snapshots import SelectionContext
from orcaview.editing import AddHydrogen, EditorService, GeometryEditCommand
from orcaview.editing.diagnostics import design_diagnostics
from orcaview.editing.hydrogens import missing_hydrogens


def add_hydrogen(editor, anchor):
    return editor.commit(editor.preview(GeometryEditCommand(editor.expected, AddHydrogen(anchor))))


def position(atom):
    return atom.x, atom.y, atom.z


class AutomaticHydrogenTests(unittest.TestCase):
    def test_furan_and_pyrrole_fill_neutral_heteroaromatic_rings(self):
        for heteroatom, expected in (("O", [1, 2, 3, 4]), ("N", [0, 1, 2, 3, 4])):
            with self.subTest(heteroatom=heteroatom):
                atoms = tuple(Atom(heteroatom if i == 0 else "C", 1.2 * math.cos(math.tau * i / 5),
                                   1.2 * math.sin(math.tau * i / 5), 0.) for i in range(5))
                bonds = tuple(Bond(i, (i + 1) % 5, 2, "aromatic") for i in range(5))
                additions, _ = missing_hydrogens(Molecule(heteroatom, atoms, bonds))
                self.assertEqual([i for i, _ in additions], expected)

    def test_fused_naphthalene_carbons_receive_no_extra_h(self):
        xy = [(-1, 1), (0, .5), (0, -.5), (-1, -1), (-2, -.5), (-2, .5),
              (1, -1), (2, -.5), (2, .5), (1, 1)]
        atoms = tuple(Atom("C", x * 1.4, y * 1.4, 0) for x, y in xy)
        edges = [(i, (i + 1) % 6) for i in range(6)] + [(2, 6), (6, 7), (7, 8), (8, 9), (9, 1)]
        bonds = tuple(Bond(a, b, 2, "aromatic") for a, b in edges)
        additions, _ = missing_hydrogens(Molecule("naphthalene", atoms, bonds))
        self.assertEqual([i for i, _ in additions], [0, 3, 4, 5, 6, 7, 8, 9])

    def test_ambiguous_imidazole_tautomer_leaves_nitrogens_for_manual_choice(self):
        atoms = tuple(Atom(e, 1.2 * math.cos(math.tau * i / 5), 1.2 * math.sin(math.tau * i / 5), 0.)
                      for i, e in enumerate("NCNCC"))
        bonds = tuple(Bond(i, (i + 1) % 5, 2, "aromatic") for i in range(5))
        molecule = Molecule("imidazole", atoms, bonds)
        additions, _ = missing_hydrogens(molecule)
        self.assertEqual([i for i, _ in additions], [1, 3, 4])
        self.assertTrue(any("N1, N3" in text for text in design_diagnostics(molecule)))

    def test_aromatic_ring_counts_fractional_orders_and_leaves_pyridine_nitrogen(self):
        atoms = tuple(Atom("N" if i == 0 else "C", 1.4 * math.cos(math.tau * i / 6),
                           1.4 * math.sin(math.tau * i / 6), 0.) for i in range(6))
        bonds = tuple(Bond(i, (i + 1) % 6, 2, "aromatic") for i in range(6))
        additions, perceived = missing_hydrogens(Molecule("pyridine", atoms, bonds))
        self.assertIsNone(perceived)
        self.assertEqual([i for i, _ in additions], list(range(1, 6)))

    def test_coordinate_donor_keeps_its_valence_and_fractional_deficit_is_rounded_down(self):
        atoms = (Atom("N", 0, 0, 0), Atom("Cu", 2.1, 0, 0),
                 Atom("C", -6, 0, 0), Atom("N", -7.2, 0, 0))
        bonds = (Bond(0, 1, 1, "coordinate"), Bond(2, 3, 3, "partial_triple"))
        additions, _ = missing_hydrogens(Molecule("ligand", atoms, bonds))
        self.assertEqual([i for i, _ in additions], [0, 0, 0, 2])

    def test_charged_or_open_shell_structure_retains_existing_electronic_state(self):
        atoms = (Atom("C", 0., 0., 0.),)
        for charge, multiplicity in ((1, 2), (0, 3)):
            molecule = Molecule("carbon", atoms, charge=charge, multiplicity=multiplicity)
            with self.assertRaisesRegex(ValueError, "中性单重态"):
                missing_hydrogens(molecule)


class ManualHydrogenTests(unittest.TestCase):
    def test_repeated_clicks_retain_parent_selection_and_one_undo_entry_each(self):
        editor = EditorService(Session(Molecule("seed", (Atom("C", .4, -.7, 1.2),))).document)
        initial = editor.document.head
        carbon, = initial.atom_ids
        editor.set_selection(SelectionContext(initial.ref, (carbon,)))
        for count in range(1, 9):
            before = editor.document.head
            committed = add_hydrogen(editor, carbon)
            after = committed.snapshot
            self.assertEqual(after.parent, before.ref)
            self.assertEqual(after.molecule.atoms[:-1], before.molecule.atoms)
            self.assertEqual(after.atom_ids[:-1], before.atom_ids)
            self.assertEqual(after.molecule.bonds, before.molecule.bonds + (Bond(0, count),))
            self.assertEqual(after.molecule.atoms[-1].element, "H")
            xyz = position(after.molecule.atoms[-1])
            self.assertAlmostEqual(math.dist(position(initial.molecule.atoms[0]), xyz), 1.07)
            self.assertGreater(min(math.dist(position(a)[:2], xyz[:2]) for a in before.molecule.atoms), .30)
            self.assertEqual(committed.selection.atom_ids, (carbon,))
            self.assertEqual(committed.mapping.added_indices, (count,))
        self.assertEqual(len(editor.undo_entries), 8)
        self.assertEqual(editor.undo().snapshot.molecule, before.molecule)
        restored = editor.redo().snapshot
        self.assertEqual(restored.atom_ids, after.atom_ids)
        self.assertEqual(restored.molecule, after.molecule)

    def test_four_clicks_on_new_carbon_give_tetrahedral_starting_geometry(self):
        editor = EditorService(Session(Molecule("C", (Atom("C", 0, 0, 0),))).document)
        carbon, = editor.document.head.atom_ids
        vectors = [position(add_hydrogen(editor, carbon).snapshot.molecule.atoms[-1]) for _ in range(4)]
        for i, first in enumerate(vectors):
            for second in vectors[i + 1:]:
                cosine = sum(a * b for a, b in zip(first, second)) / (math.hypot(*first) * math.hypot(*second))
                self.assertAlmostEqual(cosine, -1 / 3)

    def test_only_requested_anchor_gains_one_hydrogen_on_each_click(self):
        atoms = (Atom("C", 0, 0, 0), Atom("O", 1.43, 0, 0))
        editor = EditorService(Session(Molecule("sketch", atoms, (Bond(0, 1),))).document)
        carbon, oxygen = editor.document.head.atom_ids
        first = add_hydrogen(editor, oxygen).snapshot
        self.assertEqual(first.molecule.bonds, (Bond(0, 1), Bond(1, 2)))
        added_id = first.atom_ids[-1]
        second = add_hydrogen(editor, added_id).snapshot
        self.assertEqual(second.molecule.bonds, first.molecule.bonds + (Bond(2, 3),))
        self.assertAlmostEqual(math.dist(*map(position, second.molecule.atoms[-2:])), .74)
        third = add_hydrogen(editor, carbon).snapshot
        self.assertEqual(third.molecule.bonds, second.molecule.bonds + (Bond(0, 4),))

    def test_unknown_anchor_cannot_modify_document(self):
        editor = EditorService(Session(Molecule("C", (Atom("C", 0, 0, 0),))).document)
        initial = editor.document.head
        with self.assertRaises(ValueError):
            add_hydrogen(editor, "unknown-id")
        self.assertIs(editor.document.head, initial)
        self.assertFalse(editor.can_undo)

    def test_implicit_connectivity_charge_spin_and_unusual_elements(self):
        atoms = (Atom("O", 0, 0, 0), Atom("H", .98, 0, 0), Atom("Og", 9, 0, 0))
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                mol = Molecule("coordinate input", atoms, charge=1, multiplicity=2, bonds_explicit=explicit)
                editor = EditorService(Session(mol).document)
                result = add_hydrogen(editor, editor.document.head.atom_ids[2]).snapshot.molecule
                self.assertEqual(result.bonds, display_bonds(mol) + (Bond(2, 3),))
                self.assertTrue(result.bonds_explicit)
                self.assertEqual((result.charge, result.multiplicity), (1, 2))
                self.assertEqual(result.atoms[:-1], atoms)
                self.assertEqual(result.atoms[-1].element, "H")

    def test_existing_bond_order_and_three_dimensional_geometry(self):
        mol = Molecule("HCN", (Atom("C", 0, 0, 0), Atom("N", 1.16, 0, 0)), (Bond(0, 1, 3),))
        editor = EditorService(Session(mol).document)
        hcn = add_hydrogen(editor, editor.document.head.atom_ids[0]).snapshot.molecule
        self.assertEqual(hcn.bonds, (Bond(0, 1, 3), Bond(0, 2)))
        self.assertEqual(position(hcn.atoms[-1]), (-1.07, 0., 0.))

        mol = Molecule("tetrahedral", (Atom("C", 0, 0, 0), Atom("F", 1, 1, 1), Atom("Cl", 1, -1, -1),
                                      Atom("Br", -1, 1, -1)), (Bond(0, 1), Bond(0, 2), Bond(0, 3)))
        editor = EditorService(Session(mol).document)
        xyz = position(add_hydrogen(editor, editor.document.head.atom_ids[0]).snapshot.molecule.atoms[-1])
        self.assertLess(xyz[0], 0)
        self.assertAlmostEqual(xyz[0], xyz[1])
        self.assertAlmostEqual(xyz[1], -xyz[2])

    def test_crowded_sketch_places_hydrogen_away_from_other_fragment(self):
        mol = Molecule("obstacle", (Atom("C", 0, 0, 0), Atom("Ne", 1.07, 0, 0)), bonds_explicit=True)
        editor = EditorService(Session(mol).document)
        result = add_hydrogen(editor, editor.document.head.atom_ids[0]).snapshot.molecule
        self.assertGreater(math.dist(position(result.atoms[1]), position(result.atoms[2])), .75)
        self.assertEqual(result.bonds, (Bond(0, 2),))

"""Backbone detection on all-atom graphs without atom-name or coordinate metadata."""

from dataclasses import replace
import unittest

from orcaview.core.models import Atom, Bond, Molecule
from orcaview.core.polymer_backbone import topology_roles, validate_polymer_roles


def backbone_atoms(molecule, polymer=None):
    roles = topology_roles(molecule, polymer)
    return {i for i, role in enumerate(roles) if role != "S"} if roles else None


def molecule(elements, bonds):
    return Molecule("Structure", tuple(Atom(el, i, 0, 0) for i, el in enumerate(elements)),
                    tuple(Bond(*b) for b in bonds), bonds_explicit=True)


class PolymerBackboneTests(unittest.TestCase):
    def test_optional_roles_validate_length_and_alphabet(self):
        for roles in ("", "BS.", "..."):
            validate_polymer_roles(roles, 3)
        for roles in (None, 0, ["B", "S", "."], "BB", "BS?"):
            with self.subTest(roles=roles), self.assertRaisesRegex(ValueError, "Invalid polymer atom roles"):
                validate_polymer_roles(roles, 3)

    def test_peptide_ignores_side_chains_but_keeps_separate_water(self):
        chain = molecule(
            ("N", "C", "C", "O", "C", "N", "C", "C", "O", "O", "H", "O", "H", "H"),
            [(0, 1), (1, 2), (2, 3, 2), (1, 4), (2, 5), (5, 6), (6, 7),
             (7, 8, 2), (7, 9), (0, 10), (11, 12), (11, 13), (10, 11, 1, "hydrogen_bond")])
        self.assertEqual(backbone_atoms(chain), {0, 1, 2, 5, 6, 7, 11, 12, 13})
        self.assertEqual(topology_roles(chain), "BBBSSBBBSSS...")
        # The choice follows chemical identity even when file rows are reversed.
        last = len(chain.atoms) - 1
        reversed_chain = replace(chain, atoms=chain.atoms[::-1],
                                 bonds=tuple(replace(b, a=last-b.a, b=last-b.b) for b in chain.bonds))
        self.assertEqual(backbone_atoms(reversed_chain), {last-i for i in backbone_atoms(chain)})
        self.assertEqual(topology_roles(reversed_chain), topology_roles(chain)[::-1])

    def test_source_hint_handles_a_single_amino_acid_without_classifying_every_such_ligand(self):
        alanine = molecule("NCCOCO", [(0, 1), (1, 2), (2, 3, 2), (1, 4), (2, 5)])
        self.assertIsNone(backbone_atoms(alanine))
        self.assertEqual(topology_roles(alanine), "")
        self.assertEqual(backbone_atoms(alanine, "protein"), {0, 1, 2})
        # A familiar file title alone does not make a set of coordinates a protein.
        self.assertIsNone(backbone_atoms(replace(alanine, name="Protein", bonds=())))

    def test_sugar_phosphate_path_ignores_base_and_distinguishes_ribose(self):
        # Residue atom order: O5′ C5′ C4′ O4′ C1′ C2′ C3′ O3′ N(base).
        sugar = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 2), (6, 7), (4, 8)]
        units = "OCCOCCCON"
        bonds = sugar + [(a+9, b+9) for a, b in sugar]
        # Atom 18 is the bridging phosphate. Atoms 21–22 are a 3′ terminal phosphate.
        bonds += [(7, 18), (18, 9), (18, 19, 2), (18, 20), (16, 21), (21, 22, 2)]
        dna = molecule(units * 2 + "POOPO", bonds)
        expected = {0, 1, 2, 6, 7, 9, 10, 11, 15, 16, 18, 21}
        self.assertEqual(backbone_atoms(dna), expected)
        self.assertEqual(backbone_atoms(dna, "dna"), expected)
        self.assertIsNone(backbone_atoms(molecule(units * 2 + "POOPOOO",
                                                  bonds + [(5, 23), (14, 24)])))
        monomer = molecule(units, sugar)
        self.assertIsNone(backbone_atoms(monomer))
        self.assertEqual(backbone_atoms(monomer, "dna"), {0, 1, 2, 6, 7})

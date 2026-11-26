from collections import Counter, defaultdict
from importlib.util import find_spec
import math
import unittest

from orcaview.core.geometry import connected_component
from orcaview.io.biopolymer_sequence import build_sequence, build_sequence_record, normalize_sequence


class SequenceInputTests(unittest.TestCase):
    def test_plain_and_single_record_fasta(self):
        self.assertEqual(normalize_sequence("dna", "a c\ng\tt"), "ACGT")
        self.assertEqual(normalize_sequence("protein", "  >example\r\nAc\r\nGT  "), "ACGT")
        for text in ("", ">title", ">one\nAC\n>two\nGT", "AN", "A1", "A-U", "Aß"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                normalize_sequence("dna", text)
        for text in ("X", "U", "Aß", "A*"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                normalize_sequence("protein", text)


@unittest.skipUnless(find_spec("openbabel"), "requires the native sequence reader")
class SequenceStructureTests(unittest.TestCase):
    def test_native_templates_identify_only_the_continuous_chain(self):
        for kind, sequence, expected in (("protein", "AGST", "NCC" * 4), ("dna", "ACGT", "POCCCO" * 8)):
            with self.subTest(kind=kind):
                rec = build_sequence_record(kind, sequence)
                visible = "".join(atom.element for atom, role in zip(rec.molecule.atoms, rec.polymer_roles)
                                  if role == "B")
                self.assertEqual(visible, expected)
                self.assertEqual(set(rec.polymer_roles), {"B", "S"})

    def test_short_peptide_contains_a_single_amide_bond_and_explicit_hydrogens(self):
        molecule = build_sequence("protein", ">DNA-looking letters\na\ng")
        atoms = molecule.atoms
        self.assertEqual(Counter(a.element for a in atoms), {"C": 5, "H": 10, "N": 2, "O": 3})
        self.assertTrue(molecule.bonds_explicit)
        self.assertEqual(len(connected_component(molecule.bonds, 0)), len(atoms))
        neighbors = defaultdict(list)
        for b in molecule.bonds:
            neighbors[b.a].append((atoms[b.b], b.order))
            neighbors[b.b].append((atoms[b.a], b.order))
        amides = [(atoms[i], neighbor) for i, edges in neighbors.items() if atoms[i].element == "C"
                  and any(a.element == "O" and order == 2 for a, order in edges)
                  for neighbor, order in edges if neighbor.element == "N" and order == 1]
        self.assertEqual(len(amides), 1)
        carbon, nitrogen = amides[0]
        length = math.dist((carbon.x, carbon.y, carbon.z), (nitrogen.x, nitrogen.y, nitrogen.z))
        self.assertTrue(1.25 < length < 1.45)

    def test_standard_amino_acids_and_drawn_side_chain_charges(self):
        for sequence, expected in (("ACDEFGHIKLMNPQRSTVWY", 0), ("DKR", 1), ("DEP", -2)):
            with self.subTest(sequence=sequence):
                molecule = build_sequence("protein", sequence)
                molecule.validate()
                self.assertEqual((molecule.charge, molecule.multiplicity), (expected, 1))
                self.assertEqual(len(connected_component(molecule.bonds, 0)), len(molecule.atoms))

    def test_duplex_has_two_complementary_antiparallel_backbones(self):
        molecule = build_sequence("dna", "aAg")
        molecule.validate()
        self.assertEqual((molecule.charge, molecule.multiplicity), (-6, 1))
        first = connected_component(molecule.bonds, 0)
        second = connected_component(molecule.bonds, next(i for i in range(len(molecule.atoms)) if i not in first))
        self.assertEqual(len(first) + len(second), len(molecule.atoms))
        def elements(strand):
            return Counter(molecule.atoms[i].element for i in strand)
        # Input AAG (three purines) is paired with CTT (three pyrimidines).
        self.assertEqual((elements(first)["N"], elements(second)["N"]), (15, 7))
        for strand, direction in ((first, 1), (second, -1)):
            # The reader orders residues 5' to 3' and places the helix along x.
            phosphates = [molecule.atoms[i] for i in sorted(strand) if molecule.atoms[i].element == "P"]
            self.assertEqual(len(phosphates), 3)
            for start, end in zip(phosphates, phosphates[1:]):
                self.assertAlmostEqual((end.x - start.x) * direction, 3.38, places=2)

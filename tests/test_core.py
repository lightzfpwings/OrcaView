'Domain validation and display bonds without a quantum chemistry program.'

import unittest

from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.geometry import infer_bonds
from orcaview.core.models import Atom, Bond, CalculationSpec, Molecule


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.water = Molecule("water", (Atom("O", 0, 0, 0), Atom("H", 0.7586, 0, 0.5043), Atom("H", -0.7586, 0, 0.5043)))

    def test_periodic_table_complete(self):
        self.assertEqual(len(ATOMIC_NUMBERS), 118)
        self.assertEqual(ATOMIC_NUMBERS["Og"], 118)

    def test_water_electron_count(self):
        self.water.validate()
        self.assertEqual(self.water.electron_count, 10)

    def test_odd_electron_requires_compatible_spin(self):
        with self.assertRaisesRegex(ValueError, 'multiplicity'):
            Molecule("H", (Atom("H", 0, 0, 0),)).validate()
        Molecule("H", (Atom("H", 0, 0, 0),), multiplicity=2).validate()

    def test_charge_changes_spin_parity(self):
        Molecule("water cation", self.water.atoms, charge=1, multiplicity=2).validate()
        with self.assertRaises(ValueError):
            Molecule("water cation", self.water.atoms, charge=1, multiplicity=1).validate()

    def test_impossible_electronic_states(self):
        for charge, multiplicity in ((100, 1), (0, 20), (0, 0), (True, 1), (0, 1.0)):
            with self.subTest(charge=charge, multiplicity=multiplicity):
                with self.assertRaises(ValueError):
                    Molecule("water", self.water.atoms, charge=charge, multiplicity=multiplicity).validate()

    def test_invalid_atoms(self):
        for atom in (Atom("XX", 0, 0, 0), Atom("O", float("nan"), 0, 0), Atom("O", float("inf"), 0, 0), Atom("O", True, 0, 0)):
            with self.subTest(atom=atom):
                with self.assertRaises(ValueError):
                    atom.validate()

    def test_invalid_bonds(self):
        for bonds in ((Bond(0, 0),), (Bond(0, 3),), (Bond(-1, 1),), (Bond(0, 1, 4),), (Bond(0, 1), Bond(1, 0))):
            with self.subTest(bonds=bonds):
                with self.assertRaises(ValueError):
                    Molecule("water", self.water.atoms, bonds).validate_structure()

    def test_empty_molecule_is_invalid(self):
        with self.assertRaises(ValueError):
            Molecule("empty", ()).validate()

    def test_molecule_name_must_be_nonempty_string(self):
        for name in (123, "", "   "):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    Molecule(name, self.water.atoms).validate_structure()

    def test_bonds_are_display_heuristic(self):
        self.assertEqual(infer_bonds(self.water), (Bond(0, 1), Bond(0, 2)))
        isolated = Molecule("distant", (Atom("H", 0, 0, 0), Atom("H", 20, 0, 0)))
        self.assertEqual(infer_bonds(isolated), ())

    def test_calculation_input_validation(self):
        CalculationSpec().validate()
        for kwargs in ({"method": "B3LYP\n%pal"}, {"basis": "def2-SVP ! OPT"}, {"method": "!B3LYP"}, {"basis": "def2-SVP#comment"}, {"cores": 0}, {"maxcore_mb": -1}, {"cores": True}, {"job_type": "TS"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    CalculationSpec(**kwargs).validate()

    def test_only_reviewed_method_and_basis_templates_are_supported(self):
        for kwargs in ({"method": "bohrs"}, {"basis": "Opt"}, {"method": "DLPNO-CCSD(T)", "job_type": "FREQ"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    CalculationSpec(**kwargs).validate()
        for method in ("HF", "B3LYP", "PBE0", "PBE"):
            CalculationSpec(method=method).validate()
        for basis in ("def2-SVP", "def2-TZVP", "def2-TZVPP"):
            CalculationSpec(basis=basis).validate()


if __name__ == "__main__":
    unittest.main()

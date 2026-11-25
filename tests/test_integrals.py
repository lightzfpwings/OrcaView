"""SCF approximation, fitting-slot, and orbital basis contracts for ORCA 6.1.1."""

from dataclasses import replace
import unittest

from orcaview.core.integrals import (
    BASES, auxiliary_basis_block, auxiliary_options, basis_options, effective_electron_count,
    grid_options, integral_options, orbital_and_aux_keywords, scalar_options, uses_numerical_scalar_frequencies,
)
from orcaview.core.models import Atom, CalculationSpec, Molecule
from orcaview.orca.input import render_input


def atom(symbol, multiplicity=1):
    return Molecule(symbol, (Atom(symbol, 0, 0, 0),), multiplicity=multiplicity)


class IntegralTests(unittest.TestCase):
    def test_auto_preserves_the_existing_defaults_and_fixed_methods(self):
        for method, expected in (
            ("HF", ("def2-SVP",)), ("PBE0", ("def2-SVP",)), ("PBE", ("def2-SVP",)),
            ("RI-MP2", ("def2-SVP", "def2-SVP/C")), ("B2PLYP", ("def2-SVP", "def2-SVP/C")),
            ("r2SCAN-3c", ()), ("Native-GFN2-xTB", ()),
        ):
            with self.subTest(method=method):
                spec = CalculationSpec(method=method)
                self.assertEqual(orbital_and_aux_keywords(spec), expected)
                self.assertEqual(auxiliary_basis_block(spec), ())
        self.assertIn("def2-TZVPP", BASES)
        self.assertEqual(basis_options("r2SCAN-3c"), ())
        self.assertEqual(integral_options("Native-GFN2-xTB"), ("Auto",))

    def test_scf_ri_and_correlation_fits_are_independent(self):
        ri = CalculationSpec(method="RI-MP2", integral_approximation="RIJCOSX")
        self.assertEqual(orbital_and_aux_keywords(ri), ("def2-SVP", "RIJCOSX", "def2/J", "def2-SVP/C"))
        larger_fit = replace(ri, aux_c="def2-TZVPP/C")
        self.assertIn("def2-TZVPP/C", orbital_and_aux_keywords(larger_fit))
        exact = CalculationSpec(method="PBE0", integral_approximation="NoRI")
        self.assertEqual(orbital_and_aux_keywords(exact), ("def2-SVP", "NoRI"))
        self.assertIn("RI", integral_options("PBE"))
        self.assertNotIn("RI", integral_options("PBE0"))
        self.assertNotIn("RIJCOSX", integral_options("PBE"))
        self.assertIn("RIJONX", integral_options("HF"))

    def test_autoaux_is_emitted_only_in_selected_percent_basis_slots(self):
        spec = CalculationSpec(method="RI-MP2", integral_approximation="RIJCOSX", aux_j="AutoAux")
        self.assertEqual(orbital_and_aux_keywords(spec), ("def2-SVP", "RIJCOSX", "def2-SVP/C"))
        self.assertEqual(auxiliary_basis_block(spec), ("%basis", '  AuxJ "AutoAux"', "end"))
        both = replace(spec, aux_c="AutoAux")
        rendered = render_input(atom("He"), both)
        self.assertIn('! RI-MP2 def2-SVP RIJCOSX SP\n', rendered)
        self.assertIn('%basis\n  AuxJ "AutoAux"\n  AuxC "AutoAux"\nend\n', rendered)
        self.assertNotIn("AuxJK", rendered)
        jk_for_j = replace(spec, aux_j="def2/JK")
        self.assertEqual(auxiliary_basis_block(jk_for_j), ("%basis", '  AuxJ "def2/JK"', "end"))
        self.assertNotIn("def2/JK", orbital_and_aux_keywords(jk_for_j))

    def test_rijk_is_single_point_and_requires_exchange_fitting(self):
        spec = CalculationSpec(method="HF", integral_approximation="RI-JK")
        self.assertIn("RI-JK", integral_options("HF", "SP"))
        self.assertNotIn("RI-JK", integral_options("HF", "OPT"))
        self.assertEqual(orbital_and_aux_keywords(spec), ("def2-SVP", "RI-JK", "def2/JK"))
        self.assertEqual(set(auxiliary_options("HF", "def2-SVP", "RI-JK")), {"aux_jk"})
        for job in ("OPT", "FREQ", "OPT_FREQ"):
            with self.subTest(job=job), self.assertRaises(ValueError):
                orbital_and_aux_keywords(replace(spec, job_type=job))

    def test_rejects_inactive_slots_mismatched_families_and_keyword_injection(self):
        for spec in (
            CalculationSpec(method="HF", aux_j="def2/J"),
            CalculationSpec(method="PBE", integral_approximation="NoRI", aux_j="AutoAux"),
            CalculationSpec(method="HF", integral_approximation="RI-JK", aux_jk="def2/J"),
            CalculationSpec(method="RI-MP2", aux_c="cc-pVDZ/C"),
            CalculationSpec(method="RI-MP2", aux_c='def2-SVP/C\nend'),
            CalculationSpec(method="r2SCAN-3c", aux_c="AutoAux"),
            CalculationSpec(method="HF", cabs="cc-pVDZ-F12-CABS"),
        ):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                orbital_and_aux_keywords(spec)

    def test_orbital_coverage_and_explicit_electrons_follow_actual_basis(self):
        for basis in ("def2-SVP", "3-21G"):
            self.assertIn(basis, basis_options("CASSCF"))
        iodine = atom("I", 2)
        self.assertEqual(effective_electron_count("def2-SVP", iodine), 25)
        self.assertEqual(effective_electron_count("3-21G", iodine), 53)
        self.assertEqual(effective_electron_count("def2-QZVPP", atom("Lu", 2)), 43)
        with self.assertRaisesRegex(ValueError, "I"):
            orbital_and_aux_keywords(CalculationSpec(method="HF", basis="6-31G(d,p)"), iodine)
        with self.assertRaisesRegex(ValueError, "def2/J"):
            orbital_and_aux_keywords(CalculationSpec(method="PBE", basis="3-21G", aux_j="def2/J"), iodine)
        self.assertEqual(auxiliary_basis_block(CalculationSpec(method="PBE", basis="3-21G")),
                         ("%basis", '  AuxJ "AutoAux"', "end"))

    def test_correlation_fit_validates_its_own_element_coverage(self):
        spec = CalculationSpec(method="RI-MP2", basis="cc-pVDZ")
        calcium = atom("Ca")
        with self.assertRaisesRegex(ValueError, r"cc-pVDZ/C.*Ca"):
            orbital_and_aux_keywords(spec, calcium)
        self.assertEqual(orbital_and_aux_keywords(replace(spec, aux_c="AutoAux"), calcium), ("cc-pVDZ",))
        self.assertIn('  AuxC "AutoAux"', auxiliary_basis_block(replace(spec, aux_c="AutoAux")))
        with self.assertRaisesRegex(ValueError, "Ce"):
            orbital_and_aux_keywords(CalculationSpec(method="RI-MP2", basis="def2-SVPD"), atom("Ce"))

    def test_f12_requires_its_orbital_family_cabs_and_when_applicable_correlation_fit(self):
        orbitals = basis_options("F12-MP2")
        self.assertEqual(orbitals[:3], ("cc-pVDZ-F12", "cc-pVTZ-F12", "cc-pVQZ-F12"))
        self.assertEqual(sum(name.endswith("-F12") for name in orbitals), 9)
        self.assertIn("aug-cc-pVTZ-PP", orbitals)
        with self.assertRaises(ValueError):
            orbital_and_aux_keywords(CalculationSpec(method="F12-MP2", basis="def2-SVP"))
        exact = CalculationSpec(method="F12-MP2", basis="cc-pVDZ-F12")
        self.assertEqual(orbital_and_aux_keywords(exact, atom("He")), ("cc-pVDZ-F12", "cc-pVDZ-F12-OptRI"))
        self.assertEqual(set(auxiliary_options(exact.method, exact.basis, "Auto")), {"cabs"})
        ri = replace(exact, method="F12-RI-MP2")
        self.assertEqual(orbital_and_aux_keywords(ri),
                         ("cc-pVDZ-F12", "cc-pVDZ-F12-MP2Fit", "cc-pVDZ-F12-OptRI"))
        self.assertIn("cc-pVDZ-F12-CABS", orbital_and_aux_keywords(replace(ri, cabs="cc-pVDZ-F12-CABS"), atom("O")))
        with self.assertRaisesRegex(ValueError, "CABS.*He"):
            orbital_and_aux_keywords(replace(ri, cabs="cc-pVDZ-F12-CABS"), atom("He"))

    def test_pseudopotential_and_core_valence_f12_uses_matching_fits(self):
        for basis, symbol, electrons in (("cc-pVDZ-PP-F12", "Br", 25),
                                         ("cc-pVTZ-PP-F12", "I", 25),
                                         ("cc-pCVQZ-F12", "S", 16)):
            with self.subTest(basis=basis):
                molecule = atom(symbol, 2 if electrons % 2 else 1)
                spec = CalculationSpec(method="CCSD-F12/RI", basis=basis, integral_approximation="RI-JK")
                self.assertEqual(effective_electron_count(basis, molecule), electrons)
                self.assertEqual(orbital_and_aux_keywords(spec, molecule),
                                 (basis, "RI-JK", basis + "-MP2Fit", basis + "-OptRI"))
                self.assertIn('  AuxJK "AutoAux"', auxiliary_basis_block(spec))
        with self.assertRaisesRegex(ValueError, "O"):
            orbital_and_aux_keywords(replace(spec, basis="cc-pVDZ-PP-F12"), atom("O"))

    def test_molecular_all_electron_and_ecp_bases_use_different_core_counts(self):
        uo2 = Molecule("UO2", (Atom("U", 0, 0, 0), Atom("O", 0, 0, 1.8), Atom("O", 0, 0, -1.8)))
        self.assertEqual(effective_electron_count("LANL2DZ", uo2), 30)
        self.assertEqual(effective_electron_count("ANO-RCC-TZP", uo2), 108)
        self.assertIn("ANO-RCC-TZP DKH2 SARC/J", render_input(uo2, CalculationSpec(method="PBE", basis="ANO-RCC-TZP")))
        for basis in ("ma-def2-TZVP", "LANL2DZ"):
            self.assertEqual(effective_electron_count(basis, atom("Ag", 2)), 19)

    def test_split_coulomb_and_grid_choices_are_independent(self):
        for choice in ("Split-RI-J", "NoSplit-RI-J"):
            spec = CalculationSpec(method="PBE", integral_approximation=choice, integration_grid="DEFGRID3")
            self.assertEqual(orbital_and_aux_keywords(spec),
                             ("def2-SVP", "RI", choice, "DEFGRID3", "def2/J"))
        self.assertEqual(grid_options("HF"), ("Auto",))
        self.assertIn("DEFGRID3", grid_options("HF", "RIJCOSX"))
        self.assertIn("DEFGRID1", grid_options("B3LYP", "NoRI"))
        self.assertEqual(grid_options("AM1"), ("Auto",))
        with self.assertRaisesRegex(ValueError, 'grid'):
            orbital_and_aux_keywords(CalculationSpec(method="AM1", integration_grid="DEFGRID3"))

    def test_scalar_hamiltonians_and_matching_all_electron_fits_are_emitted_together(self):
        x2c = CalculationSpec(method="PBE", basis="x2c-TZVPall")
        self.assertEqual(orbital_and_aux_keywords(x2c), ("x2c-TZVPall", "X2C", "x2c/J"))
        self.assertEqual(effective_electron_count(x2c.basis, atom("I", 2)), 53)
        self.assertEqual(scalar_options("PBE", x2c.basis), ("Auto", "X2C", "DLU-X2C"))
        self.assertIn("DLU-X2C", orbital_and_aux_keywords(replace(x2c, relativity="DLU-X2C")))
        for wrong in (replace(x2c, aux_j="def2/J"), replace(x2c, relativity="ZORA"),
                      replace(x2c, basis="def2-TZVP", relativity="X2C")):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                orbital_and_aux_keywords(wrong)
        zora = replace(x2c, basis="ZORA-def2-TZVP", job_type="FREQ")
        self.assertFalse(uses_numerical_scalar_frequencies(zora))
        self.assertEqual(orbital_and_aux_keywords(zora), ("ZORA-def2-TZVP", "ZORA", "SARC/J"))
        self.assertIn("Freq", render_input(atom("O"), zora).splitlines()[1].split())
        with self.assertRaisesRegex(ValueError, "I"):
            orbital_and_aux_keywords(zora, atom("I", 2))
        actinide = replace(zora, basis="SARC-DKH-TZVP", job_type="SP")
        self.assertEqual(orbital_and_aux_keywords(actinide, atom("U")),
                         ("SARC-DKH-TZVP", "DKH2", "SARC/J"))
        self.assertIn("DKH2", render_input(atom("U"), actinide))

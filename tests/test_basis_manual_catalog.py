"""Boundaries verified against ORCA 6.1.1 §2.7 basis/ECP and §2.8 RI tables."""

import unittest
from dataclasses import replace

from orcaview.core._basis_library import FITTING_COVERAGE, ORBITAL_COVERAGE
from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.block_options import BlockOverride
from orcaview.core.integrals import (
    BASES, auxiliary_options, basis_options, effective_electron_count, grid_options,
    integral_options, orbital_and_aux_keywords,
)
from orcaview.core.models import Atom, CalculationSpec, Molecule
from orcaview.orca.input import render_input


def atom(symbol):
    return Molecule(symbol, (Atom(symbol, 0, 0, 0),), multiplicity=1 + ATOMIC_NUMBERS[symbol] % 2)


class BasisLibraryTests(unittest.TestCase):
    def test_full_library_and_matching_fits_are_reachable(self):
        self.assertEqual(len(ORBITAL_COVERAGE), 440)
        self.assertEqual(len(set(BASES)), 417)
        self.assertEqual(len(FITTING_COVERAGE), 84)
        selectable_bases, selectable_fits = set(), set()
        for method, approximation in (("HF", "RI-JK"), ("RI-MP2", "RIJCOSX"), ("F12-RI-MP2", "Auto")):
            for basis in basis_options(method):
                selectable_bases.add(basis)
                for choices in auxiliary_options(method, basis, approximation).values():
                    selectable_fits.update(choices)
        self.assertEqual(selectable_bases, set(BASES))
        self.assertEqual(selectable_fits - {"AutoAux"}, set(FITTING_COVERAGE))

    def test_orbital_and_hamiltonian_table_boundaries(self):
        for name, included, excluded in (
                ("6-31++G(2df,2pd)", "Zn", "Ga"), ("pcSseg-4", "Kr", "Rb"),
                ("pcH-1", "Ne", "Li"), ("Wachters+f", "Cu", "Zn"),
                ("old-DKH-TZVP", "I", "Xe"), ("cc-pwCVTZ-DK", "Y", "C"),
                ("old-TZVPP", "I", "Xe"), ("HGBSP3-9", "Og", None)):
            with self.subTest(name=name):
                self.assertEqual(effective_electron_count(name, atom(included)), ATOMIC_NUMBERS[included])
                if excluded:
                    with self.assertRaisesRegex(ValueError, excluded):
                        effective_electron_count(name, atom(excluded))
        for name in ("dhf-SVP-2c", "x2c-TZVPall-2c", "cc-pVTZ-DK3", "Sapporo-DKH3-TZP-2012"):
            self.assertIn(name, ORBITAL_COVERAGE)
            self.assertNotIn(name, basis_options("HF"))
            with self.assertRaises(ValueError):
                orbital_and_aux_keywords(CalculationSpec(method="HF", basis=name))

    def test_ecp_core_sizes_charge_and_uncertain_elements(self):
        for basis, symbol, core in (
                ("CRENBL", "Ga", 18), ("CRENBL", "Og", 92),
                ("def2-mTZVP", "Ra", 78), ("def2-mTZVPP", "Lr", 60),
                ("vDZP", "B", 2), ("vDZP", "Tl", 78), ("dhf-SVP", "I", 28),
                ("cc-pVQZ-PP", "U", 60), ("aug-cc-pCVDZ-PP", "Ra", 78),
                ("LANL2TZ(f)", "La", 46), ("ma-def-TZVP", "Fr", 78)):
            with self.subTest(basis=basis, symbol=symbol):
                self.assertEqual(effective_electron_count(basis, atom(symbol)), ATOMIC_NUMBERS[symbol] - core)
        ion = Molecule("Cu+", (Atom("Cu", 0, 0, 0),), charge=1)
        self.assertEqual(effective_electron_count("aug-cc-pVTZ-PP", ion), 18)
        for basis, symbol in (("dhf-SVP", "La"), ("MINIX", "I")):
            with self.assertRaisesRegex(ValueError, 'core electron count'):
                effective_electron_count(basis, atom(symbol))

    def test_standard_augmented_pp_orbitals_use_cabs_only_for_f12(self):
        name = "aug-cc-pwCVTZ-PP"
        self.assertNotIn("cabs", auxiliary_options("RI-MP2", name, "Auto"))
        spec = CalculationSpec(method="F12-RI-MP2", basis=name)
        self.assertEqual(orbital_and_aux_keywords(spec, atom("Cu")), (name, name + "/C", name + "-OptRI"))
        with self.assertRaisesRegex(ValueError, "OptRI.*Br"):
            orbital_and_aux_keywords(spec, atom("Br"))

    def test_ri_slots_for_casdft_response_and_mp2(self):
        self.assertEqual(set(auxiliary_options("RI-MP2", "def2-SVP", "RIJONX")), {"aux_j", "aux_c"})
        self.assertNotIn("RIJONX", integral_options("DLPNO-MP2"))
        self.assertEqual(auxiliary_options("tPBE", "def2-SVP", "Auto"), {})
        self.assertEqual(set(auxiliary_options("tPBE", "def2-SVP", "RIJCOSX")), {"aux_j", "aux_c"})
        self.assertNotIn("RI-JK", integral_options("tPBE"))
        self.assertEqual(set(auxiliary_options("TD-B2PLYP", "def2-SVP", "Auto")), {"aux_j", "aux_c"})
        self.assertIn("DEFGRID3", grid_options("TD-B2PLYP"))
        self.assertEqual(orbital_and_aux_keywords(CalculationSpec(method="PBE", basis="def2-mTZVP"), atom("U")),
                         ("def2-mTZVP", "def2-mTZVP/J"))

    def test_mdci_algorithms_activate_fit_and_check_actual_reference(self):
        for key, value in (("KCOpt", "KC_RI"), ("KCOpt", "KC_RI2"), ("TrafoType", "trafo_ri")):
            spec = CalculationSpec(method="CCSD", block_options=(BlockOverride("mdci", key, value),))
            self.assertIn("def2-SVP/C", render_input(atom("He"), spec))
            self.assertIn("def2-TZVPP/C", render_input(atom("He"), replace(spec, aux_c="def2-TZVPP/C")))
        for value in ("KC_RI", "KC_RI2", "KC_AO", "KC_AOBLAS"):
            spec = CalculationSpec(method="CCSD", block_options=(BlockOverride("mdci", "KCOpt", value),))
            with self.assertRaisesRegex(ValueError, 'closed-shell'):
                render_input(atom("Li"), spec)

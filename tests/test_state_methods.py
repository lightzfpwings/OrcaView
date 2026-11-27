"""Ground-state active spaces and vertical excitation templates for ORCA."""

import unittest

from orcaview.core._state_methods import (
    ACTIVE_SPACE_METHODS, CLOSED_SHELL_METHODS, ELECTRON_CHANNEL_METHODS,
    EXCITED_STATE_METHODS, MREOM_METHODS, RESPONSE_FUNCTIONALS, ROCIS_METHODS, STATE_METHOD_ALIASES,
    STATE_METHOD_GROUPS, state_keywords_and_block, validate_parameters, validate_state_system,
)
from orcaview.core.models import Atom, Molecule
from orcaview.core.methods import METHODS


class StateMethodTests(unittest.TestCase):
    def test_methods_are_single_point_templates(self):
        presets = dict(entry for _, entries in STATE_METHOD_GROUPS for entry in entries)
        self.assertEqual(set(presets), set(ACTIVE_SPACE_METHODS + EXCITED_STATE_METHODS))
        self.assertTrue(all(METHODS[name].job_types == ("SP",) for name in presets))
        self.assertEqual(presets["ADC2"], "sp-aux")
        self.assertEqual(presets["RI-CASPT2"], "sp-aux")
        self.assertEqual(presets["FIC-MRCI"], "sp")
        self.assertTrue(set(STATE_METHOD_ALIASES.values()) <= set(presets))

    def test_casscf_and_strongly_contracted_nevpt2(self):
        for method, keyword in (("CASSCF", ""), ("SC-NEVPT2", "SC-NEVPT2")):
            with self.subTest(method=method):
                self.assertEqual(state_keywords_and_block(method, 6, 6, None, None, 3), (
                    keyword, ("%casscf", "  nel 6", "  norb 6", "  mult 3", "  nroots 1", "end"),
                ))

    def test_excited_state_references_and_tamm_dancoff_switch(self):
        for functional in RESPONSE_FUNCTIONALS:
            for method, tda in (("TD-DFT", "false"), ("TDA-DFT", "true")):
                with self.subTest(method=method, reference=functional):
                    self.assertEqual(state_keywords_and_block(method, None, None, 4, functional, 1), (
                        functional, ("%tddft", "  nroots 4", f"  tda {tda}", "end"),
                    ))
        self.assertEqual(state_keywords_and_block("CIS", None, None, 3, None, 2), (
            "HF", ("%tddft", "  nroots 3", "  tda true", "end"),
        ))

    def test_missing_malformed_or_irrelevant_fields_are_rejected(self):
        for values in (
            ("CASSCF", None, 2, None, None), ("CASSCF", 2, None, None, None),
            ("CASSCF", 4, 1, None, None), ("CASSCF", True, 2, None, None),
            ("CASSCF", 2, 2**31, None, None), ("CASSCF", 2**31, 2**30, None, None),
            ("SC-NEVPT2", 2, 2, 3, None), ("CASSCF", 2, 2, None, "B3LYP"),
            ("CIS", None, None, 1, "PBE"), ("CIS", 2, 2, 1, None),
            ("TDA-DFT", None, None, False, "PBE"), ("TD-DFT", None, None, 0, "PBE"),
            ("TD-DFT", None, None, None, "PBE"), ("TD-DFT", None, None, 1, None),
            ("TD-DFT", None, None, 2**31, "PBE"),
            ("TD-DFT", None, None, 1, "HF"), ("TD-DFT", None, None, 1, "PBE\nend"),
            ("PBE", None, None, 1, None), ("HF", None, 2, None, None),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_parameters(*values)
        self.assertEqual(state_keywords_and_block("PBE", None, None, None, None, 1), ("PBE", ()))

    def test_active_electron_hole_and_inactive_pair_checks(self):
        oxygen = Molecule("O", (Atom("O", 0, 0, 0),), multiplicity=3)
        validate_state_system("CASSCF", oxygen, 4, 3)
        for nel, norb in ((4, 2), (1, 2), (10, 8), (3, 3)):
            with self.subTest(nel=nel, norb=norb), self.assertRaises(ValueError):
                validate_state_system("CASSCF", oxygen, nel, norb)
        for nel, norb in ((4, 2), (1, 3), (3, 3)):
            with self.subTest(nel=nel, norb=norb), self.assertRaises(ValueError):
                state_keywords_and_block("CASSCF", nel, norb, None, None, 3)

    def test_active_spaces_count_explicit_def2_ecp_electrons(self):
        for symbol, explicit in (("Rb", 9), ("La", 11), ("Ce", 30), ("Hf", 12), ("Rn", 26)):
            with self.subTest(element=symbol):
                multiplicity = 1 + explicit % 2
                molecule = Molecule(symbol, (Atom(symbol, 0, 0, 0),), multiplicity=multiplicity)
                norb = explicit // 2 + 2
                validate_state_system("CASSCF", molecule, explicit, norb)
                with self.assertRaises(ValueError):
                    validate_state_system("CASSCF", molecule, explicit + 2, norb)

    def test_excitation_needs_at_least_one_explicit_electron(self):
        radical = Molecule("H", (Atom("H", 0, 0, 0),), multiplicity=2)
        validate_state_system("CIS", radical, None, None)
        for symbol, charge in (("H", 1), ("Rb", 9)):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                molecule = Molecule(symbol, (Atom(symbol, 0, 0, 0),), charge=charge)
                validate_state_system("CIS", molecule, None, None)

    def test_state_specific_post_cas_and_alternative_solvers(self):
        for method, simple, extra in (
            ("CASCI", "", ("  maxiter 1",)),
            ("ICE-CASSCF", "", ("  cistep ICE",)),
            ("ICE-CASCI", "", ("  cistep ICE", "  maxiter 1")),
            ("DMRG-CASSCF", "", ("  cistep DMRGCI",)),
            ("FIC-NEVPT2", "", ("  PTMethod FIC_NEVPT2",)),
            ("RI-NEVPT2", "RI-NEVPT2", ()),
            ("CASPT2K", "CASPT2K", ()),
            ("DLPNO-NEVPT2", "DLPNO-NEVPT2", ()),
            ("FIC-NEVPT4(SD)", "FIC-NEVPT4(SD)", ()),
            ("FIC-MRCI", "FIC-MRCI", ()),
        ):
            with self.subTest(method=method):
                self.assertEqual(state_keywords_and_block(method, 4, 3, None, None, 3), (
                    simple, ("%casscf", "  nel 4", "  norb 3", "  mult 3", "  nroots 1", *extra, "end"),
                ))

    def test_neutral_and_ionized_mdci_roots_use_mdci_not_tddft(self):
        for method in ("EOM-CCSD", "STEOM-CCSD", "IH-FSMR-CCSD", "ADC2",
                       "bt-PNO-STEOM-CCSD", "IP-ADC2", "EA-ADC2", "EA-EOM-DLPNO-CCSD"):
            with self.subTest(method=method):
                self.assertEqual(state_keywords_and_block(method, None, None, 2, None, 1), (
                    method, ("%mdci", "  nroots 2", "end"),
                ))
        self.assertEqual(state_keywords_and_block("STEOM-CCSD(2)", None, None, 2, None, 1), (
            "STEOM-CCSD", ("%mdci", "  nroots 2", "  CCSD2 true", "end"),
        ))

    def test_electron_removal_and_attachment_channels_are_explicit_for_open_shell(self):
        for method in ELECTRON_CHANNEL_METHODS:
            with self.subTest(method=method):
                for channel, line in (("alpha", "  DoAlpha true"), ("beta", "  DoBeta true")):
                    self.assertEqual(state_keywords_and_block(method, None, None, 1, None, 2, channel),
                                     (method, ("%mdci", "  nroots 1", line, "end")))
                    with self.assertRaises(ValueError):
                        state_keywords_and_block(method, None, None, 1, None, 1, channel)
                with self.assertRaises(ValueError):
                    state_keywords_and_block(method, None, None, 1, None, 2)
                with self.assertRaises(ValueError):
                    state_keywords_and_block(method, None, None, 1, None, 2, "both")
        with self.assertRaises(ValueError):
            validate_parameters("EOM-CCSD", None, None, 1, None, "alpha")
        radical = Molecule("H", (Atom("H", 0, 0, 0),), multiplicity=2)
        with self.assertRaisesRegex(ValueError, "beta"):
            validate_state_system("IP-EOM-CCSD", radical, None, None, "beta", basis="cc-pVDZ")
        validate_state_system("EA-EOM-CCSD", radical, None, None, "beta", basis="cc-pVDZ")

    def test_restricted_references_and_spin_flips(self):
        for method in CLOSED_SHELL_METHODS:
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, 'closed-shell'):
                state_keywords_and_block(method, None, None, 1, None, 3)
        for method, reference in (("SF-CIS", "HF"), ("SF-TDA-BHANDHLYP", "BHANDHLYP")):
            with self.subTest(method=method):
                self.assertEqual(state_keywords_and_block(method, None, None, 3, None, 3), (
                    reference, ("%tddft", "  nroots 3", "  tda true", "  sf true", "end"),
                ))
                with self.assertRaisesRegex(ValueError, 'multiplicity'):
                    state_keywords_and_block(method, None, None, 3, None, 2)

    def test_rpa_and_cisd_corrections_are_distinct(self):
        self.assertEqual(state_keywords_and_block("TD-HF", None, None, 2, None, 1), (
            "HF", ("%tddft", "  nroots 2", "  tda false", "end"),
        ))
        for method, extra in (("CIS(D)", ()), ("SCS-CIS(D)", (
                "  doscs true", "  scspar 0.333, 1.2, 0.43, 1.24"))):
            with self.subTest(method=method):
                self.assertEqual(state_keywords_and_block(method, None, None, 2, None, 1), (
                    "HF", ("%tddft", "  nroots 2", "  tda true", "  dcorr 1", *extra, "end"),
                ))

    def test_mr_eom_configures_reference_and_final_cas_blocks(self):
        for method in MREOM_METHODS:
            with self.subTest(method=method):
                self.assertIn(method, ACTIVE_SPACE_METHODS)
                self.assertIn(method, EXCITED_STATE_METHODS)
                simple, lines = state_keywords_and_block(method, 4, 3, 2, None, 3)
                self.assertEqual(simple, "MR-EOM" if method == "MR-EOM-MRPT" else method)
                self.assertEqual(lines[:6], ("%casscf", "  nel 4", "  norb 3",
                                             "  mult 3", "  nroots 2", "end"))
                self.assertEqual(lines[-6:], ("%mrci", "  newblock 3 *", "    nroots 2",
                                               "    refs cas(4,3) end", "  end", "end"))
                expected = ("%mdci", "  DoMREOM_MRPT true", "end") if method == "MR-EOM-MRPT" else ()
                self.assertEqual(lines[6:-6], expected)
                with self.assertRaises(ValueError):
                    validate_parameters(method, 4, 3, None, None)
                with self.assertRaises(ValueError):
                    validate_parameters(method, None, None, 2, None)

    def test_mr_eom_roots_fit_spin_adapted_active_space(self):
        for electrons, orbitals, mult, capacity in ((2, 2, 1, 3), (2, 2, 3, 1), (3, 3, 2, 8),
                                                    (3, 3, 4, 1), (4, 3, 1, 6), (4, 3, 3, 3)):
            with self.subTest(electrons=electrons, orbitals=orbitals, mult=mult):
                state_keywords_and_block("MR-EOM", electrons, orbitals, capacity, None, mult)
                with self.assertRaisesRegex(ValueError, 'roots'):
                    state_keywords_and_block("MR-EOM", electrons, orbitals, capacity + 1, None, mult)
        # The representable integer limit should never trigger an unbounded
        # factorial calculation just to establish that there are enough roots.
        state_keywords_and_block("MR-EOM", 2**30, 2**30, 2**31 - 1, None, 1)

    def test_rocis_high_spin_references_scaling_and_ri(self):
        presets = dict(entry for _, entries in STATE_METHOD_GROUPS for entry in entries)
        for method in ROCIS_METHODS:
            with self.subTest(method=method):
                keyword, lines = state_keywords_and_block(method, None, None, 3, None, 3)
                self.assertIn("%rocis", lines)
                self.assertIn("  DoGenROCIS false", lines)
                self.assertIn("  NRoots 3", lines)
                ri = method.startswith("RI-")
                self.assertEqual(presets[method], "sp-aux" if ri else "sp")
                self.assertIn(f"  DoRI {'true' if ri else 'false'}", lines)
                if method.endswith("/DFT"):
                    self.assertEqual(keyword, "B3LYP")
                    self.assertIn("  DoDFTCIS true", lines)
                    self.assertIn("  DFTCIS_c = 0.18, 0.20, 0.40", lines)
                else:
                    self.assertEqual(keyword, "HF")
                    self.assertIn("  HFTyp ROHF", lines)
                    self.assertIn("  ROHF_Nel[1] = 2", lines)
                with self.assertRaisesRegex(ValueError, 'high-spin'):
                    state_keywords_and_block(method, None, None, 3, None, 1)

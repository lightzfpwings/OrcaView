"""Method-specific ORCA input blocks, including nested CAS solver stages."""

from dataclasses import replace
import unittest

from orcaview.application.session import Session
from orcaview.core.block_options import BlockOverride
from orcaview.core.models import CalculationSpec
from orcaview.core._solver_block_catalog import solver_options
from orcaview.orca.input import render_input


def slots(spec):
    return {(opt.block, opt.key) for opt in solver_options(spec)}


def overrides(*triples):
    return tuple(BlockOverride(*entry) for entry in triples)


class SolverBlockTests(unittest.TestCase):
    def setUp(self):
        self.molecule = Session().molecule

    def test_response_eom_and_adc_do_not_share_unrelated_solver_controls(self):
        for method, block in (("TD-DFT", "tddft"), ("CIS(D)", "tddft"), ("ROCIS", "rocis")):
            with self.subTest(method=method):
                self.assertIn((block, "RTol"), slots(CalculationSpec(method=method)))
        eom = CalculationSpec(method="EOM-CCSD", nroots=2, block_options=overrides(
            ("mdci", "NDav", 32), ("mdci", "DTol", 1e-6), ("mdci", "DoRootwise", False)))
        text = render_input(self.molecule, eom)
        self.assertEqual(text.count("%mdci"), 1)
        self.assertIn("  nroots 2\n", text)
        self.assertIn("  DoRootwise false\n", text)
        self.assertIn("  NDav 32\n", text)
        self.assertIn("  DTol 1e-06\n", text)
        adc_slots = slots(replace(eom, method="ADC2"))
        self.assertIn(("mdci", "RootHoming"), adc_slots)
        self.assertNotIn(("mdci", "STol"), adc_slots)
        self.assertIn(("mdci", "VThresh"), slots(replace(eom, method="STEOM-CCSD")))
        self.assertNotIn(("mdci", "VThresh"), slots(eom))
        with self.assertRaises(ValueError):
            render_input(self.molecule, replace(eom, method="CIS"))

    def test_active_space_reference_and_inner_ci_have_independent_maxiter(self):
        spec = CalculationSpec(method="CASPT2", active_electrons=2, active_orbitals=2,
                               block_options=overrides(("casscf.CI", "MaxIter", 47),
                                                       ("casscf", "MaxIter", 83),
                                                       ("casscf.PTSettings", "MaxIter", 52),
                                                       ("casscf.PTSettings", "CASPT2_ishift", 0.15)))
        text = render_input(self.molecule, spec)
        self.assertEqual(text.count("%casscf"), 1)
        self.assertIn("  MaxIter 83\n", text)
        self.assertIn("  CI\n    MaxIter 47\n  end\n", text)
        self.assertIn("  PTSettings\n    MaxIter 52\n    CASPT2_ishift 0.15\n  end\n", text)
        with self.assertRaises(ValueError):
            render_input(self.molecule, replace(spec, method="CASSCF"))
        with self.assertRaises(ValueError):
            render_input(self.molecule, replace(spec, method="CASCI"))
        with self.assertRaises(ValueError):
            render_input(self.molecule, replace(spec, block_options=overrides(("casscf", "MaxIter", 1))))

    def test_ice_maxiter_is_always_ci_not_casci_macro_iteration(self):
        spec = CalculationSpec(method="ICE-CASCI", active_electrons=2, active_orbitals=2,
                               block_options=overrides(("casscf.CI", "TGen", 1e-5),
                                                       ("casscf.CI", "TVar", -1e-7),
                                                       ("casscf.CI", "ICEType", "CFGs")))
        text = render_input(self.molecule, spec)
        self.assertIn("  maxiter 1\n", text)
        self.assertIn("  CI\n    TGen 1e-05\n    TVar -1e-07\n    ICEType CFGs\n  end", text)
        self.assertNotIn(("casscf", "MaxIter"), slots(spec))
        self.assertNotIn(("casscf.CI", "ETol"), slots(replace(spec, method="DMRG-CASSCF")))
        self.assertNotIn(("casscf.CI", "TGen"), slots(replace(spec, method="CASCI")))
        self.assertIn(("casscf.PTSettings", "D3TPre"), slots(replace(spec, method="FIC-NEVPT2")))

    def test_mr_eom_merges_mdci_and_preserves_newblock(self):
        spec = CalculationSpec(method="MR-EOM-MRPT", active_electrons=2, active_orbitals=2, nroots=2,
                               block_options=overrides(("mrci", "Etol", 1e-7), ("mdci", "STol", 1e-8)))
        text = render_input(self.molecule, spec)
        self.assertEqual(text.count("%mdci"), 1)
        self.assertEqual(text.count("%mrci"), 1)
        self.assertIn("  newblock 1 *\n", text)
        self.assertIn("  DoMREOM_MRPT true\n  STol 1e-08\nend", text)
        self.assertIn("  Etol 1e-07\n", text)

    def test_pno_presets_and_manual_cutoffs_are_exclusive(self):
        for method, block in (("DLPNO-CCSD(T)", "mdci"), ("DLPNO-MP2", "mp2")):
            spec = CalculationSpec(method=method, block_options=overrides((block, "TCutPNO", 1e-8)))
            self.assertIn("  TCutPNO 1e-08", render_input(self.molecule, spec))
            with self.assertRaises(ValueError):
                render_input(self.molecule, replace(spec, pno_preset="TightPNO"))

    def test_regularized_mp2_requires_supported_integrals_single_points_and_matching_regulator(self):
        spec = CalculationSpec(method="RI-MP2", integral_approximation="RIJCOSX",
                               block_options=overrides(("mp2", "DoRegMP2", True),
                                                       ("mp2", "RegMP2Type", 2), ("mp2", "RegMP2Sigma", .5)))
        text = render_input(self.molecule, spec)
        self.assertIn("  RegMP2Sigma 0.5\n", text)
        for changed in (replace(spec, job_type="OPT"), replace(spec, integral_approximation="Auto"),
                        replace(spec, block_options=spec.block_options[1:]),
                        replace(spec, block_options=spec.block_options + overrides(("mp2", "RegMP2Kappa", 1.1)))):
            with self.assertRaises(ValueError):
                render_input(self.molecule, changed)
        canonical = CalculationSpec(method="MP2", block_options=overrides(("mp2", "DoRegMP2", True)))
        with self.assertRaises(ValueError):
            render_input(self.molecule, canonical)
        self.assertIn("  DoRegMP2 true", render_input(self.molecule, replace(
            canonical, block_options=canonical.block_options + overrides(("mp2", "Q1Opt", 1)))))
        for q1 in (0, -1):
            with self.assertRaises(ValueError):
                render_input(self.molecule, replace(canonical, job_type="OPT",
                                                    block_options=overrides(("mp2", "Q1Opt", q1))))

    def test_correlation_implementations_have_distinct_blocks(self):
        for method, block, key, value in (("AUTOCI-CCSD", "autoci", "STol", 1e-8),
                                          ("MRCC-CCSDT", "mrcc", "ETol", 9),
                                          ("CIM-RI-MP2", "cim", "CIMTHRESH", 0.0005)):
            spec = CalculationSpec(method=method, block_options=overrides((block, key, value)))
            self.assertIn("%" + block, render_input(self.molecule, spec))
        self.assertNotIn(("mdci", "STol"), slots(CalculationSpec(method="AUTOCI-CCSD")))
        self.assertNotIn(("autoci", "MaxIter"), slots(CalculationSpec(method="AUTOCI-MP2")))
        self.assertEqual(slots(CalculationSpec(method="GFN2-xTB")), set())

    def test_module_specific_memory_can_override_the_global_default(self):
        for cap in (500, 2300):
            spec = CalculationSpec(method="RI-MP2", maxcore_mb=1000, block_options=overrides(("mp2", "MaxCore", cap)))
            self.assertIn(f"%mp2\n  MaxCore {cap}\nend", render_input(self.molecule, spec))
            self.assertEqual(spec.peak_maxcore_per_process, max(1000, cap))

    def test_casscf_orbital_stages_select_their_own_solver_controls(self):
        spec = CalculationSpec(method="CASSCF", active_electrons=2, active_orbitals=2)
        good = overrides(("casscf", "OrbStep", "SuperCI_PT"), ("casscf", "MaxRot", .04),
                         ("casscf", "SwitchStep", "NR"), ("casscf.aughess", "Solver", 2),
                         ("casscf.aughess", "MaxDIIS", 8))
        text = render_input(self.molecule, replace(spec, block_options=good))
        self.assertIn("  aughess\n    Solver 2\n    MaxDIIS 8\n  end", text)
        for bad in (good[3:], overrides(("casscf", "OrbStep", "DIIS"), ("casscf", "SwitchStep", "NR"),
                                        ("casscf", "MaxRot", .04)),
                    overrides(("casscf", "OrbStep", "NR"), ("casscf.aughess", "Solver", 2),
                              ("casscf.aughess", "MaxDim", 30))):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                render_input(self.molecule, replace(spec, block_options=bad))
        self.assertNotIn(("casscf", "OrbStep"), slots(replace(spec, method="ctPBE")))
        self.assertIn(("method", "RangeSepMu"), slots(replace(spec, method="sr-ctPBE")))

    def test_dmrg_and_multiconfigurational_response_have_distinct_nested_inputs(self):
        spec = CalculationSpec(method="DMRG-CASCI", active_electrons=2, active_orbitals=2,
                               block_options=overrides(("casscf.dmrg", "maxM", 100), ("casscf.dmrg", "SweepTol", 1e-8)))
        text = render_input(self.molecule, spec)
        self.assertIn("  maxiter 1", text)
        self.assertIn("  dmrg\n    maxM 100\n    SweepTol 1e-08\n  end", text)
        self.assertNotIn(("casscf.CI", "MaxDim"), slots(spec))
        self.assertNotIn(("casscf", "OrbStep"), slots(spec))
        with self.assertRaisesRegex(ValueError, "startM"):
            render_input(self.molecule, replace(spec, block_options=spec.block_options + overrides(("casscf.dmrg", "startM", 200))))
        mcrpa = replace(spec, method="MCTDA", nroots=2, block_options=overrides(("mcrpa", "PreConMaxRed", 200)))
        self.assertIn("  TDA true\n  PreConMaxRed 200", render_input(self.molecule, mcrpa))
        with self.assertRaisesRegex(ValueError, "PreCond"):
            render_input(self.molecule, replace(mcrpa, block_options=mcrpa.block_options + overrides(("mcrpa", "PreCond", "diag"))))

    def test_dlpno_regularization_and_post_cas_scopes(self):
        ri = CalculationSpec(method="RI-MP2", integral_approximation="RIJONX",
                             block_options=overrides(("mp2", "DoRegMP2", True)))
        self.assertIn(("mp2", "DoRegMP2"), slots(ri))
        for method in ("DLPNO-MP2", "DLPNO-B2PLYP"):
            local = CalculationSpec(method=method)
            self.assertIn(("mp2", "TCutDOij"), slots(local))
            self.assertNotIn(("mp2", "TCutDOij"), slots(replace(local, pno_preset="TightPNO")))
            self.assertNotIn(("mp2", "DoRegMP2"), slots(local))
        self.assertNotIn(("mdci", "TCutTNO"), slots(CalculationSpec(method="DLPNO-CCSD")))
        self.assertIn(("mdci", "TCutTNO"), slots(CalculationSpec(method="DLPNO-CCSD(T1)")))
        self.assertIn(("casscf.PTSettings", "imaginary"), slots(CalculationSpec(method="FIC-NEVPT2")))
        self.assertNotIn(("casscf.PTSettings", "imaginary"), slots(CalculationSpec(method="SC-NEVPT2")))
        self.assertIn(("casscf.PTSettings", "TReg"), slots(CalculationSpec(method="CASPT2K")))
        self.assertNotIn(("casscf.PTSettings", "TReg"), slots(CalculationSpec(method="CASPT2")))
        with self.assertRaisesRegex(ValueError, "Q1Opt"):
            render_input(self.molecule, CalculationSpec(method="MP2", block_options=overrides(("mp2", "Q1Opt", 3))))

    def test_canonical_mdci_has_independent_external_integral_and_transformation_choices(self):
        spec = CalculationSpec(method="CCSD", wavefunction="RHF")
        for kc, trafo in (("KC_MO", "trafo_full"), ("KC_AOX", "trafo_jk"), ("KC_AO", "trafo_jk"),
                          ("KC_RI", "trafo_jk"), ("KC_RI", "trafo_ri")):
            with self.subTest(kc=kc, trafo=trafo):
                configured = replace(spec, block_options=overrides(("mdci", "KCOpt", kc), ("mdci", "TrafoType", trafo)))
                text = render_input(self.molecule, configured)
                self.assertIn(f"  KCOpt {kc}\n  TrafoType {trafo}", text)
                self.assertNotIn("RIJCOSX", text)
        with self.assertRaisesRegex(ValueError, "KC_MO"):
            render_input(self.molecule, replace(spec, block_options=overrides(("mdci", "KCOpt", "KC_MO"),
                                                                             ("mdci", "TrafoType", "trafo_ri"))))
        with self.assertRaisesRegex(ValueError, "KCOpt"):
            render_input(self.molecule, replace(spec, wavefunction="UHF", block_options=overrides(("mdci", "KCOpt", "KC_RI"))))
        for method in ("DLPNO-CCSD", "CIS", "EOM-CCSD", "AUTOCI-CCSD", "CCSD-F12"):
            self.assertNotIn(("mdci", "TrafoType"), slots(replace(spec, method=method)))

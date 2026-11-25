import io
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import unittest

from orcaview.application.session import Session
from orcaview.application._project_format import has_advanced_settings
from orcaview.cli import main
from orcaview.core.methods import (
    ACTIVE_SPACE_METHODS, EARLIER_METHODS, EXCITED_STATE_METHODS, METHODS, METHOD_GROUPS,
    canonical_method, dispersion_options,
)
from orcaview.core._state_methods import REFERENCE_FUNCTIONAL_METHODS, ROCIS_METHODS, SPIN_FLIP_METHODS
from orcaview.core.integrals import basis_options
from orcaview.core.models import Atom, CalculationSpec, Molecule
from orcaview.orca.input import InputCompanionFile, freeze_input, render_input


class MethodCatalogTests(unittest.TestCase):
    def setUp(self):
        self.geometry = Session().document.head

    def test_catalog_entries_render_through_preview_and_freeze(self):
        listed = [name for names in METHOD_GROUPS.values() for name in names]
        self.assertCountEqual(listed, METHODS.keys())
        for name, preset in METHODS.items():
            params = {}
            if name in ACTIVE_SPACE_METHODS:
                params.update(active_electrons=2, active_orbitals=2)
            if name in EXCITED_STATE_METHODS:
                params["nroots"] = 2
            if name in REFERENCE_FUNCTIONAL_METHODS:
                params["reference_functional"] = "B3LYP"
            geometry = self.geometry
            if name in SPIN_FLIP_METHODS or name in ROCIS_METHODS:
                geometry = replace(geometry, molecule=replace(geometry.molecule, multiplicity=3))
            for job in preset.job_types:
                with self.subTest(name=name, job=job):
                    basis = (basis_options(name) or ("def2-SVP",))[0]
                    spec = CalculationSpec(method=name, job_type=job, basis=basis, **params)
                    text = render_input(geometry.molecule, spec)
                    self.assertEqual(freeze_input(geometry, spec, target_orca_version="6.1.1").input_text, text)
                    self.assertEqual(basis in text.splitlines()[1].split(), preset.uses_orbital_basis)

    def test_reviewed_keyword_combinations(self):
        for method, job, expected in (
            ("B3LYP", "OPT_FREQ", "B3LYP def2-TZVP Opt Freq"),
            ("r2SCAN-3c", "OPT_FREQ", "r2SCAN-3c Opt Freq"),
            ("Native-GFN2-xTB", "OPT", "Native-GFN2-xTB Opt"),
            ("RI-MP2", "FREQ", "RI-MP2 def2-TZVP def2-TZVP/C NumFreq"),
            ("B2PLYP", "FREQ", "B2PLYP def2-TZVP def2-TZVP/C NumFreq"),
            ("DLPNO-CCSD(T)", "SP", "DLPNO-CCSD(T) def2-TZVP def2-TZVP/C SP"),
            ("B3LYP-D3(BJ)", "SP", "B3LYP D3BJ def2-TZVP SP"),
            ("B2PLYP-D4", "SP", "B2PLYP D4 def2-TZVP def2-TZVP/C SP"),
        ):
            with self.subTest(method=method):
                spec = CalculationSpec(method=method, basis="def2-TZVP", job_type=job)
                self.assertEqual(render_input(self.geometry.molecule, spec).splitlines()[1], "! " + expected)

    def test_element_ranges_and_restart_compatibility(self):
        electron_even = Molecule("uranium", (Atom("U", 0., 0., 0.),))
        render_input(electron_even, CalculationSpec(method="r2SCAN-3c"))
        for method in ("HF", "RI-MP2", "wB97X-3c", "Native-GFN2-xTB", "AM1"):
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, 'cover U'):
                render_input(electron_even, CalculationSpec(method=method))
        gbw = InputCompanionFile("initial_gbw", "guess.gbw", b"fixture")
        for method in ("PM3", "Native-spGFN1-xTB"):
            with self.assertRaisesRegex(ValueError, "GBW"):
                freeze_input(self.geometry, CalculationSpec(method=method), companions=(gbw,))
        fixed = CalculationSpec(method="HF-3c")
        first = freeze_input(self.geometry, fixed, companions=(gbw,))
        second = freeze_input(self.geometry, replace(fixed, basis="def2-TZVP"), companions=(gbw,))
        self.assertEqual(first.content_digest, second.content_digest)

    def test_manual_keyword_tables_select_the_right_module_and_basis(self):
        def preview(name, **params):
            return render_input(self.geometry.molecule, CalculationSpec(method=name, **params))

        self.assertIn("! DSD-BLYP D3BJ def2-SVP def2-SVP/C SP", preview("DSD-BLYP-D3BJ"))
        self.assertEqual(dispersion_options("WB97X-D4REV"), ("Auto",))
        for name in ("CNDO/S", "INDO/1"):
            self.assertIn("Method " + name.replace("/", "_"), preview(name))
        self.assertNotIn("def2-", preview("ZINDO/S-CIS", nroots=3))
        local = preview("DLPNO-B2PLYP", pno_preset="TightPNO")
        self.assertIn("def2-SVP/C TightPNO", local)
        self.assertIn("%mp2\n  DLPNO true\nend", local)
        for prefix, tda in (("TD", "false"), ("TDA", "true")):
            text = preview(prefix + "-SCS/SOS-B2PLYP21", nroots=3)
            self.assertIn("! SCS/SOS-B2PLYP21 def2-SVP def2-SVP/C SP", text)
            self.assertIn(f"tda {tda}\n  dcorr 1", text)
        for alias, name in (("OO-SOS-RIMP2", "OO-RI-SOS-MP2"), ("MP2-F12D-RI", "F12/D-RI-MP2"),
                            ("SOS-RI-MP2", "RI-SOS-MP2"), ("DMRG", "DMRG-CASSCF")):
            self.assertEqual(canonical_method(alias), name)
        self.assertTrue(EARLIER_METHODS.isdisjoint(("PR2SCAN50", "INDO/1", "DMRG-CASCI", "CI-ctPBE")))
        old = CalculationSpec(method="TD-DFT", nroots=3, reference_functional="B3LYP")
        new = replace(old, reference_functional="BHANDHLYP")
        self.assertFalse(has_advanced_settings(old))
        self.assertTrue(has_advanced_settings(new))
        self.assertIn("! BHANDHLYP def2-SVP SP", render_input(self.geometry.molecule, new))

    def test_multireference_reference_roots_differ_from_response_roots(self):
        params = dict(active_electrons=2, active_orbitals=2)

        def preview(name, **settings):
            return render_input(self.geometry.molecule, CalculationSpec(method=name, **params, **settings))

        self.assertIn("! TRAH CI-sr-ctPBE def2-SVP SP", preview("CI-sr-ctPBE", nroots=2))
        self.assertIn("nroots 2", preview("CI-sr-ctPBE", nroots=2))
        self.assertIn("PTSettings\n    QDType QD_VanVleck\n  end", preview("QD-SC-NEVPT2", nroots=2))
        self.assertIn("cistep DMRGCI\n  maxiter 1", preview("DMRG-CASCI"))
        with self.assertRaisesRegex(ValueError, 'configurations'):
            preview("SA-CASSCF", nroots=4)
        text = preview("MCTDA", nroots=4)
        self.assertIn("def2-SVP/C", text)
        self.assertIn("nroots 1\nend\n%mcrpa\n  NRoots 4\n  TDA true", text)

    def test_canonical_ri_cc_rejects_open_shell_auto_and_explicit_uhf(self):
        triplet = replace(self.geometry.molecule, multiplicity=3)
        for name in ("RI-CCSD", "RI-CCSD(T)"):
            with self.subTest(method=name), self.assertRaisesRegex(ValueError, 'closed-shell'):
                render_input(triplet, CalculationSpec(method=name))
            with self.assertRaises(ValueError):
                render_input(self.geometry.molecule, CalculationSpec(method=name, wavefunction="UHF"))
            self.assertIn("RHF", render_input(self.geometry.molecule, CalculationSpec(method=name, wavefunction="RHF")))

    def test_cli_aliases_and_unsupported_combinations(self):
        for flags, keyword in (
            (["--method", "M06-2X"], "M062X"), (["--method", "SCAN"], "SCANFUNC"),
            (["--method", "CASSCF", "--active-electrons", "2", "--active-orbitals", "2"], "%casscf"),
            (["--method", "tddft", "--nroots", "3"], "tda false"),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["preview", *flags]), 0)
            self.assertIn(keyword, output.getvalue())
        for flags in (
            ["--method", "r2SCAN-3c", "--basis", "def2-TZVP"],
            ["--method", "CCSD(T)", "--job", "FREQ"],
            ["--method", "CASSCF"], ["--method", "Mulliken"],
            ["--method", "EDA"], ["--method", "NBO"], ["--method", "B3LYP", "--nroots", "5"],
        ):
            with self.subTest(flags=flags), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["preview", *flags]), 2)

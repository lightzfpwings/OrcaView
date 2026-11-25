import unittest
from dataclasses import replace

from orcaview.core._block_catalog import catalog_options, validate_common_combinations
from orcaview.core.block_options import parse_option_value
from orcaview.core.methods import METHODS
from orcaview.core.models import CalculationSpec


def options(spec):
    return {(option.block, option.key): option for option in catalog_options(spec)}


class CommonBlockOptionsTests(unittest.TestCase):
    def test_all_presets_expose_only_relevant_job_blocks(self):
        for method, preset in METHODS.items():
            for job in preset.job_types:
                with self.subTest(method=method, job=job):
                    spec = CalculationSpec(method=method, job_type=job)
                    available = catalog_options(spec)
                    keys = {(o.block, o.key) for o in available}
                    self.assertEqual(len(keys), len(available))
                    self.assertEqual(("geom", "MaxIter") in keys, job in ("OPT", "OPT_FREQ", "OPT_TS"))
                    self.assertEqual(("freq", "ProjectTR") in keys, job in ("FREQ", "OPT_FREQ"))

    def test_electronic_engines_have_distinct_scf_controls(self):
        for method in ("HF", "B3LYP", "HF-3c", "FCI", "MRCC-CCSDT"):
            self.assertIn(("scf", "MaxIter"), options(CalculationSpec(method=method)))
        for method in ("GFN-FF", "GFN2-xTB", "PM3"):
            self.assertFalse(any(block == "scf" for block, key in options(CalculationSpec(method=method))))
        native = CalculationSpec(method="Native-GFN2-xTB")
        self.assertIn(("scf", "UseXTBMixer"), options(native))
        self.assertNotIn(("scf", "DIISMaxEq"), options(native))
        with self.assertRaisesRegex(ValueError, "UseXTBMixer"):
            validate_common_combinations(native, {("scf", "MaxIter"): 200})
        validate_common_combinations(native, {("scf", "MaxIter"): 200, ("scf", "UseXTBMixer"): False})
        self.assertNotIn(("scf", "Convergence"), options(CalculationSpec(method="HF-CBS(2/3,cc)")))

    def test_displacement_controls_match_the_hessian_algorithm(self):
        analytical = CalculationSpec(method="PBE0", job_type="FREQ")
        for option in ("ProjectTR", "TransInvar"):
            self.assertIn(("freq", option), options(analytical))
        self.assertIn(("method", "Z_Tol"), options(analytical))
        self.assertNotIn(("freq", "CentralDiff"), options(analytical))
        self.assertNotIn(("geom", "Recalc_Hess"), options(analytical))
        for method, basis, numerical in (("RI-MP2", "def2-TZVP", True), ("PBE0", "DKH-def2-TZVP", False)):
            available = options(replace(analytical, method=method, basis=basis))
            for option in ("CentralDiff", "Increment", "NumHessTransInvar"):
                self.assertEqual(("freq", option) in available, numerical)

    def test_method_options_and_structured_choices_do_not_collide(self):
        scf = CalculationSpec(method="PBE0")
        self.assertIn(("method", "BFCut"), options(scf))
        self.assertNotIn(("method", "BFCut"), options(replace(scf, integration_grid="DEFGRID3")))
        self.assertNotIn(("scf", "AutoTRAH"), options(replace(scf, wavefunction="ROKS")))
        self.assertNotIn(("scf", "AutoTRAH"), options(replace(scf, method="PWPB95")))
        self.assertIn(("scf", "AutoTRAH"), options(replace(scf, method="LibXC(PWPB95)")))
        self.assertIn(("method", "D4S9"), options(replace(scf, dispersion="D4")))
        self.assertNotIn(("method", "D3alpha6"), options(replace(scf, dispersion="D4")))
        self.assertIn(("method", "LibXCDensityThreshold"), options(replace(scf, method="LibXC(B3LYP)")))
        self.assertNotIn(("method", "LibXCDensityThreshold"), options(scf))
        self.assertIn(("method", "ADFTNRTol"), options(replace(scf, method="ADFT(CC)")))
        mp2 = replace(scf, method="MP2")
        self.assertIn(("method", "CheckFrozenCore"), options(mp2))
        self.assertNotIn(("method", "CorrectFrozenCore"), options(replace(mp2, frozen_core="NoFrozenCore")))

    def test_cross_field_conflicts_and_boundaries(self):
        spec = CalculationSpec(method="PBE0", job_type="OPT_FREQ")
        avail = options(spec)
        for key, bad in ((("scf", "DampFac"), "1"), (("scf", "TolE"), "0"), (("geom", "MaxIter"), "0"),
                         (("scf", "ConvCheckMode"), "3"), (("scf.trah", "NStart"), "1")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_option_value(avail[key], bad)
        for pairs in (
            ((("scf", "CNVDIIS"), False), (("scf", "DIISMaxEq"), 15)),
            ((("scf", "AutoTRAH"), False), (("scf.trah", "MaxRed"), 25)),
            ((("scf.trah", "AlphaMin"), 5), (("scf.trah", "AlphaMax"), 4)),
            ((("scf", "DampMin"), 0.8), (("scf", "DampMax"), 0.7)),
            ((("method", "Z_Solver"), "Pople"), (("method", "Z_Shift"), 0.2)),
            ((("geom", "Calc_Hess"), True), (("geom", "InHess"), "Swart")),
            ((("geom", "coordsys"), "cartesian"), (("geom", "InHess"), "Lindh")),
            ((("geom", "optimizeHydrogens"), True), (("geom", "freezeHydrogens"), True)),
            ((("geom", "Trust"), 0.0),),
        ):
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                validate_common_combinations(spec, dict(pairs))
        validate_common_combinations(spec, {("geom", "Trust"): -0.3, ("scf", "CNVDIIS"): False})
        validate_common_combinations(spec, {("method", "Z_Solver"): "DIIS", ("method", "Z_Shift"): 0.2})
        numerical = replace(spec, method="RI-MP2")
        with self.assertRaisesRegex(ValueError, "NumHess"):
            validate_common_combinations(numerical, {("geom", "Calc_Hess"): True})
        validate_common_combinations(numerical, {("geom", "Calc_Hess"): True, ("geom", "NumHess"): True})

    def test_static_and_zerner_damping_are_alternative_convergers(self):
        spec = CalculationSpec(method="HF")
        validate_common_combinations(spec, {("scf", "CNVDamp"): False, ("scf", "CNVZerner"): True,
                                            ("scf", "DampMin"): .05})
        with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
            validate_common_combinations(spec, {("scf", "CNVDamp"): True, ("scf", "CNVZerner"): True})
        with self.assertRaisesRegex(ValueError, 'damping'):
            validate_common_combinations(spec, {("scf", "CNVDamp"): False, ("scf", "DampErr"): .1})

    def test_trah_internal_coordinates_and_grid_dependencies(self):
        spec = CalculationSpec(method="PBE0", job_type="OPT_FREQ", integral_approximation="RIJCOSX")
        validation_cases = [
            ({("scf.trah", "PreconMaxRed"): 90}, ("scf.trah", "Precond"), "Full"),
            ({("scf.trah", "Randomize"): False, ("scf.trah", "MaxNoise"): .01}, ("scf.trah", "Randomize"), True),
            ({("geom", "ProjectTR"): True}, ("geom", "coordsys"), "cartesian"),
            ({("geom", "coordsys"): "cartesian", ("geom", "AddExtraBonds"): True}, ("geom", "coordsys"), "redundant"),
            ({("geom", "Update"): "Powell", ("geom", "NResetHess"): 25}, ("geom", "Update"), "BFGS"),
            ({("method", "NThetaMax"): .4}, ("method", "AngularGrid"), 0),
        ]
        for values, switch, setting in validation_cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    validate_common_combinations(spec, values)
                validate_common_combinations(spec, {**values, switch: setting})
        self.assertNotIn(("geom", "HESS_MinEV"), options(spec))
        self.assertIn(("method", "Z_GridX"), options(spec))
        self.assertNotIn(("method", "Z_GridX"), options(replace(spec, integral_approximation="NoRI")))
        self.assertIn(("method", "Z_GridXC"), options(spec))
        self.assertNotIn(("method", "Z_GridXC"), options(replace(spec, integration_grid="DEFGRID3")))
        self.assertNotIn(("method", "Z_GridX_RHS"), options(spec))
        self.assertIn(("method", "Z_GridX_RHS"), options(replace(spec, method="RI-MP2")))
        self.assertNotIn(("scf", "AutoTRAH"), options(CalculationSpec(method="ctPBE")))
        self.assertIn(("method", "RPACNPoints"), options(CalculationSpec(method="RPAC(PBE)")))

    def test_cosx_overlap_fitting_depends_on_the_chosen_integral_algorithm(self):
        spec = CalculationSpec(method="HF", integral_approximation="RIJCOSX")
        self.assertIn(("method", "COSX_IntSymmetry"), options(spec))
        self.assertNotIn(("method", "UseQGradFit"), options(spec))
        self.assertIn(("method", "UseQGradFit"), options(replace(spec, job_type="OPT")))
        self.assertNotIn(("method", "SFitInvertType"), options(replace(spec, integral_approximation="RI-JK")))
        values = {("method", "SFitInvertType"): "Diag_Q", ("method", "SInvThresh"): 1e-9}
        validate_common_combinations(spec, values)
        with self.assertRaisesRegex(ValueError, 'overlap fitting'):
            validate_common_combinations(spec, {**values, ("method", "UseSFitting"): False})
        with self.assertRaisesRegex(ValueError, "SInvThresh"):
            validate_common_combinations(spec, {**values, ("method", "SFitInvertType"): "Cholesky"})

    def test_saddle_point_hessian_and_default_update_are_job_specific(self):
        spec = CalculationSpec(method="HF", job_type="OPT_TS")
        self.assertIn(("geom", "HESS_MinEV"), options(spec))
        self.assertIn(("geom", "HESS_Modification"), options(spec))
        self.assertNotIn(("geom", "Step"), options(spec))
        self.assertNotIn(("freq", "ProjectTR"), options(spec))
        with self.assertRaisesRegex(ValueError, "BFGS"):
            validate_common_combinations(spec, {("geom", "NResetHess"): 10})
        validate_common_combinations(spec, {("geom", "Update"): "BFGS", ("geom", "NResetHess"): 10})
        self.assertNotIn(("geom", "MaxIter"), options(replace(spec, job_type="IRC")))

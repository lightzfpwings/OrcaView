from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.block_options import BlockOverride, available_options
from orcaview.core.manual import lookup
from orcaview.core.models import CalculationSpec
from orcaview.core.solvation import SOLVENTS, solvation_input
from orcaview.orca.input import freeze_input, render_input
from orcaview.orca.output import parse_output


class ManualCalculationTests(unittest.TestCase):
    def test_ordinary_adjustments_preserve_analytic_frequencies_and_documented_exceptions(self):
        molecule = Session().molecule
        for method, options, keyword in (
            ("B3LYP-D4", dict(solvation_model="SMD", solvent="water", integral_approximation="RIJCOSX"), "Freq"),
            ("PBE0-D3(BJ)", dict(integration_grid="DEFGRID3", cores=8), "Freq"),
            ("B3LYP", dict(dispersion="D4", solvation_model="CPCM", solvent="water"), "Freq"),
            ("r2SCAN-3c", {}, "Freq"), ("B2PLYP-D4", {}, "NumFreq"),
            ("WB97X-V", {}, "NumFreq"), ("RI-MP2", dict(frozen_core="NoFrozenCore"), "NumFreq"),
        ):
            for job in ("FREQ", "OPT_FREQ"):
                with self.subTest(method=method, job=job):
                    spec = CalculationSpec(method=method, job_type=job, **options)
                    words = render_input(molecule, spec).splitlines()[1].split()
                    self.assertEqual(set(words) & {"Freq", "NumFreq"}, {keyword})
                    self.assertEqual("Opt" in words, job == "OPT_FREQ")
                    self.assertEqual(("freq", "Increment") in {(o.block, o.key) for o in available_options(spec)},
                                     keyword == "NumFreq")

    def test_dual_edition_lookup(self):
        for number, title, page in (("2.13", "Implicit Solvation", "141"), ("3.18", "CASSCF and DFT", "497"),
                                    ("4.4", "Intrinsic Reaction Coordinate", "631")):
            results = lookup(number)
            self.assertEqual((results[0][0], results[0][1], results[0][3]), (number, title, page))
            self.assertTrue(all(row[0] == number or row[0].startswith(number + ".") for row in results))
        self.assertTrue(any(row[0].startswith("5.9") for row in lookup("EOM")))
        self.assertTrue(any(row[0].startswith("2.6") for row in lookup("MaxIter")))
        self.assertFalse(any(row[0] == "5.1" for row in lookup("")))

    def test_all_catalog_solvent_aliases_have_single_unambiguous_output(self):
        for name, model in (("B3LYP", "CPCM"), ("B3LYP", "SMD"), ("GFN2-xTB", "CPCMX"),
                            ("GFN2-xTB", "DDCOSMO"), ("Native-GFN2-xTB", "ALPB")):
            for solvent in SOLVENTS[model]:
                with self.subTest(name=name, solvent=solvent):
                    words, lines = solvation_input(CalculationSpec(method=name, solvation_model=model, solvent=solvent))
                    if lines:
                        self.assertIn('"' + solvent + '"', " ".join(lines))
                    else:
                        self.assertRegex(words[0], r"^[A-Z]+\([^\s()]+\)$")
        self.assertNotIn("phenol", SOLVENTS["SMD"])
        self.assertIn("phenol", SOLVENTS["CPCM"])
        self.assertIn("sulfolane", SOLVENTS["SMD"])

    def test_solvated_schema6_freeze_and_derivative_fields(self):
        session = Session()
        opt = BlockOverride("cpcm", "SMD18", True)
        spec = CalculationSpec(solvation_model="SMD", solvent="formic acid", job_type="FREQ", block_options=(opt,))
        session.calculation = spec
        rendered = session.input_text()
        self.assertIn("Freq", rendered.splitlines()[1].split())
        self.assertEqual(rendered.count("%cpcm"), 1)
        self.assertIn('SMDsolvent "formic acid"', rendered)
        self.assertIn("  SMD18 true", rendered)
        self.assertNotIn(("freq", "Increment"), [(o.block, o.key) for o in available_options(spec)])
        self.assertEqual(freeze_input(session.document.head, spec).input_text, rendered)
        for model, solvent in (("CPCM", "water"), ("SMD", "phenol"), ("Gas", "water"),
                               ("CPCM", 'water)\n%scf\nend'), ("ALPB", "water")):
            with self.subTest(model=model, solvent=solvent), self.assertRaises(ValueError):
                replace(spec, solvation_model=model, solvent=solvent).validate()
        with TemporaryDirectory() as temp:
            path = Path(temp) / "water.json"
            save_project(session, path)
            self.assertEqual(json.loads(path.read_text())["schema_version"], 6)
            self.assertEqual(load_project(path).input_text(), rendered)
            saved = json.loads(path.read_text())
            saved["calculation"]["solvent"] = "unlisted"
            path.write_text(json.dumps(saved))
            with self.assertRaises(ValueError):
                load_project(path)

    def test_irc_hessian_initialization_and_single_point_exclusion(self):
        molecule = Session().molecule
        spec = CalculationSpec(job_type="IRC", solvation_model="SMD", solvent="water")
        self.assertNotIn("InitHess calc_numfreq", render_input(molecule, spec))
        for algorithm in ("calc_anfreq", "calc_numfreq"):
            selected = replace(spec, block_options=(BlockOverride("irc", "InitHess", algorithm),))
            self.assertIn("InitHess " + algorithm, render_input(molecule, selected))
        down = BlockOverride("irc", "Direction", "down")
        self.assertNotIn("InitHess", render_input(molecule, replace(spec, block_options=(down,))))
        for job, options in (("SP", (down,)), ("OPT_TS", (down,)), ("IRC", (down, BlockOverride("irc", "hessMode", 0))),
                             ("IRC", (BlockOverride("irc", "hessMode", 999),)),
                             ("IRC", (BlockOverride("irc", "InitHess", "invalid"),)),
                             ("IRC", (BlockOverride("irc", "Scale_Init_Displ", 0.2),))):
            with self.subTest(job=job, options=options), self.assertRaises(ValueError):
                render_input(molecule, replace(spec, job_type=job, block_options=options))
        opt_ts = CalculationSpec(job_type="OPT_TS", block_options=(BlockOverride("geom", "Calc_Hess", True),))
        self.assertIn("OptTS", render_input(molecule, opt_ts))
        with self.assertRaises(ValueError):
            CalculationSpec(method="CCSD", job_type="IRC").validate()
        log = "SCF CONVERGED AFTER 7 CYCLES\nFINAL SINGLE POINT ENERGY -1.2\nORCA TERMINATED NORMALLY"
        self.assertEqual(parse_output(log, "IRC").status, "needs_review")

    def test_ddcosmo_chooses_named_solvent_or_user_dielectric(self):
        eps = BlockOverride("xtb", "EPSILON", 23.5)
        spec = CalculationSpec(method="GFN2-xTB", solvation_model="DDCOSMO", block_options=(eps,))
        rendered = render_input(Session().molecule, spec)
        self.assertIn("%xtb\n  DODDCOSMO true\n  EPSILON 23.5\nend", rendered)
        with self.assertRaises(ValueError):
            replace(spec, solvent="water").validate()
        with self.assertRaises(ValueError):
            replace(spec, block_options=()).validate()

    def test_cpcmx_is_external_gfn2_single_point(self):
        spec = CalculationSpec(method="GFN2-xTB", solvation_model="CPCMX", solvent="water")
        self.assertIn("CPCMX(water)", render_input(Session().molecule, spec))
        for name, job in (("GFN2-xTB", "OPT"), ("GFN-FF", "SP"), ("Native-GFN2-xTB", "SP")):
            with self.assertRaises(ValueError):
                replace(spec, method=name, job_type=job).validate()

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.cli import main
from orcaview.core.block_options import BlockOverride, available_options
from orcaview.core.models import CalculationSpec
from orcaview.orca.input import freeze_input, render_input


def setting(spec, name, value):
    found = next(option for option in available_options(spec)
                 if f"{option.block}.{option.key}".casefold() == name.casefold())
    return BlockOverride(found.block, found.key, value)


class BlockInputTests(unittest.TestCase):
    def setUp(self):
        self.geometry = Session().document.head

    def test_defaults_unchanged_and_order_independent_snapshot(self):
        base = CalculationSpec(job_type="OPT")
        original = freeze_input(self.geometry, base)
        self.assertNotIn("%geom", original.input_text)
        self.assertNotIn("%scf", original.input_text)
        overrides = (setting(base, "geom.MaxIter", 65), setting(base, "scf.MaxIter", 250))
        tuned = replace(base, block_options=overrides)
        snapshot = freeze_input(self.geometry, tuned)
        self.assertIn("maxiter 65", snapshot.input_text.lower().split("%geom\n")[1].split("end")[0])
        self.assertIn("MaxIter 250", snapshot.input_text.split("%scf\n")[1].split("end")[0])
        self.assertEqual(snapshot.input_text, render_input(self.geometry.molecule, tuned))
        self.assertNotEqual(original.content_digest, snapshot.content_digest)
        self.assertEqual(snapshot.content_digest,
                         freeze_input(self.geometry, replace(base, block_options=overrides[::-1])).content_digest)
        self.assertEqual(original.input_bytes, freeze_input(self.geometry, replace(tuned, block_options=())).input_bytes)

    def test_generated_and_nested_sections_are_merged(self):
        spec = CalculationSpec(method="CASSCF", active_electrons=2, active_orbitals=2)
        overrides = (setting(spec, "casscf.CI.MaxIter", 40), setting(spec, "casscf.MaxIter", 70))
        text = render_input(self.geometry.molecule, replace(spec, block_options=overrides))
        self.assertEqual(text.count("%casscf"), 1)
        self.assertIn("  nel 2\n", text)
        self.assertIn("  CI\n    MaxIter 40\n  end", text)
        self.assertIn("\n  maxiter 70\n", text.lower())
        self.assertNotIn("%CI", text)
        spec = CalculationSpec(method="MR-EOM", nroots=2, active_electrons=2, active_orbitals=2)
        self.assertIn("    refs cas(2,2) end\n  end\nend", render_input(
            self.geometry.molecule, replace(spec, block_options=(setting(spec, "scf.MaxIter", 250),))))
        spec = CalculationSpec(method="MP2", frozen_core="FrozenCore")
        text = render_input(self.geometry.molecule, replace(spec, block_options=(
            setting(spec, "method.CheckFrozenCore", False),)))
        self.assertEqual(text.count("%method"), 1)
        self.assertIn("  FrozenCore FC_ELECTRONS", text)
        self.assertIn("  CheckFrozenCore false", text)

    def test_model_rejects_inapplicable_reserved_malformed_and_duplicate_fields(self):
        valid = BlockOverride("scf", "MaxIter", 20)
        for options in (
            (BlockOverride("geom", "MaxIter", 60),), (BlockOverride("scf", "HFTyp", "UHF"),),
            (BlockOverride("scf", "MaxIter", False),), (BlockOverride("scf", "MaxIter", "20"),),
            (BlockOverride("scf", "TolE", float("nan")),), (BlockOverride("scf", "MaxIter", 2**32),),
            (BlockOverride("scf\nend", "MaxIter", 3),), (valid, valid), [valid], ({"key": "MaxIter"},),
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                freeze_input(self.geometry, CalculationSpec(block_options=options))

    def test_schema_five_roundtrip_and_inapplicable_project_rejected(self):
        base = CalculationSpec(job_type="OPT")
        settings = (setting(base, "scf.TolE", 1e-9), setting(base, "geom.MaxIter", 45))
        session = Session(calculation=replace(base, block_options=settings))
        with TemporaryDirectory() as folder:
            path = Path(folder) / "job.oview.json"
            save_project(session, path)
            saved = json.loads(path.read_text())
            self.assertEqual(saved["schema_version"], 5)
            self.assertEqual(load_project(path).calculation, session.calculation)
            self.assertEqual(load_project(path).input_text(), session.input_text())
            saved["calculation"]["job_type"] = "SP"
            path.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError, "geom"):
                load_project(path)
            saved["schema_version"] = 4
            path.write_text(json.dumps(saved))
            with self.assertRaises(ValueError):
                load_project(path)
            session.calculation = base
            save_project(session, path)
            reset_record = json.loads(path.read_text())
            self.assertEqual(reset_record["schema_version"], 2)
            self.assertNotIn("block_options", reset_record["calculation"])

    def test_module_memory_override_preserves_real_execution_estimate(self):
        base = CalculationSpec(method="RI-MP2", cores=4, maxcore_mb=1000)
        for local, estimated in ((512, 4000), (2000, 8000)):
            spec = replace(base, block_options=(setting(base, "mp2.MaxCore", local),))
            snapshot = freeze_input(self.geometry, spec)
            self.assertIn(f"  MaxCore {local}", snapshot.input_text)
            self.assertEqual(snapshot.estimated_maxcore_mb, estimated)

    def test_cli_lists_scoped_options_and_accepts_typed_repeats(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["methods", "B3LYP", "--job", "SP", "--blocks"]), 0)
        self.assertIn("%scf.MaxIter", output.getvalue())
        self.assertNotIn("%geom.", output.getvalue())
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["preview", "--job", "OPT", "--set", "%SCF.maxiter=125",
                                   "--set", "geom.maxiter=60"]), 0)
        self.assertIn("  MaxIter 125", output.getvalue())
        for flag in ("geom.MaxIter=100", "scf.MaxIter=2\nend", "scf.MaxIter=1.2", "scf.TolE=NaN",
                     "scf.Convergence=bad", "scf.MaxIter"):
            with self.subTest(flag=flag), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["preview", "--set", flag]), 2)

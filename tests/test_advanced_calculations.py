import io
import json
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.cli import main
from orcaview.core.models import Atom, CalculationSpec, Molecule
from orcaview.orca.input import render_input


class AdvancedCalculationTests(unittest.TestCase):
    def test_method_recipes_emit_native_keywords_and_blocks(self):
        water = Session().molecule
        for name, basis, expected in (
            ("FCI", "def2-SVP", ("%casscf", "  DoFCI true")),
            ("RPAC(PBE)", "def2-SVP", ("PBE RPAC", "def2/J", "def2-SVP/C")),
            ("ADFT(CC)", "def2-SVP", ("ADFT(CC)", "XFit/3", "def2/J")),
            ("MRCC-CCSD[T]", "cc-pVDZ", ("HF Conv", "%mrcc", 'method "CCSD[T]"')),
            ("AUTOCI-MP5", "cc-pVDZ", ("UHF AUTOCI-MP5",)),
            ("CIM-RI-MP2", "cc-pVDZ", ("RI-MP2 CIM", "cc-pVDZ/C")),
            ("LibXC(HSE12S)", "def2-SVP", ("LibXC(HSE12S)",)),
            ("LibXC(B2GP-PLYP)", "def2-SVP", ("LibXC(B2GP-PLYP)", "def2-SVP/C")),
        ):
            with self.subTest(method=name):
                text = render_input(water, CalculationSpec(method=name, basis=basis))
                for fragment in expected:
                    self.assertIn(fragment, text)
        triplet = replace(water, multiplicity=3)
        for name in ("F12/D-DLPNO-MP2", "F12-DLPNO-MP2"):
            with self.assertRaisesRegex(ValueError, 'closed-shell'):
                render_input(triplet, CalculationSpec(method=name, basis="cc-pVDZ-F12"))
        for name in ("F12-RI-MP2", "DLPNO-CCSD(T1)-F12"):
            self.assertIn(name, render_input(triplet, CalculationSpec(method=name, basis="cc-pVDZ-F12")))
        for name in ("CIM-RI-MP2", "CIM-CCSD(T)", "CIM-DLPNO-MP2", "CIM-DLPNO-CCSD(T)"):
            with self.assertRaisesRegex(ValueError, 'closed-shell'):
                render_input(triplet, CalculationSpec(method=name))

    def test_advanced_projects_reopen_with_identical_native_input(self):
        water = Session().molecule
        radical = Molecule("OH", (Atom("O", 0, 0, 0), Atom("H", 0, 0, .97)), multiplicity=2)
        cases = (
            (water, CalculationSpec(method="PBE0", basis="x2c-TZVPall", relativity="DLU-X2C",
                                    integral_approximation="RIJCOSX", aux_j="x2c/J", integration_grid="DEFGRID3",
                                    dispersion="D4", wavefunction="RKS")),
            (water, CalculationSpec(method="DLPNO-CCSD(T)-F12", basis="cc-pVDZ-F12",
                                    aux_c="cc-pVTZ/C", cabs="cc-pVDZ-F12-OptRI", pno_preset="TightPNO")),
            (water, CalculationSpec(method="RI-MP2", integral_approximation="RI-JK", aux_jk="def2/JK",
                                    frozen_core="NoFrozenCore")),
            (radical, CalculationSpec(method="IP-EOM-CCSD", nroots=1, electron_channel="beta")),
            (water, CalculationSpec(method="FCI")),
            (water, CalculationSpec(method="HF", basis="STO-3G")),
        )
        with TemporaryDirectory() as temp:
            destination = Path(temp) / "advanced.oview.json"
            for molecule, spec in cases:
                with self.subTest(method=spec.method):
                    session = Session(molecule=molecule, calculation=spec)
                    save_project(session, destination)
                    record = json.loads(destination.read_text())
                    self.assertEqual(record["schema_version"], 4)
                    restored = load_project(destination)
                    self.assertEqual(restored.calculation, spec)
                    self.assertEqual(restored.input_text(), session.input_text())
                    record["calculation"]["aux_c"] = "bad\nend"
                    destination.write_text(json.dumps(record))
                    with self.assertRaises(ValueError):
                        load_project(destination)

    def test_reference_and_frozen_core_approximations(self):
        water = Session().molecule
        sodium = Molecule("Na", (Atom("Na", 0, 0, 0),), multiplicity=2)
        ecp = CalculationSpec(method="LibXC(B3LYP)", basis="LANL2DZ", wavefunction="ROKS")
        self.assertIn("ROKS", render_input(sodium, ecp))
        with self.assertRaisesRegex(ValueError, 'explicit electrons'):
            render_input(replace(sodium, multiplicity=4), ecp)
        for method, reference in (("PBE0", "RKS"), ("HF", "RHF")):
            spec = CalculationSpec(method=method, wavefunction=reference)
            self.assertIn(reference, render_input(water, spec))
            with self.assertRaisesRegex(ValueError, 'singlet'):
                render_input(replace(water, multiplicity=3), spec)
        for method, reference in (("HF", "ROHF"), ("PBE", "ROKS")):
            spec = CalculationSpec(method=method, wavefunction=reference)
            self.assertIn(reference, render_input(replace(water, multiplicity=3), spec))
        for choice, native in (("FrozenCore", "FrozenCore FC_ELECTRONS"), ("NoFrozenCore", " NoFrozenCore ")):
            self.assertIn(native, render_input(water, CalculationSpec(method="MP2", frozen_core=choice)))
        for field in ({"pno_preset": "TightPNO"}, {"wavefunction": "RHF"}, {"dispersion": "D4\nend"},
                      {"frozen_core": "NoFrozenCore"}, {"relativity": "ZORA"}):
            with self.assertRaises(ValueError):
                render_input(water, CalculationSpec(method="PBE0", **field))

    def test_cli_inspection_matches_actual_export(self):
        for argv, fragments in (
            (["methods", "HF", "--ri", "RI-JK"], ("aux_jk", "def2/JK", "ROHF")),
            (["preview", "--method", "RI-MP2-F12"], ("F12-RI-MP2", "cc-pVDZ-F12-OptRI", "cc-pVDZ-F12-MP2Fit")),
            (["preview", "--method", "PBE0", "--ri", "RIJCOSX", "--dispersion", "D4",
              "--aux-j", "def2/J", "--grid", "DEFGRID3"], ("def2/J", "RIJCOSX", "D4", "DEFGRID3")),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(argv), 0)
            for fragment in fragments:
                self.assertIn(fragment, output.getvalue())

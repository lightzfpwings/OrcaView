from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orcaview.gui.result_import import read_native_session


class PopulationFrameTests(unittest.TestCase):
    def test_optional_mulliken_total_must_be_valid_when_printed(self):
        fixture = Path(__file__).resolve().parents[1] / "examples/m5_orca/water-sp.out"
        text = fixture.read_text(encoding="utf-8")
        total = "Sum of atomic charges:    0.0000000"
        self.assertIn(total, text)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "water.out"
            for label, log, expected in (
                ("absent", text.replace(total, ""), (-0.42, 0.2, 0.22)),
                ("malformed", text.replace(total, "Sum of atomic charges: abc"), None),
                ("wrong charge", text.replace(total, "Sum of atomic charges: 1.0"), None),
                ("inconsistent rounded sum", text.replace("0.220000", "0.220002"), None),
            ):
                with self.subTest(label=label):
                    path.write_text(log)
                    session = read_native_session(path)
                    charges = [d for d in session.document.records()[1] if d.kind == "mulliken-charge"]
                    self.assertEqual([d.values for d in charges], [expected])
                    self.assertEqual(bool(charges[0].missing_reason), expected is None)

    def test_later_geometry_cannot_supply_charges_for_the_selected_frame(self):
        block = """CARTESIAN COORDINATES{gap}(ANGSTROEM)
---
H 0 0 0
H {distance} 0 0

Number of atoms ... 2
MULLIKEN ATOMIC CHARGES
---
0 H : -{charge}
1 H : {charge}
Sum of atomic charges: 0.0

"""
        selected = ("Program Version 6.1.1\n| 1> * xyz 0 1\n"
                    "*** FINAL ENERGY EVALUATION AT THE STATIONARY POINT ***\n"
                    + block.format(gap=" ", distance=1, charge=0.1))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "optimization.out"
            for gap in (" ", "    ", "\t"):
                with self.subTest(gap=gap):
                    path.write_text(selected + block.format(gap=gap, distance=2, charge=0.2))
                    session = read_native_session(path)
                    charges = [d for d in session.document.records()[1] if d.kind == "mulliken-charge"]
                    self.assertEqual([d.values for d in charges], [(-0.1, 0.1)])
                    frame = session.document.resolve(charges[0].geometry)
                    self.assertEqual(frame.molecule.atoms[1].x, 1.0)
                    self.assertEqual(dict(charges[0].provenance.parameters)["population_line"], "10")

'XYZ format boundaries and lossless geometry round trips.'

from pathlib import Path
import tempfile
import unittest

from orcaview.core.models import Atom, Molecule
from orcaview.io.xyz import load_xyz, parse_xyz, write_xyz


WATER = "3\nwater\nO 0 0 0\nH 0.7586 0 0.5043\nH -0.7586 0 0.5043\n"


class XyzTests(unittest.TestCase):
    def test_roundtrip_geometry(self):
        molecule = parse_xyz(WATER, name="water")
        restored = parse_xyz(write_xyz(molecule), name="water")
        self.assertEqual(restored, molecule)

    def test_load_uses_path_stem(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "molecule with spaces.xyz"
            path.write_text(WATER, encoding="utf-8")
            self.assertEqual(load_xyz(path).name, "molecule with spaces")

    def test_comment_is_required_even_if_empty(self):
        self.assertEqual(len(parse_xyz("1\n\nHe 0 0 0\n").atoms), 1)
        with self.assertRaises(ValueError):
            parse_xyz("1\nHe 0 0 0\n")

    def test_odd_electron_geometry_loads_without_guessing_spin(self):
        molecule = parse_xyz("1\nradical geometry\nH 0 0 0\n")
        self.assertEqual(molecule.multiplicity, 1)
        with self.assertRaises(ValueError):
            molecule.validate()

    def test_rejects_multiframe_and_extra_columns(self):
        for text in (WATER + WATER, WATER + "garbage", "1\n\nH 0 0 0 extra\n"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_xyz(text)

    def test_rejects_invalid_counts_and_coordinates(self):
        for text in ("", "three\n\n", "0\n\n", "2\n\nH 0 0 0\n", "1\n\nH nan 0 0\n", "1\n\nQq 0 0 0\n"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_xyz(text)

    def test_write_sanitizes_multiline_comment(self):
        molecule = Molecule("first\nsecond", (Atom("He", 0, 0, 0),))
        self.assertEqual(write_xyz(molecule).splitlines()[1], "first second")


if __name__ == "__main__":
    unittest.main()

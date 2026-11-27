"""Analytic Gaussians, ORCA cube samples and non-destructive GBW conversion."""

import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orcaview.application.structure_import import prepare_gbw_open, read_linked_orbitals, read_structure_file
from orcaview.core.units import BOHR_IN_ANGSTROM
from orcaview.io.molden_orbitals import read_molden_orbitals
from orcaview.io.quantum_structure import read_quantum_structure
from orcaview.orca.gbw import file_state
from orcaview.results.orbital_basis import orbital_expansion, orbital_value
from orcaview.results.orbital_surface import make_orbital_surface, sample_grid


EXAMPLES = Path(__file__).resolve().parents[1] / "examples/orbitals"


def wave_from_bytes(raw):
    record = read_quantum_structure(Path("test.molden"), raw)
    return read_molden_orbitals(raw, record.molecule)


class MoldenNumericsTests(unittest.TestCase):
    def test_signed_orca_cube_values_for_closed_open_shell_and_high_angular_momentum(self):
        # Six points from each ORCA 6.1.1 %plots Gaussian cube in the example inputs.
        indices = ((13, 15, 15), (16, 14, 17), (17, 17, 11), (19, 18, 17), (15, 19, 16), (15, 15, 16))
        cases = {
            "water": ((-8.433550, -7., -7.), (.544100, .451613, .487368), {
                ("Alpha", 4): (-.0432394, -.112966, .039672, .0363084, .139115, -.124992),
                ("Alpha", 5): (-.0123292, -.0372207, .0223883, .0478175, -.0018789, -.143031),
                ("Alpha", 74): (-.161685, .01193, .0253033, .0394827, .0632724, .0202245),
            }),
            "OH": ((-7., -7., -7.), (.451613, .451613, .510743), {
                ("Alpha", 4): (.097927, -.0678104, .0161799, .000396377, .0881022, -.0158551),
                ("Beta", 3): (.0978493, -.0700863, .0164581, .000412156, .0904541, -.0158415),
                ("Beta", 4): (.221163, .0239744, -.104426, -.06278, -.0547774, .0879222),
            }),
        }
        for name, (origin, step, cases_by_spin) in cases.items():
            wave = read_structure_file(EXAMPLES / (name + ".molden.input")).orbitals
            for key, reference in cases_by_spin.items():
                with self.subTest(name=name, orbital=key):
                    mo = next(m for m in wave.orbitals if (m.spin, m.number) == key)
                    expansion = orbital_expansion(wave.shells, mo.coefficients)
                    for cell, expected in zip(indices, reference):
                        point = [o+s*i for o, s, i in zip(origin, step, cell)]
                        self.assertAlmostEqual(orbital_value(expansion, *point), expected, delta=5e-6)
                        grid, = sample_grid(expansion, [[v] for v in point])
                        self.assertAlmostEqual(grid, expected, delta=5e-6)

    def test_sparse_coefficients_sp_cartesian_d_and_angstrom_origin(self):
        raw = b"""[Molden Format]
[Atoms] Angs
He 1 2 0.529177210544 0 0
[GTO]
1 0
sp 1 1.00
1D0 1.0 1.0
d 1 1.00
1.0 1.0
[MO]
Ene= -.5
Spin= Alpha
Occup= 2
8 1D0
"""
        wave = wave_from_bytes(raw)
        mo, = wave.orbitals
        # One s, three p and six Cartesian d AOs. AO 8 is normalized xy.
        self.assertEqual(len(mo.coefficients), 10)
        expansion = orbital_expansion(wave.shells, mo.coefficients)
        self.assertAlmostEqual(orbital_value(expansion, 2, -1, 0), -4*(2/math.pi)**.75*math.exp(-2))
        self.assertEqual(orbital_value(expansion, 1, 1, 0), 0.)
        for bad in (b'11 1', b'8 nan', b'8 1\n8 2'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                wave_from_bytes(raw.replace(b'8 1D0', bad))

    def test_s_surface_radius_phase_and_units(self):
        wave = read_structure_file(EXAMPLES.parent / "m6_reference/helium-closed.molden").orbitals
        mesh = make_orbital_surface(wave, 0, .05)
        radius = math.sqrt(-math.log(.05 / (1.5/math.pi)**.75)/.75) * BOHR_IN_ANGSTROM
        self.assertFalse(mesh.clipped)
        self.assertTrue(mesh.faces)
        self.assertEqual({face[-1] for face in mesh.faces}, {1})
        self.assertLess(max(abs(math.hypot(*p)-radius) for p in mesh.vertices), .012)
        self.assertFalse(make_orbital_surface(wave, 0, 2.).faces)

    def test_diffuse_and_compact_orbitals_enclose_the_analytic_radius(self):
        template = (EXAMPLES.parent / "m6_reference/helium-closed.molden").read_bytes()
        for exponent, level in ((.008, .004), (1800., .05)):
            with self.subTest(exponent=exponent):
                wave = wave_from_bytes(template.replace(b"0.7500000000", str(exponent).encode()))
                peak = (2*exponent/math.pi)**.75
                radius = math.sqrt(math.log(peak/level)/exponent)*BOHR_IN_ANGSTROM
                surface = make_orbital_surface(wave, 0, level)
                self.assertTrue(surface.faces)
                self.assertFalse(surface.clipped)
                self.assertLess(max(abs(math.hypot(*p)/radius-1) for p in surface.vertices), .025)

    def test_complete_occupations_and_effective_core_charge(self):
        raw = (EXAMPLES.parent / "m6_reference/helium-closed.molden").read_bytes()
        ion = raw.replace(b"He 1 2", b"Li 1 3")
        self.assertEqual(wave_from_bytes(ion).molecule.charge, 1)
        with_ecp = ion.replace(b"[GTO]", b"[Pseudo]\nLi 1 2\n[GTO]")
        self.assertEqual(wave_from_bytes(with_ecp).molecule.charge, 0)
        hydroxyl = read_structure_file(EXAMPLES / "OH.molden.input").record.molecule
        self.assertEqual((hydroxyl.charge, hydroxyl.multiplicity), (0, 2))


class GbwSidecarTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.gbw = Path(tmp.name) / "OH trial.1.GBW"
        self.gbw.write_bytes(b"source gbw")
        self.target = self.gbw.with_suffix(".molden.input")
        self.raw = (EXAMPLES / "OH.molden.input").read_bytes()

    def convert(self, raw, work, converter, cancel=None):
        output = work / "wave.molden.input"
        output.write_bytes(self.raw)
        return output

    def prepare(self):
        with patch("orcaview.application.structure_import.run_converter", self.convert):
            return prepare_gbw_open(self.gbw, Path("orca_2mkl"), file_state(self.target))

    def test_atomic_sidecar_and_both_sources(self):
        prepared = self.prepare()
        self.assertFalse(self.target.exists())
        opened = prepared.publish()
        self.assertEqual(self.target.read_bytes(), self.raw)
        self.assertEqual(self.gbw.read_bytes(), b"source gbw")
        self.assertEqual(opened.source.path_hint, str(self.target.absolute()))
        self.assertEqual(opened.record.auxiliary_sources[0].path_hint, str(self.gbw.absolute()))
        self.assertEqual(len(read_linked_orbitals(opened.source).orbitals), 38)
        self.target.write_bytes(self.raw + b"\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            read_linked_orbitals(opened.source)

    def test_new_and_replaced_targets_are_rechecked_at_publish(self):
        prepared = self.prepare()
        self.target.write_bytes(b"new competing file")
        with self.assertRaisesRegex(ValueError, "destination changed"):
            prepared.publish()
        prepared = self.prepare()
        self.target.write_bytes(b"newer before replacement")
        with self.assertRaisesRegex(ValueError, "destination changed"):
            prepared.publish()
        self.assertEqual(self.target.read_bytes(), b"newer before replacement")
        prepared = self.prepare()
        self.gbw.write_bytes(b"updated binary")
        with self.assertRaisesRegex(ValueError, "GBW changed"):
            prepared.publish()
        self.assertEqual(self.target.read_bytes(), b"newer before replacement")
        self.prepare().publish()
        self.assertEqual(self.target.read_bytes(), self.raw)
        self.assertFalse(list(self.gbw.parent.glob(".orcaview-*")))

    def test_invalid_converter_output_preserves_old_file_and_geometry_only_import(self):
        self.target.write_bytes(self.raw)
        self.raw = self.raw.split(b"[GTO]")[0]
        with self.assertRaisesRegex(ValueError, "no molecular orbitals"):
            self.prepare()
        self.assertIn(b"[MO]", self.target.read_bytes())
        self.target.write_bytes(self.raw)
        opened = read_structure_file(self.target)
        self.assertIsNone(opened.orbitals)
        self.assertEqual(len(opened.record.molecule.atoms), 2)

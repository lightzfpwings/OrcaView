"""ORCA orbital identity, natural occupations and numerical decomposition references."""

from concurrent.futures import CancelledError
import math
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from orcaview.application.structure_import import open_file_filters, prepare_gbw_open, read_linked_orbitals, read_structure_file
from orcaview.core.models import Atom
from orcaview.orca.orbital_files import ORCA_ORBITAL_SUFFIXES, molden_destination, orbital_kind
from orcaview.results.orbital_basis import GaussianShell

try:
    import numpy as np
    from orcaview.results.orbital_analysis import CubeOrbitalAnalysis, OrbitalAnalysis, overlap_matrix
except ModuleNotFoundError as exc:
    if exc.name != "numpy":
        raise
    np = None

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/orbitals"


def one_center_gbw(occupation):
    atom = struct.pack("<i6dii", 1, 0., 0., 0., 2., 0., 0., 2, 0)
    primitives = (1., *([0.] * 36))
    shell = struct.pack("<4i74d", 0, 0, 1, 0, *primitives, *primitives)
    basis = struct.pack("<4i", 1, 1, 0, 1) + shell
    orbital = struct.pack("<iq3d2i", 1, 1, 1., occupation, -.5, 0, 0)
    header = struct.pack("<2q8s6q", -1, 149839, bytes(8), 72, 80, 80+len(atom), 80+len(atom)+len(basis), 0, 0)
    return header + bytes(8) + atom + basis + orbital


class OrbitalFileTests(unittest.TestCase):
    def test_sibling_sets_convert_independently_and_keep_identity_after_rename(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp) / "OH test"
            targets = []
            for ext, kind in ORCA_ORBITAL_SUFFIXES.items():
                with self.subTest(ext=ext):
                    self.assertIn("*"+ext, open_file_filters())
                    source = base.with_suffix(ext.upper())
                    occupation = -.375 if kind == "unso" else 1.75
                    source.write_bytes(one_center_gbw(occupation))
                    with patch("orcaview.application.structure_import.find_converter", side_effect=AssertionError):
                        opened = read_structure_file(source)
                        prepared = prepare_gbw_open(source, None, None)
                    target = prepared.destination
                    self.assertEqual(target, molden_destination(source))
                    targets.append(target)
                    self.assertFalse(target.exists())
                    published = prepared.publish()
                    renamed = Path(tmp) / "reopened.molden"
                    renamed.write_bytes(target.read_bytes())
                    for wave in (opened.orbitals, read_linked_orbitals(opened.source),
                                 read_linked_orbitals(published.source), read_structure_file(renamed).orbitals):
                        self.assertEqual(wave.kind, kind)
                        self.assertEqual(wave.orbitals[0].occupation, occupation)
                        self.assertEqual(wave.orbitals[0].energy, -.5 if kind in ("mo", "qro") else None)
            self.assertEqual(len(set(targets)), len(targets))
            self.assertTrue(all(p.is_file() for p in targets))
            self.assertEqual(orbital_kind("state.loc.gbw"), "localized")
            self.assertEqual(orbital_kind("state.mp2nat.molden.input"), "natural")

    def test_signed_unso_and_relaxed_density_do_not_use_canonical_energy_or_frontiers(self):
        spin = read_structure_file(EXAMPLES / "OH.unso.molden.input").orbitals
        self.assertEqual(spin.kind, "unso")
        self.assertEqual(spin.frontiers(), {})
        self.assertEqual((spin.molecule.charge, spin.molecule.multiplicity), (0, 2))
        spin.molecule.validate()
        self.assertFalse(spin.complete_density)
        ns = [mo.occupation for mo in spin.orbitals]
        self.assertAlmostEqual(sum(ns), 1., places=6)
        self.assertAlmostEqual(min(ns), -.058375, places=6)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "relaxed.nat.molden"
            raw = one_center_gbw(2.001)
            binary = path.with_suffix("")
            binary.write_bytes(raw)
            prepared = prepare_gbw_open(binary, None, None)
            text = prepared.staged.read_text()
            prepared.folder.cleanup()
            path.write_text("\n".join(line for line in text.splitlines() if "Ene=" not in line))
            self.assertEqual(read_structure_file(path).orbitals.orbitals[0].occupation, 2.001)


@unittest.skipUnless(np is not None, "Requires NumPy")
class CompositionTests(unittest.TestCase):
    def test_overlap_keeps_ao_order_across_contractions_and_mixed_d_shells(self):
        atom = Atom("O", .41, .52, -.39)
        rows = ((.5, .8), (2.1, -.26))
        spherical, cartesian = (GaussianShell.from_molden(atom, 2, rows, spherical, False)
                                for spherical in (True, False))
        contracted = GaussianShell.from_molden(atom, 0, rows, False, False)
        shells = [GaussianShell.from_molden(Atom("H", i*.17, i%3*.7, i%5*.31), 0,
                                             ((.4+i*.03, 1.),), False, False) for i in range(48)]
        shells[1:1] = [spherical, contracted, cartesian]
        cancel = Event()
        with patch.object(cancel, "is_set", side_effect=(False, False, True)), self.assertRaises(CancelledError):
            overlap_matrix(shells, cancel)
        overlap = overlap_matrix(shells)
        np.testing.assert_allclose(overlap, overlap.T, atol=2e-14, rtol=0)
        np.testing.assert_allclose(overlap.diagonal(), 1., atol=2e-14, rtol=0)
        # The last spherical d and fourth Cartesian d are the same normalized xy function.
        np.testing.assert_allclose(overlap[5], overlap[10], atol=2e-14, rtol=0)
        offsets = np.cumsum([0] + [len(shell.functions) for shell in shells])
        s_shells = [(offset, shell) for offset, shell in zip(offsets, shells) if shell.angular == 0]
        for i, a in s_shells:
            for j, b in s_shells:
                r2 = math.dist(a.center, b.center)**2
                reference = sum(c*d*(math.pi/(p+q))**1.5 * math.exp(-p*q*r2/(p+q))
                                for p, c in a.primitives for q, d in b.primitives)
                self.assertAlmostEqual(overlap[i, j], reference, places=13)

    def test_unrestricted_total_density_reproduces_orca_uno(self):
        wave = read_structure_file(EXAMPLES / "OH.molden.input").orbitals
        engine = OrbitalAnalysis(wave)
        natural = engine.natural_orbitals()
        uno = read_structure_file(EXAMPLES / "OH.uno.molden.input").orbitals
        np.testing.assert_allclose([mo.occupation for mo in natural.orbitals],
                                   [mo.occupation for mo in uno.orbitals], atol=5.1e-7, rtol=0)
        c = np.array([mo.coefficients for mo in natural.orbitals])
        np.testing.assert_allclose(c @ engine.overlap() @ c.T, np.eye(len(c)), atol=2e-12)
        # The leading seven occupations are distinct at the precision of the reference Molden.
        ref = np.array([mo.coefficients for mo in uno.orbitals[:7]])
        np.testing.assert_allclose(abs(np.diag(c[:7] @ engine.overlap() @ ref.T)), 1., atol=2e-7)
        self.assertTrue(all(mo.energy is None for mo in natural.orbitals))

    def test_orca_atom_and_shell_populations_and_negative_contributions(self):
        wave = read_structure_file(EXAMPLES / "OH.molden.input").orbitals
        engine = OrbitalAnalysis(wave)
        # ORCA 6.1.1 Print[P_OrbPopMO_M/L], summed by atom and shell after rounding to 0.1%.
        for key, ref in (("mulliken", [[8.3, 68., .3], [22.7, .5, 0]]),
                         ("lowdin", [[8.9, 72.5, .6], [17.6, .4, 0]])):
            result = engine.composition(wave.orbitals[2], key)
            np.testing.assert_allclose(result.percentages, ref, atol=.1)
            self.assertAlmostEqual(result.percentages.sum(), 100.)
        self.assertTrue((engine.composition(wave.orbitals[5], "mulliken").percentages < 0).any())

    def test_nao_and_real_space_agree_with_independent_pyscf_reference(self):
        wave = read_structure_file(EXAMPLES / "OH.uno.molden.input").orbitals
        engine = OrbitalAnalysis(wave)
        # PySCF 2.12.1, def2-SVP and file density, nao() projected onto MO 2.
        nao = [[16.98314591, 69.56965635, .12312227], [13.27662738, .04744803, 0.]]
        result = engine.composition(wave.orbitals[2], "nao")
        np.testing.assert_allclose(result.percentages, nao, atol=2e-6)
        # PySCF AO evaluation on its (100 radial, 590 Lebedev) grid with matching
        # Bragg-adjusted Becke weights and the same stockholder reference densities.
        for key, expected in (("becke", [80.15429915, 19.84570085]), ("hirshfeld", [83.79778826, 16.20221174])):
            result = engine.composition(wave.orbitals[2], key)
            np.testing.assert_allclose(result.percentages[:, 0], expected, atol=.001)
            self.assertAlmostEqual(result.norm, 1., places=4)

    def test_modified_mulliken_overlap_terms_and_scpa(self):
        wave = read_structure_file(EXAMPLES / "OH.uno.molden.input").orbitals
        engine = OrbitalAnalysis(wave)
        mo = wave.orbitals[2]
        c = np.asarray(mo.coefficients)
        populations = sum(o.occupation*np.square(o.coefficients) for o in wave.orbitals)
        for key in ("stout", "bickelhaupt", "scpa"):
            squares = populations if key == "bickelhaupt" else c**2
            shares = c**2
            if key != "scpa":
                s = engine.overlap()
                for a in range(len(c)):
                    for b in range(a):
                        pair = 2*c[a]*c[b]*s[a,b]
                        fraction = squares[a]/(squares[a]+squares[b]) if squares[a]+squares[b] else .5
                        shares[a] += pair*fraction
                        shares[b] += pair*(1-fraction)
            expected = np.zeros((2,3))
            np.add.at(expected, (engine.atoms, engine.angular), shares)
            np.testing.assert_allclose(engine.composition(mo, key).percentages, 100*expected/expected.sum(), atol=1e-8)
        self.assertNotIn("density", vars(engine))
        before = engine.composition(mo, "bickelhaupt").percentages
        np.testing.assert_allclose(engine.density.diagonal(), populations, atol=1e-12)
        np.testing.assert_allclose(engine.composition(mo, "bickelhaupt").percentages, before, atol=1e-12)

    def test_cube_atom_shares_follow_the_same_orbital_and_cancellation(self):
        cube = read_structure_file(EXAMPLES / "water-homo.cube").cube_grid
        engine = CubeOrbitalAnalysis(cube)
        wave = read_structure_file(EXAMPLES / "water.molden.input").orbitals
        for method in ("becke", "hirshfeld"):
            grid = engine.composition(cube.fields[0], method)
            wfn = OrbitalAnalysis(wave).composition(wave.orbitals[4], method)
            np.testing.assert_allclose(grid.percentages, wfn.percentages, atol=.04)
        cancel = Event()
        cancel.set()
        with self.assertRaises(CancelledError):
            engine.composition(cube.fields[0], "becke", cancel)
        with self.assertRaisesRegex(ValueError, "coefficients"):
            engine.composition(cube.fields[0], "nao")
        spin = read_structure_file(EXAMPLES / "OH.unso.molden.input").orbitals
        with self.assertRaisesRegex(ValueError, "electron-density"):
            OrbitalAnalysis(spin).composition(spin.orbitals[0], "bickelhaupt")

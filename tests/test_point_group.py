"""Element-labelled Cartesian test structures for Schoenflies classification."""

from itertools import product
from math import cos, pi, sin, sqrt, tau
import unittest

from orcaview.core.models import Atom, Molecule
from orcaview.core.point_group import geometric_symmetry, point_group


def molecule(atoms):
    return Molecule("symmetry test", tuple(atoms))


def ring(symbol, n, z, phase=0, radius=1):
    return [Atom(symbol, radius * cos(phase + tau * i / n),
                 radius * sin(phase + tau * i / n), z) for i in range(n)]


class PointGroupTests(unittest.TestCase):
    def test_single_atom_and_linear(self):
        for atoms, expected in (
            ([], "—"),
            ([Atom("He", 2, 3, 4)], "Kh"),
            ([Atom("C", 1, 2, 3), Atom("H", 1, 2, 3)], 'Undetermined'),
            ([Atom("C", 0, 0, 0), Atom("O", 1, 2, 3)], "C∞v"),
            ([Atom("O", -1, -2, -3), Atom("C", 0, 0, 0), Atom("O", 1, 2, 3)], "D∞h"),
        ):
            with self.subTest(expected=expected):
                self.assertEqual(point_group(molecule(atoms)), expected)

    def test_asymmetric_mirror_and_inversion(self):
        planar = [Atom("C", 0, 0, 0), Atom("F", 0, 1, 0), Atom("Cl", 2, 0, 0)]
        pairs = [Atom(e, s*x, s*y, s*z) for s in (-1, 1)
                 for e, x, y, z in [("H", 1, 0, 0), ("C", 1, 2, 0), ("O", 0.5, 1, 3)]]
        for expected, atoms in [("Cs", planar), ("C1", planar + [Atom("Br", 0, 0, 2)]),
                                ("Ci", pairs)]:
            with self.subTest(expected=expected):
                group, axis = geometric_symmetry(molecule(atoms))
                self.assertEqual(group, expected)
                self.assertIsNone(axis.direction)

    def test_axial_families(self):
        upper = ring("H", 3, 1)
        twist = 0.31
        for group, atoms in [
            ("D6h", ring("C", 6, 0, radius=1.4) + ring("H", 6, 0, radius=2.5)),
            ("D3", upper + ring("H", 3, -1, twist)),
            ("D3d", upper + ring("H", 3, -1, pi/3)),
            ("C3v", upper + [Atom("N", 0, 0, -0.7)]),
            ("C3", upper + ring("F", 3, -1, twist)),
            ("C7", ring("H", 7, 0.6) + ring("F", 7, -1, 0.20)),
            ("D12h", ring("C", 12, 0, radius=2)),
            ("C3h", upper + ring("H", 3, -1) + ring("F", 3, 0, twist)),
        ]:
            with self.subTest(expected=group):
                self.assertEqual(point_group(molecule(atoms)), group)

    def test_allene_principal_axis_follows_the_carbon_chain(self):
        atoms = ring("H", 2, -1.4) + ring("H", 2, 1.4, pi/2)
        atoms += [Atom("C", 0, 0, z) for z in (-1, 0, 1)]
        group, axis = geometric_symmetry(molecule(atoms))
        self.assertEqual(group, "D2d")
        self.assertEqual(axis.order, 2)
        self.assertAlmostEqual(abs(axis.direction[2]), 1)

    def test_improper_only_groups(self):
        for n in (4, 6):
            atoms = []
            for symbol, phase, height in [("C", 0, 0.6), ("F", 0.28, 1.3)]:
                for i in range(n):
                    angle = phase + tau * i / n
                    atoms.append(Atom(symbol, cos(angle), sin(angle), (-1)**i * height))
            with self.subTest(n=n):
                self.assertEqual(point_group(molecule(atoms)), f"S{n}")

    def test_polyhedral_groups(self):
        tetrahedron = [Atom("H", x, y, z) for x, y, z in product((-1, 1), repeat=3)
                       if x*y*z == 1]
        # Cyclic coordinate permutations and an even number of sign flips
        # are the twelve proper rotations of this tetrahedron.
        chiral = [Atom("H", a*x, b*y, a*b*z) for a, b in product((-1, 1), repeat=2)
                  for x, y, z in [(1, 2, 3), (2, 3, 1), (3, 1, 2)]]
        inverted = [Atom("H", -p.x, -p.y, -p.z) for p in chiral]
        quarter_turn = [Atom("H", -p.y, p.x, p.z) for p in chiral]
        octahedron = [Atom("F", x, y, z) for s in (1, -1)
                      for x, y, z in [(s, 0, 0), (0, s, 0), (0, 0, s)]]
        phi = (1+sqrt(5))/2
        icosahedron = [Atom("C", x, y, z) for a, b in product((-1, 1), repeat=2)
                       for x, y, z in [(0, a, b*phi), (a, b*phi, 0), (b*phi, 0, a)]]
        for group, atoms in [("Td", tetrahedron), ("T", chiral), ("Th", chiral + inverted),
                             ("O", chiral + quarter_turn), ("Oh", octahedron), ("Ih", icosahedron)]:
            with self.subTest(expected=group):
                self.assertEqual(point_group(molecule(atoms)), group)

    def test_matching_is_tolerance_dependent_and_orientation_independent(self):
        # An asymmetric in-plane stretch breaks the C2 axis when measured
        # tightly, but either tolerance retains the molecular mirror plane.
        water = [Atom("O", 0, 0, 0), Atom("H", 0.76, 0, 0.58),
                 Atom("H", -0.77, 0, 0.58)]
        for tol, expected in [(0.001, "Cs"), (0.05, "C2v")]:
            transformed = [Atom(a.element, 4.1+a.z, 2.3+a.x, -6.4+a.y)
                           for a in reversed(water)]
            with self.subTest(tolerance=tol):
                self.assertEqual(point_group(molecule(transformed), tol), expected)

    def test_incompatible_near_symmetries_are_reported_as_undetermined(self):
        points = [(1.3743, 0.0079, 0.0099), (0.6892, 1.1845, -0.0007),
                  (-0.69, 1.2355, -0.0122), (-1.4272, 0.0148, 0.0047),
                  (-0.6678, -1.1918, -0.001), (0.6942, -1.1585, -0.0029)]
        # Some perpendicular two-fold axes and mirrors pass at 0.05 Å,
        # but their products do not all map the six carbon atoms.
        group, axis = geometric_symmetry(molecule(Atom("C", *p) for p in points))
        self.assertEqual(group, 'Undetermined')
        self.assertEqual(axis.order, 2)

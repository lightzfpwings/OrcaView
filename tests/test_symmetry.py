"""Numerical regression cases for finding the highest proper rotation axis."""

import math
import random
import unittest

from orcaview.core.models import Atom, Molecule
from orcaview.core.symmetry import analyze_rotations, principal_rotation_axis


class RotationAxisTests(unittest.TestCase):
    def test_whole_orbit_must_pass_even_if_one_small_step_matches(self):
        # The cosine modulation has two lobes. Adjacent samples look alike to
        # 0.05 Å, although rotating through a quarter-turn exchanges the lobes and minima.
        count = 36
        atoms = []
        for i in range(count):
            a = math.tau * i / count
            radius = 3 + 0.1 * math.cos(2*a)
            atoms.append(Atom("C", radius*math.cos(a), radius*math.sin(a), 0))
        analysis = analyze_rotations(Molecule("distorted ring", tuple(atoms)))
        self.assertEqual(analysis.principal.order, 2)
        self.assertFalse(any(op.determinant == 1 and op.order > 2 for op in analysis.operations))

    def test_equivalent_axes_are_repeatable_after_reordering_atoms(self):
        vertices = [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]
        atoms = [Atom("C", 0, 0, 0)] + [Atom("H", *v) for v in vertices]
        original = principal_rotation_axis(Molecule("methane", tuple(atoms)))
        random.Random(3).shuffle(atoms)
        reordered = principal_rotation_axis(Molecule("methane", tuple(atoms)))
        self.assertEqual(original, reordered)
        self.assertEqual(reordered.order, 3)
        self.assertAlmostEqual(sum(x*x for x in reordered.direction), 1)

    def test_spatial_matching_preserves_multiplicities(self):
        # Three unique labels fix the yz plane. Every H position has a
        # mirrored partner, but the multiplicities on opposite sides differ.
        atoms = (Atom("O", 0, 0, 0), Atom("N", 0, 1, 2), Atom("F", 0, -1, .3))
        atoms += tuple(Atom("H", x, y, 0) for x, y in
                       [(1, 1), (1, 1), (-1, 1), (-1, 3), (-1, 3), (1, 3)])
        analysis = analyze_rotations(Molecule("unequal multiplicities", atoms))
        self.assertTrue(analysis.closed)
        self.assertEqual(len(analysis.operations), 1)
        self.assertEqual(analysis.operations[0].determinant, 1)

    def test_scale_extremes_and_indistinguishable_sites(self):
        for scale, tolerance in [(1e140, 1e132), (1e-140, 1e-148)]:
            atoms = (Atom("C", 0, 0, 0), Atom("O", scale, scale, 0))
            axis = principal_rotation_axis(Molecule("linear", atoms), tolerance)
            self.assertEqual(axis.order, math.inf)
            self.assertAlmostEqual(abs(axis.direction[0]), 2**-.5)
        atoms = (Atom("C", 1, 2, 3), Atom("O", 1, 2, 3))
        self.assertFalse(analyze_rotations(Molecule("coincident", atoms)).closed)
        large = (Atom("H", 1e302, 0, 0), Atom("H", -1e302, 0, 0))
        self.assertFalse(analyze_rotations(Molecule("unresolved", large)).closed)

    def test_invalid_matching_tolerance(self):
        molecule = Molecule("helium", (Atom("He", 0, 0, 0),))
        for tolerance in [-1, 0, math.nan, math.inf]:
            with self.subTest(tolerance=tolerance), self.assertRaises(ValueError):
                principal_rotation_axis(molecule, tolerance)


if __name__ == "__main__":
    unittest.main()

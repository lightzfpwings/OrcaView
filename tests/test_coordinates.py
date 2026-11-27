"""M2 coordinate conventions, degeneracy and explicit moving-set behavior."""

from dataclasses import FrozenInstanceError, replace
import math
import unittest

from orcaview.application.document import MoleculeDocument
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.core.snapshots import GeometryRef
from orcaview.editing.coordinates import CoordinateDefinition, edit_distance, measure


def snapshot(points, bonds=(), **state):
    return MoleculeDocument.from_molecule(Molecule(
        "coordinate fixture", tuple(Atom("H", *p) for p in points), bonds, **state)).head


def coordinate(geometry, kind, rows):
    return CoordinateDefinition(geometry.ref, kind, tuple(geometry.atom_ids[i] for i in rows))


class CoordinateTests(unittest.TestCase):
    def test_definition_is_immutable_versioned_and_units_are_explicit(self):
        geometry = snapshot(((0, 0, 0), (1, 0, 0), (0, 1, 0)))
        distance = coordinate(geometry, "distance", (0, 1))
        self.assertEqual((distance.contract_version, distance.unit), (1, "angstrom"))
        self.assertEqual(coordinate(geometry, "angle", (0, 1, 2)).unit, "degree")
        with self.assertRaises(FrozenInstanceError):
            distance.kind = "angle"
        for kwargs in (
            {"geometry": None}, {"kind": "torsion"}, {"kind": []},
            {"atom_ids": list(distance.atom_ids)}, {"atom_ids": (distance.atom_ids[0],) * 2},
            {"atom_ids": geometry.atom_ids}, {"unit": "bohr"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(distance, **kwargs)

    def test_water_distance_and_ordered_angle(self):
        water = MoleculeDocument.from_molecule(Molecule("water", (
            Atom("O", 0, 0, 0), Atom("H", 1, 0, 0),
            Atom("H", math.cos(math.radians(104.5)), math.sin(math.radians(104.5)), 0),
        ))).head
        self.assertAlmostEqual(measure(water, coordinate(water, "distance", (0, 1))), 1)
        self.assertAlmostEqual(measure(water, coordinate(water, "angle", (1, 0, 2))), 104.5)
        self.assertAlmostEqual(measure(water, coordinate(water, "angle", (0, 1, 2))), 37.75)

    def test_exact_geometry_reference_and_known_ids_required(self):
        geometry = snapshot(((0, 0, 0), (1, 0, 0)))
        definition = coordinate(geometry, "distance", (0, 1))
        other_ref = GeometryRef(geometry.ref.document_id, geometry.ref.revision)
        for invalid in (replace(definition, geometry=other_ref),
                        replace(definition, atom_ids=(geometry.atom_ids[0], "missing"))):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                measure(geometry, invalid)

    def test_collinear_angle_is_defined_and_coincident_arm_is_rejected(self):
        line = snapshot(((-1, 0, 0), (0, 0, 0), (1, 0, 0), (2, 0, 0)))
        self.assertEqual(measure(line, coordinate(line, "angle", (0, 1, 2))), 180)
        self.assertEqual(measure(line, coordinate(line, "angle", (2, 1, 3))), 0)
        coincident = snapshot(((0, 0, 0), (0, 0, 0), (1, 0, 0)))
        self.assertEqual(measure(coincident, coordinate(coincident, "distance", (0, 1))), 0)
        with self.assertRaises(ValueError):
            measure(coincident, coordinate(coincident, "angle", (0, 1, 2)))

    def test_signed_dihedral_and_periodic_boundary(self):
        for expected in (0, 90, -90, 179.999, -179.999, -180):
            theta = math.radians(expected)
            geometry = snapshot(((0, 1, 0), (0, 0, 0), (1, 0, 0),
                                 (1, math.cos(theta), math.sin(theta))))
            measured = measure(geometry, coordinate(geometry, "dihedral", (0, 1, 2, 3)))
            with self.subTest(expected=expected):
                self.assertAlmostEqual(measured, expected)
                self.assertGreaterEqual(measured, -180)
                self.assertLess(measured, 180)
                self.assertAlmostEqual(measure(geometry, coordinate(geometry, "dihedral", (3, 2, 1, 0))), expected)

    def test_undefined_dihedral_planes_or_axis_are_rejected(self):
        for points in (
            ((-1, 0, 0), (0, 0, 0), (1, 0, 0), (1, 1, 0)),
            ((0, 1, 0), (0, 0, 0), (1, 0, 0), (2, 0, 0)),
            ((0, 1, 0), (0, 0, 0), (0, 0, 0), (1, 1, 0)),
            ((0, 0, 0), (0, 0, 0), (1, 0, 0), (1, 1, 0)),
            ((-1, 1e-14, 0), (0, 0, 0), (1, 0, 0), (1, 1, 0)),
        ):
            geometry = snapshot(points)
            with self.subTest(points=points), self.assertRaises(ValueError):
                measure(geometry, coordinate(geometry, "dihedral", (0, 1, 2, 3)))

    def test_dihedral_is_scale_invariant_for_subnormal_coordinates(self):
        # Every subnormal component is an exact integer multiple of the
        # smallest binary64 value; only the normalization, not input rounding,
        # can change this shape's dihedral under the scale transformation.
        points = ((0, 1, 0), (0, 0, 0), (1, 1, 1), (3, 2, 0))
        normal = snapshot(points)
        subnormal = snapshot(tuple(tuple(value * 5e-324 for value in point)
                                   for point in points))
        expected = measure(normal, coordinate(normal, "dihedral", (0, 1, 2, 3)))
        actual = measure(subnormal, coordinate(subnormal, "dihedral", (0, 1, 2, 3)))
        self.assertAlmostEqual(expected, -79.1066053508691)
        self.assertAlmostEqual(actual, expected)

    def test_distance_edit_holds_other_atoms_and_retains_full_state(self):
        geometry = snapshot(((0, 0, 0), (1, 0, 0), (1, 1, 0), (8, 8, 8)),
                            (Bond(0, 1, 2), Bond(1, 2)), charge=1, multiplicity=2)
        before = geometry.molecule
        changed = edit_distance(geometry, coordinate(geometry, "distance", (0, 1)), 2,
                                geometry.atom_ids[1:3], (geometry.atom_ids[0], geometry.atom_ids[3]))
        self.assertEqual(changed.atoms, (Atom("H", 0, 0, 0), Atom("H", 2, 0, 0),
                                        Atom("H", 2, 1, 0), Atom("H", 8, 8, 8)))
        self.assertEqual((changed.name, changed.bonds, changed.charge, changed.multiplicity),
                         (before.name, before.bonds, before.charge, before.multiplicity))
        self.assertEqual(geometry.molecule, before)

    def test_ring_edit_uses_explicit_set_without_guessing_a_side(self):
        ring = snapshot(((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)),
                        (Bond(0, 1), Bond(1, 2), Bond(2, 3), Bond(3, 0)))
        changed = edit_distance(ring, coordinate(ring, "distance", (0, 1)), 1.5,
                                ring.atom_ids[1:3])
        self.assertEqual(changed.atoms[1].x, 1.5)
        self.assertEqual(changed.atoms[2].x, 1.5)
        self.assertEqual(changed.atoms[3], ring.molecule.atoms[3])
        self.assertEqual(changed.bonds, ring.molecule.bonds)
        with self.assertRaises(ValueError):
            edit_distance(ring, coordinate(ring, "distance", (0, 1)), 1.5, ())

    def test_invalid_distance_edits_fail_without_mutation(self):
        geometry = snapshot(((0, 0, 0), (1, 0, 0), (1, 1, 0)))
        distance = coordinate(geometry, "distance", (0, 1))
        first, second, third = geometry.atom_ids
        before = geometry.molecule
        for target, moving, fixed in (
            (0, (second,), ()), (-1, (second,), ()), (True, (second,), ()),
            (float("nan"), (second,), ()), (float("inf"), (second,), ()),
            (2, (first, second), ()), (2, (third,), ()), (2, (second,), (second,)),
            (2, ("missing", second), ()), (2, (second,), ("missing",)),
            (2, (second, second), ()), (2, [second], ()), (2, (second,), [first]),
        ):
            with self.subTest(target=target, moving=moving, fixed=fixed), self.assertRaises(ValueError):
                edit_distance(geometry, distance, target, moving, fixed)
            self.assertEqual(geometry.molecule, before)
        with self.assertRaises(ValueError):
            edit_distance(geometry, coordinate(geometry, "angle", (0, 1, 2)), 2, (second,))

    def test_coincident_endpoints_cannot_define_edit_direction(self):
        geometry = snapshot(((0, 0, 0), (0, 0, 0)))
        with self.assertRaises(ValueError):
            edit_distance(geometry, coordinate(geometry, "distance", (0, 1)), 1, (geometry.atom_ids[1],))

    def test_unrepresentable_measurements_and_targets_fail_clearly(self):
        geometry = snapshot(((-1e308, 0, 0), (1e308, 0, 0)))
        with self.assertRaises(ValueError):
            measure(geometry, coordinate(geometry, "distance", (0, 1)))
        geometry = snapshot(((1e16, 0, 0), (1e16 + 2, 0, 0)))
        with self.assertRaises(ValueError):
            edit_distance(geometry, coordinate(geometry, "distance", (0, 1)), 1, (geometry.atom_ids[1],))


if __name__ == "__main__":
    unittest.main()

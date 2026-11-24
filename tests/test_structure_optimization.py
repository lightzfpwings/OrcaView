"""Exercise the same isolated native worker used by the desktop application."""

from dataclasses import replace
from importlib.util import find_spec
import math
import unittest
from unittest.mock import patch

from orcaview.core.geometry import display_bonds
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.editing.optimization import clean_sketch, optimize_structure


def points(molecule):
    return [(a.x, a.y, a.z) for a in molecule.atoms]


def ring():
    return Molecule("ring", tuple(Atom("C", 2 * math.cos(i * math.pi/3), math.sin(i * math.pi/3), 2.)
                                  for i in range(6)), tuple(Bond(i, (i+1) % 6) for i in range(6)))


class OptimizationFailureTests(unittest.TestCase):
    def test_single_bond_chain_is_an_extended_2d_zigzag_in_bond_order(self):
        atoms = tuple(Atom("C", i, -i, i * .2) for i in range(6))
        path = (2, 4, 1, 0, 5, 3)
        molecule = Molecule("hexane", atoms, tuple(Bond(a, b) for a, b in zip(path, path[1:])))
        sketch = tuple((9., 7. + path.index(i)) for i in range(6))
        with patch("orcaview.editing.optimization.run_babel_worker", side_effect=AssertionError):
            layout = clean_sketch(molecule, sketch)
            self.assertEqual(clean_sketch(molecule, layout), layout)
        chain = [layout[i] for i in path]
        for a, b in zip(chain, chain[1:]):
            self.assertAlmostEqual(math.dist(a, b), 1.5)
        for a, c in zip(chain, chain[2:]):
            self.assertAlmostEqual(math.dist(a, c), 1.5 * math.sqrt(3))
        self.assertGreater(math.dist(chain[0], chain[-1]), 6.5)
        self.assertGreater(chain[-1][1], chain[0][1])
        self.assertAlmostEqual(sum(x for x, _ in layout), 54.)
        self.assertAlmostEqual(sum(y for _, y in layout), 57.)

    def test_single_atom_and_explicit_empty_graph_have_no_optimizable_bonds(self):
        with self.assertRaisesRegex(ValueError, "at least one bond"):
            optimize_structure(Molecule("C", (Atom("C", 0, 0, 0),)), "3D")
        m = Molecule("unbonded", (Atom("C", 0, 0, 0), Atom("O", 1.3, 0, 0)), bonds_explicit=True)
        with self.assertRaisesRegex(ValueError, "at least one bond"):
            optimize_structure(m, "2D")

    def test_forcefield_requires_representable_charge_and_spin(self):
        for attrs in ({"charge": 1}, {"multiplicity": 3}):
            with self.subTest(attrs=attrs), self.assertRaisesRegex(ValueError, "neutral singlets"):
                optimize_structure(replace(ring(), **attrs), "3D")

    def test_changed_atom_or_incomplete_result_is_rejected(self):
        m = ring()
        wrong_rows = [("N", 1, 1, 1)] + [("C", 1, 1, 1)] * 5
        for rows in [[], wrong_rows]:
            response = {"atoms": rows, "method": "MMFF94"}
            with patch("orcaview.editing.optimization.run_babel_worker", return_value=response):
                with self.assertRaisesRegex(ValueError, "atom mapping"):
                    optimize_structure(m, "3D")


@unittest.skipUnless(find_spec("openbabel"), "requires desktop Open Babel")
class NativeOptimizationTests(unittest.TestCase):
    def test_depiction_centers_a_regular_ring_on_its_drawing_not_its_conformer(self):
        physical = optimize_structure(ring(), "3D").molecule
        reference = tuple((a.x + 8, a.y - 4) for a in physical.atoms)
        layout = clean_sketch(physical, reference)
        for bond in physical.bonds:
            self.assertAlmostEqual(math.dist(layout[bond.a], layout[bond.b]), 1.5, places=5)
        self.assertGreater(max(a.z for a in physical.atoms) - min(a.z for a in physical.atoms), .3)
        for after, before in zip(zip(*layout), zip(*reference)):
            self.assertAlmostEqual(sum(after), sum(before))

    def test_aromatic_ring_uses_aromatic_force_field_and_keeps_editor_bonds(self):
        cycle = ring()
        cycle = replace(cycle, bonds=tuple(replace(b, order=2, style="aromatic") for b in cycle.bonds))
        for mode in ("2D", "3D"):
            result = optimize_structure(cycle, mode)
            self.assertEqual(result.molecule.bonds, cycle.bonds)
            coords = points(result.molecule)
            expected = 1.5 if mode == "2D" else 1.40
            for bond in result.molecule.bonds:
                self.assertAlmostEqual(math.dist(coords[bond.a], coords[bond.b]), expected, delta=.035)

    def test_partial_and_coordinate_sketches_remain_editable_without_integer_force_field_approximation(self):
        atoms = (Atom("N", 0., 0., 0.), Atom("B", 1.5, 0., 0.))
        for order, style, diagnostic in ((1, "coordinate", "coordinate bonds"), (1, "coordinate_arrow", "coordinate bonds"),
                                         (3, "partial_triple", "2.5"), (2, "aromatic", "aromatic system")):
            with self.subTest(style=style):
                m = Molecule("fragment", atoms, (Bond(0, 1, order, style),))
                self.assertEqual(optimize_structure(m, "2D").molecule.bonds, m.bonds)
                with self.assertRaisesRegex(ValueError, diagnostic):
                    optimize_structure(m, "3D")

    def test_native_wedge_handedness_and_unknown_stereo(self):
        from openbabel import openbabel as ob
        from orcaview.editing.optimization import _perceive_stereo, _prepare_graph
        from orcaview.io.babel_geometry import geometry_payload

        def config(molecule):
            payload = geometry_payload(molecule)
            payload["infer_orders"] = False
            work, _ = _prepare_graph(payload, "optimize-2d", ob)
            return _perceive_stereo(work, ob, (0, 1))

        atoms = tuple(Atom(e, x, y, 0.) for e, (x, y) in zip(("C","F","Cl","Br","I"),
                      ((0.,0.),(1.,0.),(0.,1.),(-1.,0.),(0.,-1.))))
        stereo = {}
        for style in ("wedge", "hollow_wedge", "hashed_wedge", "wavy", "wavy_wedge"):
            m = Molecule("stereocenter", atoms,
                         (Bond(0, 1, 1, style), Bond(0, 2), Bond(0, 3), Bond(0, 4)))
            stereo[style] = config(m)
            result = optimize_structure(m, "2D")
            self.assertEqual(config(result.molecule), stereo[style])
            self.assertEqual(result.molecule.bonds, m.bonds)
        self.assertEqual(stereo["wedge"], stereo["hollow_wedge"])
        self.assertIn(("tetra", 0), stereo["wedge"])
        self.assertIn(("tetra", 0), stereo["hashed_wedge"])
        self.assertNotEqual(stereo["wedge"], stereo["hashed_wedge"])
        self.assertFalse(stereo["wavy"] or stereo["wavy_wedge"])
        alkene = Molecule("alkene", tuple(Atom(e, x, y, 0.) for e, (x,y) in zip(
            ("F", "C", "C", "F"), ((0.,1.),(1.,0.),(2.,0.),(3.,1.)))),
            (Bond(0, 1), Bond(1, 2, 2, "crossed"), Bond(2, 3)))
        self.assertFalse(config(alkene))
        self.assertIn(("alkene", 1), config(replace(alkene, bonds=(Bond(0, 1), Bond(1, 2, 2), Bond(2, 3)))))

    def test_distorted_ring_becomes_a_regular_planar_hexagon(self):
        molecule = ring()
        for plane in ("XY", "XZ", "YZ"):
            with self.subTest(plane=plane):
                result = optimize_structure(molecule, "2D", plane)
                self.assertEqual(result.method, "gen2D")
                coords = points(result.molecule)
                for i in range(len(coords)):
                    self.assertAlmostEqual(math.dist(coords[i], coords[(i+1) % 6]), 1.50, places=4)
                    self.assertAlmostEqual(math.dist(coords[i], coords[(i+2) % 6]), 1.5*math.sqrt(3), places=4)
                normal = next(i for i, axis in enumerate("XYZ") if axis not in plane)
                self.assertLess(max(p[normal] for p in coords) - min(p[normal] for p in coords), 1e-8)
                for before, after in zip(zip(*points(molecule)), zip(*coords)):
                    self.assertAlmostEqual(sum(before), sum(after))
                self.assertEqual(result.molecule.bonds, molecule.bonds)

    def test_3d_puckers_a_planar_cyclohexane_without_appending_atoms(self):
        m = ring()
        result = optimize_structure(m, "3D")
        self.assertEqual(result.method, "MMFF94")
        self.assertEqual(len(result.molecule.atoms), 6)
        self.assertEqual(m.bonds, result.molecule.bonds)
        coords = points(result.molecule)
        self.assertGreater(max(p[2] for p in coords) - min(p[2] for p in coords), .3)
        for b in m.bonds:
            self.assertAlmostEqual(math.dist(coords[b.a], coords[b.b]), 1.53, delta=.04)

    def test_manual_h_seed_rebuilds_only_the_flat_ring_fragment(self):
        from openbabel import openbabel as ob
        from orcaview.editing.optimization import _perceive_stereo, _prepare_graph, _seed_3d
        from orcaview.io.babel_geometry import geometry_payload

        # Put a distorted 3D stereocenter first so neither fragment's IDs
        # nor the unaffected reference coordinates can be inferred by order.
        chiral = (Atom("C", 10, 0, 0), Atom("Br", 11.1, 1.3, 1.2), Atom("F", 9.2, -.8, .8),
                  Atom("Cl", 11.2, -1.2, -1.2), Atom("H", 9.4, .6, -.6))
        cycle = ring()
        above = replace(cycle.atoms[0], element="H", z=3.)
        mol = Molecule("two fragments", chiral + cycle.atoms + (above,),
                       tuple(Bond(0, i) for i in range(1, 5))
                       + tuple(Bond(b.a + 5, b.b + 5) for b in cycle.bonds) + (Bond(5, 11),))
        payload = geometry_payload(mol)
        payload["infer_orders"] = False
        work, _ = _prepare_graph(payload, "optimize-3d", ob)
        stereo = _perceive_stereo(work, ob, None)
        self.assertIn(("tetra", 0), stereo)
        original = points(mol)
        _seed_3d(work, original, ob, planar=False, stereo=stereo)
        updated = [(a.GetX(), a.GetY(), a.GetZ()) for a in ob.OBMolAtomIter(work)]
        self.assertEqual(updated[:5], original[:5])
        carbons = updated[5:11]
        self.assertGreater(max(p[2] for p in carbons) - min(p[2] for p in carbons), .3)

    def test_real_uff_fallback_for_a_magnesium_bond(self):
        m = Molecule("MgOH", (Atom("Mg", 0, 0, 0), Atom("O", 2.6, 0, 0),
                               Atom("H", 2.9, .9, 0)), (Bond(0,1), Bond(1,2)))
        result = optimize_structure(m, "3D")
        self.assertEqual(result.method, "UFF")
        coords = points(result.molecule)
        self.assertTrue(1.6 < math.dist(coords[0], coords[1]) < 2.3)
        self.assertEqual(result.molecule.bonds, m.bonds)

    def test_xyz_benzene_retains_unsaturation_on_repeated_optimization(self):
        m = Molecule("benzene.xyz", tuple(Atom(e, r*math.cos(i*math.pi/3), r*math.sin(i*math.pi/3), 0.)
                                         for e, r in [("C", 1.4), ("H", 2.48)] for i in range(6)))
        edges = [(b.a, b.b) for b in display_bonds(m)]
        for mode in ("3D", "3D", "2D"):
            m = optimize_structure(m, mode).molecule
            self.assertEqual(len(m.atoms), 12)
            self.assertTrue(m.bonds_explicit)
            self.assertEqual([(b.a, b.b) for b in m.bonds], edges)
            self.assertEqual(sum(b.order == 2 for b in m.bonds), 3)
            coords = points(m)
            if mode == "3D":
                for b in m.bonds:
                    if m.atoms[b.b].element == "C":
                        self.assertAlmostEqual(math.dist(coords[b.a], coords[b.b]), 1.40, delta=.04)

    def test_distorted_chiral_3d_conformer_retains_handedness(self):
        coords = [(0, 0, 0), (1.1, 1.3, 1.2), (-.8, -.8, .8), (1.2, -1.2, -1.2), (-.6, .6, -.6)]
        m = Molecule("CHBrClF", tuple(Atom(e, *p) for e, p in zip(("C","Br","F","Cl","H"), coords)),
                     tuple(Bond(0, i) for i in range(1, 5)))
        with self.assertRaisesRegex(ValueError, "tetrahedral stereochemistry"):
            optimize_structure(m, "2D")
        result = optimize_structure(m, "3D")
        corrected = points(result.molecule)
        # The scalar triple product of the three fixed atom-ID vectors has
        # the same sign before and after the minimization.
        for xyz in (coords, corrected):
            a, b, c = [tuple(v-u for v,u in zip(xyz[i],xyz[0])) for i in (1,2,3)]
            self.assertGreater(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])
                               +a[2]*(b[0]*c[1]-b[1]*c[0]), 1.)
        self.assertNotEqual(coords, corrected)
        self.assertEqual([a.element for a in result.molecule.atoms], [a.element for a in m.atoms])

    def test_preserves_cis_trans_on_rotated_plane(self):
        for terminal_z in (1., -1.):
            m = Molecule("alkene", (Atom("F", 0., 4., 1.), Atom("C", 1., 4., 0.),
                                    Atom("C", 2., 4., 0.), Atom("F", 3., 4., terminal_z)),
                         (Bond(0,1), Bond(1,2,2), Bond(2,3)))
            for mode in ("2D", "3D"):
                coords = points(optimize_structure(m, mode, "XZ").molecule)
                def line_side(point):
                    x, _, z = point
                    a, b = coords[1:3]
                    return (b[0]-a[0])*(z-a[2]) - (b[2]-a[2])*(x-a[0])
                signs = line_side(coords[0])*line_side(coords[3])
                self.assertGreater(signs*terminal_z, .1)

    def test_missing_uff_parameters_and_local_ionic_valences_fail_atomically(self):
        m = Molecule("late element", (Atom("Og", 0., 0., 0.), Atom("C", 2., 0., 0.)), (Bond(0,1),))
        with self.assertRaisesRegex(ValueError, "parameters"):
            optimize_structure(m, "3D")
        m = Molecule("ammonium sketch", (Atom("N", 0, 0, 0),) + tuple(
            Atom("C", *p) for p in ((1,1,1),(-1,-1,1),(-1,1,-1),(1,-1,-1))),
                     tuple(Bond(0, i) for i in range(1, 5)))
        with self.assertRaisesRegex(ValueError, "formal charge"):
            optimize_structure(m, "3D")

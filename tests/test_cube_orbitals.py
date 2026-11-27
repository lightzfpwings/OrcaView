"""Cube sample ordering, affine geometry, scalar-field interpolation and surface normals."""

from collections import Counter
from dataclasses import replace
from math import exp, hypot, isclose, log, pi, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from concurrent.futures import CancelledError

from orcaview.application.structure_import import read_linked_orbitals, read_structure_file
from orcaview.core.units import BOHR_IN_ANGSTROM
from orcaview.io.cube import read_cube
from orcaview.results.orbital_surface import _interpolator, make_cube_surface, make_orbital_surface


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def cube_bytes(header, axes, tail):
    return ("Grid example\nScalar values\n" + "\n".join([header, *axes, tail]) + "\n").encode()


def sphere_grid():
    values = [exp(-((x-5)**2+(y-5)**2+(z-5)**2)/7) for x in range(11) for y in range(11) for z in range(11)]
    raw = cube_bytes("0 -5 -5 -5", ("-11 1 0 0", "-11 0 1 0", "-11 0 0 1"), " ".join(map(str, values)))
    return read_cube("sphere.cub", raw)


class CubeOrbitalsTests(unittest.TestCase):
    def test_real_orca_water_homo_data_and_phase(self):
        opened = read_structure_file(EXAMPLES / "orbitals/water-homo.cube")
        cube = opened.cube_grid
        self.assertEqual(cube.grid.shape, (32, 32, 32))
        self.assertEqual(cube.source_unit, "bohr")
        self.assertEqual(cube.fields[0].identifier, 4)
        self.assertEqual(cube.molecule.atoms[0].element, "O")
        self.assertAlmostEqual(cube.molecule.atoms[1].x, 1.433550*BOHR_IN_ANGSTROM)
        field = cube.fields[0]
        self.assertEqual(field.values[(13*32+15)*32+15], -.0432394)
        self.assertEqual(field.values[(15*32+19)*32+16], .139115)
        self.assertTrue(field.values.readonly)
        self.assertEqual(field.initial_isovalue(), .05)
        for quality in ("coarse", "standard", "smooth", "fine"):
            mesh = make_cube_surface(cube, 0, quality=quality)
            self.assertFalse(mesh.clipped)
            self.assertEqual({f[-1] for f in mesh.faces}, {-1, 1})
            # ORCA's water HOMO has a node in its xz molecular plane.
            tolerance = cube.grid.steps[1][1]/2 if quality == "coarse" else 0.
            incidence = Counter()
            for face in mesh.faces:
                ring = face[:-1]
                self.assertGreater(face[-1]*sum(mesh.vertices[k][1] for k in ring)/len(ring), -tolerance)
                incidence.update(tuple(sorted(edge)) for edge in zip(ring, ring[1:]+ring[:1]))
            self.assertEqual(set(incidence.values()), {2})  # closed, crack-free phase surfaces

    def test_project_resolves_verified_sibling_after_moving_between_platforms(self):
        with TemporaryDirectory() as directory:
            tmp = Path(directory)
            source = EXAMPLES / "orbitals/water-homo.cube"
            (tmp/source.name).write_bytes(source.read_bytes())
            ref = replace(read_structure_file(source).source, path_hint=r"C:\calculations\water-homo.cube")
            restored = read_linked_orbitals(ref, tmp/"water.oview.json")
            self.assertEqual(restored.fields[0].identifier, 4)
            self.assertEqual(restored.grid.shape, (32, 32, 32))

    def test_multi_dataset_ids_and_nval_are_the_innermost_stride(self):
        axes = ("-2 1 0 0", "-2 0 1 0", "-2 0 0 1")
        data = " ".join(f"{i}D0 {-1-i}" for i in range(8))
        for hdr, tail, ids in (("-1 0 0 0", "1 1 0 0 0\n2 31\n47\n", [31, 47]),
                               ("1 0 0 0 2", "1 1 0 0 0\n", [1, 2])):
            cube = read_cube("field.CUB", cube_bytes(hdr, axes, tail+data))
            self.assertEqual([f.identifier for f in cube.fields], ids)
            self.assertEqual(cube.source_unit, "angstrom")
            self.assertEqual(cube.molecule.multiplicity, 2)
            self.assertEqual(list(cube.fields[0].values), list(range(8)))
            self.assertEqual(list(cube.fields[1].values), list(range(-1, -9, -1)))
            self.assertEqual(cube.fields[1].initial_isovalue(), 4.5)

    def test_skew_and_left_handed_grids_have_correct_coordinates_winding_and_normals(self):
        for dy in (1., -1.):
            axes = ("-2 1 0 0", f"-2 .3 {dy} 0", "-2 -.2 .1 1")
            cube = read_cube("skew.cube", cube_bytes("0 10 20 30", axes, "-2 -2 -2 -2 2 2 2 2"))
            mesh = make_cube_surface(cube, 0, 1., quality="standard")
            self.assertTrue(mesh.clipped)
            self.assertEqual({f[-1] for f in mesh.faces}, {-1, 1})
            grad = cube.grid.reciprocal[0]
            for face in mesh.faces:
                sign = face[-1]
                for k in face[:-1]:
                    p = mesh.vertices[k]
                    expected_x = (.25 if sign < 0 else .75)
                    self.assertAlmostEqual(sum(a*(v-o) for a, v, o in zip(grad, p, cube.grid.origin)), expected_x)
                    self.assertAlmostEqual(sum(a*b for a, b in zip(grad, mesh.normals[k])), -sign*hypot(*grad))
                a, b, c = (mesh.vertices[k] for k in face[:3])
                u, v = (tuple(t-s for t, s in zip(p, a)) for p in (b, c))
                normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
                self.assertGreater(sum(a*b for a, b in zip(normal, mesh.normals[face[0]])), 0.)

    def test_smoother_levels_converge_toward_analytic_isosurfaces(self):
        cube = sphere_grid()
        wave = read_structure_file(EXAMPLES / "m6_reference/helium-closed.molden").orbitals
        for builder, obj, level, radius in (
            (make_cube_surface, cube, .29, sqrt(-7*log(.29))),
            (make_orbital_surface, wave, .05, sqrt(-log(.05/(1.5/pi)**.75)/.75)*BOHR_IN_ANGSTROM)
        ):
            counts, errors = [], []
            for quality in ("coarse", "standard", "smooth", "fine"):
                mesh = builder(obj, 0, level, quality=quality)
                self.assertFalse(mesh.clipped)
                counts.append(len(mesh.faces))
                errors.append(sqrt(sum((hypot(*p)-radius)**2 for p in mesh.vertices)/len(mesh.vertices)))
                for p, n in zip(mesh.vertices[::97], mesh.normals[::97]):
                    self.assertTrue(isclose(hypot(*n), 1.))
                    self.assertGreater(sum(v*w for v, w in zip(p,n))/hypot(*p), .99)
            for low, high in zip(counts, counts[1:]):
                self.assertLess(low, high)
            for low, high in zip(errors, errors[1:]):
                self.assertGreater(low, high)
        stop = Event()
        stop.set()
        with self.assertRaises(CancelledError):
            make_cube_surface(cube, 0, .29, stop)
        self.assertFalse(make_cube_surface(cube, 0, 2.).faces)

    def test_cube_refinement_preserves_nodes_and_stays_between_cell_extrema(self):
        profile = (-4., -.001, .7, .71, .71, -2.)
        values = [a*b+c for a in profile for b in profile for c in profile]
        size = len(profile)
        for factor in (2, 3, 4):
            sample = _interpolator(values, (size,)*3, factor)
            for x in range(size):
                for y in range(size):
                    for z in range(size):
                        origin = x*factor, y*factor, z*factor
                        self.assertEqual(sample(*origin), values[(x*size+y)*size+z])
                        if max(x, y, z) == size-1:
                            continue
                        corners = [values[((x+i)*size+y+j)*size+z+k]
                                   for i in (0, 1) for j in (0, 1) for k in (0, 1)]
                        low, high = min(corners)-1e-12, max(corners)+1e-12
                        for i in range(factor):
                            for j in range(factor):
                                for k in range(factor):
                                    self.assertTrue(low <= sample(origin[0]+i, origin[1]+j, origin[2]+k) <= high)

    def test_incomplete_invalid_and_nonfinite_volumes(self):
        valid = cube_bytes("-1 0 0 0", ("2 1 0 0", "2 0 1 0", "2 0 0 1"), "1 1 0 0 0\n1 7\n0 1 2 3 4 5 6 7")
        for old, new in ((b"2 0 1 0", b"-2 0 1 0"), (b"2 0 1 0", b"2 1 0 0"),
                         (b"2 0 0 1", b"1 0 0 1"), (b"1 7\n", b"2 7 7\n"),
                         (b"5 6 7", b"5 6"), (b"5 6 7", b"5 6 7 8"), (b"5 6 7", b"5 inf 7")):
            with self.subTest(old=old, new=new), self.assertRaises(ValueError):
                read_cube("bad.cube", valid.replace(old, new))

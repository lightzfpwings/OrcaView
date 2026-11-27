import importlib.util
import math
import unittest

from orcaview.io.babel_structure import read_babel_structure, read_xyz_structure
from orcaview.io.structure_record import PeriodicStructureError


CIF = b"""data_structure
_cell_length_a 5
_cell_length_b 5
_cell_length_c 5
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P -1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
He1 He 0.1 0.2 0.3
"""

MOL = b"""Methanol
  sample            2D

  2  1  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
M  END
"""


class PeriodicCoordinatesTests(unittest.TestCase):
    def test_extended_xyz_columns_finite_cell_and_units(self):
        raw = (b'2\nProperties=tag:I:1:pos:R:3:Z:I:1 Lattice="4 0 0 0 4 0 0 0 4" '
               b'pbc="T F F" units=Bohr\n4 0 0 0 2\n9 1 0 0 10\n')
        with self.assertRaises(PeriodicStructureError):
            read_xyz_structure(raw, "cell")
        record = read_xyz_structure(raw, "cell", remove_periodicity=True)
        self.assertTrue(record.removed_periodicity)
        self.assertEqual([a.element for a in record.molecule.atoms], ["He", "Ne"])
        self.assertAlmostEqual(record.molecule.atoms[1].x, 0.52917721, places=7)
        self.assertEqual(record.source_unit, "bohr")
        self.assertFalse(read_xyz_structure(raw.replace(b"T F F", b"F F F"), "box").removed_periodicity)
        self.assertEqual(read_xyz_structure(b"1\n\nHe 1 0 0\n", "he", default_unit="bohr").source_unit, "bohr")

    def test_poscar_direct_with_skew_and_cartesian_scaling(self):
        raw = b"finite cell\n2\n2 0 0\n1 3 0\n0 0 4\nHe Ne\n1 1\nSelective dynamics\nDirect\n0 0 0 F F F\n0.5 0.5 0.5 T T T\n"
        with self.assertRaises(PeriodicStructureError):
            read_babel_structure(raw, "crystal", "poscar")
        record = read_babel_structure(raw, "crystal", "poscar", remove_periodicity=True)
        xyz = record.molecule.atoms[1]
        self.assertEqual((xyz.x, xyz.y, xyz.z), (3, 3, 4))
        cart = read_babel_structure(raw.replace(b"Direct", b"Cartesian"), "cell", "poscar", remove_periodicity=True)
        self.assertEqual(cart.molecule.atoms[1].z, 1)


@unittest.skipUnless(importlib.util.find_spec("openbabel"), "Open Babel is an optional desktop dependency")
class NativeBabelTests(unittest.TestCase):
    def test_smiles_and_inchi_generate_explicit_3d(self):
        for fmt, raw in (("smi", b"C[NH3+]"), ("inchi", b"InChI=1S/CH4/h1H4")):
            with self.subTest(fmt=fmt):
                record = read_babel_structure(raw, "structure", fmt)
                self.assertTrue(record.generated_3d)
                self.assertGreaterEqual(len(record.molecule.atoms), 5)
                self.assertEqual(record.molecule.charge, 1 if fmt == "smi" else 0)
                self.assertTrue(any(abs(a.z) > 0.1 for a in record.molecule.atoms))
                record.molecule.validate()
        with self.assertRaisesRegex(ValueError, 'multiple'):
            read_babel_structure(b"C ethane\nO water", "two", "smi")

    def test_mdl_dimension_flag_preserves_flat_3d(self):
        for fmt in ("mol", "sdf"):
            if fmt == "sdf":
                raw = MOL + b"$$$$\n"
            else:
                raw = MOL
            with self.subTest(fmt=fmt):
                self.assertTrue(read_babel_structure(raw, "drawing", fmt).generated_3d)
                fixed = read_babel_structure(raw.replace(b"2D", b"3D"), "cartesian", fmt)
                self.assertFalse(fixed.generated_3d)
                self.assertEqual(len(fixed.molecule.atoms), 2)
                self.assertEqual((fixed.molecule.atoms[1].x, fixed.molecule.atoms[1].z), (1.5, 0.0))

    def test_single_fragment_cdxml_wedge_reflects_in_3d(self):
        atoms = ((2, "0 0", 6), (3, "0 20", 9), (4, "20 0", 17),
                 (5, "0 -20", 35), (6, "-20 0", 53))
        nodes = "".join(f'<n id="{i}" p="{point}" Element="{z}"/>' for i, point, z in atoms)
        bonds = '<b id="10" B="2" E="3" Display="WedgeBegin"/>' + "".join(
            f'<b id="{i+10}" B="2" E="{i}"/>' for i in (4, 5, 6))
        fragment = f'<fragment id="1">{nodes}{bonds}</fragment>'
        raw = f'<CDXML><page>{fragment}</page></CDXML>'.encode()
        signs = []
        for style in (b"WedgeBegin", b"WedgedHashBegin"):
            record = read_babel_structure(raw.replace(b"WedgeBegin", style), "drawing", "cdxml")
            self.assertTrue(record.generated_3d)
            self.assertEqual(len(record.molecule.atoms), 5)
            first, *remaining = record.molecule.atoms[1:]
            a, b, c = [(at.x-first.x, at.y-first.y, at.z-first.z) for at in remaining]
            volume = sum(a[i] * (b[(i+1)%3] * c[(i+2)%3] - b[(i+2)%3] * c[(i+1)%3]) for i in range(3))
            self.assertGreater(abs(volume), 1)
            signs.append(math.copysign(1, volume))
        self.assertEqual(signs[0], -signs[1])
        with self.assertRaisesRegex(ValueError, 'single molecule'):
            read_babel_structure(raw.replace(b"</page>", fragment.encode() + b"</page>"), "two", "cdxml")

    def test_cml_dimension_preserves_cartesian_values(self):
        text = (b'<cml xmlns="http://www.xml-cml.org/schema"><molecule><atomArray>'
                b'<atom id="a1" elementType="C" x2="0" y2="0"/>'
                b'<atom id="a2" elementType="O" x2="1.5" y2="0"/></atomArray>'
                b'<bondArray><bond atomRefs2="a1 a2" order="1"/></bondArray></molecule></cml>')
        self.assertTrue(read_babel_structure(text, "drawing", "cml").generated_3d)
        xyz = text.replace(b"x2=", b'x3=').replace(b'y2=', b'z3="0" y3=')
        fixed = read_babel_structure(xyz, "model", "cml")
        self.assertFalse(fixed.generated_3d)
        self.assertEqual(fixed.molecule.atoms[1].x, 1.5)

    def test_cif_expands_symmetry_into_one_cartesian_cell(self):
        with self.assertRaises(PeriodicStructureError):
            read_babel_structure(CIF, "unit cell", "cif")
        record = read_babel_structure(CIF, "unit cell", "cif", remove_periodicity=True)
        self.assertTrue(record.removed_periodicity)
        self.assertEqual(len(record.molecule.atoms), 2)
        self.assertAlmostEqual(record.molecule.atoms[0].x, 0.5)
        self.assertAlmostEqual(record.molecule.atoms[1].x, 4.5)
        self.assertFalse(record.molecule.bonds)

    def test_pdb_and_mol2_keep_3d_atoms_and_recognise_unit_cells(self):
        pdb = (b"CRYST1    1.000    1.000    1.000  90.00  90.00  90.00 P 1           1\n"
               b"HETATM    1  C1  LIG A   1       1.000   2.000   0.000  1.00 20.00           C\n"
               b"HETATM    2  O1  LIG A   1       2.200   2.000   0.000  1.00 20.00           O\n"
               b"CONECT    1    2\nEND\n")
        mol2 = (b"@<TRIPOS>MOLECULE\nCO\n2 1 0 0 0\nSMALL\nNO_CHARGES\n"
                b"@<TRIPOS>ATOM\n1 C1 1.0 2.0 0.0 C.2\n2 O1 2.2 2.0 0.0 O.2\n"
                b"@<TRIPOS>BOND\n1 1 2 2\n")
        for fmt, plain, periodic in (("mol2", mol2, mol2 + b"@<TRIPOS>CRYSIN\n10 10 10 90 90 90 1 1\n"),
                                     ("pdb", pdb, pdb.replace(b"   1.000", b"  10.000", 3))):
            with self.subTest(fmt=fmt):
                record = read_babel_structure(plain, "model", fmt)
                self.assertEqual([a.element for a in record.molecule.atoms], ["C", "O"])
                self.assertFalse(record.generated_3d)
                self.assertFalse(record.removed_periodicity)
                self.assertAlmostEqual(record.molecule.atoms[1].x, 2.2)
                with self.assertRaises(PeriodicStructureError):
                    read_babel_structure(periodic, "crystal", fmt)
                detached = read_babel_structure(periodic, "finite", fmt, remove_periodicity=True)
                self.assertTrue(detached.removed_periodicity)
                self.assertEqual(detached.molecule.atoms, record.molecule.atoms)

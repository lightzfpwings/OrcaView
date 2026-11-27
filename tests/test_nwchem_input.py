import math
import unittest
from pathlib import Path

from orcaview.core.units import BOHR_IN_ANGSTROM
from orcaview.io.nwchem_input import read_nwchem_input
from orcaview.io.structure_record import PeriodicStructureError


def read(text, remove_periodicity=False):
    return read_nwchem_input(Path("test.nw"), text.encode(), remove_periodicity=remove_periodicity)


class NwchemGeometryTests(unittest.TestCase):
    def test_cartesian_units_atom_labels_and_electronic_state(self):
        text = ('title "molecule; geometry; # doublet"\ncharge -1; geometry named units nm noautoz\n'
                'O_ion 0 0 0\nH2 0 0 .1 mass 2 # isotope\nend\ndft; mult 2; end\n')
        result = read(text)
        self.assertEqual((result.molecule.charge, result.molecule.multiplicity), (-1, 2))
        self.assertEqual([a.element for a in result.molecule.atoms], ["O", "H"])
        self.assertAlmostEqual(result.molecule.atoms[1].z, 1)
        self.assertEqual(result.unit_source, "nwchem-units-nm")
        result = read("geometry units au; Xe 1D0 0 0; end; scf; triplet; end")
        self.assertEqual(result.source_unit, "bohr")
        self.assertEqual(result.molecule.atoms[0].x, BOHR_IN_ANGSTROM)
        self.assertEqual(result.molecule.multiplicity, 3)

    def test_triclinic_crystal_needs_confirmation_then_primitive_cartesians(self):
        text = ("geometry units angstrom; system crystal; lat_a 2 lat_b 2 lat_c 2; "
                "alpha 60 beta 60 gamma 60; end; He 0 1 0; H 0 0 1; end")
        with self.assertRaises(PeriodicStructureError):
            read(text)
        result = read(text, True)
        self.assertTrue(result.removed_periodicity)
        he, h = result.molecule.atoms
        self.assertAlmostEqual(he.x, 1.)
        self.assertAlmostEqual(he.y, math.sqrt(3))
        self.assertAlmostEqual(h.x, 1.)
        self.assertAlmostEqual(h.y, 1 / math.sqrt(3))
        self.assertAlmostEqual(h.z, math.sqrt(8 / 3))

    def test_ase_style_crystal_vectors_preserve_basis_and_cell_unit(self):
        text = ("geometry units angstrom; system crystal units bohr; lattice_vectors; "
                "0 2 0; -4 0 0; 0 0 8; end; He .5 .25 .125; end")
        with self.assertRaises(PeriodicStructureError):
            read(text)
        pos = read(text, True).molecule.atoms[0]
        self.assertAlmostEqual(pos.x, -BOHR_IN_ANGSTROM)
        self.assertAlmostEqual(pos.y, BOHR_IN_ANGSTROM)
        self.assertAlmostEqual(pos.z, BOHR_IN_ANGSTROM)

    def test_only_periodic_axes_are_fractional_for_surfaces_and_polymers(self):
        surface = ("geometry units pm; He .5 .25 300; system surface; lat_a 200; lat_b 400; "
                   "gamma 90; end; end")
        with self.assertRaises(PeriodicStructureError):
            read(surface)
        pos = read(surface, True).molecule.atoms[0]
        self.assertAlmostEqual(pos.x, 1.)
        self.assertAlmostEqual(pos.y, 1.)
        self.assertAlmostEqual(pos.z, 3.)
        polymer = "geometry; system polymer; lat_c 10; end; H 2 3 .75; end"
        pos = read(polymer, True).molecule.atoms[0]
        self.assertEqual((pos.x, pos.y, pos.z), (2., 3., 7.5))

    def test_simulation_cell_boundary_and_incomplete_geometries(self):
        xyz = "geometry; He 0 1 0; end; nwpw; simulation_cell; sc 20; boundary_conditions "
        with self.assertRaises(PeriodicStructureError):
            read(xyz + "periodic; end; end")
        self.assertTrue(read(xyz + "periodic; end; end", True).removed_periodicity)
        self.assertFalse(read(xyz + "aperiodic; end; end").removed_periodicity)
        with self.assertRaisesRegex(ValueError, 'Missing explicit NWChem cell parameters'):
            read("geometry; system crystal; lat_a 30; end; He 0 0 0; end", True)
        with self.assertRaisesRegex(ValueError, 'explicit'):
            read("geometry; zmatrix; H; H 1 1; end; end")
        with self.assertRaisesRegex(ValueError, 'Expand'):
            read("geometry; symmetry c2v; O 0 0 0; H 0 0 1; end")

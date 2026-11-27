import math
import tempfile
import unittest
from pathlib import Path

from orcaview.core.units import BOHR_IN_ANGSTROM
from orcaview.io.quantum_structure import read_quantum_structure
from orcaview.io.structure_record import PeriodicStructureError


def read(name, contents, **options):
    return read_quantum_structure(Path(name), contents.encode("utf-8"), **options)


class QuantumGeometryTests(unittest.TestCase):
    def test_gaussian_units_state_and_periodic_vectors(self):
        text = "%chk=sample.chk\n#p HF units=bohr\n\n0 1 in title\n\n1 2\n8  0 0 0 0\nH -1 1D0 0 0\n"
        result = read("input.GJF", text)
        self.assertEqual((result.molecule.charge, result.molecule.multiplicity), (1, 2))
        self.assertEqual(result.source_unit, "bohr")
        self.assertEqual(result.molecule.atoms[1].x, BOHR_IN_ANGSTROM)
        text += "Tv 5 0 0\n"
        with self.assertRaises(PeriodicStructureError):
            read("input.com", text)
        finite = read("input.com", text, remove_periodicity=True)
        self.assertTrue(finite.removed_periodicity)
        self.assertEqual(finite.molecule.atoms, result.molecule.atoms)
        with self.assertRaisesRegex(ValueError, 'coordinates'):
            read("input.gjf", "%chk=x.chk\n# geom=allcheck\n")

    def test_zmatrix_water_bohr_and_radians(self):
        text = ("# HF Units=(AU,Rad)\n\nwater\n\n0 1\nO1\nH1 O1 ROH\nH2 O1 ROH H1 a\n"
                "Variables:\nROH=1.8\na 1.82\n")
        record = read("water.gjf", text)
        self.assertEqual(record.source_unit, "bohr")
        o, h1, h2 = record.molecule.atoms
        r = 1.8 * BOHR_IN_ANGSTROM
        self.assertAlmostEqual(h1.z - o.z, r)
        self.assertAlmostEqual(h2.x - o.x, r * math.sin(1.82))
        self.assertAlmostEqual(h2.z - o.z, r * math.cos(1.82))

    def test_zmatrix_dummy_and_negative_torsion_keep_chirality(self):
        from orcaview.core.provenance import Provenance
        from orcaview.core.snapshots import GeometryRef, GeometrySnapshot
        from orcaview.editing.coordinates import CoordinateDefinition, measure

        text = ("#HF\n\nammonia\n\n0 1\nN\nX 1 1\nH1 1 r 2 110\n"
                "H2 1 r 2 110 3 d\nH3 1 r 2 110 3 -d 0\n\nr=1.03\nd=120\n")
        mol = read("ammonia.com", text).molecule
        self.assertEqual([a.element for a in mol.atoms], ["N", "H", "H", "H"])
        self.assertAlmostEqual(mol.atoms[2].y, -mol.atoms[3].y)
        self.assertLess(mol.atoms[2].y, 0)
        peroxide = ("# hf\n\nperoxide\n\n0 1\nH  \nO1 1 .98\nO2 2 1.46 1 95\n"
                    "H2 O2 .98 O1 95 1 -d 0\n\nd 65\n")
        mol = read("peroxide.gjf", peroxide).molecule
        ids = ("H1", "O1", "O2", "H2")
        snap = GeometrySnapshot(GeometryRef("test", 1), mol, ids, Provenance("fixture"))
        self.assertAlmostEqual(measure(snap, CoordinateDefinition(snap.ref, "dihedral", ids)), -65.)

    def test_zmatrix_reports_undefined_geometry(self):
        for rows, expected in (("O\nH 1 missing", 'defined variable'), ("O\nH 2 1", 'reference atom'),
                               ("O\nX 1 1\nH 1 2 2 180\nH 1 1 2 90 3 42", 'Collinear'),
                               ("O\nH 1 1\nH 1 1 2 181", 'bond angle'),
                               ("O\nH 1 1\nH 1 1 2 105\nH 1 1 2 90 3 45 1", 'two-angle')):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, expected):
                read("invalid.com", "# HF\n\nZ-matrix\n\n0 1\n" + rows + "\n")

    def test_orca_inputs_and_percent_coordinates(self):
        path = Path(__file__).resolve().parents[1] / "examples/native_methods/water-cpcm.inp"
        result = read_quantum_structure(path, path.read_bytes())
        self.assertEqual([a.element for a in result.molecule.atoms], ["O", "H", "H"])
        block = "%coords\n CTyp xyz\n Units Bohrs\n Charge -1\n Mult 1\n coords\n O(1) 0 0 0\n H 1 0 0\n end\nend\n"
        record = read("hydroxyl.inp", block)
        self.assertEqual(record.molecule.atoms[1].x, BOHR_IN_ANGSTROM)
        self.assertEqual(record.molecule.charge, -1)
        with self.assertRaisesRegex(ValueError, 'multiple'):
            read("duplicate.inp", "* xyz 0 1\nHe 0 0 0\n*\n* xyz 0 1\nHe 1 0 0\n*")

    def test_orca_external_xyz_keeps_evidence_on_both_sides_of_periodic_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "choice.inp"
            sidecar = path.with_name("unit cell.xyz")
            sidecar.write_text('1\nLattice="4 0 0 0 4 0 0 0 4" pbc="T T T"\nH 1 0 0\n')
            raw = b'! UHF\n* xyzfile 0 2 "unit cell.xyz"\n'
            with self.assertRaises(PeriodicStructureError) as err:
                read_quantum_structure(path, raw)
            record = read_quantum_structure(path, raw, remove_periodicity=True)
            self.assertTrue(record.removed_periodicity)
            self.assertEqual(record.molecule.multiplicity, 2)
            source, = record.auxiliary_sources
            self.assertEqual(source.sha256, err.exception.source.sha256)
            self.assertEqual(source.path_hint, err.exception.source.path_hint)
            self.assertEqual(source.path_hint, str(sidecar.resolve()))

    def test_molden_atom_units_and_cell(self):
        path = Path(__file__).resolve().parents[1] / "examples/m6_reference/hydrogen-open.molden"
        for filename in ("H.molden", "H.MOLDEN.INPUT"):
            result = read_quantum_structure(Path(filename), path.read_bytes())
            self.assertAlmostEqual(result.molecule.atoms[0].x, .4*BOHR_IN_ANGSTROM)
        periodic = "[Molden Format]\n[Atoms] Angs\nCl1 1 17 1 2 3\n[Cell]\n4 4 4 90 90 90\n"
        with self.assertRaises(PeriodicStructureError):
            read("crystal.molden", periodic)
        self.assertEqual(read("crystal.molden", periodic, remove_periodicity=True).molecule.atoms[0].element, "Cl")

    def test_formatted_checkpoint_xyz_lengths_and_periodicity(self):
        fchk = ("fixture\nsp RHF\nNumber of atoms        I  2\nCharge   I   -1\nMultiplicity       I   2\n"
                "Number of translation vectors    I   0\nAtomic numbers    I  N= 2\n  8 1\n"
                "Current cartesian coordinates   R  N= 6\n  0.0 0.0 0.0 1.0D+00 0.0\n  0.0\n")
        result = read("dist.fch", fchk)
        self.assertEqual(result.molecule.atoms[-1].x, BOHR_IN_ANGSTROM)
        self.assertEqual(result.molecule.charge, -1)
        with self.assertRaises(ValueError):
            read("truncated.fchk", fchk[:-7])
        periodic = fchk.replace("vectors    I   0", "vectors    I   3")
        with self.assertRaises(PeriodicStructureError):
            read("crystal.fchk", periodic)
        self.assertTrue(read("crystal.fchk", periodic, remove_periodicity=True).removed_periodicity)

    def test_wfn_wfx_and_mwfn_use_format_units(self):
        wfn = ("Test\nGAUSSIAN   1 MOL ORBITALS   1 PRIMITIVES    1 NUCLEI\n"
               " CL   1    (CENTRE  1)  1.00000000    0.00000000   -0.00000000  CHARGE =  7.0\n")
        record = read("cl.wfn", wfn)
        self.assertEqual(record.molecule.atoms[0].element, "Cl")
        self.assertEqual(record.molecule.atoms[0].x, BOHR_IN_ANGSTROM)
        self.assertEqual(read("cl.wfn", wfn.replace("GAUSSIAN", "GTO")).molecule, record.molecule)
        wfx = ("<Number of Nuclei>1</Number of Nuclei>\n<Atomic Numbers>17</Atomic Numbers>\n"
               "<Nuclear Cartesian Coordinates>1D0 0 0</Nuclear Cartesian Coordinates>\n"
               "<Net Charge>-1.0</Net Charge>\n<Electronic Spin Multiplicity>1</Electronic Spin Multiplicity>\n")
        self.assertEqual(read("cl.wfx", wfx).molecule.atoms, record.molecule.atoms)
        self.assertEqual(read("cl.wfx", wfx).molecule.charge, -1)
        with self.assertRaises(PeriodicStructureError):
            read("crystal.wfx", wfx + "<Number of Translation Vectors>3</Number of Translation Vectors>")
        mwfn = "Charge= -1.0\nNaelec= 4.0\nNbelec= 4.0\nNcenter= 1\n$Centers\n1 Cl 17 7.0 1.0 0.0 0.0\n"
        record = read("cl.mwfn", mwfn)
        self.assertEqual(record.molecule.atoms[0].x, 1.0)
        self.assertEqual(record.molecule.charge, -1)
        with self.assertRaises(PeriodicStructureError):
            read("crystal.mwfn", "Ndim= 1\ncellv1= 6.0 0 0\n" + mwfn)
        with self.assertRaisesRegex(ValueError, 'binary'):
            read_quantum_structure(Path("invalid.fchk"), b"\x00\x01")

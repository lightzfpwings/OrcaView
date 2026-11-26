"""Import a PDBx polymer without mixing copies, solvents or unresolved sites."""

import gzip
from importlib.util import find_spec
from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree

from orcaview.io import biopolymer_record as records
from orcaview.io.babel_structure import read_babel_structure


def pdbml(categories):
    root = ElementTree.Element("datablock", xmlns="http://pdbml.pdb.org/schema/pdbx-v50.xsd")
    for name, rows in categories:
        category = ElementTree.SubElement(root, name + "Category")
        for attributes, fields in rows:
            row = ElementTree.SubElement(category, name, attributes)
            for key, value in fields.items():
                child = ElementTree.SubElement(row, key)
                child.text = str(value) if value is not None else None
    return gzip.compress(ElementTree.tostring(root))


def site(entity, chain, seq, comp, name, element, x, *, alt=None, occupancy=1, model=1):
    return {}, {"label_entity_id": entity, "label_asym_id": chain, "label_seq_id": seq,
                "label_comp_id": comp, "label_atom_id": name, "type_symbol": element,
                "Cartn_x": x, "Cartn_y": 0, "Cartn_z": 0, "occupancy": occupancy,
                "label_alt_id": alt, "pdbx_PDB_model_num": model}


def component_bond(comp, a, b, order):
    return {"comp_id": comp, "atom_id_1": a, "atom_id_2": b}, {"value_order": order}


def bridge(symmetry):
    return {}, {"conn_type_id": "disulf", "ptnr1_label_asym_id": "A", "ptnr2_label_asym_id": "B",
                "ptnr1_label_seq_id": 2, "ptnr2_label_seq_id": 1, "ptnr1_label_comp_id": "CYS",
                "ptnr2_label_comp_id": "CYS", "ptnr1_label_atom_id": "SG", "ptnr2_label_atom_id": "SG",
                "ptnr1_symmetry": "1_555", "ptnr2_symmetry": symmetry}


def entry(symmetry="1_555"):
    return pdbml([
        ("atom_site", [
            site("1", "A", 1, "ALA", "C", "C", 2.1),
            site("1", "A", 1, "ALA", "O", "O", 1.1, alt="A", occupancy=.4),
            site("1", "A", 1, "ALA", "O", "O", .9, alt="B", occupancy=.6),
            site("1", "A", 2, "CYS", "N", "N", 3.4),
            site("1", "A", 2, "CYS", "SG", "S", 5),
            site("1", "B", 1, "CYS", "SG", "S", 7),
            site("2", "D", 1, "DA", "O3'", "O", 0),
            site("2", "D", 2, "DT", "P", "P", 1.60),
            site("2", "D", 2, "DT", "O3'", "O", 2.9),
            site("2", "D", 3, "DA", "P", "P", 13),
            site("3", "W", None, "HOH", "O", "O", 25),
            site("1", "A", 1, "ALA", "C", "C", 30, model=2),
        ]),
        ("chem_comp_bond", [component_bond("ALA", "C", "O", "doub"),
                            component_bond("CYS", "CA", "N", "sing"),
                            component_bond("DT", "P", "O3'", "sing")]),
        ("entry", [({"id": "1ABC"}, {})]),
        ("entity_poly", [({"entity_id": "1"}, {"type": "polypeptide(L)"}),
                         ({"entity_id": "2"}, {"type": "polydeoxyribonucleotide"})]),
        ("struct_conn", [bridge(symmetry)]),
    ])


class PdbRecordTests(unittest.TestCase):
    def test_backbone_roles_use_named_sites_even_for_incomplete_residues(self):
        for kind, expected in (("protein", "BSBSS"), ("dna", "BBBB")):
            with self.subTest(kind=kind), patch.object(records, "urlopen", return_value=BytesIO(entry())):
                record = records.load_pdb_record(kind, "1ABC")
                self.assertEqual(record.polymer_roles, expected)

    def test_protein_first_model_altloc_peptide_and_disulfide(self):
        with patch.object(records, "urlopen", return_value=BytesIO(entry())) as fetch:
            mol = records.load_pdb("protein", " PDB_00001abc ")
        request = fetch.call_args.args[0]
        self.assertEqual(request.full_url, "https://files.rcsb.org/download/pdb_00001abc.xml.gz")
        self.assertEqual([a.x for a in mol.atoms], [2.1, .9, 3.4, 5, 7])
        self.assertEqual([(b.a, b.b, b.order) for b in mol.bonds], [(0, 1, 2), (0, 2, 1), (3, 4, 1)])
        self.assertTrue(mol.bonds_explicit)
        self.assertEqual(mol.multiplicity, 2)
        mol.validate()
        with patch.object(records, "urlopen", return_value=BytesIO(entry("2_555"))):
            other = records.load_pdb("protein", "1abc")
        self.assertEqual(len(other.bonds), 2)

    def test_dna_excludes_protein_water_and_unresolved_chain_break(self):
        with patch.object(records, "urlopen", return_value=BytesIO(entry())):
            mol = records.load_pdb("dna", "1ABC")
        self.assertEqual([a.x for a in mol.atoms], [0, 1.6, 2.9, 13])
        self.assertEqual({(b.a, b.b) for b in mol.bonds}, {(0, 1), (1, 2)})
        self.assertIn("1ABC", mol.name)
        self.assertEqual(mol.multiplicity, 1)
        mol.validate()

    def test_errors_distinguish_wrong_entry_empty_polymer_and_connection(self):
        with patch.object(records, "urlopen") as fetch:
            with self.assertRaisesRegex(ValueError, "PDB ID"):
                records.load_pdb("protein", "../1ABC")
            fetch.assert_not_called()
        with patch.object(records, "urlopen", return_value=BytesIO(entry())):
            with self.assertRaisesRegex(ValueError, "does not match"):
                records.load_pdb("protein", "2ABC")
        only_rna = pdbml([("entry", [({"id": "1ABC"}, {})]),
                          ("entity_poly", [({"entity_id": "1"}, {"type": "polyribonucleotide"})]),
                          ("atom_site", [site("1", "R", 1, "A", "P", "P", 0)])])
        with patch.object(records, "urlopen", return_value=BytesIO(only_rna)):
            with self.assertRaisesRegex(ValueError, "No DNA coordinates"):
                records.load_pdb("dna", "1ABC")
        with patch.object(records, "urlopen", side_effect=HTTPError("", 404, "Not Found", {}, None)):
            with self.assertRaisesRegex(ValueError, "not found"):
                records.load_pdb("dna", "1ABC")
        with patch.object(records, "urlopen", side_effect=URLError("timed out")):
            with self.assertRaisesRegex(ValueError, "internet connection"):
                records.load_pdb("dna", "1ABC")

    def test_bounds_and_malformed_downloads(self):
        with patch.object(records, "_MAX_XML", 256), patch.object(records, "urlopen", return_value=BytesIO(entry())):
            with self.assertRaisesRegex(ValueError, "import limit"):
                records.load_pdb("protein", "1ABC")
        for raw in (b"error page", gzip.compress(b"<datablock>")):
            with self.subTest(raw=raw[:10]), patch.object(records, "urlopen", return_value=BytesIO(raw)):
                with self.assertRaisesRegex(ValueError, "incomplete or invalid"):
                    records.load_pdb("protein", "1ABC")

    @unittest.skipUnless(find_spec("openbabel"), "requires the native PDB reader")
    def test_local_pdb_side_atoms_mixed_ligands_gaps_and_insertion_codes(self):
        def site_line(serial, atom_id, residue, chain, seq, ins, x, element, record="ATOM"):
            return (f"{record:6}{serial:5} {atom_id:4} {residue:>3} {chain}{seq:4}{ins:1}   "
                    f"{x:8.3f}{0.:8.3f}{0.:8.3f}{1.:6.2f}{0.:6.2f}          {element:>2}")
        lines = [
            "CRYST1   65.000   65.000   65.000  90.00  90.00  90.00 P 1",
            site_line(1, "C", "GLY", "A", 10, "A", 1., "C"),
            site_line(2, "N", "ALA", "A", 10, "B", 2.3, "N"),
            site_line(3, "C", "ALA", "A", 10, "B", 4., "C"),
            site_line(4, "N", "GLY", "A", 14, "", 5.3, "N"),
            site_line(5, "CB", "ALA", "B", 1, "", 9., "C"),
            site_line(6, "C5*", "DA", "D", 1, "", 11., "C"),
            site_line(7, "C2*", "DA", "D", 1, "", 13., "C"),
            site_line(8, "CA", "LIG", "X", 4, "", 15., "Ca", "HETATM"),
            site_line(9, "N", "GLY", "X", 6, "", 32., "N", "HETATM"),
            site_line(10, "C", "GLY", "F", 2, "", 40., "C"),
            "TER",
            site_line(11, "N", "GLY", "F", 3, "", 41.3, "N"),
            site_line(12, "C", "GLY", "G", 2, "", 50., "C"),
            "CONECT   11   12",
            "END",
        ]
        protein = read_babel_structure("\n".join(lines).encode(), "mixed", "pdb", remove_periodicity=True)
        self.assertEqual(protein.polymer_roles, "BBBBSBS..BBB")
        self.assertEqual(protein.backbone_links, ((0, 1),))
        self.assertEqual(protein.molecule.bonds, ())
        self.assertFalse(protein.molecule.bonds_explicit)
        finite = read_babel_structure("\n".join(lines[1:]).encode(), "mixed", "pdb")
        self.assertEqual(finite.backbone_links, protein.backbone_links)
        edges = {tuple(sorted((bond.a, bond.b))) for bond in finite.molecule.bonds}
        self.assertTrue({(0, 1), (2, 3), (10, 11)} <= edges)
        self.assertTrue(finite.molecule.bonds_explicit)
        isolated = read_babel_structure((lines[3] + "\nEND").encode(), "one", "pdb")
        self.assertEqual(isolated.polymer_roles, "B")
        self.assertEqual(isolated.backbone_links, ())
        self.assertFalse(isolated.molecule.bonds_explicit)

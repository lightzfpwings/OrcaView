"""Backbone annotations across structure readers, edit history and project files."""

import json
import unittest
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory

from orcaview.application.polymer_sketch import sketch_annotations
from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.application.structure_import import read_structure_file
from orcaview.core.polymer_backbone import topology_roles
from orcaview.editing import DeleteAtoms, EditorService, GenerateBiopolymer, GeometryEditCommand, ReorderAtoms, SetBond
from orcaview.io.biopolymer_sequence import build_sequence_record


_PEPTIDE_AND_WATER = """\
ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA  ALA A   1       1.450   0.000   0.100  1.00 20.00           C
ATOM      3  C   ALA A   1       2.000   1.420   0.000  1.00 20.00           C
ATOM      4  O   ALA A   1       1.300   2.390   0.000  1.00 20.00           O
ATOM      5  CB  ALA A   1       2.000  -0.780   1.270  1.00 20.00           C
ATOM      6  N   GLY A   2       3.300   1.550   0.000  1.00 20.00           N
ATOM      7  CA  GLY A   2       3.980   2.800   0.170  1.00 20.00           C
ATOM      8  C   GLY A   2       5.480   2.690   0.120  1.00 20.00           C
ATOM      9  O   GLY A   2       6.100   1.660   0.100  1.00 20.00           O
TER
HETATM   10  O   HOH W   1      12.800   8.600   2.300  1.00 20.00           O
END
"""


def apply_edit(editor, operation):
    command = GeometryEditCommand(editor.expected, operation)
    return editor.commit(editor.preview(command)).snapshot


def sketch_roles(document, snapshot):
    return sketch_annotations(document, snapshot)[0]


def generate(kind, sequence):
    record = build_sequence_record(kind, sequence)
    session = Session()
    editor = EditorService(session.document)
    apply_edit(editor, GenerateBiopolymer(record.molecule, kind, "sequence", sequence, record.polymer_roles))
    return session, editor, record


@unittest.skipUnless(find_spec("openbabel"), "requires the native structure readers")
class BackboneProjectTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def assert_full_input(self, session, molecule):
        lines = session.input_text().splitlines()
        start = lines.index(f"* xyz {molecule.charge} {molecule.multiplicity}") + 1
        rows = [line.split() for line in lines[start:lines.index("*", start)]]
        self.assertEqual(len(rows), len(molecule.atoms))
        for (element, *xyz), atom in zip(rows, molecule.atoms):
            self.assertEqual(element, atom.element)
            self.assertEqual(xyz, [f"{value:.8f}" for value in (atom.x, atom.y, atom.z)])

    def assert_project_roundtrip(self, session, original, roles):
        head = session.document.head
        self.assertEqual(sketch_roles(session.document, head), roles)
        self.assert_full_input(session, original)
        path = self.directory / "backbone.oview.json"
        save_project(session, path)
        reopened = load_project(path)
        saved = reopened.document.head
        self.assertEqual(saved.atom_ids, head.atom_ids)
        self.assertEqual(saved.molecule, original)
        self.assertEqual(sketch_annotations(reopened.document, saved), sketch_annotations(session.document, head))
        self.assertEqual(reopened.input_text(), session.input_text())
        self.assert_full_input(reopened, original)

    def test_generated_dna_preserves_bases_hydrogens_and_coordinates(self):
        session, _, record = generate("dna", "AC")
        roles = record.polymer_roles
        self.assertEqual(roles.count("B"), 24)
        self.assertTrue(any(role == "S" and atom.element == "N" for atom, role in zip(record.molecule.atoms, roles)))
        self.assertTrue(any(role == "S" and atom.element == "H" for atom, role in zip(record.molecule.atoms, roles)))
        self.assert_project_roundtrip(session, record.molecule, roles)

    def test_local_pdb_preserves_named_backbone_and_independent_water(self):
        path = self.directory / "peptide.pdb"
        path.write_text(_PEPTIDE_AND_WATER, encoding="ascii")
        opened = read_structure_file(path)
        session = opened.session(Session().calculation)
        self.assert_project_roundtrip(session, opened.record.molecule, "BBBSSBBBS.")
        doc = session.document
        roles, links = sketch_annotations(doc, doc.head)
        self.assertEqual(links, ((0, 1), (1, 2), (2, 5), (5, 6), (6, 7)))
        editor = EditorService(doc)
        ids = doc.head.atom_ids
        apply_edit(editor, SetBond(ids[2], ids[5], 0))
        self.assertEqual(sketch_annotations(doc, doc.head)[1], tuple(pair for pair in links if pair != (2, 5)))
        editor.undo()
        self.assertEqual(sketch_annotations(doc, doc.head), (roles, links))
        apply_edit(editor, ReorderAtoms(ids[::-1]))
        last = len(ids) - 1
        self.assertEqual(sketch_annotations(doc, doc.head),
                         (roles[::-1], tuple(sorted((last - b, last - a) for a, b in links))))

    def test_deleting_middle_backbone_atom_then_undo_and_redo_follows_atom_ids(self):
        session, editor, record = generate("protein", "A")
        doc = session.document
        before = doc.head
        roles = record.polymer_roles
        role_by_id = dict(zip(before.atom_ids, roles))
        alpha_index = next(i for i, atom in enumerate(before.molecule.atoms) if roles[i] == "B" and atom.element == "C")
        removed_id = before.atom_ids[alpha_index]
        after = apply_edit(editor, DeleteAtoms((removed_id,)))
        self.assertNotIn(removed_id, after.atom_ids)
        expected = "".join(role_by_id[i] for i in after.atom_ids)
        self.assertEqual(expected.count("B"), 2)
        self.assertEqual(sketch_roles(doc, after), expected)
        undone = editor.undo().snapshot
        self.assertEqual(undone.atom_ids, before.atom_ids)
        self.assertEqual(sketch_roles(doc, undone), roles)
        redone = editor.redo().snapshot
        self.assertEqual(redone.atom_ids, after.atom_ids)
        self.assert_project_roundtrip(session, redone.molecule, expected)

    @unittest.skipUnless(find_spec("PySide6"), "requires Qt MIME data")
    def test_copy_single_residue_to_another_project_includes_the_hidden_atoms(self):
        from orcaview.gui.fragment_clipboard import copy_fragment, read_fragment

        source, _, record = generate("protein", "A")
        head = source.document.head
        roles = sketch_roles(source.document, head)
        self.assertFalse(topology_roles(record.molecule))
        selected = roles.index("B")
        mime, count = copy_fragment(head, (selected,), roles)
        self.assertEqual(count, len(record.molecule.atoms))
        fragment = read_fragment(mime)
        self.assertEqual(fragment.atoms, record.molecule.atoms)
        self.assertEqual(fragment.bonds, record.molecule.bonds)
        self.assertEqual(fragment.polymer_roles, roles)
        target = Session()
        water = target.document.head
        pasted = apply_edit(EditorService(target.document), fragment)
        offset = len(water.atom_ids)
        self.assertEqual(pasted.atom_ids[:offset], water.atom_ids)
        self.assertTrue(set(head.atom_ids).isdisjoint(pasted.atom_ids[offset:]))
        self.assertEqual([a.element for a in pasted.molecule.atoms[offset:]], [a.element for a in fragment.atoms])
        self.assert_project_roundtrip(target, pasted.molecule, "." * offset + roles)

    def test_legacy_generated_single_residue_uses_stored_polymer_kind(self):
        session, _, record = generate("protein", "G")
        path = self.directory / "a67.oview.json"
        save_project(session, path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["software_version"] = "0.1.0a67"
        last = payload["document"]["snapshots"][-1]["provenance"]
        last["parameters"] = [p for p in last["parameters"] if p[0] not in ("polymer_roles", "backbone_links")]
        path.write_text(json.dumps(payload), encoding="utf-8")
        restored = load_project(path)
        head = restored.document.head
        self.assertFalse(topology_roles(head.molecule))
        self.assertEqual(head.atom_ids, session.document.head.atom_ids)
        self.assert_project_roundtrip(restored, record.molecule, record.polymer_roles)

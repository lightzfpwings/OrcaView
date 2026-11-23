"""Exercise the separate drawing and calculation geometries across revision boundaries."""

import json
from pathlib import Path
import tempfile
import unittest

from orcaview.application.document import MoleculeDocument, StaleRevisionError
from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.geometry import display_bonds
from orcaview.core.models import Atom, CalculationSpec, Molecule
from orcaview.core.provenance import Provenance
from orcaview.core.results import ResultDataset
from orcaview.editing import (
    AddHydrogen, AttachAtom, DeleteAtoms, EditorService, GeometryEditCommand, InsertRing,
    MoveAtom, MoveSketchAtom, OptimizeCoordinates, ReorderAtoms, SetSketchLayout,
)
from orcaview.orca.input import InputSnapshot


class SketchRevisionTests(unittest.TestCase):
    def setUp(self):
        molecule = Molecule("water", (Atom("O", 0., 0., 1.), Atom("H", .8, .2, 1.5),
                                      Atom("H", -.8, .2, 1.5)))
        self.doc = MoleculeDocument.from_molecule(molecule, source_unit="bohr")
        self.editor = EditorService(self.doc)
        self.root = self.doc.head
        self.oxygen, self.h1, self.h2 = self.root.atom_ids
        self.xy = ((8., 4.), (17., 6.), (-2., 6.))
        self.xyz = ((1., 1., 1.), (1.1, 1.2, 1.9), (1.3, 1.9, .9))

    def commit(self, operation):
        return self.editor.commit(self.editor.preview(GeometryEditCommand(self.editor.expected, operation))).snapshot

    def test_two_d_keeps_scientific_input_implicit_topology_and_bound_result(self):
        ref = self.doc.add_frame(self.root.ref, "result", self.root.molecule, self.root.atom_ids,
                                 Provenance("calculation")).ref
        energy = ResultDataset("energy", ref, Provenance("calculation"), "float64", (), "Eh", (-75.,))
        self.doc.add_dataset(energy)
        before = InputSnapshot(self.root, CalculationSpec())
        cleaned = self.commit(SetSketchLayout(self.xy))
        after = InputSnapshot(cleaned, CalculationSpec())
        self.assertEqual(before.input_bytes, after.input_bytes)
        self.assertEqual(before.content_digest, after.content_digest)
        self.assertEqual(self.root.content_hash, cleaned.content_hash)
        self.assertEqual(cleaned.source_unit, self.root.source_unit)
        self.assertEqual(cleaned.molecule, self.root.molecule)
        self.assertEqual(self.doc.resolve(self.doc.dataset(energy.dataset_id).geometry).molecule, cleaned.molecule)
        drawing = cleaned.sketch_molecule()
        self.assertEqual(tuple((a.x, a.y) for a in drawing.atoms), self.xy)
        self.assertEqual(display_bonds(drawing), display_bonds(self.root.molecule))
        self.assertEqual(self.editor.undo().snapshot.sketch_xy, None)
        self.assertEqual(self.editor.redo().snapshot.sketch_xy, self.xy)

    def test_first_three_d_freezes_current_drawing_and_later_operations_are_independent(self):
        optimized = self.commit(OptimizeCoordinates("UFF", self.xyz))
        self.assertEqual(optimized.sketch_xy, tuple((a.x, a.y) for a in self.root.molecule.atoms))
        self.assertEqual(optimized.coordinates(), self.xyz)
        cleaned = self.commit(SetSketchLayout(self.xy))
        self.assertEqual(cleaned.molecule, optimized.molecule)
        optimized_again = self.commit(OptimizeCoordinates("MMFF94", self.root.coordinates()))
        self.assertEqual(optimized_again.sketch_xy, self.xy)
        moved = self.commit(MoveSketchAtom(self.h1, 3., -9.))
        self.assertEqual(moved.molecule, optimized_again.molecule)
        self.assertEqual(moved.sketch_xy[1], (3., -9.))
        recentered = self.commit(MoveAtom(self.h1, 10., 20., 30.))
        self.assertEqual(recentered.sketch_xy, moved.sketch_xy)
        self.assertEqual(self.editor.undo().snapshot.molecule, moved.molecule)
        self.assertEqual(self.editor.undo().snapshot.sketch_xy, self.xy)
        self.assertEqual(self.editor.undo().snapshot.coordinates(), self.xyz)
        self.assertEqual(self.editor.redo().snapshot.sketch_xy, self.xy)

    def test_drawing_positions_follow_atom_ids_across_topology_changes(self):
        self.commit(SetSketchLayout(self.xy))
        attached = self.commit(AttachAtom(self.oxygen, Atom("C", 1.5, -0.5, 1.), 1))
        carbon = attached.atom_ids[-1]
        self.assertEqual(attached.sketch_xy[-1], (9.5, 3.5))
        ring = self.commit(InsertRing(6, True, "XY", anchor_id=carbon))
        self.assertEqual(ring.sketch_xy[:4], attached.sketch_xy)
        self.assertEqual(len(set(ring.sketch_xy[4:])), 6)
        hydrogenated = self.commit(AddHydrogen(carbon))
        self.assertEqual(hydrogenated.sketch_xy[:-1], ring.sketch_xy)
        reordered = self.commit(ReorderAtoms(hydrogenated.atom_ids[::-1]))
        self.assertEqual(reordered.sketch_xy, hydrogenated.sketch_xy[::-1])
        deleted = self.commit(DeleteAtoms((self.h2,)))
        self.assertEqual(dict(zip(deleted.atom_ids, deleted.sketch_xy))[self.oxygen], self.xy[0])
        self.assertIsNone(self.commit(DeleteAtoms(deleted.atom_ids)).sketch_xy)
        self.assertEqual(self.editor.undo().snapshot.sketch_xy, deleted.sketch_xy)

    def test_old_projects_keep_their_schema_and_new_projects_restore_and_validate_layout_history(self):
        session = Session.from_document(self.doc, CalculationSpec(), "")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "drawing.json"
            save_project(session, path)
            old = json.loads(path.read_text())
            self.assertEqual(old["schema_version"], 2)
            self.assertNotIn("sketch_xy", old["document"]["snapshots"][0])
            self.assertEqual(load_project(path).document.head, self.root)
            self.commit(SetSketchLayout(self.xy))
            self.editor.undo()
            self.editor.redo()
            save_project(session, path)
            self.assertEqual(load_project(path).document.records(), self.doc.records())
            payload = json.loads(path.read_text())
            self.assertEqual(payload["schema_version"], 11)
            for bad in ([[4, 4]], [[1, 2], [1, 2], [1, True]], [[1, 2], [3, 4], [5, 6]]):
                payload["document"]["snapshots"][-1]["sketch_xy"] = bad
                path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    load_project(path)

    def test_stale_or_malformed_layout_never_changes_the_head(self):
        with self.assertRaises(ValueError):
            self.commit(SetSketchLayout(((0., 0.),)))
        with self.assertRaises(ValueError):
            SetSketchLayout(((0., float("nan")),))
        with self.assertRaises(ValueError):
            OptimizeCoordinates("gen2D", self.xyz)
        obsolete = GeometryEditCommand(self.root.ref, SetSketchLayout(self.xy))
        head = self.commit(MoveAtom(self.oxygen, 1., 2., 3.))
        with self.assertRaises(StaleRevisionError):
            self.editor.preview(obsolete)
        self.assertEqual(self.doc.head, head)

"""M2 transactions on real M1 history, identity, persistence and input guards."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from orcaview.application.document import MoleculeDocument, StaleRevisionError
from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, CalculationSpec, Molecule
from orcaview.core.provenance import Provenance
from orcaview.core.results import DatasetAxis, ResultDataset
from orcaview.core.snapshots import SelectionContext
from orcaview.editing import (
    AddAtoms, CoordinateDefinition, DeleteAtoms, EditorService, EditStateError,
    GeometryEditCommand, InsertRing, ReorderAtoms, ReplaceElement, SetDistance,
    SetElectronicState, measure,
)
from orcaview.io.xyz import parse_xyz, write_xyz
from orcaview.orca.input import render_input


class EditorServiceTests(unittest.TestCase):
    def setUp(self):
        self.doc = MoleculeDocument.from_molecule(Molecule(
            "water cation", (Atom("O", 0, 0, 0), Atom("H", 1, 0, 0),
                             Atom("H", 0, 1, 0)),
            (Bond(0, 1), Bond(0, 2)), charge=1, multiplicity=2),
            source_unit="bohr")
        self.root = self.doc.head
        self.o, self.h1, self.h2 = self.root.atom_ids
        selection = SelectionContext(self.root.ref, (self.h2, self.o, self.h1),
                                     "ordered-coordinate")
        self.editor = EditorService(self.doc, selection)

    def preview(self, operation, editor=None):
        editor = self.editor if editor is None else editor
        return editor.preview(GeometryEditCommand(editor.expected, operation))

    def commit(self, operation, editor=None):
        editor = self.editor if editor is None else editor
        return editor.commit(self.preview(operation, editor))

    def assert_same_state(self, actual, target):
        self.assertEqual(actual.molecule, target.molecule)
        self.assertEqual(actual.atom_ids, target.atom_ids)
        self.assertEqual(actual.source_unit, target.source_unit)
        self.assertEqual(actual.content_hash, target.content_hash)

    def test_preview_cancel_does_not_publish_or_allocate_atom_ids(self):
        before = self.doc.records()
        with patch("orcaview.application.document.new_id",
                   side_effect=AssertionError("preview allocated a document identity")):
            preview = self.preview(AddAtoms((Atom("He", 2, 0, 0),)))
            self.assertEqual(preview.mapping.target_ids, self.root.atom_ids + (None,))
            self.assertEqual(preview.mapping.added_indices, (3,))
            self.assertEqual(self.doc.records(), before)
            self.editor.cancel(preview)
        self.assertIsNone(self.editor.pending)
        self.assertEqual(self.doc.records(), before)
        self.assertEqual(self.editor.undo_entries, ())
        self.assertEqual(self.editor.redo_entries, ())
        self.assertEqual(self.editor.selection.geometry, self.root.ref)

    def test_add_commit_assigns_new_identity_and_keeps_bonds_and_state(self):
        result = self.commit(AddAtoms((Atom("He", 2, 0, 0), Atom("Ne", 3, 0, 0))))
        snapshot = result.snapshot
        self.assertEqual(snapshot.atom_ids[:3], self.root.atom_ids)
        self.assertEqual(len(set(snapshot.atom_ids)), 5)
        self.assertTrue(set(snapshot.atom_ids[3:]).isdisjoint(self.root.atom_ids))
        self.assertEqual(snapshot.molecule.bonds, self.root.molecule.bonds)
        self.assertEqual((snapshot.molecule.charge, snapshot.molecule.multiplicity), (1, 2))
        self.assertEqual(result.mapping.source_to_target, (0, 1, 2))
        self.assertEqual(result.mapping.target_to_source, (0, 1, 2, None, None))
        self.assertEqual(result.mapping.added_indices, (3, 4))
        self.assertEqual(snapshot.provenance.producer, "orcaview.editing")
        self.assertEqual(snapshot.parent, self.root.ref)
        self.assertEqual(snapshot.source_unit, "angstrom")

    def test_delete_all_and_rebuild_preserve_selection_history_and_identity(self):
        prior_selection = self.editor.selection
        cleared = self.commit(DeleteAtoms(self.root.atom_ids))
        self.assertEqual(cleared.snapshot.molecule.atoms, ())
        self.assertEqual(cleared.snapshot.molecule.bonds, ())
        self.assertTrue(cleared.snapshot.molecule.bonds_explicit)
        self.assertEqual(cleared.mapping.removed_ids, self.root.atom_ids)
        self.assertEqual(cleared.selection.atom_ids, ())
        self.assertIsNone(cleared.electronic_state_error)
        restored = self.editor.undo()
        self.assert_same_state(restored.snapshot, self.root)
        self.assertEqual(restored.selection.atom_ids, prior_selection.atom_ids)
        self.assert_same_state(self.editor.redo().snapshot, cleared.snapshot)
        fresh = self.commit(AddAtoms((self.root.molecule.atoms[0],))).snapshot
        self.assertEqual(len(fresh.atom_ids), 1)
        self.assertNotIn(fresh.atom_ids[0], self.root.atom_ids)
        self.assert_same_state(self.editor.undo().snapshot, cleared.snapshot)
        ring = self.commit(InsertRing(6, True, "XY", (0., 0., 0.))).snapshot
        self.assertEqual(len(ring.molecule.bonds), 6)
        self.assertTrue(set(ring.atom_ids).isdisjoint(self.root.atom_ids))

    def test_empty_head_roundtrip_keeps_old_frames_but_cannot_generate_results(self):
        frame = self.doc.add_frame(self.root.ref, "source", self.root.molecule,
                                   self.root.atom_ids, Provenance("source-frame"))
        value = ResultDataset("energy", frame.ref, Provenance("calculation"), "float64", (), "Eh", (-75.,))
        self.doc.add_dataset(value)
        empty = self.commit(DeleteAtoms(self.root.atom_ids)).snapshot
        session = Session.from_document(self.doc, CalculationSpec(), "")
        with self.assertRaisesRegex(ValueError, "at least one atom"):
            session.input_text()
        with self.assertRaisesRegex(ValueError, "at least one atom"):
            write_xyz(empty.molecule)
        with self.assertRaises(ValueError):
            parse_xyz("0\nempty\n")
        with self.assertRaisesRegex(ValueError, "at least one atom"):
            self.doc.add_frame(empty.ref, "calculation", empty.molecule, (), Provenance("source-frame"))
        with self.assertRaisesRegex(ValueError, "at least one atom"):
            self.doc.add_dataset(replace(value, geometry=empty.ref))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "design.oview.json"
            save_project(session, path)
            self.assertEqual(load_project(path).document.records(), self.doc.records())
            payload = json.loads(path.read_text())
            self.assertEqual(payload["schema_version"], 10)
            payload["schema_version"] = 9
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "at least one atom"):
                load_project(path)
            self.editor.undo()
            save_project(session, path)
            self.assertEqual(json.loads(path.read_text())["schema_version"], 10)
            self.assertEqual(load_project(path).document.records(), self.doc.records())

    def test_delete_remaps_explicit_bonds_and_filters_selection(self):
        result = self.commit(DeleteAtoms((self.h1,)))
        self.assertEqual(result.snapshot.atom_ids, (self.o, self.h2))
        self.assertEqual(result.snapshot.molecule.bonds, (Bond(0, 1),))
        self.assertEqual(result.selection.atom_ids, (self.h2, self.o))
        self.assertEqual(result.mapping.source_to_target, (0, None, 1))
        self.assertEqual(result.mapping.target_to_source, (0, 2))
        self.assertEqual(result.mapping.removed_ids, (self.h1,))
        self.assertIsNotNone(result.electronic_state_error)
        self.assertEqual(result.snapshot.molecule.multiplicity, 2)
        with self.assertRaises(ValueError):
            render_input(result.snapshot.molecule, CalculationSpec())
        undone = self.editor.undo()
        self.assert_same_state(undone.snapshot, self.root)
        self.assertEqual(undone.selection.atom_ids, (self.h2, self.o, self.h1))

    def test_reorder_maps_both_directions_and_preserves_identity_on_replace(self):
        order = (self.h2, self.o, self.h1)
        result = self.commit(ReorderAtoms(order))
        self.assertEqual(result.mapping.source_to_target, (1, 2, 0))
        self.assertEqual(result.mapping.target_to_source, (2, 0, 1))
        self.assertEqual(result.snapshot.molecule.bonds, (Bond(1, 2), Bond(1, 0)))
        replaced = self.commit(ReplaceElement(self.h1, "F"))
        self.assertEqual(replaced.snapshot.atom_ids, order)
        self.assertEqual(replaced.snapshot.molecule.atoms[2].element, "F")
        self.assertEqual(replaced.snapshot.molecule.atoms[2].x, 1)
        self.assertEqual(replaced.snapshot.molecule.bonds, result.snapshot.molecule.bonds)

    def test_incompatible_electronic_state_is_flagged_until_explicitly_fixed(self):
        preview = self.preview(SetElectronicState(0, 2))
        self.assertIsNotNone(preview.electronic_state_error)
        result = self.editor.commit(preview)
        self.assertIsNotNone(result.electronic_state_error)
        with self.assertRaises(ValueError):
            render_input(self.doc.head.molecule, CalculationSpec())
        fixed = self.commit(SetElectronicState(0, 1))
        self.assertIsNone(fixed.electronic_state_error)
        self.assertIn("* xyz 0 1", render_input(fixed.snapshot.molecule, CalculationSpec()))

    def test_multiple_undo_redo_restore_full_states_and_saved_selections(self):
        added = self.commit(AddAtoms((Atom("He", 2, 0, 0),)))
        he = added.snapshot.atom_ids[-1]
        self.editor.set_selection(SelectionContext(added.snapshot.ref, (he, self.h2, self.o), "atom"))
        self.commit(DeleteAtoms((self.h2,)))
        self.commit(ReorderAtoms(self.doc.head.atom_ids[::-1]))
        self.commit(SetElectronicState(-1, 1))
        entries = self.editor.undo_entries
        for entry in reversed(entries):
            previous = self.doc.head
            result = self.editor.undo()
            self.assert_same_state(result.snapshot, entry.before)
            self.assertEqual(result.snapshot.parent, previous.ref)
            self.assertNotEqual(result.snapshot.ref, entry.before.ref)
            self.assertEqual(result.selection.atom_ids, entry.selection_before.atom_ids)
            self.assertEqual(result.selection.mode, entry.selection_before.mode)
            self.assertEqual(result.selection.geometry, result.snapshot.ref)
        self.assertEqual(self.doc.head.source_unit, "bohr")
        self.assertFalse(self.editor.can_undo)
        self.assertTrue(self.editor.can_redo)
        for entry in entries:
            result = self.editor.redo()
            self.assert_same_state(result.snapshot, entry.after)
            self.assertEqual(result.selection.atom_ids, entry.selection_after.atom_ids)
            self.assertEqual(result.selection.mode, entry.selection_after.mode)
        self.assertFalse(self.editor.can_redo)
        for entry in entries:
            self.assertEqual(self.doc.resolve(entry.before.ref), entry.before)
            self.assertEqual(self.doc.resolve(entry.after.ref), entry.after)

    def test_redo_survives_canceled_invalid_and_failed_commits_only_success_clears(self):
        self.commit(ReplaceElement(self.h1, "F"))
        self.editor.undo()
        redo = self.editor.redo_entries
        preview = self.preview(AddAtoms((Atom("He", 2, 0, 0),)))
        self.assertEqual(self.editor.redo_entries, redo)
        self.editor.cancel(preview)
        with self.assertRaises(ValueError):
            self.preview(DeleteAtoms(("unknown",)))
        self.assertEqual(self.editor.redo_entries, redo)
        preview = self.preview(ReplaceElement(self.o, "S"))
        with patch.object(self.doc, "publish_revision", side_effect=ValueError("publication failed")):
            with self.assertRaises(ValueError):
                self.editor.commit(preview)
        self.assertIs(self.editor.pending, preview)
        self.assertEqual(self.editor.redo_entries, redo)
        self.editor.commit(preview)
        self.assertEqual(self.editor.redo_entries, ())

    def test_foreign_forged_superseded_canceled_and_reused_previews_fail(self):
        first = self.preview(ReplaceElement(self.o, "S"))
        foreign = EditorService(self.doc)
        with self.assertRaises(EditStateError):
            foreign.commit(first)
        with self.assertRaises(EditStateError):
            self.editor.commit(replace(first, molecule=replace(first.molecule, name="forged")))
        current = self.preview(ReplaceElement(self.h1, "F"))
        with self.assertRaises(EditStateError):
            self.editor.commit(first)
        self.editor.cancel(current)
        with self.assertRaises(EditStateError):
            self.editor.commit(current)
        current = self.preview(ReplaceElement(self.o, "S"))
        self.editor.commit(current)
        records = self.doc.records()
        with self.assertRaises(EditStateError):
            self.editor.commit(current)
        self.assertEqual(self.doc.records(), records)

    def test_stale_commit_cannot_overwrite_external_head_and_reset_is_explicit(self):
        preview = self.preview(ReplaceElement(self.o, "S"))
        other = EditorService(self.doc)
        external = self.commit(DeleteAtoms((self.h2,)), other).snapshot
        records = self.doc.records()
        with self.assertRaises(StaleRevisionError):
            self.editor.commit(preview)
        self.assertIs(self.editor.pending, preview)
        self.assertEqual(self.doc.records(), records)
        self.editor.cancel(preview)
        with self.assertRaises(StaleRevisionError):
            self.preview(ReplaceElement(self.o, "S"))
        selection = self.editor.reset_to_head()
        self.assertEqual(selection.atom_ids, (self.o, self.h1))
        self.assertEqual(selection.geometry, external.ref)
        self.assertEqual(self.editor.undo_entries, ())
        self.assertEqual(self.editor.redo_entries, ())
        self.commit(ReplaceElement(self.o, "S"))

    def test_stale_undo_and_redo_do_not_move_stacks(self):
        for want_redo in (False, True):
            with self.subTest(redo=want_redo):
                doc = MoleculeDocument.from_molecule(self.root.molecule)
                editor = EditorService(doc)
                atom_id = doc.head.atom_ids[0]
                self.commit(ReplaceElement(atom_id, "S"), editor)
                if want_redo:
                    editor.undo()
                undo, redo = editor.undo_entries, editor.redo_entries
                head = doc.head
                doc.publish_revision(head.ref, replace(head.molecule, name="external"), head.atom_ids)
                records = doc.records()
                with self.assertRaises(StaleRevisionError):
                    editor.redo() if want_redo else editor.undo()
                self.assertFalse(editor.can_undo)
                self.assertFalse(editor.can_redo)
                self.assertEqual((editor.undo_entries, editor.redo_entries), (undo, redo))
                self.assertEqual(doc.records(), records)
                editor.reset_to_head()
                self.assertEqual(editor.undo_entries, ())
                self.assertEqual(editor.redo_entries, ())

    def test_two_editors_racing_commit_have_one_winner_and_one_history_entry(self):
        other = EditorService(self.doc)
        previews = (self.preview(ReplaceElement(self.o, "S")),
                    self.preview(ReplaceElement(self.h1, "F"), other))
        barrier = threading.Barrier(2)

        def submit(editor, preview):
            barrier.wait(timeout=5)
            try:
                return editor.commit(preview)
            except StaleRevisionError:
                return None

        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(submit, editor, preview)
                       for editor, preview in zip((self.editor, other), previews)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(self.doc.records()[0]), 2)
        self.assertEqual(sorted(len(editor.undo_entries) for editor in (self.editor, other)), [0, 1])
        loser = self.editor if results[0] is None else other
        self.assertIsNotNone(loser.pending)
        self.assertFalse(loser.can_undo)
        self.assertEqual(loser.expected, self.root.ref)

    def test_invalid_and_noop_operations_are_atomic_and_keep_pending(self):
        pending = self.preview(ReplaceElement(self.o, "S"))
        records = self.doc.records()
        operations = (DeleteAtoms(("unknown",)),
                      ReorderAtoms((self.o,)), ReorderAtoms(self.root.atom_ids),
                      ReplaceElement("unknown", "C"), ReplaceElement(self.o, "O"),
                      SetElectronicState(1, 2))
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                self.preview(operation)
            self.assertEqual(self.doc.records(), records)
            self.assertIs(self.editor.pending, pending)
        for constructor in (lambda: DeleteAtoms((self.o, self.o)),
                            lambda: ReorderAtoms((self.o, self.o)),
                            lambda: AddAtoms(())):
            with self.assertRaises(ValueError):
                constructor()
        with self.assertRaises(EditStateError):
            self.editor.set_selection(SelectionContext(self.root.ref, ()))
        with self.assertRaises(EditStateError):
            self.editor.undo()
        self.editor.cancel(pending)

    def test_old_actual_frame_and_dataset_remain_bound_after_edit_undo_redo(self):
        moved = replace(self.root.molecule, atoms=tuple(
            replace(atom, z=atom.z + 0.2) for atom in self.root.molecule.atoms))
        frame = self.doc.add_frame(self.root.ref, "synthetic-actual-frame", moved,
                                   self.root.atom_ids, Provenance("synthetic_fixture"))
        data = ResultDataset("charge", frame.ref, Provenance("synthetic_fixture"),
                             "float64", (3,), "e", (0.2, 0.4, 0.4),
                             (DatasetAxis("atom", frame.atom_ids),))
        self.doc.add_dataset(data)
        self.commit(DeleteAtoms((self.h1,)))
        self.editor.undo()
        self.editor.redo()
        self.assertIs(self.doc.dataset(data.dataset_id), data)
        self.assertIs(self.doc.resolve(data.geometry), frame)
        self.assertEqual(self.doc.resolve(self.root.ref), self.root)
        self.assertNotEqual(self.doc.head.ref, frame.ref)

    def test_project_reopen_keeps_history_but_fresh_editor_has_empty_stacks(self):
        self.commit(DeleteAtoms((self.h1,)))
        self.editor.undo()
        session = Session.from_document(self.doc, CalculationSpec(), "")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "m2.oview.json"
            save_project(session, path)
            reopened = load_project(path)
        self.assertEqual(reopened.document.records(), self.doc.records())
        fresh = EditorService(reopened.document)
        self.assertEqual(fresh.undo_entries, ())
        self.assertEqual(fresh.redo_entries, ())
        self.assertFalse(fresh.can_undo)
        self.assertFalse(fresh.can_redo)
        self.assertEqual(fresh.expected, reopened.document.head.ref)
        self.commit(ReplaceElement(self.o, "S"), fresh)

    def test_distance_preview_commit_undo_and_error_preserve_transaction_state(self):
        definition = CoordinateDefinition(self.root.ref, "distance", (self.o, self.h1))
        preview = self.preview(SetDistance(definition, 1.3, (self.h1,), (self.o, self.h2)))
        self.assertEqual(self.doc.head, self.root)
        self.assertEqual(preview.molecule.atoms[0], self.root.molecule.atoms[0])
        self.assertEqual(preview.molecule.atoms[2], self.root.molecule.atoms[2])
        records = self.doc.records()
        with self.assertRaises(ValueError):
            self.preview(SetDistance(definition, 1.3, (self.h1,), (self.h1,)))
        self.assertEqual(self.doc.records(), records)
        self.assertIs(self.editor.pending, preview)
        edited = self.editor.commit(preview).snapshot
        actual = CoordinateDefinition(edited.ref, "distance", (self.o, self.h1))
        self.assertAlmostEqual(measure(edited, actual), 1.3)
        self.assertEqual(edited.molecule.bonds, self.root.molecule.bonds)
        self.assert_same_state(self.editor.undo().snapshot, self.root)
        self.assert_same_state(self.editor.redo().snapshot, edited)


if __name__ == "__main__":
    unittest.main()

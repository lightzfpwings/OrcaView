"""Selection behavior by stable IDs across edits, history and actual frames."""

from dataclasses import replace
import unittest

from orcaview.application.document import MoleculeDocument
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.core.provenance import Provenance
from orcaview.core.snapshots import SelectionContext
from orcaview.selection import SelectionService


class SelectionServiceTests(unittest.TestCase):
    def setUp(self):
        self.doc = MoleculeDocument.from_molecule(Molecule(
            "water", (Atom("O", 0, 0, 0), Atom("H", 1, 0, 0),
                      Atom("H", 0, 1, 0)), (Bond(0, 1), Bond(0, 2))))
        self.base = self.doc.head
        self.o, self.h1, self.h2 = self.base.atom_ids
        self.service = SelectionService(self.base)

    def test_replace_add_remove_toggle_keep_click_order(self):
        service = self.service
        self.assertEqual(service.selection.atom_ids, ())
        chosen = service.select((self.h2, self.o))
        self.assertEqual(chosen.indices(self.base), (2, 0))
        self.assertEqual(service.select((self.o, self.h1), "add").atom_ids,
                         (self.h2, self.o, self.h1))
        self.assertEqual(service.select((self.o,), "remove").atom_ids,
                         (self.h2, self.h1))
        self.assertEqual(service.select((self.h2, self.o), "toggle").atom_ids,
                         (self.h1, self.o))
        self.assertEqual(service.clear().atom_ids, ())
        self.assertEqual(self.doc.records(), ((self.base,), ()))

    def test_invalid_requests_do_not_change_context(self):
        previous = self.service.select((self.h2, self.o))
        invalid = (([self.h1], "replace"), ((self.o, self.o), "add"),
                   (("unknown",), "remove"), ((1,), "toggle"),
                   (("",), "replace"), ((self.h1,), "reorder"))
        for atom_ids, operation in invalid:
            with self.subTest(atom_ids=atom_ids, operation=operation):
                with self.assertRaises(ValueError):
                    self.service.select(atom_ids, operation)
                self.assertIs(self.service.selection, previous)

    def test_rebind_filters_deleted_ids_without_changing_order(self):
        self.service.select((self.h2, self.o, self.h1))
        edited = self.doc.publish_revision(
            self.base.ref, Molecule("OH", (self.base.molecule.atoms[1],
                                           self.base.molecule.atoms[0]),
                                     (Bond(0, 1),), multiplicity=2),
            (self.h1, self.o))
        chosen = self.service.rebind(edited)
        self.assertEqual(chosen.atom_ids, (self.o, self.h1))
        self.assertEqual(chosen.indices(edited), (1, 0))
        self.assertEqual(self.service.snapshot, edited)
        self.assertEqual(self.service.rebind(self.base).atom_ids,
                         (self.o, self.h1))

    def test_actual_frames_require_explicit_rebinding(self):
        chosen = self.service.select((self.h2, self.o))
        frame = self.doc.add_frame(
            self.base.ref, "source-frame", self.base.molecule,
            self.base.atom_ids, Provenance("synthetic_fixture"))
        with self.assertRaises(ValueError):
            chosen.indices(frame)
        with self.assertRaises(ValueError):
            SelectionService(frame, chosen)
        rebound = self.service.rebind(frame)
        self.assertEqual(rebound.geometry, frame.ref)
        self.assertEqual(rebound.atom_ids, chosen.atom_ids)
        self.assertEqual(self.doc.head, self.base)

    def test_initial_selection_mode_survives_operations_and_navigation(self):
        initial = SelectionContext(self.base.ref, (self.o,), "ordered-coordinate")
        service = SelectionService(self.base, initial)
        self.assertIs(service.selection, initial)
        self.assertEqual(service.select((self.h1,), "add").mode,
                         "ordered-coordinate")
        edited = self.doc.publish_revision(self.base.ref, self.base.molecule,
                                           self.base.atom_ids)
        self.assertEqual(service.rebind(edited).mode, "ordered-coordinate")
        self.assertEqual(service.clear().mode, "ordered-coordinate")

    def test_bad_initial_context_and_foreign_rebind_are_rejected(self):
        for initial in ("invalid", SelectionContext(self.base.ref, ("unknown",)),
                        SelectionContext(replace(self.base.ref, snapshot_id="other"), ())):
            with self.subTest(initial=initial), self.assertRaises(ValueError):
                SelectionService(self.base, initial)
        with self.assertRaises(ValueError):
            SelectionService(None)
        selected = self.service.select((self.o,))
        other = MoleculeDocument.from_molecule(self.base.molecule)
        for snapshot in (None, other.head):
            with self.subTest(snapshot=snapshot), self.assertRaises(ValueError):
                self.service.rebind(snapshot)
            self.assertIs(self.service.selection, selected)
            self.assertIs(self.service.snapshot, self.base)


if __name__ == "__main__":
    unittest.main()

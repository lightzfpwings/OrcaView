"""Append-only history restoration, identity protection and project replay regressions."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import unittest

from orcaview import __version__
from orcaview.application.document import MoleculeDocument, StaleRevisionError
from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, CalculationSpec, Molecule
from orcaview.core.provenance import Provenance
from orcaview.core.results import DatasetAxis, ResultDataset


# An independently specified schema 2 fixture, predating history-restore semantics.
# Its geometry digest is the documented binary64 hash of He at the origin.
SCHEMA2 = {
    "schema_version": 2, "software_version": "0.1.0a1", "contract_version": 1,
    "source_path": "unavailable/helium.xyz",
    "calculation": {"method": "HF", "basis": "def2-SVP", "job_type": "SP", "cores": 1, "maxcore_mb": 1000},
    "document": {
        "coordinate_unit": "angstrom", "datasets": [],
        "snapshots": [{
            "ref": {"document_id": "old-doc", "revision": 1, "frame_id": None, "snapshot_id": "old-root"},
            "molecule": {"name": "Helium", "atoms": [{"element": "He", "x": 0, "y": 0, "z": 0}],
                         "bonds": [], "charge": 0, "multiplicity": 1},
            "atom_ids": ["old-he"],
            "provenance": {"kind": "created", "producer": None, "producer_version": None,
                           "parents": [], "parameters": []},
            "parent": None, "source_unit": "angstrom",
            "content_hash": "794b859edd7c63cc85a409c499aa14633ebfc88c21ec7c250eec127120658a0c",
        }],
    },
}


def restore_provenance(target):
    return Provenance("history-restore", "orcaview.document", "1", parameters=(
        ("target_document_id", target.document_id),
        ("target_revision", str(target.revision)),
        ("target_snapshot_id", target.snapshot_id),
    ))


class HistoryRestoreTests(unittest.TestCase):
    def setUp(self):
        molecule = Molecule("H2 cation", (Atom("H", 0, 0, 0), Atom("H", 0.74, 0, 0)),
                            (Bond(0, 1),), charge=1, multiplicity=2)
        self.doc = MoleculeDocument.from_molecule(molecule, source_unit="bohr")
        self.session = Session.from_document(self.doc, CalculationSpec(), "")
        self.root = self.doc.head

    def delete_first(self):
        return self.doc.publish_revision(
            self.doc.head.ref,
            Molecule("H radical", (self.root.molecule.atoms[1],), charge=0, multiplicity=2),
            (self.root.atom_ids[1],),
        )

    def assert_same_state(self, actual, target):
        self.assertEqual(actual.molecule, target.molecule)
        self.assertEqual(actual.atom_ids, target.atom_ids)
        self.assertEqual(actual.source_unit, target.source_unit)
        self.assertEqual(actual.content_hash, target.content_hash)
        self.assertNotEqual(actual.ref, target.ref)

    def test_add_delete_replace_reorder_can_undo_and_redo_full_states(self):
        root = self.root
        added = self.doc.publish_revision(
            root.ref, Molecule("H3 cation", root.molecule.atoms + (Atom("H", 1.48, 0, 0),),
                               (Bond(0, 1), Bond(1, 2)), charge=1, multiplicity=1),
            root.atom_ids + (None,),
        )
        self.assertNotIn(added.atom_ids[2], root.atom_ids)
        deleted = self.doc.publish_revision(
            added.ref, Molecule("H2", added.molecule.atoms[1:], (Bond(0, 1),)), added.atom_ids[1:],
        )
        replaced = self.doc.publish_revision(
            deleted.ref, Molecule("HeH radical", (Atom("He", 0.74, 0, 0), deleted.molecule.atoms[1]),
                                 (Bond(0, 1, 2),), multiplicity=2), deleted.atom_ids,
        )
        reordered = self.doc.publish_revision(
            replaced.ref, Molecule("HHe cation", replaced.molecule.atoms[::-1], (Bond(0, 1, 3),), charge=1),
            replaced.atom_ids[::-1],
        )
        original_history = self.doc.records()[0]
        for target in (replaced, deleted, added, root, added, deleted, replaced, reordered):
            previous = self.doc.head
            restored = self.doc.restore_revision(previous.ref, target.ref)
            self.assert_same_state(restored, target)
            self.assertEqual(restored.parent, previous.ref)
            self.assertEqual(restored.ref.revision, previous.ref.revision + 1)
            self.assertEqual(restored.provenance, restore_provenance(target.ref))
        for old in original_history:
            self.assertEqual(self.doc.resolve(old.ref), old)
        self.assertEqual(len(self.doc.records()[0]), len(original_history) + 8)

    def test_plain_publication_cannot_reactivate_deleted_identity_or_use_reserved_kind(self):
        deleted = self.delete_first()
        before = self.doc.records()
        with self.assertRaises(ValueError):
            self.doc.publish_revision(deleted.ref, self.root.molecule, self.root.atom_ids)
        with self.assertRaises(ValueError):
            self.doc.publish_revision(deleted.ref, deleted.molecule, deleted.atom_ids,
                                      restore_provenance(self.root.ref))
        self.assertEqual(self.doc.records(), before)
        restored = self.doc.restore_revision(deleted.ref, self.root.ref)
        self.assertEqual(restored.atom_ids, self.root.atom_ids)
        replacement = self.doc.publish_revision(restored.ref, self.root.molecule, (None, self.root.atom_ids[1]))
        self.assertNotEqual(replacement.atom_ids[0], self.root.atom_ids[0])

    def test_invalid_target_and_stale_base_leave_history_unchanged(self):
        frame = self.doc.add_frame(self.root.ref, "fixture-frame", self.root.molecule, self.root.atom_ids,
                                   Provenance("fixture"))
        deleted = self.delete_first()
        other = MoleculeDocument.from_molecule(self.root.molecule)
        cases = (
            (self.root.ref, self.root.ref),
            (deleted.ref, deleted.ref),
            (deleted.ref, frame.ref),
            (deleted.ref, other.head.ref),
            (deleted.ref, replace(self.root.ref, snapshot_id="unrecorded-target")),
            (deleted.ref, replace(self.root.ref, document_id="foreign-document")),
            (deleted.ref, replace(self.root.ref, revision=2)),
        )
        before = self.doc.records()
        for expected, target in cases:
            with self.subTest(expected=expected, target=target), self.assertRaises(ValueError):
                self.doc.restore_revision(expected, target)
            self.assertEqual(self.doc.records(), before)

    def test_independent_branch_refs_do_not_authorize_restoration(self):
        branch = replace(self.session).document
        left = self.delete_first()
        right = branch.publish_revision(self.root.ref, self.root.molecule, self.root.atom_ids)
        self.assertEqual(left.ref.revision, right.ref.revision)
        before = self.doc.records()
        with self.assertRaises(StaleRevisionError):
            self.doc.restore_revision(right.ref, self.root.ref)
        with self.assertRaises(ValueError):
            self.doc.restore_revision(left.ref, right.ref)
        self.assertEqual(self.doc.records(), before)

    def test_concurrent_restores_have_one_winner(self):
        deleted = self.delete_first()
        ready = threading.Barrier(2)

        def restore():
            ready.wait(timeout=10)
            try:
                return self.doc.restore_revision(deleted.ref, self.root.ref)
            except StaleRevisionError:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: restore(), range(2)))
        self.assertEqual(sum(item is not None for item in outcomes), 1)
        self.assertEqual(self.doc.head.ref.revision, 3)
        self.assertEqual(self.doc.head.atom_ids, self.root.atom_ids)

    def test_old_frame_results_stay_bound_after_restore(self):
        moved = replace(self.root.molecule, atoms=(self.root.molecule.atoms[0], Atom("H", 0.8, 0, 0)))
        frame = self.doc.add_frame(self.root.ref, "synthetic-step", moved, self.root.atom_ids,
                                   Provenance("fixture"))
        data = ResultDataset("atomic_charge", frame.ref, Provenance("fixture"), "float64", (2,), "e",
                             (0.5, 0.5), (DatasetAxis("atom", frame.atom_ids),), quality=("synthetic-fixture",))
        self.doc.add_dataset(data)
        deleted = self.delete_first()
        restored = self.doc.restore_revision(deleted.ref, self.root.ref)
        saved = self.doc.dataset(data.dataset_id)
        self.assertEqual(saved, data)
        self.assertEqual(self.doc.resolve(saved.geometry), frame)
        self.assertNotEqual(saved.geometry, restored.ref)
        self.assertNotEqual(frame.molecule, restored.molecule)

    def test_restore_history_roundtrip_copy_and_further_restore(self):
        deleted = self.delete_first()
        restored = self.doc.restore_revision(deleted.ref, self.root.ref)
        branch = replace(self.session)
        self.assertEqual(branch.document.records(), self.doc.records())
        branch.document.restore_revision(restored.ref, deleted.ref)
        self.assertEqual(self.doc.head, restored)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.oview.json"
            save_project(self.session, path)
            payload = json.loads(path.read_text())
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["contract_version"], 1)
            reopened = load_project(path)
            self.assertEqual(reopened.document.records(), self.doc.records())
            redone = reopened.document.restore_revision(restored.ref, deleted.ref)
            self.assert_same_state(redone, deleted)
            save_project(reopened, path)
            self.assertEqual(load_project(path).document.records(), reopened.document.records())

    def test_reserved_restore_kind_is_rejected_for_root_and_actual_frame(self):
        before = self.doc.records()
        origin = restore_provenance(self.root.ref)
        with self.assertRaises(ValueError):
            MoleculeDocument.from_molecule(self.root.molecule, origin)
        with self.assertRaises(ValueError):
            self.doc.add_frame(self.root.ref, "fake-restore", self.root.molecule, self.root.atom_ids, origin)
        self.assertEqual(self.doc.records(), before)

    def test_old_schema2_fixture_stays_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old-schema2.oview.json"
            path.write_text(json.dumps(SCHEMA2), encoding="utf-8")
            loaded = load_project(path)
            self.assertEqual(loaded.document.head.atom_ids, ("old-he",))
            save_project(loaded, path)
            self.assertEqual(json.loads(path.read_text()), dict(SCHEMA2, software_version=__version__))

    def test_project_replay_rejects_forged_restore_evidence_and_state(self):
        deleted = self.delete_first()
        restored = self.doc.restore_revision(deleted.ref, self.root.ref)
        before = self.doc.records()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.oview.json"
            save_project(self.session, path)
            template = json.loads(path.read_text())
            changes = (
                (("provenance", "kind"), "edit"),
                (("provenance", "producer"), "other"),
                (("provenance", "producer_version"), "2"),
                (("provenance", "parameters", 0, 1), "foreign-document"),
                (("provenance", "parameters", 1, 1), "2"),
                (("provenance", "parameters", 2, 1), "absent-snapshot"),
                (("provenance", "parameters"), []),
                (("provenance", "parameters"), template["document"]["snapshots"][-1]["provenance"]["parameters"]
                 + [["unrecognized", "evidence"]]),
                (("atom_ids", 0), "invented-id"),
                (("molecule", "name"), "wrong historical molecule"),
                (("molecule", "charge"), 0),
                (("molecule", "multiplicity"), 1),
                (("molecule", "bonds", 0, "order"), 2),
                (("source_unit",), "angstrom"),
            )
            for keys, value in changes:
                with self.subTest(keys=keys, value=value):
                    record = deepcopy(template)
                    changed = record["document"]["snapshots"][-1]
                    for key in keys[:-1]:
                        changed = changed[key]
                    changed[keys[-1]] = value
                    path.write_text(json.dumps(record), encoding="utf-8")
                    raw = path.read_bytes()
                    with self.assertRaises(ValueError):
                        load_project(path)
                    self.assertEqual(path.read_bytes(), raw)
                    self.assertEqual(self.doc.records(), before)
            # Preserve a valid geometry digest to reach the exact-history check.
            moved = replace(restored, molecule=replace(restored.molecule, atoms=(Atom("H", 0.1, 0, 0),
                                                                              restored.molecule.atoms[1])))
            record = deepcopy(template)
            record["document"]["snapshots"][-1]["molecule"]["atoms"][0]["x"] = 0.1
            record["document"]["snapshots"][-1]["content_hash"] = moved.content_hash
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_project(path)
            self.assertEqual(self.doc.records(), before)


if __name__ == "__main__":
    unittest.main()

"""Project-format compatibility and failure recovery through the public application service."""

from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from orcaview import __version__
from orcaview.application.project import load_project, migrate_project, save_project
from orcaview.application.document import GeometryLookupError
from orcaview.application.session import Session
from orcaview.core.models import CalculationSpec
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.core.results import DatasetAxis, ResultDataset


# Independent of the current encoder, including an unresolved historic source hint.
SCHEMA1 = {
    "schema_version": 1, "software_version": "0.1.0a1", "source_path": "missing/old-hydrogen.xyz",
    "molecule": {"name": "H2 cation", "charge": 1, "multiplicity": 2,
                 "atoms": [{"element": "H", "x": 0, "y": 0, "z": 0},
                           {"element": "H", "x": 0.74, "y": 0, "z": 0}],
                 "bonds": [{"a": 0, "b": 1, "order": 1}]},
    "calculation": {"method": "HF", "basis": "def2-SVP", "job_type": "OPT", "cores": 3, "maxcore_mb": 720},
}


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.old = self.work / "old.oview.json"
        self.new = self.work / "new.oview.json"
        self.raw = json.dumps(SCHEMA1, indent=2).encode("utf-8")
        self.old.write_bytes(self.raw)

    def test_plain_legacy_project_preserves_wire_format_and_input(self):
        loaded = load_project(self.old)
        self.assertIsNone(loaded.tracked_document)
        self.assertEqual(loaded.molecule.electron_count, 1)
        self.assertIn("* xyz 1 2", loaded.input_text())
        save_project(loaded, self.new)
        self.assertEqual(json.loads(self.new.read_text()), dict(SCHEMA1, software_version=__version__))
        self.assertEqual(self.old.read_bytes(), self.raw)

    def test_legacy_changes_before_tracking_keep_their_provenance(self):
        session = load_project(self.old)
        session.apply_settings(session.calculation, 0, 1)
        self.assertIsNone(session.tracked_document)
        self.assertEqual(session.document.head.provenance.kind, "legacy-edit")
        self.assertEqual(session.document.head.provenance.parents[0].sha256, sha256(self.raw).hexdigest())

    def test_dataclass_copy_preserves_legacy_projection_and_branches_tracked_history(self):
        old = replace(load_project(self.old))
        self.assertIsNone(old.tracked_document)
        self.assertEqual(set(asdict(old)), {"molecule", "calculation", "source_path"})
        self.assertEqual(old.legacy_project_path, self.old.resolve())
        session, result = self._rich_project()
        branch = replace(session)
        self.assertEqual(branch.document.records(), session.document.records())
        branch.apply_settings(branch.calculation, 1, 2)
        self.assertEqual(session.document.head.ref.revision, 2)
        self.assertEqual(branch.document.head.ref.revision, 3)
        self.assertEqual(branch.document.dataset(result.dataset_id), result)

    def test_migrate_preserves_original_ids_provenance_settings_and_bonds(self):
        migrated = migrate_project(self.old, self.new)
        reopened = load_project(self.new)
        self.assertEqual(json.loads(self.new.read_text())["schema_version"], 2)
        self.assertEqual(migrated.document.records(), reopened.document.records())
        self.assertEqual(migrated.input_text(), load_project(self.old).input_text())
        self.assertEqual(reopened.molecule.bonds[0].order, 1)
        parents = reopened.document.head.provenance.parents
        self.assertEqual(parents[0].sha256, sha256(self.raw).hexdigest())
        self.assertEqual(parents[1].path_hint, SCHEMA1["source_path"])
        self.assertIsNone(parents[1].sha256)
        self.assertEqual(self.old.read_bytes(), self.raw)

    def test_migration_never_overwrites_source_or_an_existing_destination(self):
        loaded = load_project(self.old)
        before = loaded.document.head.ref
        with self.assertRaisesRegex(ValueError, 'new location'):
            save_project(loaded, self.old)
        self.assertEqual(before, loaded.document.head.ref)
        with self.assertRaises(ValueError):
            migrate_project(self.old, self.old)
        self.new.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            migrate_project(self.old, self.new)
        self.assertEqual(self.old.read_bytes(), self.raw)
        self.assertEqual(self.new.read_bytes(), b"existing")
        self.assertCountEqual(self.work.iterdir(), [self.new, self.old])

    def test_failed_migration_and_rich_save_leave_no_partial_project(self):
        with patch("orcaview.application.project.os.link", side_effect=OSError("I/O error")):
            with self.assertRaises(OSError):
                migrate_project(self.old, self.new)
        self.assertEqual(self.old.read_bytes(), self.raw)
        self.assertEqual(list(self.work.iterdir()), [self.old])
        session = migrate_project(self.old, self.new)
        good = self.new.read_bytes()
        with patch("orcaview.application.project.os.replace", side_effect=OSError("I/O error")):
            with self.assertRaises(OSError):
                save_project(session, self.new)
        self.assertEqual(self.new.read_bytes(), good)
        self.assertEqual(load_project(self.new).document.records(), session.document.records())
        self.assertCountEqual(self.work.iterdir(), [self.old, self.new])

    def _rich_project(self):
        session = Session()
        xyz = self.work / "fixture.xyz"
        xyz.write_text("2\nunits=bohr\nHe 0 0 0\nHe 3 0 0\n", encoding="utf-8")
        session.open_xyz(xyz)
        doc = session.document
        root = doc.head
        mol = replace(root.molecule, atoms=root.molecule.atoms[::-1])
        frame = doc.add_frame(root.ref, "out:block-0:step-3", mol, root.atom_ids[::-1], Provenance("fixture"))
        ds = ResultDataset("charge", frame.ref, Provenance("fixture"), "float64", (2,), "e",
                           (None, 0.0), (DatasetAxis("atom", frame.atom_ids),), missing_reason="missing row")
        doc.add_dataset(ds)
        doc.publish_revision(root.ref, mol, root.atom_ids[::-1])
        save_project(session, self.new)
        return session, ds

    def test_roundtrip_restores_history_and_actual_frame_with_original_rows(self):
        session, ds = self._rich_project()
        self.assertEqual(session.document.head.ref.revision, 2)
        (self.work / "fixture.xyz").unlink()
        other = load_project(self.new)
        self.assertEqual(session.document.records(), other.document.records())
        result = other.document.dataset(ds.dataset_id)
        frame = other.document.resolve(result.geometry)
        self.assertEqual(frame.atom_ids, result.axes[0].ids)
        self.assertNotEqual(frame.ref, other.document.head.ref)
        self.assertEqual(frame.ref.frame_id, "out:block-0:step-3")
        self.assertEqual(other.document.resolve(frame.parent).source_unit, "bohr")
        self.assertEqual(other.input_text(), session.input_text())

    def test_old_formats_preserve_settings_outside_current_export_element_range(self):
        heavy = deepcopy(SCHEMA1)
        heavy["molecule"]["atoms"][0]["element"] = "Fr"
        self.old.write_text(json.dumps(heavy))
        legacy = load_project(self.old)
        with self.assertRaises(ValueError):
            legacy.input_text()
        migrated = migrate_project(self.old, self.new)
        record = json.loads(self.new.read_text())
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(record["calculation"], SCHEMA1["calculation"])
        self.assertEqual(load_project(self.new).document.records(), migrated.document.records())

    def test_structured_methods_roundtrip_and_choose_schema_3_automatically(self):
        specs = (
            CalculationSpec(method="CASSCF", active_electrons=2, active_orbitals=2),
            CalculationSpec(method="SC-NEVPT2", active_electrons=2, active_orbitals=2),
            CalculationSpec(method="CIS", nroots=2),
            CalculationSpec(method="TD-DFT", nroots=2, reference_functional="PBE0"),
            CalculationSpec(method="TDA-DFT", nroots=2, reference_functional="B3LYP"),
        )
        for spec in specs:
            with self.subTest(method=spec.method):
                session = Session(calculation=spec)
                self.assertIsNone(session.tracked_document)
                save_project(session, self.new)
                saved = json.loads(self.new.read_text())
                self.assertEqual(saved["schema_version"], 3)
                self.assertEqual(saved["contract_version"], 1)
                fields = (*SCHEMA1["calculation"], "active_electrons", "active_orbitals", "nroots", "reference_functional")
                self.assertEqual(saved["calculation"], {key: getattr(spec, key) for key in fields})
                reopened = load_project(self.new)
                self.assertEqual(reopened.calculation, spec)
                self.assertEqual(reopened.document.records(), session.document.records())
                self.assertEqual(reopened.input_text(), session.input_text())

    def test_structured_settings_preserve_history_and_protect_legacy_source(self):
        session, dataset = self._rich_project()
        original = session.document.records()
        session.calculation = CalculationSpec(method="CIS", nroots=1)
        save_project(session, self.new)
        reopened = load_project(self.new)
        self.assertEqual(reopened.document.records(), original)
        self.assertEqual(reopened.document.dataset(dataset.dataset_id), dataset)
        reopened.calculation = CalculationSpec()
        save_project(reopened, self.new)
        basic = json.loads(self.new.read_text())
        self.assertEqual(basic["schema_version"], 2)
        self.assertEqual(set(basic["calculation"]), set(SCHEMA1["calculation"]))

        legacy = load_project(self.old)
        legacy.apply_settings(CalculationSpec(method="CASSCF", active_electrons=2, active_orbitals=2), 0, 1)
        with self.assertRaisesRegex(ValueError, 'new location'):
            save_project(legacy, self.old)
        self.assertEqual(self.old.read_bytes(), self.raw)
        self.assertIsNone(legacy.tracked_document)
        save_project(legacy, self.new)
        self.assertEqual(json.loads(self.new.read_text())["schema_version"], 3)
        self.assertEqual(load_project(self.new).document.head.provenance.parents[0].sha256, sha256(self.raw).hexdigest())

    def test_structured_settings_require_matching_schema_method_parameters_and_electron_count(self):
        session = Session(calculation=CalculationSpec(method="CASSCF", active_electrons=2, active_orbitals=2))
        save_project(session, self.new)
        valid = json.loads(self.new.read_text())
        for version, changes in (
            (2, {}), (3, {"unexpected": 1}), (3, {"active_electrons": True}),
            (3, {"active_electrons": 12, "active_orbitals": 8}), (3, {"active_electrons": None}),
            (3, {"method": "HF"}), (3, {"method": "HF", "active_orbitals": None, "active_electrons": None}),
            (3, {"method": "TD-DFT", "active_orbitals": None, "active_electrons": None,
                 "nroots": 2, "reference_functional": "CCSD"}),
        ):
            with self.subTest(version=version, changes=changes):
                record = deepcopy(valid)
                record["schema_version"] = version
                record["calculation"].update(changes)
                self.new.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    load_project(self.new)
        del valid["calculation"]["nroots"]
        self.new.write_text(json.dumps(valid))
        with self.assertRaises(ValueError):
            load_project(self.new)

    def test_incompatible_active_space_cannot_replace_a_project_or_promote_a_plain_session(self):
        session = Session(calculation=CalculationSpec(method="CASSCF", active_electrons=12, active_orbitals=8))
        self.new.write_bytes(b"existing")
        with self.assertRaises(ValueError):
            save_project(session, self.new)
        self.assertIsNone(session.tracked_document)
        self.assertEqual(self.new.read_bytes(), b"existing")

    def test_independent_reopens_never_alias_new_revisions_or_frames(self):
        first = migrate_project(self.old, self.new).document
        second = load_project(self.new).document
        original = first.head
        moved = replace(original.molecule, atoms=tuple(reversed(original.molecule.atoms)))
        left = first.publish_revision(original.ref, moved, original.atom_ids[::-1])
        right = second.publish_revision(original.ref, original.molecule, original.atom_ids)
        self.assertEqual(left.ref.revision, right.ref.revision)
        self.assertNotEqual(left.ref.snapshot_id, right.ref.snapshot_id)
        frame = first.add_frame(original.ref, "step-1", moved, original.atom_ids[::-1], Provenance("fixture"))
        second.add_frame(original.ref, "step-1", original.molecule, original.atom_ids, Provenance("fixture"))
        for ref in (left.ref, frame.ref):
            result = ResultDataset("energy", ref, Provenance("fixture"), "float64", (), "hartree", (0,))
            with self.assertRaises(GeometryLookupError):
                second.add_dataset(result)
        self.assertEqual(second.resolve(original.ref), original)

    def test_external_array_reference_survives_missing_file(self):
        session, ds = self._rich_project()
        path = self.work / "external.raw"
        path.write_bytes(struct.pack("<2d", -3, 3))
        data = replace(ds, dataset_id="external", values=None, missing_reason=None,
                       array_ref=ArtifactRef.from_file(path, "raw-le"))
        session.document.add_dataset(data)
        save_project(session, self.new)
        path.unlink()
        restored = load_project(self.new)
        saved = restored.document.dataset("external")
        self.assertEqual(saved, data)
        with self.assertRaises(FileNotFoundError), saved.open_array(path):
            pass

    def test_rejects_unknown_fields_versions_and_misbound_geometry(self):
        self._rich_project()
        template = json.loads(self.new.read_text())
        cases = [
            (("contract_version",), 100), (("schema_version",), True),
            (("document", "coordinate_unit"), "bohr"),
            (("document", "snapshots", 0, "content_hash"), "wrong"),
            (("document", "snapshots", 1, "parent", "revision"), 4),
            (("document", "snapshots", 2, "ref", "revision"), 5),
            (("document", "datasets", 0, "geometry", "frame_id"), "other"),
            (("document", "datasets", 0, "shape"), "2"),
            (("document", "datasets", 0, "axes", 0, "ids"), ["new", "foreign"]),
            (("document", "datasets", 0, "unrecognized_quality"), 1),
            (("document", "snapshots", 0, "provenance", "parents", 0, "sha3"), "unknown"),
            (("document", "snapshots", 0, "molecule", "atoms", 0, "annotations"), []),
        ]
        for path, value in cases:
            with self.subTest(path=path):
                record = deepcopy(template)
                target = record
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                self.new.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    load_project(self.new)

    def test_legacy_unknown_nested_duplicate_and_nonfinite_are_rejected(self):
        for raw in (
            self.raw.replace(b'"order": 1', b'"order": 1, "future": 1'),
            self.raw.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1'),
            self.raw.replace(b'"z": 0', b'"z": NaN'),
        ):
            with self.subTest(raw=raw):
                self.old.write_bytes(raw)
                with self.assertRaises(ValueError):
                    migrate_project(self.old, self.new)
                self.assertEqual(self.old.read_bytes(), raw)
                self.assertFalse(self.new.exists())

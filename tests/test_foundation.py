"""G0 identity, unit and producer/consumer regressions. All numeric fixtures are synthetic."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

from orcaview.application.document import GeometryLookupError, StaleRevisionError
from orcaview.application.session import Session
from orcaview.core.models import Atom, CalculationSpec, Molecule
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.core.results import DatasetAxis, ResultDataset
from orcaview.core.snapshots import GeometryRef, SelectionContext
from orcaview.core.tasks import ErrorInfo, ResourceBudget, TaskEvent
from orcaview.core.units import BOHR_IN_ANGSTROM, convert_length
from orcaview.io.xyz import parse_xyz, parse_xyz_record, write_xyz
from orcaview.orca.input import render_input


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.session = Session()
        self.doc = self.session.document
        self.base = self.doc.head

    def test_add_delete_reorder_and_resolve_old_result(self):
        root = self.base
        o, h1, h2 = root.atom_ids
        result = ResultDataset("charge", root.ref, Provenance("fixture"), "float64", (3,), "e",
                               (-0.8, 0.4, 0.4), (DatasetAxis("atom", root.atom_ids),))
        self.doc.add_dataset(result)
        mol = replace(root.molecule, atoms=(root.molecule.atoms[2], root.molecule.atoms[0], Atom("F", 3, 0, 0)))
        updated = self.doc.publish_revision(root.ref, mol, (h2, o, None))
        self.assertEqual(updated.atom_ids[:2], (h2, o))
        self.assertNotIn(updated.atom_ids[2], root.atom_ids)
        self.assertNotIn(h1, updated.atom_ids)
        self.assertEqual(updated.index_of(o), 1)
        original = self.doc.resolve(self.doc.dataset(result.dataset_id).geometry)
        self.assertIs(original, root)
        self.assertEqual(original.id_at(0), o)
        self.assertEqual(original.index_of(h1), 1)
        with self.assertRaises(ValueError):
            self.doc.publish_revision(updated.ref, root.molecule, root.atom_ids)

    def test_actual_frames_do_not_advance_or_alias_revisions(self):
        b = self.base
        moved = replace(b.molecule, atoms=tuple(reversed(b.molecule.atoms)))
        frame = self.doc.add_frame(b.ref, "source-0", moved, b.atom_ids[::-1], Provenance("fixture"))
        self.assertEqual(frame.parent, b.ref)
        self.assertIs(self.doc.head, b)
        head = self.doc.publish_revision(b.ref, b.molecule, b.atom_ids)
        other = self.doc.add_frame(head.ref, "source-0", moved, b.atom_ids[::-1], Provenance("fixture"))
        self.assertNotEqual(frame.ref, other.ref)
        self.assertEqual(frame.content_hash, other.content_hash)
        self.assertIs(self.doc.resolve(frame.ref), frame)
        with self.assertRaises(ValueError):
            self.doc.add_frame(b.ref, "source-0", b.molecule, b.atom_ids, Provenance("fixture"))
        with self.assertRaises(ValueError):
            self.doc.add_frame(b.ref, "bad-map", moved, b.atom_ids, Provenance("fixture"))
        with self.assertRaises(ValueError):
            self.doc.add_frame(b.ref, "bad-state", replace(b.molecule, charge=1), b.atom_ids, Provenance("fixture"))
        with self.assertRaises(StaleRevisionError):
            self.doc.publish_revision(frame.ref, moved, frame.atom_ids)
        for ref in (GeometryRef("foreign", 1), replace(b.ref, frame_id="missing")):
            with self.assertRaises(GeometryLookupError):
                self.doc.resolve(ref)

    def test_failed_mapping_is_atomic(self):
        b = self.base
        for ids in ((b.atom_ids[0],) * 3, ("foreign", None, None), (), (1, None, None)):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.doc.publish_revision(b.ref, b.molecule, ids)
        self.assertEqual(self.doc.records(), ((b,), ()))

    def test_two_writers_to_same_revision_only_one_commits(self):
        b = self.base
        ready = threading.Barrier(2)

        def commit():
            ready.wait(timeout=5)
            try:
                return self.doc.publish_revision(b.ref, b.molecule, b.atom_ids).ref.revision
            except StaleRevisionError:
                return "stale"

        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(commit) for _ in range(2)]
            self.assertCountEqual([f.result() for f in futures], [2, "stale"])
        self.assertEqual(len(self.doc.records()[0]), 2)

    def test_ordered_selection_and_invalid_index(self):
        b = self.base
        selection = SelectionContext(b.ref, (b.id_at(2), b.id_at(0)))
        self.assertEqual(selection.indices(b), (2, 0))
        self.assertEqual(selection.atom_set, frozenset((b.id_at(0), b.id_at(2))))
        with self.assertRaises(ValueError):
            SelectionContext(b.ref, (b.id_at(0),) * 2)
        with self.assertRaises(ValueError):
            SelectionContext(b.ref, ("foreign",)).indices(b)
        for index in (-1, 3, True, 1.0):
            with self.assertRaises(ValueError):
                b.id_at(index)
        other = self.doc.publish_revision(b.ref, b.molecule, b.atom_ids)
        with self.assertRaises(ValueError):
            selection.indices(other)

    def test_legacy_settings_update_keeps_identity_and_separates_electronic_state(self):
        b = self.base
        self.session.apply_settings(CalculationSpec(job_type="OPT"), 0, 1)
        self.assertIs(self.doc.head, b)
        with self.assertRaises(ValueError):
            self.session.apply_settings(CalculationSpec(job_type="FREQ"), 0, 2)
        self.assertIs(self.doc.head, b)
        self.assertEqual(self.session.calculation.job_type, "OPT")
        self.session.apply_settings(CalculationSpec(), 1, 2)
        new = self.doc.head
        self.assertEqual(new.atom_ids, b.atom_ids)
        self.assertEqual(new.content_hash, b.content_hash)
        self.assertNotEqual(new.ref, b.ref)
        self.assertEqual(self.doc.resolve(b.ref).molecule.charge, 0)
        with self.assertRaises(FrozenInstanceError):
            new.molecule.charge = 2
        self.session.molecule = replace(new.molecule, atoms=tuple(reversed(new.molecule.atoms)))
        self.assertTrue(set(new.atom_ids).isdisjoint(self.doc.head.atom_ids))

    def test_geometry_hash_depends_on_rows_and_coordinates_only(self):
        b = self.base
        renamed = replace(b.molecule, name="display name")
        same = replace(b, molecule=renamed, source_unit="bohr")
        self.assertEqual(same.content_hash, b.content_hash)
        atoms = (Atom("O", -0.0, 0, 0.0), *b.molecule.atoms[1:])
        self.assertEqual(replace(b, molecule=replace(renamed, atoms=atoms)).content_hash, b.content_hash)
        moved = replace(renamed, atoms=(Atom("O", 0, 0, 0.1), *atoms[1:]))
        self.assertNotEqual(replace(b, molecule=moved).content_hash, b.content_hash)

    def test_preview_cannot_overwrite_an_intervening_geometry_edit(self):
        base = self.base
        moved = replace(base.molecule, atoms=(Atom("O", 0, 0, 0.1), *base.molecule.atoms[1:]))

        def render_while_editing(molecule, calculation):
            self.doc.publish_revision(base.ref, moved, base.atom_ids)
            return render_input(molecule, calculation)

        with patch("orcaview.application.session.render_input", side_effect=render_while_editing):
            with self.assertRaises(StaleRevisionError):
                self.session.apply_settings(CalculationSpec(job_type="OPT"), 1, 2)
        self.assertEqual(self.session.molecule, moved)
        self.assertEqual(self.session.calculation.job_type, "SP")


class UnitAndSourceTests(unittest.TestCase):
    def test_bohr_to_angstrom_at_file_and_abi_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.xyz"
            raw = b'1\r\nunits=bohr pbc="F F F"\r\nHe 1 -2 0\r\n'
            path.write_bytes(raw)
            session = Session()
            session.open_xyz(path)
            snapshot = session.document.head
            self.assertEqual(snapshot.source_unit, "bohr")
            self.assertEqual(dict(snapshot.provenance.parameters)["unit_source"], "xyz-comment")
            self.assertAlmostEqual(snapshot.molecule.atoms[0].x, 0.529177210544, places=13)
            self.assertEqual(snapshot.coordinates("bohr"), ((1.0, -2.0, 0.0),))
            origin = snapshot.provenance.parents[0]
            self.assertEqual(origin.sha256, sha256(raw).hexdigest())
            self.assertEqual(session.document.artifact(origin.artifact_id), origin)
            path.write_bytes(b'invalid')
            with self.assertRaises(ValueError):
                session.open_xyz(path)
            self.assertIs(session.document.head, snapshot)

    def test_missing_or_unsupported_unit_and_periodicity(self):
        for comment in ('Lattice="1 0 0 0 1 0 0 0 1"', 'pbc="T F F"', "k_points=1",
                        "pbc=maybe", "units=furlong", "unit=bohr units=angstrom"):
            with self.subTest(comment=comment), self.assertRaises(ValueError):
                parse_xyz("1\n" + comment + "\nHe 1 0 0\n")
        plain = parse_xyz_record('1\nlabel="test units=bohr" units=Å\nHe 1 0 0\n')
        self.assertEqual((plain.source_unit, plain.molecule.atoms[0].x), ("angstrom", 1.0))
        self.assertEqual(parse_xyz_record("1\nordinary comment\nHe 0 0 0").unit_source, "xyz-default")
        for bad in (float("inf"), float("nan"), True, 10**600):
            with self.assertRaises(ValueError):
                convert_length(bad, "bohr", "angstrom")
        with self.assertRaises(ValueError):
            convert_length(1.7e308, "angstrom", "bohr")
        with self.assertRaises(ValueError):
            convert_length(1, "unknown", "angstrom")
        self.assertAlmostEqual(convert_length(BOHR_IN_ANGSTROM, "angstrom", "bohr"), 1)

    def test_xyz_writer_does_not_reinterpret_name_as_unit_metadata(self):
        mol = Molecule('geometry units=bohr', (Atom("He", 1, 2, 3),))
        self.assertEqual(parse_xyz(write_xyz(mol)).atoms, mol.atoms)


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.doc = Session().document
        self.base = self.doc.head
        self.scalar = ResultDataset("energy", self.base.ref, Provenance("fixture"), "float64", (), "hartree", (0,))

    def test_native_and_analysis_use_same_atom_axis_and_preserve_missing(self):
        axis = DatasetAxis("atom", self.base.atom_ids)
        native = ResultDataset("charge", self.base.ref, Provenance("import", "fixture.native", "1"),
                               "float64", (3,), "e", (0, None, 0), (axis,),
                               missing_reason="row absent", method="Mulliken")
        computed = replace(native, dataset_id="second", provenance=Provenance("analysis", "fixture.analysis", "1"),
                           values=(-0.4, 0.2, 0.2), missing_reason=None, method="Hirshfeld", density="total")
        for result in (native, computed):
            self.doc.add_dataset(result)
            self.assertIs(self.doc.resolve(self.doc.dataset(result.dataset_id).geometry), self.base)
        self.assertEqual(native.valid_mask, (True, False, True))
        self.assertEqual(computed.valid_mask, (True,) * 3)
        self.assertIsNone(replace(self.scalar, values=None, missing_reason="truncated").values)
        self.doc.add_dataset(native)  # Identical delivery may be retried.
        self.assertEqual(len(self.doc.records()[1]), 2)
        with self.assertRaises(ValueError):
            self.doc.add_dataset(replace(native, method="other"))
        with self.assertRaises(ValueError):
            self.doc.add_dataset(replace(native, axes=(DatasetAxis("atom", ("x", "y", "z")),)))

    def test_rejects_invalid_shapes_values_units_axes_and_missing_states(self):
        for change in ({"shape": (1,)}, {"dtype": "unknown"}, {"values": ()}, {"values": [1]},
                       {"values": (float("nan"),)}, {"values": (float("inf"),)}, {"values": (True,)},
                       {"shape": (True,), "axes": (DatasetAxis("index"),)}, {"unit": ""},
                       {"values": None}, {"values": (None,)}, {"missing_reason": "contradiction"},
                       {"dtype": "int64", "values": (2**63,)}, {"shape": (0,), "axes": (DatasetAxis("index"),)},
                       {"shape": (2,), "axes": (DatasetAxis("state", ("S1",)),)}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.scalar, **change)
        with self.assertRaises(ValueError):
            DatasetAxis("orbital")
        immutable = replace(self.scalar, dtype="int64", values=(3,))
        self.assertEqual(immutable.values, (3,))

    def test_external_array_verified_mapping_has_owned_lifetime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grid.bin"
            raw = struct.pack("<2d", 1.0, 2.0)
            path.write_bytes(raw)
            ref = ArtifactRef.from_file(path, "raw-le")
            data = replace(self.scalar, values=None, shape=(2,), axes=(DatasetAxis("grid-x"),), array_ref=ref)
            with data.open_array(path) as view:
                with self.assertRaises(TypeError):
                    view[0] = 0
                path.write_bytes(struct.pack("<2d", 3.0, 4.0))
                self.assertEqual(view[:], raw)
            with self.assertRaises(ValueError):
                view[:]
            with self.assertRaisesRegex(ValueError, "SHA-256"), data.open_array(path):
                pass
            path.write_bytes(raw[:8])
            with self.assertRaisesRegex(ValueError, 'byte count'), data.open_array(path):
                pass
            path.write_bytes(struct.pack("<2d", 1, float("nan")))
            invalid = replace(data, array_ref=ArtifactRef.from_file(path, "raw-le"))
            with self.assertRaisesRegex(ValueError, 'nonfinite'), invalid.open_array(path):
                pass
            path.unlink()
            with self.assertRaises(FileNotFoundError), data.open_array(path):
                pass

    def test_conflicting_artifact_is_never_published(self):
        art = ArtifactRef.from_bytes(b"fixture", "out")
        first = replace(self.scalar, provenance=Provenance("import", parents=(art,)))
        self.doc.add_dataset(first)
        other = replace(art, sha256="0" * 64)
        second = replace(first, dataset_id="other", provenance=Provenance("import", parents=(other,)))
        with self.assertRaises(ValueError):
            self.doc.add_dataset(second)
        self.assertEqual(self.doc.records()[1], (first,))
        self.assertEqual(self.doc.artifact(art.artifact_id), art)


class TaskContractTests(unittest.TestCase):
    def test_resource_envelope_and_per_attempt_sequence(self):
        budget = ResourceBudget(2, 4, 8000)
        self.assertEqual(budget.total_threads, 8)
        for kwargs in ({"processes": True}, {"total_memory_mb": -1}, {"threads_per_process": 0}):
            with self.assertRaises(ValueError):
                replace(budget, **kwargs)
        error = ErrorInfo("missing.input", "file not supplied")
        event = TaskEvent("t", "a", 0, datetime.now(timezone.utc), "notice", "import", error=error)
        self.assertIsNone(event.error.retryable)
        self.assertIsNone(event.progress)
        replace(event, sequence=2, progress=0.0).check_after(event)
        for newer in (event, replace(event, task_id="u", sequence=1), replace(event, attempt_id="b", sequence=1)):
            with self.assertRaises(ValueError):
                newer.check_after(event)
        for kwargs in ({"sequence": -1}, {"progress": float("nan")}, {"progress": 1.01},
                       {"timestamp": datetime(2026, 1, 1)}, {"progress": True}):
            with self.assertRaises(ValueError):
                replace(event, **kwargs)

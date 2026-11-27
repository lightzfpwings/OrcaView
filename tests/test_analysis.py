"""M6 analysis-contract and synthetic result regressions."""

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from orcaview.analysis import (
    HIRSHFELD_CHARGE,
    AnalysisRequest,
    WavefunctionRef,
    adapt_hirshfeld_fixture,
    check_capability,
)
from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.provenance import ArtifactRef, Provenance
from orcaview.core.snapshots import SelectionContext
from orcaview.core.tasks import ResourceBudget


class AnalysisContractTests(unittest.TestCase):
    def setUp(self):
        self.session = Session()
        self.document = self.session.document
        self.base = self.document.head
        self.source_parent = ArtifactRef.from_bytes(b"synthetic conversion source", "orca-out")
        self.frame = self.document.add_frame(
            self.base.ref, "test-source", self.base.molecule, self.base.atom_ids,
            Provenance("synthetic-source", parents=(self.source_parent,)),
        )
        self.wavefunction = WavefunctionRef(
            artifact=ArtifactRef.from_bytes(b"synthetic metadata only", "molden", "absent.molden"),
            geometry=self.frame.ref,
            geometry_sha256=self.frame.content_hash,
            atom_ids=self.frame.atom_ids[::-1],
            provenance=self.frame.provenance,
            source_unit="angstrom",
            basis_convention="spherical",
            has_basis=True,
            has_orbitals=True,
            has_occupations=True,
            spin_type="restricted",
            has_ecp=False,
            densities=("total",),
            periodic=False,
        )
        self.request = AnalysisRequest(
            capability_id=HIRSHFELD_CHARGE.capability_id,
            wavefunction=self.wavefunction,
            density="total",
        )
        self.fixture = ArtifactRef.from_bytes(b'{"synthetic_fixture": true}', "orcaview.synthetic-json")

    def adapt(self, values=(0.0, 0.1, -0.1), *, request=None, snapshot=None, missing_reason=None):
        return adapt_hirshfeld_fixture(
            self.request if request is None else request, self.frame if snapshot is None else snapshot,
            self.fixture, values,
            missing_reason=missing_reason,
        )

    def assert_issue(self, request, code, *, snapshot=None):
        checked = check_capability(request, snapshot or self.frame)
        self.assertFalse(checked.available)
        self.assertIn(code, {issue.code for issue in checked.issues})
        self.assertTrue(all(issue.reason for issue in checked.issues))

    def test_public_contract_import_does_not_load_native_library_or_start_worker(self):
        code = """
import sys

def fail_on_runtime_effect(event, args):
    if event in ('ctypes.dlopen', 'subprocess.Popen', 'os.posix_spawn', 'os.fork', 'os.system'):
        raise AssertionError(event)

sys.addaudithook(fail_on_runtime_effect)
from orcaview.analysis import AnalysisRequest, WavefunctionRef
assert WavefunctionRef.contract_version == AnalysisRequest.contract_version == 1
"""
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_valid_metadata_reports_internal_engine_unavailable(self):
        self.assert_issue(self.request, "internal_engine_unavailable")
        checked = check_capability(self.request, self.frame)
        self.assertEqual(checked.capability, HIRSHFELD_CHARGE)
        self.assertEqual(tuple(issue.code for issue in checked.issues), ("internal_engine_unavailable",))

    def test_missing_metadata_unsupported_format_and_periodic_input_report_reasons(self):
        cases = (
            (replace(self.wavefunction, has_occupations=None), "metadata_missing"),
            (replace(self.wavefunction, periodic=True), "periodic_unsupported"),
            (replace(self.wavefunction, artifact=self.source_parent), "input_unsupported"),
        )
        for wavefunction, code in cases:
            with self.subTest(code=code):
                request = replace(self.request, wavefunction=wavefunction)
                self.assert_issue(request, code)
                with self.assertRaises(ValueError):
                    self.adapt(request=request)

    def test_unknown_feature_and_future_version_are_rejected(self):
        for request, code in (
            (replace(self.request, capability_id="unregistered-analysis"), "unknown_capability"),
            (replace(self.request, feature_version=self.request.feature_version + 1), "feature_version_unsupported"),
        ):
            with self.subTest(code=code):
                self.assert_issue(request, code)
                with self.assertRaises(ValueError):
                    self.adapt(request=request)

    def test_known_unsupported_evidence_and_multiworker_budget_are_rejected(self):
        for source in (
            replace(self.wavefunction, has_basis=False),
            replace(self.wavefunction, has_ecp=True),
            replace(self.wavefunction, densities=("spin",)),
        ):
            with self.subTest(source=source):
                self.assert_issue(replace(self.request, wavefunction=source), "input_unsupported")
        self.assert_issue(replace(self.request, density="spin"), "input_unsupported")
        self.assert_issue(replace(self.request, resources=ResourceBudget(2, 1, 128)), "resource_unsupported")

    def test_paths_and_hashes_have_distinct_roles(self):
        with self.assertRaises(ValueError):
            replace(self.wavefunction, artifact=ArtifactRef("molden", "unknown-content.molden"))
        for fixture in (ArtifactRef("orcaview.synthetic-json"), self.source_parent):
            with self.subTest(fixture_format=fixture.format), self.assertRaises(ValueError):
                adapt_hirshfeld_fixture(self.request, self.frame, fixture, (0.1, 0.0, -0.1))
        self.assertEqual(self.adapt().datasets[0].provenance.parents[0], self.wavefunction.artifact)

    def test_atom_mapping_rejects_duplicates_unknown_ids_and_incomplete_coverage(self):
        a, b, c = self.frame.atom_ids
        with self.assertRaises(ValueError):
            replace(self.wavefunction, atom_ids=(a, a, b))
        for atoms in ((a, b), (a, c, "not-an-atom-in-this-document")):
            with self.subTest(atoms=atoms):
                request = replace(self.request, wavefunction=replace(self.wavefunction, atom_ids=atoms))
                self.assert_issue(request, "atom_mapping_mismatch")
                with self.assertRaises(ValueError):
                    self.adapt(request=request)

    def test_content_hash_alone_does_not_authorize_rebinding_to_editable_head(self):
        newer = self.document.publish_revision(self.base.ref, self.base.molecule, self.base.atom_ids)
        self.assertEqual(newer.content_hash, self.frame.content_hash)
        self.assert_issue(self.request, "geometry_mismatch", snapshot=newer)
        with self.assertRaises(ValueError):
            self.adapt(snapshot=newer)
        self.assertEqual(self.adapt().datasets[0].geometry, self.frame.ref)
        self.assertEqual(self.document.head, newer)
        self.assertEqual(self.document.records()[1], ())

    def test_false_geometry_hash_blocks_even_the_correct_geometry_reference(self):
        unverified = replace(self.wavefunction, geometry_sha256="b" * 64)
        request = replace(self.request, wavefunction=unverified)
        self.assert_issue(request, "geometry_mismatch")
        with self.assertRaises(ValueError):
            self.adapt(request=request)

    def test_complete_payload_keeps_unit_density_axis_and_original_provenance(self):
        result = self.adapt()
        data, = result.datasets
        self.assertEqual(result.task.status, "synthetic-fixture")
        self.assertEqual((data.kind, data.dtype, data.unit, data.shape), ("hirshfeld-charge", "float64", "e", (3,)))
        self.assertEqual((data.method, data.density, data.geometry), ("Hirshfeld", self.request.density, self.frame.ref))
        self.assertEqual((data.axes[0].kind, data.axes[0].ids), ("atom", self.wavefunction.atom_ids))
        self.assertEqual(data.values, (0.0, 0.1, -0.1))
        self.assertEqual(data.valid_mask, (True, True, True))
        self.assertIsNone(data.missing_reason)
        self.assertIsNone(data.array_ref)
        self.assertIn("synthetic-fixture", data.quality)
        self.assertEqual(data.provenance.parents, (self.wavefunction.artifact, self.fixture, self.source_parent))
        expected = {
            "synthetic_fixture": "true",
            "capability_id": self.request.capability_id,
            "feature_version": str(self.request.feature_version),
            "wavefunction_sha256": self.wavefunction.artifact.sha256,
            "geometry_sha256": self.frame.content_hash,
            "density": self.request.density,
            "task_id": result.task.task_id,
        }
        parameters = dict(data.provenance.parameters)
        self.assertEqual({key: parameters.get(key) for key in expected}, expected)

    def test_matching_provenance_artifact_deduplicates_but_conflicting_artifact_is_rejected(self):
        artifact = self.wavefunction.artifact
        provenance = replace(self.wavefunction.provenance, parents=(artifact, self.source_parent))
        source = replace(self.wavefunction, provenance=provenance)
        request = replace(self.request, wavefunction=source)
        data = self.adapt(request=request).datasets[0]
        self.assertEqual(data.provenance.parents, (artifact, self.fixture, self.source_parent))

        conflicting_artifact = replace(artifact, sha256="0" * 64)
        conflicting_source = replace(source, provenance=replace(provenance, parents=(conflicting_artifact,)))
        with self.assertRaises(ValueError):
            self.adapt(request=replace(request, wavefunction=conflicting_source))

    def test_partial_and_whole_missing_keep_distinct_forms_without_zero_fill(self):
        partial = self.adapt((0.0, None, 0.2), missing_reason="Synthetic row omitted").datasets[0]
        whole = self.adapt(None, missing_reason="Synthetic array omitted").datasets[0]
        self.assertEqual(partial.values, (0.0, None, 0.2))
        self.assertEqual(partial.valid_mask, (True, False, True))
        self.assertEqual(partial.missing_reason, "Synthetic row omitted")
        self.assertEqual(whole.shape, partial.shape)
        self.assertEqual(whole.axes, partial.axes)
        self.assertIsNone(whole.values)
        self.assertIsNone(whole.valid_mask)
        self.assertEqual(whole.missing_reason, "Synthetic array omitted")

    def test_inconsistent_missing_shape_or_nonfinite_values_are_rejected(self):
        for values, reason in (
            (None, None), ((0.2, None, 0.1), None), ((0.2, 0.0, 0.1), "unexpected reason"),
            ((0.0, -0.1), None), ((0.0, -0.1, float("nan")), None),
        ):
            with self.subTest(values=values, reason=reason), self.assertRaises(ValueError):
                self.adapt(values, missing_reason=reason)

    def test_project_reopens_and_sorted_rows_find_source_frame_instead_of_head(self):
        data = self.adapt((0.0, None, -0.2), missing_reason="Synthetic row omitted").datasets[0]
        self.document.add_dataset(data)
        a, b, c = self.base.molecule.atoms
        a_id, b_id, c_id = self.base.atom_ids
        edited = self.document.publish_revision(
            self.base.ref, replace(self.base.molecule, atoms=(b, c, a)), (b_id, c_id, a_id),
        )
        with TemporaryDirectory() as directory:
            project = Path(directory) / "analysis.oview.json"
            save_project(self.session, project)
            reopened = load_project(project).document

        self.assertEqual(reopened.records(), self.document.records())
        loaded_data = reopened.dataset(data.dataset_id)
        stored_frame = reopened.resolve(loaded_data.geometry)
        self.assertEqual(stored_frame, self.frame)
        self.assertEqual(reopened.head, edited)
        self.assertEqual(reopened.artifact(self.fixture.artifact_id), self.fixture)
        rows = sorted(zip(loaded_data.axes[0].ids, loaded_data.values), key=lambda row: stored_frame.index_of(row[0]))
        self.assertEqual(rows, [(a_id, -0.2), (b_id, None), (c_id, 0.0)])
        selection = SelectionContext(loaded_data.geometry, tuple(atom_id for atom_id, _ in rows))
        self.assertEqual(selection.indices(stored_frame), (0, 1, 2))
        self.assertEqual(tuple(reopened.head.index_of(atom_id) for atom_id in selection.atom_ids), (2, 0, 1))
        with self.assertRaises(ValueError):
            selection.indices(reopened.head)

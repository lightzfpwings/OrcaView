"""M5 result-import regressions using synthetic ORCA-style text."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orcaview.application.document import MoleculeDocument
from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.core.models import Atom, CalculationSpec, Molecule
from orcaview.core.snapshots import SelectionContext
from orcaview.orca.output import OutputSummary, parse_output
from orcaview.results import OrcaImportError, commit_orca_output, inspect_orca_output


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "m5_orca" / "water-sp.out"


class NativeResultsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.text = FIXTURE.read_text(encoding="utf-8")

    def source(self, text=None, *, name="water-sp.out"):
        path = self.directory / name
        if text is None:
            path.write_bytes(FIXTURE.read_bytes())
        else:
            path.write_text(text, encoding="utf-8")
        return path

    def assert_rejected(self, inspection, code, *, document=None):
        self.assertFalse(inspection.importable)
        self.assertIn(code, {issue.code for issue in inspection.issues})
        with self.assertRaises(OrcaImportError) as failure:
            commit_orca_output(inspection, document=document)
        self.assertIn(code, {issue.code for issue in failure.exception.issues})

    def change_line(self, fragment, replacement=None):
        lines = self.text.splitlines(keepends=True)
        index = next(i for i, line in enumerate(lines) if fragment in line)
        lines[index:index + 1] = [] if replacement is None else [replacement + "\n"]
        return "".join(lines)

    def test_publish_scalar_and_atomic_values_on_exact_source_frame(self):
        source = self.source()
        inspection = inspect_orca_output(source)
        self.assertTrue(inspection.importable, inspection.issues)
        self.assertEqual(inspection.issues, ())
        self.assertEqual(inspection.artifact.sha256, sha256(source.read_bytes()).hexdigest())
        self.assertEqual(inspection.artifact.path_hint, str(source.resolve()))
        evidence = inspection.evidence
        self.assertEqual(evidence.program_version, "6.1.1")
        self.assertIs(evidence.normal_termination, True)
        self.assertIs(evidence.scf_converged, True)
        self.assertIsNone(evidence.optimization_converged)
        self.assertIn("FINAL SINGLE POINT ENERGY", source.read_text().splitlines()[evidence.energy_line - 1])

        imported = commit_orca_output(inspection)
        document, frame = imported.document, imported.frame
        self.assertIsNotNone(frame.ref.frame_id)
        self.assertEqual(frame.parent, document.head.ref)
        self.assertEqual(frame.source_unit, "angstrom")
        self.assertEqual(frame.molecule.atoms, evidence.atoms)
        self.assertEqual(frame.molecule.atoms, (
            Atom("O", 0, 0, 0), Atom("H", 0.758602, 0, 0.586541), Atom("H", -0.758602, 0, 0.586541),
        ))
        self.assertEqual((frame.molecule.charge, frame.molecule.multiplicity), (0, 1))
        self.assertEqual(len(set(frame.atom_ids)), 3)
        self.assertEqual(document.resolve(frame.ref), frame)
        self.assertEqual(document.artifact(inspection.artifact.artifact_id), inspection.artifact)
        self.assertIn(inspection.artifact, frame.provenance.parents)

        energy, charges = imported.datasets
        self.assertEqual((energy.kind, energy.unit, energy.shape, energy.axes), ("energy", "hartree", (), ()))
        self.assertEqual(energy.values, (-76.123456789012,))
        self.assertEqual((charges.kind, charges.unit, charges.shape), ("mulliken-charge", "e", (3,)))
        self.assertEqual(charges.axes[0].kind, "atom")
        self.assertEqual(charges.axes[0].ids, frame.atom_ids)
        self.assertEqual(charges.values, (-0.42, 0.2, 0.22))
        self.assertEqual(charges.valid_mask, (True, True, True))
        self.assertEqual(SelectionContext(charges.geometry, charges.axes[0].ids[::-1]).indices(frame), (2, 1, 0))
        for dataset in imported.datasets:
            self.assertEqual(dataset.geometry, frame.ref)
            self.assertIn(inspection.artifact, dataset.provenance.parents)
            self.assertIsNotNone(dataset.provenance.producer_version)
            self.assertEqual(document.dataset(dataset.dataset_id), dataset)

    def test_project_reopens_after_edit_without_accessing_original_out(self):
        source = self.source()
        imported = commit_orca_output(inspect_orca_output(source))
        document, frame = imported.document, imported.frame
        head = document.head
        new_head = document.publish_revision(head.ref, replace(head.molecule, atoms=head.molecule.atoms[::-1]),
                                             head.atom_ids[::-1])
        session = Session.from_document(document, CalculationSpec(), str(source))
        project_path = self.directory / "results.oview.json"
        save_project(session, project_path)
        source.unlink()

        reopened = load_project(project_path).document
        self.assertEqual(reopened.records(), document.records())
        self.assertEqual(reopened.head, new_head)
        for dataset in imported.datasets:
            restored = reopened.dataset(dataset.dataset_id)
            self.assertEqual(restored, dataset)
            self.assertEqual(reopened.resolve(restored.geometry), frame)
            self.assertNotEqual(restored.geometry, reopened.head.ref)

    def test_explicit_historical_revision_is_valid_after_editing_head_moves(self):
        source = self.source()
        atoms = inspect_orca_output(source).evidence.atoms
        doc = MoleculeDocument.from_molecule(Molecule(source.stem, atoms))
        initial = doc.head
        inspection = inspect_orca_output(source, document=doc, target=initial.ref)
        self.assertTrue(inspection.importable, inspection.issues)
        self.assertEqual(inspection.target, initial.ref)
        self.assertEqual(inspection.atom_ids, initial.atom_ids)
        changed = doc.publish_revision(initial.ref, replace(initial.molecule, atoms=atoms[::-1]), initial.atom_ids[::-1])
        before = doc.records()
        imported = commit_orca_output(inspection, document=doc)
        self.assertEqual(doc.records(), before)
        self.assertIsNot(imported.document, doc)
        self.assertEqual(imported.base_records, before)
        self.assertEqual(imported.document.head, changed)
        self.assertEqual(imported.frame.parent, initial.ref)
        self.assertEqual(imported.frame.atom_ids, initial.atom_ids)
        self.assertEqual(imported.datasets[1].axes[0].ids, initial.atom_ids)

    def test_publication_failure_after_first_dataset_does_not_change_original(self):
        source = self.source()
        atoms = inspect_orca_output(source).evidence.atoms
        doc = MoleculeDocument.from_molecule(Molecule("Water", atoms))
        inspection = inspect_orca_output(source, document=doc, target=doc.head.ref)
        before = doc.records()
        add_dataset = MoleculeDocument.add_dataset
        published = []

        def fail_second_dataset(candidate, dataset):
            if dataset.kind == "mulliken-charge":
                raise ValueError("synthetic publication failure")
            add_dataset(candidate, dataset)
            published.append((candidate, candidate.resolve(dataset.geometry), dataset))

        with patch.object(MoleculeDocument, "add_dataset", fail_second_dataset):
            with self.assertRaises(OrcaImportError) as failure:
                commit_orca_output(inspection, document=doc)
        self.assertIn("publication_failed", {issue.code for issue in failure.exception.issues})
        self.assertEqual(len(published), 1)
        candidate, frame, energy = published[0]
        self.assertIsNot(candidate, doc)
        self.assertEqual(energy.geometry, frame.ref)
        self.assertEqual(doc.records(), before)

    def test_retry_against_already_imported_revision_preserves_candidate(self):
        source = self.source()
        atoms = inspect_orca_output(source).evidence.atoms
        doc = MoleculeDocument.from_molecule(Molecule("Water", atoms))
        inspection = inspect_orca_output(source, document=doc, target=doc.head.ref)
        imported = commit_orca_output(inspection, document=doc)
        candidate = imported.document
        before = candidate.records()
        with self.assertRaises(OrcaImportError) as failure:
            commit_orca_output(inspection, document=candidate)
        self.assertIn("already_imported", {issue.code for issue in failure.exception.issues})
        self.assertEqual(candidate.records(), before)

    def test_commit_uses_reparsed_evidence(self):
        inspection = inspect_orca_output(self.source())
        altered = replace(inspection, evidence=replace(inspection.evidence, energy_hartree=-1.0))
        imported = commit_orca_output(altered)
        self.assertEqual(imported.datasets[0].values, (-76.123456789012,))


    def test_association_checks_order_coordinates_electronic_state_and_reference(self):
        source = self.source()
        atoms = inspect_orca_output(source).evidence.atoms
        water = Molecule(source.stem, atoms)
        cases = (
            (replace(water, atoms=atoms[::-1]), "atom_order_mismatch"),
            (replace(water, atoms=(replace(atoms[0], x=atoms[0].x + 0.02),) + atoms[1:]), "coordinates_mismatch"),
            (replace(water, multiplicity=3), "electronic_state_mismatch"),
        )
        for molecule, code in cases:
            with self.subTest(code=code):
                doc = MoleculeDocument.from_molecule(molecule)
                before = doc.records()
                same_name = inspect_orca_output(source, document=doc, target=doc.head.ref)
                self.assert_rejected(same_name, code, document=doc)
                self.assertEqual(doc.records(), before)

        doc = MoleculeDocument.from_molecule(water)
        other = MoleculeDocument.from_molecule(water)
        foreign_target = inspect_orca_output(source, document=doc, target=other.head.ref)
        self.assert_rejected(foreign_target, "target_unavailable", document=doc)
        inspection = inspect_orca_output(source, document=doc, target=doc.head.ref)
        with self.assertRaises(OrcaImportError) as failure:
            commit_orca_output(inspection, document=other)
        self.assertIn("target_unavailable", {issue.code for issue in failure.exception.issues})
        self.assertEqual(len(doc.records()[0]), 1)
        self.assertEqual(len(other.records()[0]), 1)

    def test_changed_source_rejects_commit_and_preserves_original_document(self):
        source = self.source()
        atoms = inspect_orca_output(source).evidence.atoms
        doc = MoleculeDocument.from_molecule(Molecule("Water", atoms))
        inspection = inspect_orca_output(source, document=doc, target=doc.head.ref)
        self.assertTrue(inspection.importable, inspection.issues)
        before, original = doc.records(), source.read_bytes()
        source.write_bytes(original + b"\nSynthetic file changed after inspection.\n")
        with self.assertRaises(OrcaImportError) as failure:
            commit_orca_output(inspection, document=doc)
        self.assertIn("source_changed", {issue.code for issue in failure.exception.issues})
        self.assertEqual(doc.records(), before)
        source.write_bytes(original)
        self.assertEqual(commit_orca_output(inspection, document=doc).frame.parent, doc.head.ref)
        self.assertEqual(doc.records(), before)

    def test_unverified_same_stem_companions_are_never_grouped(self):
        source = self.source()
        self.source('{"geometry":"unrelated"}', name="water-sp.property.json")
        self.source("Unrelated GBW bytes", name="water-sp.gbw")
        inspection = inspect_orca_output(source)
        imported = commit_orca_output(inspection)
        self.assertEqual(imported.frame.provenance.parents, (inspection.artifact,))
        for dataset in imported.datasets:
            self.assertEqual(dataset.provenance.parents, (inspection.artifact,))

    def test_termination_and_scf_evidence_are_independent_and_do_not_come_from_input_echo(self):
        cases = (
            ("truncated", self.text.split("****ORCA TERMINATED NORMALLY****", 1)[0],
             None, True, "incomplete_output"),
            ("explicit failure", self.change_line("ORCA TERMINATED NORMALLY", "ORCA finished by error termination"),
             False, True, "abnormal_termination"),
            ("explicit nonconvergence", self.change_line("SCF CONVERGED AFTER", "* SCF NOT CONVERGED *"),
             True, False, "scf_unconverged"),
            ("echoed success", self.change_line("SCF CONVERGED AFTER", "| 7> # SCF CONVERGED AFTER 8 CYCLES"),
             True, None, "missing_scf_convergence"),
        )
        for case, raw, normal, scf, code in cases:
            with self.subTest(case=case):
                inspection = inspect_orca_output(self.source(raw))
                self.assert_rejected(inspection, code)
                self.assertIs(inspection.evidence.normal_termination, normal)
                self.assertIs(inspection.evidence.scf_converged, scf)
                self.assertIsNone(inspection.evidence.optimization_converged)

    def test_rejects_unknown_version_unsupported_task_and_ambiguous_job_evidence(self):
        cases = (
            (self.text.replace("6.1.1", "7.0.0"), "unsupported_version"),
            (self.change_line("Program Version"), "missing_version"),
            (self.text.replace("Single Point Calculation", "Geometry Optimization"), "unsupported_task"),
            (self.text * 2, "multiple_jobs"),
            (self.text + "\nSCF ITERATIONS\n", "multiple_jobs"),
            (self.text + "\nFINAL SINGLE POINT ENERGY -45.0\n", "ambiguous_energy"),
        )
        for raw, code in cases:
            with self.subTest(code=code):
                self.assert_rejected(inspect_orca_output(self.source(raw)), code)

    def test_rejects_ambiguous_units_and_disagreement_between_geometry_tables(self):
        cases = (
            (self.text.replace("ANGSTROEM", "FURLONG"), "unsupported_geometry_unit"),
            (self.text.replace("1.433550", "1.433600", 1), "conflicting_geometry"),
            (self.change_line("FINAL SINGLE POINT ENERGY", "FINAL SINGLE POINT ENERGY -76.2 eV"), "invalid_energy"),
            (self.change_line("FINAL SINGLE POINT ENERGY", "FINAL SINGLE POINT ENERGY -1E999"), "invalid_energy"),
        )
        for raw, code in cases:
            with self.subTest(code=code):
                self.assert_rejected(inspect_orca_output(self.source(raw)), code)

    def test_required_data_absent_or_conflicting_cannot_publish(self):
        no_state = self.change_line("Multiplicity           Mult").replace("|  2> * xyz 0 1\n", "")
        wrong_state = self.change_line("Multiplicity           Mult", " Multiplicity  Mult .... 3")
        start = self.text.index("CARTESIAN COORDINATES (A.U.)")
        end = self.text.index("SHARK INTEGRAL PACKAGE", start)
        angstrom_only = self.text[:start] + self.text[end:]
        unverified_count = "\n".join(line for line in angstrom_only.splitlines() if "Number of atoms" not in line)
        self.assertTrue(inspect_orca_output(self.source(angstrom_only)).importable)
        cases = (
            (self.change_line("FINAL SINGLE POINT ENERGY"), "missing_energy"),
            (no_state, "missing_electronic_state"),
            (wrong_state, "conflicting_electronic_state"),
            (unverified_count, "missing_atom_count"),
        )
        for raw, code in cases:
            with self.subTest(code=code):
                self.assert_rejected(inspect_orca_output(self.source(raw)), code)

    def test_optional_mulliken_absence_or_bad_indices_produce_explicit_missing_dataset(self):
        before, after = self.text.split("MULLIKEN ATOMIC CHARGES", 1)
        after = after.split("Sum of atomic charges:    0.0000000\n", 1)[1]
        without_mulliken = before + after
        cases = (
            ("no table", without_mulliken),
            ("wrong element", self.change_line("1 H :", "   1 O : 0.2")),
            ("repeated index", self.change_line("1 H :", "   2 H : 0.2")),
            ("total conflicts with rows", self.change_line("1 H :", "   1 H : 0.3")),
        )
        for case, raw in cases:
            with self.subTest(case=case):
                inspection = inspect_orca_output(self.source(raw))
                self.assertTrue(inspection.importable, inspection.issues)
                imported = commit_orca_output(inspection)
                energy, missing = imported.datasets
                self.assertEqual(energy.values, (-76.123456789012,))
                self.assertEqual(missing.geometry, imported.frame.ref)
                self.assertEqual(missing.axes[0].ids, imported.frame.atom_ids)
                self.assertIsNone(missing.values)
                self.assertIsNone(missing.valid_mask)
                self.assertTrue(missing.missing_reason)

    def test_legacy_api_remains_a_limited_summary(self):
        summary = parse_output("SCF CONVERGED AFTER 3 CYCLES\n"
                               "FINAL SINGLE POINT ENERGY -7.5D+01\n"
                               "****ORCA TERMINATED NORMALLY****\n")
        self.assertIsInstance(summary, OutputSummary)
        self.assertEqual(summary, OutputSummary(True, None, True, -75.0, "completed", ()))


if __name__ == "__main__":
    unittest.main()

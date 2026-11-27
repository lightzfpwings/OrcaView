"""Exercise real ORCA logs through the desktop reader and portable project format."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.gui.result_import import read_native_session
from orcaview.orca.log_report import LogReport

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "artifacts/public/validation/ORCA-6.1.1-macOS-arm64"
SPECTRA = ROOT / "artifacts/public/validation/results-0.1.0a12"


class LogImportTests(unittest.TestCase):
    def test_hirshfeld_charges_and_spins_match_the_printed_atom_table(self):
        source = ROOT / "artifacts/public/validation/results-grid-0.1.0a22/water-hirshfeld.out"
        session = read_native_session(source)
        populations = {d.kind: d for d in session.document.records()[1] if d.method == "Hirshfeld"}
        charges = populations["hirshfeld-charge"]
        self.assertEqual(charges.values, (-.333873, .166938, .166938))
        self.assertEqual(populations["hirshfeld-spin"].values, (0., 0., 0.))
        self.assertEqual(charges.axes[0].ids, session.document.resolve(charges.geometry).atom_ids)
        self.assertEqual(charges.provenance.parents, (session.log_report.source,))
        text = source.read_text()
        with tempfile.TemporaryDirectory() as tmp:
            damaged = Path(tmp) / "water.out"
            for original, replacement in (("0 O   -0.333873", "0 H   -0.333873"),
                                          ("TOTAL   0.000004", "TOTAL   1.000004")):
                self.assertIn(original, text)
                damaged.write_text(text.replace(original, replacement))
                result = read_native_session(damaged)
                self.assertFalse(any(d.method == "Hirshfeld" for d in result.document.records()[1]))

    def test_optfreq_uses_converged_frame_and_retains_original_optimization_history(self):
        session = read_native_session(REAL / "optfreq/job.out")
        self.assertIsInstance(session, Session)
        oxygen = session.molecule.atoms[0]
        self.assertAlmostEqual(oxygen.z, -.009906)
        report = session.log_report
        first = report.properties[0]
        self.assertEqual(first.value, -76.321268537024)
        self.assertEqual(len([p for p in report.properties if p.label == first.label]), 5)
        self.assertEqual(report.spectra[0].rows[0][1], 1637.65)
        charges = next(d for d in session.document.records()[1] if d.kind == "mulliken-charge")
        self.assertEqual(charges.values[0], -.293615)
        frame = session.document.resolve(charges.geometry)
        self.assertEqual(charges.axes[0].ids, frame.atom_ids)
        self.assertEqual(frame.molecule.atoms[0], oxygen)

    def test_nmr_project_roundtrips_offline_and_rejects_cross_source_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "water.log"
            source.write_bytes((SPECTRA / "nmr/water-shield.out").read_bytes())
            session = read_native_session(source)
            report = session.log_report
            shields, coupling = report.spectra
            self.assertEqual(shields.rows[2][:3], (0, "O", 347.078))
            self.assertEqual(coupling.rows, (("1 H", "2 H", -15.538),))
            self.assertEqual(replace(session).log_report, report)
            project = Path(tmp) / "water.oview.json"
            save_project(session, project)
            source.unlink()
            self.assertEqual(load_project(project).log_report, report)
            raw = json.loads(project.read_bytes())
            self.assertEqual(raw["schema_version"], 7)
            raw["log_report"]["source"]["sha256"] = "c" * 64
            project.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_project(project)

    def test_compound_energies_show_both_steps_without_claiming_one_geometry(self):
        report = read_native_session(REAL / "compound-wb97m2/job.out")
        self.assertIsInstance(report, LogReport)
        self.assertIn('multiple-job', report.status)
        energies = report.properties[:2]
        self.assertEqual({(p.context, p.value) for p in energies},
                         {('Job 1', -76.429725928501), ('Job 2', -76.468167713548)})
        self.assertEqual(report.spectra, ())

    def test_file_fragment_with_observed_result_does_not_create_a_molecule(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fragment.log"
            path.write_text("| 1> # FINAL SINGLE POINT ENERGY -900\nFINAL SINGLE POINT ENERGY -12.25\n")
            report = read_native_session(path)
            self.assertIsInstance(report, LogReport)
            self.assertEqual([(p.line, p.value) for p in report.properties], [(2, -12.25)])
            self.assertIn('Normal termination not recorded', report.status)

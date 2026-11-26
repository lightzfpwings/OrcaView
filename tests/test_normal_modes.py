"""Source association, matrix transposition and persistence of ORCA normal modes."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orcaview.application.project import load_project, save_project
from orcaview.cli_io import load_session
from orcaview.core.provenance import ArtifactRef
from orcaview.orca import log_report


VALIDATION = Path(log_report.__file__).resolve().parents[3] / "artifacts" / "public" / "validation"
RAMAN = VALIDATION / "results-0.1.0a12" / "raman" / "water.out"
OPTFREQ = VALIDATION / "ORCA-6.1.1-macOS-arm64" / "optfreq" / "job.out"


def report(text):
    return log_report.parse_log_report(text, ArtifactRef.from_bytes(text.encode(), "orca-out"))


class NormalModeParsingTests(unittest.TestCase):
    def test_real_block_columns_match_xyz_components_for_each_atom(self):
        group, = report(RAMAN.read_text()).normal_modes
        self.assertEqual((group.geometry_line, group.frequency_line, group.source_line), (211, 925, 942))
        self.assertEqual([atom.element for atom in group.atoms], ["O", "H", "H"])
        self.assertEqual([(mode.index, mode.frequency) for mode in group.modes],
                         [(6, 1791.17), (7, 3956.30), (8, 4046.70)])
        self.assertEqual(group.modes[0].displacements, ((-.000003, 0., -.070067),
                                                        (-.433977, 0., .556066),
                                                        (.434020, 0., .556032)))
        self.assertEqual(group.modes[-1].displacements[1], (.558029, 0., .431426))
        lines = RAMAN.read_text().splitlines()
        self.assertEqual(lines[group.modes[0].source_line - 1].split(), ["6", "7", "8"])

    def test_optfreq_uses_the_final_optimized_structure(self):
        group, = report(OPTFREQ.read_text()).normal_modes
        self.assertEqual(group.geometry_line, 2328)
        self.assertAlmostEqual(group.atoms[0].z, -.009906, places=6)
        self.assertEqual([m.frequency for m in group.modes], [1637.65, 3787.02, 3882.00])

    def test_imaginary_and_rounded_zero_frequencies_keep_their_nonzero_vectors(self):
        text = RAMAN.read_text().replace("1791.17 cm**-1", "-1791.17 cm**-1 ***imaginary mode***")
        text = text.replace("3956.30 cm**-1", "0.00 cm**-1")
        group, = report(text).normal_modes
        self.assertEqual([(m.index, m.frequency) for m in group.modes[:2]], [(6, -1791.17), (7, 0.)])

    def test_bohr_only_and_displaced_numerical_frequency_output(self):
        raw = RAMAN.read_text()
        start, end = raw.index("CARTESIAN COORDINATES (ANGSTROEM)"), raw.index("CARTESIAN COORDINATES (A.U.)")
        bohr, = report(raw[:start] + raw[end:]).normal_modes
        self.assertAlmostEqual(bohr.atoms[1].x, .758602, places=6)
        # Some verbose numerical outputs include a displaced coordinates table
        # during the finite differences, after the numerical-frequency driver starts.
        text = raw.replace("VIBRATIONAL FREQUENCIES", raw[start:end].replace("0.758602", "2.558602")
                           + "\nVIBRATIONAL FREQUENCIES")
        group, = report(text).normal_modes
        self.assertEqual(group.atoms[1].x, .758602)

    def test_no_guess_for_missing_geometry_conflicts_truncation_or_duplicate_columns(self):
        raw = RAMAN.read_text()
        lines = raw.splitlines()
        matrix = lines[941:970]
        bad = [
            "\n".join(lines[924:]),
            raw.replace("   1 H     1.0000", "   1 O     1.0000"),
            raw.replace("6          7          8", "6          6          8"),
            "\n".join(lines[:941] + matrix[:-6]),
            "\n".join(lines[:941] + [s for s in matrix if "0.556032" not in s]),
            raw.replace("0.556032", "********"),
        ]
        for i, damaged in enumerate(bad):
            with self.subTest(case=i):
                self.assertFalse(report(damaged).normal_modes)
                self.assertTrue(report(damaged).spectra)

    def test_sections_do_not_share_coordinates_or_displacement_matrices(self):
        raw = RAMAN.read_text().splitlines()
        structures = raw[210:226]
        spectra = raw[924:971]
        joined = "\n".join(["COMPOUND JOB 1", *structures, *spectra,
                            "COMPOUND JOB 2", *spectra, "COMPOUND JOB 3", *structures, *spectra])
        first, last = report(joined).normal_modes
        self.assertEqual((first.title, last.title), ("Job 1 · Vibrational frequencies",
                                                    "Job 3 · Vibrational frequencies"))
        self.assertEqual(joined.splitlines()[last.frequency_line - 1], "VIBRATIONAL FREQUENCIES")
        self.assertGreater(last.source_line, first.modes[-1].source_line)

    def test_project_reopens_without_external_log_and_rejects_damaged_modes(self):
        with TemporaryDirectory() as temp:
            log = Path(temp, "input.out")
            target = Path(temp, "vibrations.oview.json")
            log.write_bytes(RAMAN.read_bytes())
            session = load_session(log)
            save_project(session, target)
            log.unlink()
            self.assertEqual(load_project(target).log_report, session.log_report)
            data = json.loads(target.read_text())
            self.assertEqual(data["schema_version"], 14)
            data["log_report"]["normal_modes"][0]["modes"][0]["displacements"].pop()
            target.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "geometry"):
                load_project(target)
            data["schema_version"] = 13
            target.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "unknown fields"):
                load_project(target)
            del data["log_report"]["normal_modes"]
            target.write_text(json.dumps(data))
            self.assertEqual(load_project(target).log_report.normal_modes, ())

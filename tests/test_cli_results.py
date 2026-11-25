"""Machine-readable result and spectrum exports through the application entry point."""

import csv
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import orcaview
from orcaview.application.project import save_project
from orcaview.gui.result_demo import build_result_demo


class ResultsCommandsTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / "history.oview.json"
        self.session, self.dataset_id = build_result_demo()
        save_project(self.session, self.project)
        self.raw = self.root / "ir.log"
        self.raw.write_text(
            "IR SPECTRUM\n-----------\nMode freq eps Int T**2 TX TY TZ\n"
            "   1:  1000.0  0.01 2.0  1.0  0.2  0.3  0.4\n"
            "   2:  1100.0  0.02 1.0  2.0  0.1  0.5  0.3\n"
            "\n****ORCA TERMINATED NORMALLY****\n", encoding="utf-8")

    def invoke(self, *args, no_qt=True):
        env = dict(os.environ, PYTHONPATH=str(Path(orcaview.__file__).resolve().parents[1]),
                   QT_QPA_PLATFORM="offscreen")
        cmd = [sys.executable, "-B", *(["-S"] if no_qt else []), "-m", "orcaview", *map(str, args)]
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)

    def test_dataset_uses_actual_frame_and_stable_atom_ids(self):
        p = self.invoke("results", self.project)
        self.assertEqual(p.returncode, 0, p.stderr)
        items = json.loads(p.stdout)
        self.assertIn(self.dataset_id, [data["id"] for data in items["datasets"]])
        ds = self.session.document.dataset(self.dataset_id)
        frame = self.session.document.resolve(ds.geometry)
        p = self.invoke("results", self.project, "--dataset", self.dataset_id, "--format", "csv")
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = list(csv.DictReader(StringIO(p.stdout)))
        self.assertEqual([r["id"] for r in rows], list(frame.atom_ids))
        self.assertEqual([r["value (e)"] for r in rows], ["-0.2", "", "0.0"])
        self.assertEqual([r["value_status"] for r in rows], ["available", "missing", "available"])
        self.assertNotEqual(frame.atom_ids, self.session.document.head.atom_ids)
        p = self.invoke("results", self.project, "--evidence")
        self.assertTrue(any(s["path_hint"] == "synthetic-charges.json" and s["sha256"]
                            for s in json.loads(p.stdout)))

    def test_log_only_and_numeric_csv_without_renderer(self):
        p = self.invoke("results", self.raw, "--all")
        self.assertEqual(p.returncode, 0, p.stderr)
        inventory = json.loads(p.stdout)
        self.assertFalse(inventory["geometries"])
        self.assertEqual(inventory["log_report"]["spectra"][0]["source_line"], 1)
        p = self.invoke("spectrum", self.raw)
        self.assertEqual(json.loads(p.stdout)[0]["kind"], "ir")
        out = self.root / "curve.csv"
        p = self.invoke("spectrum", self.raw, "--table", "ir", "--format", "curve", "--fwhm", 8,
                        "--range", 980, 1130, "--points", 401, "--normalize", "--shape", "pseudo-voigt",
                        "--mix", .75, "-o", out)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, "")
        with out.open(encoding="utf-8", newline="") as stream:
            rows = csv.reader(stream)
            self.assertEqual(next(rows), ["Wavenumber (cm⁻¹)", "Relative height"])
            curve = [(float(x), float(y)) for x, y in rows]
        self.assertEqual((curve[0][0], curve[-1][0]), (980., 1130.))
        self.assertAlmostEqual(max(y for x, y in curve), 1.)
        before = out.read_bytes()
        p = self.invoke("spectrum", self.raw, "--format", "curve", "--fwhm", 0, "-o", out)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(before, out.read_bytes())
        p = self.invoke("spectrum", self.raw, "--format", "sticks")
        self.assertEqual(list(csv.reader(StringIO(p.stdout)))[1:], [["1000.0", "2.0"], ["1100.0", "1.0"]])

    def test_quiet_offscreen_spectrum_export(self):
        try:
            import PySide6
        except ImportError:
            self.skipTest("Requires optional Qt renderer")
        out = self.root / "ir.png"
        p = self.invoke("spectrum", self.raw, "--format", "png", "--table", 1, "--no-reverse",
                        "--no-grid", "--layers", "curve", "--color", "#45AA22", "--stroke-width", 5,
                        "-o", out, no_qt=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, "")
        header = out.read_bytes()[:24]
        self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(int.from_bytes(header[16:20], "big"), 1800)
        self.assertEqual(int.from_bytes(header[20:24], "big"), 1100)

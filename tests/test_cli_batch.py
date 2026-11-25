"""Exercise real CLI argument parsing in a Python environment without Qt or a display."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import orcaview


ROOT = Path(orcaview.__file__).resolve().parents[2]


class BatchCliTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), ORCAVIEW_HEADLESS="1",
                        ORCAVIEW_CONFIG_DIR=str(self.root / "prefs"))
        self.env.pop("DISPLAY", None)
        self.env.pop("WAYLAND_DISPLAY", None)

    def invoke(self, *args, status=0):
        result = subprocess.run([sys.executable, "-B", "-S", "-m", "orcaview", *map(str, args)],
                                cwd=self.root, env=self.env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, status, result.stderr.decode(errors="replace"))
        return result.stdout

    def test_project_configuration_and_atomic_input_output(self):
        project = self.root / "water.oview.json"
        source = ROOT / "examples/water.xyz"
        self.invoke("project", source, "--job", "OPT", "--cores", "1", "--set", "scf.MaxIter=80",
                    "-o", project)
        preview = self.invoke("preview", project)
        self.assertIn(b" Opt", preview)
        self.assertIn(b"MaxIter 80", preview)
        destination = self.root / "job.inp"
        self.invoke("preview", project, "--set", "scf.MaxIter=120", "-o", destination)
        self.assertIn(b"MaxIter 120", destination.read_bytes())
        self.assertEqual(self.invoke("preview", project), preview)
        before = destination.read_bytes()
        self.invoke("preview", project, "--cores", "0", "-o", destination, status=2)
        self.assertEqual(destination.read_bytes(), before)
        self.assertIn(b"0.758602", self.invoke("project", project, "--format", "xyz", "-o", "-"))
        self.invoke("project", project, "--cores", "2", "-o", project)
        self.assertIn(b"nprocs 2", self.invoke("preview", project))
        legacy = self.root / "native.inp"
        native_bytes = b"\xef\xbb\xbf! HF\r\n# mixed\n"
        legacy.write_bytes(native_bytes)
        self.assertEqual(self.invoke("native-input", legacy), native_bytes)
        self.invoke("preview", project, "-o", project, status=2)

    def test_preferences_and_window_skip_without_site_packages(self):
        sample = ROOT / "color-packs" / "contrast.json"
        current = json.loads(self.invoke("settings", "appearance", "--model", "stick",
                                         "--import-palette", sample, "--bond-scale", "1.5"))
        self.assertEqual(current["settings"]["palette_id"], "contrast")
        self.assertEqual(current, json.loads(self.invoke("settings", "appearance")))
        self.invoke("settings", "appearance", "--atom-scale", "10", status=2)
        self.assertEqual(json.loads(self.invoke("settings", "appearance")), current)
        langs = json.loads(self.invoke("settings", "language", "--directory", ROOT / "language-packs",
                                       "--locale", "zh-Hans"))
        self.assertEqual(langs["locale"], "zh-Hans")
        self.assertEqual(self.invoke("gui", "unavailable.xyz"), b"")
        self.assertEqual(json.loads(self.invoke("settings", "language")), langs)

    def test_project_fixture_import_preserves_frame_data(self):
        project = self.root / "result.oview.json"
        self.invoke("project", ROOT / "examples/m5_orca/water-sp.out", "-o", project)
        self.assertGreaterEqual(len(json.loads(self.invoke("results", project))["geometries"]), 2)

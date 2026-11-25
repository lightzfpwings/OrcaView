import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from orcaview.application.project import load_project
from orcaview.cli import main
from orcaview.core.resource_defaults import ResourceAssessment


class CliResourceDefaultsTest(unittest.TestCase):
    def invoke(self, *arguments):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(list(map(str, arguments))), 0)
        return output.getvalue()

    def test_host_recommendation_is_separate_from_input_defaults(self):
        host = ResourceAssessment(32, 32 * 1024)
        with patch("orcaview.core.resource_defaults.detect_resources", return_value=host) as detect:
            report = json.loads(self.invoke("resources"))
            for flags, cores, memory in (((), 16, 4096), (("--cores", 12), 12, 4096),
                                         (("--maxcore", 6144), 16, 6144)):
                with self.subTest(flags=flags):
                    lines = self.invoke("preview", *flags).splitlines()
                    self.assertIn(f"  nprocs {cores}", lines)
                    self.assertIn(f"%maxcore {memory}", lines)
            detect.assert_called_once_with()
        self.assertEqual(report["target"], {"cores": 16, "maxcore_mb": 4096})
        self.assertEqual(report["recommended"], {"cores": 6, "maxcore_mb": 4096, "total_mb": 24576})

    def test_saved_overrides_survive_reopen_and_reset_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "saved.json"
            self.invoke("project", "--new", "water", "--cores", 40, "--maxcore", 8123, "-o", project)
            for flags, cores, memory in (((), 40, 8123), (("--cores", 2), 2, 8123),
                                         (("--maxcore", 2048), 40, 2048),
                                         (("--reset-calculation",), 16, 4096),
                                         (("--reset-calculation", "--cores", 8), 8, 4096)):
                with self.subTest(flags=flags):
                    lines = self.invoke("preview", project, *flags).splitlines()
                    self.assertIn(f"  nprocs {cores}", lines)
                    self.assertIn(f"%maxcore {memory}", lines)
            saved = load_project(project).calculation
            self.assertEqual((saved.cores, saved.maxcore_mb), (40, 8123))

    def test_design_project_from_raw_geometry_uses_fixed_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "carbon.xyz"
            source.write_text("1\nCarbon\nC 0 0 0\n", encoding="utf-8")
            project = Path(tmp) / "design.json"
            self.invoke("design", source, "-o", project)
            spec = load_project(project).calculation
            self.assertEqual((spec.cores, spec.maxcore_mb), (16, 4096))

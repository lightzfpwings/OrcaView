"""Desktop gating and real background output through the public command line."""

import contextlib
import io
import os
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orcaview import cli_render
from orcaview.cli import main

try:
    from PySide6.QtGui import QImage
except ImportError:
    QImage = None


class DisplayCommandTests(unittest.TestCase):
    def run_cli(self, *args):
        stderr, stdout = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            result = main(list(map(str, args)))
        return result, stdout.getvalue(), stderr.getvalue()

    @unittest.skipUnless(QImage, "Requires Qt raster support")
    def test_thumbnail_fits_both_sketch_labels(self):
        with TemporaryDirectory() as temp, patch.dict(os.environ, {"ORCAVIEW_CONFIG_DIR": temp}):
            source, output = Path(temp, "pair.xyz"), Path(temp, "thumbnail.png")
            source.write_text("2\nPair\nN -1.4 0 0\nO 1.4 0 0\n", encoding="utf-8")
            self.assertEqual(self.run_cli("render", source, output, "--view", "2d", "--width", 88,
                                          "--height", 80, "--transparent"), (0, "", ""))
            image = QImage(str(output))
            self.assertEqual((image.width(), image.height()), (88, 80))
            colors = {image.pixelColor(x, y).name() for x in range(88) for y in range(80)}
            self.assertIn("#3265a7", colors)
            self.assertIn("#b84138", colors)

    def test_headless_display_skips_without_opening_input_or_qt(self):
        for system, env in (("linux", {}), ("linux", {"DISPLAY": ":5", "QT_QPA_PLATFORM": "offscreen"}),
                            ("darwin", {"SSH_CONNECTION": "remote"}), ("darwin", {"ORCAVIEW_HEADLESS": "1"})):
            with self.subTest(system=system, env=env), patch.object(sys, "platform", system), \
                    patch.dict(os.environ, env, clear=True), patch.object(cli_render, "_qt_worker") as qt:
                self.assertEqual(self.run_cli("gui", "missing.xyz", "--workspace", "result"), (0, "", ""))
                qt.assert_not_called()

    def test_bad_native_backend_skips_display_but_an_image_reports_failure(self):
        aborted = subprocess.CompletedProcess([], -6, stdout=b"", stderr=b"Platform plugin missing")
        with patch.object(cli_render, "_desktop_candidate", return_value=True), \
                patch.object(cli_render, "_qt_worker", return_value=aborted):
            self.assertEqual(self.run_cli("gui", "missing.xyz"), (0, "", ""))
            result, stdout, stderr = self.run_cli("render", "example.xyz", "figure.png")
            self.assertEqual((result, stdout), (2, ""))
            self.assertIn("offscreen", stderr)
            self.assertIn("Platform plugin", stderr)

    def test_renderer_timeout_does_not_leave_a_batch_waiting(self):
        with patch.dict(os.environ, {"ORCAVIEW_RENDER_TIMEOUT": "20"}), \
                patch.object(cli_render, "_qt_worker", side_effect=subprocess.TimeoutExpired([], 20)):
            result, _, stderr = self.run_cli("gui", "--screenshot", "figure.png")
            self.assertEqual(result, 2)
            self.assertIn("timed out after 20 seconds", stderr)

    def test_rendering_with_no_qt_installation(self):
        command = [sys.executable, "-B", "-S", "-m", "orcaview.cli_render"]
        env = dict(os.environ, PYTHONPATH=str(Path(cli_render.__file__).resolve().parents[1]))
        with patch.object(cli_render, "_worker_command", return_value=(command, env)):
            result, stdout, stderr = self.run_cli("render", "example.xyz", "figure.png")
            self.assertEqual((result, stdout), (2, ""))
            self.assertIn("renderer could not be loaded", stderr)

    @unittest.skipUnless(QImage, "Requires Qt offscreen renderer")
    def test_background_images_with_no_desktop_and_invalid_interactive_plugin(self):
        with TemporaryDirectory() as temp, patch.dict(os.environ, {"ORCAVIEW_HEADLESS": "1",
                    "QT_QPA_PLATFORM": "invalid-plugin", "DISPLAY": "", "WAYLAND_DISPLAY": ""}):
            root = Path(temp)
            source = root / "water.xyz"
            source.write_text("3\nwater\nO 0 0 0\nH .95 0 0\nH -.25 .92 0\n")
            output = root / "water.png"
            self.assertEqual(self.run_cli("render", source, output, "--width", 320, "--height", 240,
                                          "--scale", 2, "--transparent", "--rotate", "x:30", "--labels"), (0, "", ""))
            image = QImage(str(output))
            self.assertEqual((image.width(), image.height()), (640, 480))
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
            self.assertTrue(any(image.pixelColor(x, y).alpha() for x in range(20, 620, 4) for y in range(20, 460, 4)))
            custom = root / "color.json"
            custom.write_text('{"id":"ruby","name":"Ruby","colors":{"O":"#CC00CC"}}')
            vector = root / "sketch.pdf"
            self.assertEqual(self.run_cli("render", source, vector, "--view", "2d", "--color-pack", custom), (0, "", ""))
            self.assertTrue(vector.read_bytes().startswith(b"%PDF-"))
            screenshot = root / "window.png"
            self.assertEqual(self.run_cli("gui", source, "--screenshot", screenshot,
                                          "--workspace", "design", "--model", "stick", "--select", 1, 2), (0, "", ""))
            self.assertGreater(struct.unpack(">II", screenshot.read_bytes()[16:24])[0], 1000)
            original = output.read_bytes()
            result, _, error = self.run_cli("render", source, output, "--palette", "missing-pack")
            self.assertEqual(result, 2)
            self.assertIn("Unknown color pack", error)
            self.assertEqual(original, output.read_bytes())

    @unittest.skipUnless(QImage, "Requires Qt offscreen renderer")
    def test_gui_workspace_controls_and_empty_project_capture(self):
        from orcaview.application.project import save_project
        from orcaview.application.session import Session
        from orcaview.core.models import Molecule
        from orcaview.gui.result_demo import build_result_demo

        with TemporaryDirectory() as temp, patch.dict(os.environ, {"ORCAVIEW_HEADLESS": "1"}):
            project = Path(temp) / "result.oview.json"
            output = Path(temp) / "result.png"
            session, dataset_id = build_result_demo()
            save_project(session, project)
            self.assertEqual(self.run_cli("gui", project, "--dataset", dataset_id, "--screenshot", output,
                                          "--show-panel", "navigation", "--hide-panel", "inspector",
                                          "--bottom-tab", "log", "--rotation-step", 30,
                                          "--window-size", 1200, 850), (0, "", ""))
            self.assertEqual(struct.unpack(">II", output.read_bytes()[16:24]), (1200, 850))
            self.assertEqual(self.run_cli("gui", project, "--snapshot", session.document.head.ref.snapshot_id,
                                          "--screenshot", output), (0, "", ""))
            save_project(Session(molecule=Molecule("empty draft", (), bonds_explicit=True)), project)
            self.assertEqual(self.run_cli("gui", project, "--workspace", "result", "--screenshot", output), (0, "", ""))

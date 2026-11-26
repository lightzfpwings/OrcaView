"""Exercise the headless vibrational animation command on printed ORCA modes."""

from contextlib import redirect_stderr, redirect_stdout
from importlib.util import find_spec
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import orcaview
from orcaview.cli import main


ROOT = Path(orcaview.__file__).resolve().parents[2]
VALIDATION = ROOT / "artifacts/public/validation"
WATER = VALIDATION / "ORCA-6.1.1-macOS-arm64/optfreq/job.out"


def command(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(["vibration", *map(str, args)])
    return code, stdout.getvalue(), stderr.getvalue()


class VibrationCommandTests(unittest.TestCase):
    def test_rejects_invalid_parameters_and_output_type_before_render(self):
        for suffix, flags in (("gjf", []), ("gif", ["--amplitude", "nan"]), ("mp4", ["--speed", "0"])):
            with self.subTest(suffix=suffix, flags=flags):
                code, output, error = command(WATER, f"motion.{suffix}", "--mode", 8, *flags)
                self.assertEqual((code, output), (2, ""))
                self.assertTrue(error)

    @unittest.skipUnless(find_spec("PySide6"), "requires Qt offscreen support")
    def test_multiple_calculations_require_explicit_group_and_printed_mode(self):
        with TemporaryDirectory() as temp:
            target = Path(temp) / "mode.mp4"
            target.write_bytes(b"retain original")
            source = Path(temp) / "two-water-jobs.out"
            source.write_bytes(WATER.read_bytes() * 2)
            for flags, message in (((), "--group"), (("--group", 3), "1 to 2"),
                                   (("--group", 2, "--mode", 0), "mode 0")):
                with self.subTest(flags=flags):
                    code, output, error = command(source, target, "--mode", 8, *flags)
                    self.assertEqual((code, output), (2, ""))
                    self.assertIn(message, error)
                    self.assertEqual(target.read_bytes(), b"retain original")

    @unittest.skipUnless(find_spec("PySide6") and find_spec("imageio_ffmpeg"), "requires Qt and movie encoder")
    def test_raw_gif_and_reopened_project_mp4_are_animated(self):
        import imageio_ffmpeg
        from PySide6.QtGui import QImageReader
        from orcaview.application.project import save_project
        from orcaview.cli_io import load_session

        with TemporaryDirectory() as temp:
            gif = Path(temp) / "water.gif"
            self.assertEqual(command(WATER, gif, "--mode", 8, "--speed", "2.5", "--rotate", "y:45"),
                             (0, "", ""))
            reader = QImageReader(str(gif), b"gif")
            self.assertEqual(reader.imageCount(), 10)
            self.assertEqual(reader.loopCount(), -1)
            first = reader.read()
            self.assertEqual((first.width(), first.height()), (1280, 960))
            self.assertNotEqual(reader.read(), first)

            project = Path(temp) / "water.oview.json"
            save_project(load_session(WATER), project)
            movie = Path(temp) / "water.mp4"
            self.assertEqual(command(project, movie, "--group", 1, "--mode", 6, "--speed", 3,
                                     "--amplitude", .52, "--rotate", "x:65"), (0, "", ""))
            frames = imageio_ffmpeg.read_frames(str(movie))
            try:
                metadata = next(frames)
                self.assertEqual(metadata["size"], (1280, 960))
                self.assertEqual(metadata["fps"], 25)
                self.assertEqual(metadata["codec"], "h264")
                self.assertNotEqual(next(frames), next(frames))
            finally:
                frames.close()

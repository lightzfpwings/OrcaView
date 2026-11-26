"""User-facing animation export, phase and destination handling."""

from importlib.util import find_spec
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import orcaview


@unittest.skipUnless(find_spec("PySide6") and find_spec("imageio_ffmpeg"), "requires Qt and FFmpeg")
class AnimationExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from orcaview.gui.result_import import read_native_session

        cls.app = QApplication.instance() or QApplication([])
        root = Path(orcaview.__file__).resolve().parents[2]
        path = root / "artifacts/public/validation/ORCA-6.1.1-macOS-arm64/optfreq/job.out"
        cls.groups = read_native_session(path).log_report.normal_modes

    def setUp(self):
        from orcaview.gui.normal_mode_dialog import NormalModeDialog

        self.dialog = NormalModeDialog(self.groups)
        self.addCleanup(self.dialog.close)
        self.dialog.show()
        self.app.processEvents()
        self.dialog.viewport.rotate_view("x", 75)
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def test_export_menu_writes_a_playable_loop_and_preserves_paused_pose(self):
        from PySide6.QtGui import QImageReader
        from orcaview.gui import normal_mode_export as export

        dialog = self.dialog
        dialog.play.setChecked(False)
        dialog._phase = .7
        dialog.amplitude.setValue(.42)
        dialog.speed.setValue(1.5)
        positions = dialog.viewport._local_positions
        camera = dialog.viewport._camera
        output = self.folder / "water.gif"
        with patch.object(export.QFileDialog, "exec", return_value=1), \
             patch.object(export.QFileDialog, "selectedFiles", return_value=[str(output)]):
            dialog.export_button.menu().actions()[0].trigger()
        reader = QImageReader(str(output))
        self.assertEqual(reader.format().data(), b"gif")
        self.assertEqual(reader.loopCount(), -1)
        self.assertEqual(reader.imageCount(), 17)
        first = reader.read()
        self.assertEqual(max(first.width(), first.height()), 1280)
        self.assertEqual(reader.nextImageDelay(), 40)
        self.assertNotEqual(reader.read(), first)
        self.assertIs(dialog.viewport._local_positions, positions)
        self.assertEqual(dialog.viewport._camera, camera)
        self.assertEqual(dialog._phase, .7)
        self.assertFalse(dialog.play.isChecked())

    def test_cancel_and_encoder_failure_preserve_existing_animation(self):
        from orcaview.gui.normal_mode_export import save_mode_animation

        target = self.folder / "existing.mp4"
        target.write_bytes(b"existing movie")
        result = save_mode_animation(self.dialog.viewport, target, amplitude=.35, speed=1.,
                                     progress=lambda done, count: done < 2)
        self.assertFalse(result)
        with patch("orcaview.gui.normal_mode_movie.write_movie", side_effect=OSError("encoding error")):
            with self.assertRaisesRegex(OSError, "encoding error"):
                save_mode_animation(self.dialog.viewport, target, amplitude=.35, speed=1.)
        self.assertEqual(target.read_bytes(), b"existing movie")
        self.assertEqual(list(self.folder.iterdir()), [target])

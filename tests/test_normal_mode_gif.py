"""Decode exported GIFs with Qt's independent reader to check motion and timing."""

from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


@unittest.skipUnless(find_spec("PySide6") and find_spec("imageio_ffmpeg"), "requires Qt and the movie encoder")
class NormalModeGifTests(unittest.TestCase):
    def test_moving_frames_preserve_background_color_delay_and_loop(self):
        from PySide6.QtGui import QColor, QImage, QImageReader, QPainter
        from orcaview.gui.normal_mode_movie import write_movie

        centers = (10, 25, 40, 25)
        background = QColor("#faf8f5")
        atom = QColor("#d84237")

        def frames():
            for x in centers:
                image = QImage(52, 30, QImage.Format.Format_RGB32)
                image.fill(background)
                painter = QPainter(image)
                painter.fillRect(x - 3, 12, 7, 7, atom)
                painter.end()
                yield image

        with TemporaryDirectory() as directory:
            path = Path(directory) / "mode.gif"
            write_movie(path, frames(), 25)
            reader = QImageReader(str(path), b"gif")
            self.assertTrue(reader.canRead(), reader.errorString())
            self.assertEqual(reader.imageCount(), len(centers))
            self.assertEqual(reader.loopCount(), -1)
            for x in centers:
                decoded = reader.read()
                self.assertFalse(decoded.isNull(), reader.errorString())
                self.assertEqual((decoded.width(), decoded.height()), (52, 30))
                self.assertEqual(reader.nextImageDelay(), 40)
                for sample in set(centers):
                    color = decoded.pixelColor(sample, 15)
                    expected = atom if sample == x else background
                    for actual, reference in zip(color.getRgb(), expected.getRgb()):
                        self.assertLessEqual(abs(actual - reference), 3)

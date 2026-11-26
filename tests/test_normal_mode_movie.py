"""Exercise the packaged H.264 stream and report native encoder failures."""

from importlib.util import find_spec
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest


@unittest.skipUnless(find_spec("PySide6") and find_spec("imageio_ffmpeg"), "requires Qt and the movie encoder")
class NormalModeMovieTests(unittest.TestCase):
    def test_mp4_roundtrip_frame_order_color_and_timebase(self):
        from imageio_ffmpeg import get_ffmpeg_exe
        from PySide6.QtGui import QColor, QImage, QPainter
        from orcaview.gui.normal_mode_movie import write_movie

        width, height = 82, 60
        positions = (20, 40, 60, 40, 20)

        def frames():
            for x in positions:
                image = QImage(width, height, QImage.Format.Format_RGB32)
                image.fill(QColor("white"))
                painter = QPainter(image)
                painter.fillRect(x - 5, 21, 10, 10, QColor("#bf3325"))
                painter.end()
                yield image

        with TemporaryDirectory() as temp:
            movie = Path(temp) / "project mode 7.mp4"
            write_movie(movie, frames(), 25)
            result = subprocess.run(
                [get_ffmpeg_exe(), "-hide_banner", "-i", movie, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                check=True, capture_output=True, timeout=30)
            info = result.stderr.decode(errors="replace")
            self.assertIn("Video: h264", info)
            self.assertIn("yuv420p", info)
            self.assertIn("25 fps", info)
            bytes_per_frame = width * height * 3
            self.assertEqual(len(result.stdout), bytes_per_frame * len(positions))
            for i, x in enumerate(positions):
                for sample in set(positions):
                    offset = i * bytes_per_frame + (25 * width + sample) * 3
                    red, green, blue = result.stdout[offset:offset + 3]
                    if sample == x:
                        self.assertGreater(red, green + 70)
                        self.assertGreater(red, blue + 70)
                    else:
                        self.assertGreater(min(red, green, blue), 235)

    def test_invalid_frames_and_canceled_source(self):
        from PySide6.QtGui import QImage
        from orcaview.gui.normal_mode_movie import write_movie

        image = QImage(24, 24, QImage.Format.Format_RGB32)
        image.fill(0)

        def interrupted():
            yield image
            raise InterruptedError("stop")

        with TemporaryDirectory() as temp:
            path = Path(temp) / "staged.mp4"
            with self.assertRaisesRegex(InterruptedError, "stop"):
                write_movie(path, interrupted(), 24)
            for frames, fps in (([], 24), ([image], 0), ([image.copy(0, 0, 23, 12)], 24),
                                ([image, image.copy(0, 0, 20, 20)], 24)):
                with self.subTest(fps=fps), self.assertRaises(ValueError):
                    write_movie(path, frames, fps)

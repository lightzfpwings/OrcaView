"""Stream the vibration viewport's sampled frames to a local video encoder."""

from contextlib import suppress
from itertools import chain
from pathlib import Path
import subprocess
from tempfile import TemporaryFile

from PySide6.QtGui import QImage

from .normal_mode_gif import gif_encoding_args


def write_movie(path, frames, fps):
    """Encode equal-sized QImages into the caller's temporary MP4 or GIF file."""
    path = Path(path)
    if type(fps) is not int or not 1 <= fps <= 100:
        raise ValueError("Movie frame rate must be an integer between 1 and 100.")
    suffix = path.suffix.lower()
    if suffix == ".gif":
        options = gif_encoding_args(fps)
    elif suffix == ".mp4":
        options = ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", "-f", "mp4"]
    else:
        raise ValueError("Choose an MP4 or GIF file.")
    frames = iter(frames)
    first = next(frames, None)
    if first is None or first.isNull():
        raise ValueError("Movie export requires a rendered frame.")
    size = first.size()
    if suffix == ".mp4" and (size.width() % 2 or size.height() % 2):
        raise ValueError("MP4 frame width and height must be even.")

    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        encoder = get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise OSError("The FFmpeg video encoder is unavailable.") from exc
    args = [encoder, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "rawvideo",
            "-pixel_format", "rgba", "-video_size", f"{size.width()}x{size.height()}",
            "-framerate", str(fps), "-i", "pipe:0", "-an", *options, str(path.resolve())]

    # A file lets the encoder report errors while the GUI is writing frames.
    # A second pipe could fill and block both processes on long exports.
    with TemporaryFile() as errors, subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as process:
        try:
            for frame in chain((first,), frames):
                if frame.isNull() or frame.size() != size:
                    raise ValueError("Movie frames must all have the same dimensions.")
                # RGBA8888 is byte-ordered and has no scan-line padding at four bytes per pixel.
                rgba = frame.convertToFormat(QImage.Format.Format_RGBA8888)
                process.stdin.write(rgba.constBits())
        except BrokenPipeError:
            pass  # Read the encoder's own error after it exits.
        except BaseException:
            process.kill()
            raise
        finally:
            with suppress(BrokenPipeError):
                process.stdin.close()
        status = process.wait()
        if status:
            errors.seek(0)
            detail = errors.read(2048).decode("utf-8", errors="replace").strip()
            raise OSError(f"FFmpeg could not encode the movie ({status}). {detail}")

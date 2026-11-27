"""Regenerate the launcher's Windows icon and resource object from the GUI artwork."""

import io
import json
from pathlib import Path
import struct
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image


HERE = Path(__file__).resolve().parent
ARTWORK = HERE.parents[1] / "src/orcaview/gui/assets/orcaview.png"
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def frame(image):
    width, height = image.size
    if width >= 64:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    # Small Shell icons use a bottom-up 32-bit DIB followed by a DWORD-aligned AND mask.
    pixels = image.tobytes("raw", "BGRA", 0, -1)
    mask = image.getchannel("A").point(lambda a: 255 if a == 0 else 0).convert("1")
    header = struct.pack("<IiiHHIIiiII", 40, width, height*2, 1, 32, 0, len(pixels), 0, 0, 0, 0)
    return header + pixels + mask.tobytes("raw", "1", 4*((width+31)//32), -1)


def generate():
    with Image.open(ARTWORK) as source:
        rgba = source.convert("RGBA")
        frames = [frame(rgba.resize((s, s), Image.Resampling.LANCZOS)) for s in SIZES]
    directory = bytearray(struct.pack("<HHH", 0, 1, len(frames)))
    offset = len(directory) + 16*len(frames)
    for size, data in zip(SIZES, frames):
        dimension = size % 256  # zero encodes 256 pixels in an ICO directory
        directory.extend(struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    with TemporaryDirectory(dir=HERE) as temp:
        work = Path(temp)
        icon = work / "OrcaView.ico"
        icon.write_bytes(directory + b"".join(frames))
        # RT_STRING block 1 holds IDs 0..15 as length-prefixed UTF-16 strings.
        display_name = "OrcaView".encode("utf-16le")
        (work / "strings.bin").write_bytes(struct.pack("<HH", 0, len(display_name)//2) + display_name + bytes(28))
        spec = {"RT_GROUP_ICON": {"#1": {"0000": icon.name}}, "RT_STRING": {"#1": {"0000": "strings.bin"}}}
        (work / "resources.json").write_text(json.dumps(spec), encoding="utf-8")
        subprocess.run(["go-winres", "make", "--in", "resources.json", "--arch", "amd64", "--out", "resources"],
                       cwd=work, check=True)
        for name in (icon.name, "resources_windows_amd64.syso"):
            (work / name).replace(HERE / name)


if __name__ == "__main__":
    generate()

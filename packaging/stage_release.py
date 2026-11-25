"""Collect the platform and extension packages into the ordered GitHub release."""

import argparse
from hashlib import file_digest
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from orcaview import __version__


def stage(dist, output):
    prefix = f"OrcaView-{__version__}"
    items = []
    for platform, suffix in (("linux", "Linux-x86_64.tar.gz"), ("windows", "Windows-x64-portable.zip"),
                             ("macos", "macOS-arm64.dmg")):
        source = dist / platform / __version__ / f"{prefix}-{suffix}"
        # GitHub sorts by the filename even when an asset has a display label.
        name = f"{prefix}.{suffix}" if platform == "macos" else source.name
        items.append((source, name))
    for group in ("01-Language", "02-Color"):
        name = f"OrcaView-Extensions-{group}-{__version__}.zip"
        items.append((dist / "extensions" / __version__ / name, name))
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        ready = Path(temporary) / "release"
        ready.mkdir()
        lines = []
        for source, name in items:
            target = ready / name
            shutil.copyfile(source, target)
            with target.open("rb") as stream:
                lines.append(f"{file_digest(stream, 'sha256').hexdigest()}  {name}\n")
        (ready / "SHA256UMS.txt").write_bytes("".join(lines).encode("ascii"))
        ready.rename(output)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--output", type=Path, help="Destination for the new release directory")
    args = parser.parse_args()
    stage(args.dist, args.output or args.dist / "github" / f"v{__version__}")

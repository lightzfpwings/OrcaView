"""Stage the locked source archives for the desktop animation encoders."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen
from zipfile import ZIP_STORED, ZipFile, ZipInfo


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
from orcaview import __version__


def checked_source(name, record, cache, work):
    target = cache / name
    if not target.is_file():
        incoming = work / name
        req = Request(record["url"], headers={"User-Agent": "OrcaView-source-packager"})
        with urlopen(req, timeout=120) as response, incoming.open("wb") as out:
            shutil.copyfileobj(response, out)
        verify(incoming, record["sha256"])
        shutil.copyfile(incoming, target)
    verify(target, record["sha256"])
    return target


def verify(path, expected):
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f"Unexpected SHA-256 for {path.name}")


def add_file(archive, member, source):
    info = ZipInfo(member)
    info.external_attr = 0o100644 << 16
    with archive.open(info, "w") as out, source.open("rb") as incoming:
        shutil.copyfileobj(incoming, out)


def build(output, cache=None):
    manifest = HERE / "encoder_sources.json"
    records = json.loads(manifest.read_text(encoding="utf-8"))["archives"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as folder:
        work = Path(folder)
        cache = cache or work / "sources"
        cache.mkdir(parents=True, exist_ok=True)
        ready = work / "encoder-sources.zip"
        with ZipFile(ready, "w", ZIP_STORED) as archive:
            add_file(archive, "README.md", HERE / "encoder_sources.md")
            add_file(archive, "manifest.json", manifest)
            for name, record in sorted(records.items()):
                add_file(archive, f"sources/{name}", checked_source(name, record, cache, work))
        ready.replace(output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, help="Directory for verified upstream source downloads")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "sources" / __version__ /
                        f"OrcaView-ThirdParty-FFmpeg-{__version__}.zip")
    args = parser.parse_args()
    print(build(args.output, args.cache))

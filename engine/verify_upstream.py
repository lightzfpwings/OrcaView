"""Verify the pinned Multiwfn source archive without extracting or building it."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from zipfile import BadZipFile, ZipFile


VERSION = "2026.11.12"
ARCHIVE_ROOT = f"Multiwfn_{VERSION}_src_Linux"
SHA256 = "f41897accb99d0a7bc1d156ef6a387075f6b2f21acdac0f775db3dccb8424503"
ARCHIVE_SIZE = 3_635_867
ENTRY_COUNT = 78
REQUIRED_MEMBERS = (
    "COMPILATION_METHOD.txt",
    "Makefile",
    "Multiwfn.f90",
    "define.f90",
    "fileIO.f90",
    "function.f90",
    "libreta_hybrid/libreta.f90",
    "noGUI/dislin_d_empty.f90",
    "settings.ini",
)


def verify(path: Path) -> dict:
    # Use the same bytes for validation and ZIP inspection.
    with path.open("rb") as archive:
        contents = archive.read(ARCHIVE_SIZE + 1)
    if len(contents) != ARCHIVE_SIZE:
        raise ValueError(f"archive size must be {ARCHIVE_SIZE} bytes")
    digest = sha256(contents).hexdigest()
    if digest != SHA256:
        raise ValueError(f"unexpected SHA-256 {digest}, expected {SHA256}")

    with ZipFile(BytesIO(contents)) as source:
        members = source.namelist()
        required = {f"{ARCHIVE_ROOT}/{name}" for name in REQUIRED_MEMBERS}
        missing = required.difference(members)
        if missing:
            raise ValueError(f"expected ZIP members missing: {', '.join(sorted(missing))}")
        if len(members) != ENTRY_COUNT:
            raise ValueError(f"expected {ENTRY_COUNT} ZIP entries, found {len(members)}")
        main_program = source.read(f"{ARCHIVE_ROOT}/Multiwfn.f90")
        if VERSION.encode("ascii") not in main_program:
            raise ValueError(f"main program does not report source version {VERSION}")
    return {
        "version": VERSION,
        "sha256": digest,
        "size_bytes": len(contents),
        "entries": len(members),
        "archive_root": ARCHIVE_ROOT,
        "checked_members": list(REQUIRED_MEMBERS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="locally acquired Linux source ZIP")
    args = parser.parse_args()
    try:
        evidence = verify(args.archive)
    except (OSError, ValueError, BadZipFile) as exc:
        print(f"Source verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

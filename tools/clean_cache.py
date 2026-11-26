"""Preview or remove recognized cache files from this OrcaView development checkout."""

import argparse
from importlib.util import MAGIC_NUMBER, source_from_cache
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CODE_DIRS = {"src", "tools", "tests", "packaging", "engine"}
EXCLUDED = {".git", ".venv", "dist", "artifacts", "build"}
FINDER_HEADER = bytes.fromhex("0000000142756431")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def clean(apply):
    if Path(os.fsdecode(git("rev-parse", "--show-toplevel")).rstrip("\n")).resolve() != ROOT:
        raise RuntimeError("Run this script in its OrcaView Git checkout.")
    if not hasattr(os, "fwalk") or not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("This development tool requires POSIX directory file descriptors.")
    tracked = {Path(os.fsdecode(p)) for p in git("ls-files", "-z").split(b"\0") if p}
    directories = {Path(".")}
    for path in tracked:
        if path.parts[0] in CODE_DIRS:
            directories.update(path.parents)
    device = ROOT.stat().st_dev
    # ismount() alone cannot recognize a Linux bind mount on the same filesystem.
    mounts = set()
    if sys.platform.startswith("linux"):
        for line in Path("/proc/self/mountinfo").read_bytes().splitlines():
            point = re.sub(rb"\\([0-7]{3})", lambda m: bytes([int(m[1], 8)]), line.split()[4])
            mounts.add(Path(os.fsdecode(point)))
    count = 0
    for folder, dirs, files, fd in os.fwalk(ROOT, follow_symlinks=False):
        base = Path(folder)
        relative = base.relative_to(ROOT)
        if os.fstat(fd).st_dev != device or (base != ROOT and (".git" in dirs or ".git" in files)):
            dirs.clear()
            continue
        dirs[:] = [name for name in dirs if name.casefold() not in EXCLUDED
                   and not name.casefold().endswith(".app")
                   and (relative / name in directories or name == "__pycache__" and relative in directories)
                   and base / name not in mounts and not os.path.ismount(base / name)]
        for name in sorted(files):
            path = relative / name
            if path in tracked:
                continue
            if name == ".DS_Store":
                header = FINDER_HEADER
            elif relative.name == "__pycache__" and name.endswith(".pyc"):
                try:
                    source = Path(source_from_cache(str(path)))
                except ValueError:
                    continue
                if source not in tracked:
                    continue
                try:
                    if not stat.S_ISREG(os.stat("../" + source.name, dir_fd=fd, follow_symlinks=False).st_mode):
                        continue
                except FileNotFoundError:
                    continue
                header = MAGIC_NUMBER
            else:
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_size <= len(header):
                continue
            # Pin both the directory and the opened file before examining its signature.
            with os.fdopen(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd), "rb") as f:
                if not os.path.samestat(info, os.fstat(f.fileno())) or f.read(len(header)) != header:
                    continue
            if apply:
                if not os.path.samestat(info, os.stat(name, dir_fd=fd, follow_symlinks=False)):
                    continue
                os.unlink(name, dir_fd=fd)
            print(path)
            count += 1
    print(f"{count} file(s) {'removed' if apply else 'eligible (preview)'}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete the displayed types of cache files")
    try:
        clean(parser.parse_args().apply)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")

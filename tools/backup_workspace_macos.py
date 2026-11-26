"""Create and verify a locked recovery snapshot outside the OrcaView checkout."""

import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = Path.home() / "Library/Application Support/OrcaView/Workspace Backups"
CACHE_DIRECTORIES = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def workspace_paths(root, *, exclude=False):
    def visit(directory):
        for path in sorted(directory.iterdir()):
            rel = path.relative_to(root)
            if exclude:
                if rel.parts[0] in {".git", ".venv", "build", ".presentation-build", "htmlcov"}:
                    continue
                if path.name == ".DS_Store" and not any(part.endswith(".app") for part in rel.parts[:-1]):
                    continue
                # A packaged runtime can depend on bytecode or data named like a cache.
                if rel.parts[0] != "dist" and path.name in CACHE_DIRECTORIES:
                    continue
            yield rel
            if not path.is_symlink() and path.is_dir():
                yield from visit(path)
    return list(visit(root))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path):
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        return mode, os.readlink(path)
    if stat.S_ISDIR(mode):
        return mode, None
    if stat.S_ISREG(mode):
        return mode, sha256(path)
    raise ValueError(f"Unsupported file type: {path}")


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd)


def git_state():
    return (git("rev-parse", "HEAD"), git("show-ref", "--head"),
            git("diff", "--cached", "--no-ext-diff", "--binary", "--full-index", "HEAD"))


def backup(destination):
    destination = destination.expanduser().resolve()
    if destination.is_relative_to(ROOT):
        raise ValueError("Choose a backup destination outside the checkout.")
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".creating-", dir=destination) as work:
        work = Path(work)
        ready = work / "snapshot"
        ready.mkdir(mode=0o700)
        state = git_state()
        bundle = ready / "history.bundle"
        git("bundle", "create", str(bundle), "--all", "HEAD")
        if state[2]:
            (ready / "index.patch").write_bytes(state[2])
        archive = ready / "workspace.tar.gz"
        paths = workspace_paths(ROOT, exclude=True)
        subprocess.run(["/usr/bin/tar", "-czf", archive, "--format", "pax", "--no-recursion",
                        "--null", "-T", "-"], cwd=ROOT, check=True,
                       input=b"".join(b"./" + os.fsencode(p) + b"\0" for p in paths))

        # Verify from the finished artifacts, independently of the checkout's Git objects.
        with TemporaryDirectory(prefix="orcaview-restore-check-") as check:
            check = Path(check)
            mirror = check / "history.git"
            git("clone", "--quiet", "--mirror", str(bundle), str(mirror))
            git("fsck", "--full", "--no-dangling", cwd=mirror)
            restored = check / "workspace"
            restored.mkdir()
            subprocess.run(["/usr/bin/tar", "-xpf", archive, "--no-fflags", "-C", restored], check=True)
            if paths != workspace_paths(restored) or paths != workspace_paths(ROOT, exclude=True):
                raise ValueError("Workspace file list changed or the archive is incomplete. Run the backup again.")
            for path in paths:
                if file_record(ROOT / path) != file_record(restored / path):
                    raise ValueError(f"Contents, mode or symlink mismatch: {path}")
            if git_state() != state:
                raise ValueError("Git references or staged changes changed during the backup. Run it again.")

        checksums = ready / "SHA256SUMS.txt"
        checksums.write_text("".join(f"{sha256(p)}  {p.name}\n" for p in sorted(ready.iterdir())),
                             encoding="ascii")
        subprocess.run(["/usr/bin/shasum", "-a", "256", "-c", checksums.name], cwd=ready, check=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot = destination / f"{timestamp}-{work.name.removeprefix('.creating-')}"
        locked = []
        try:
            for path in ready.iterdir():
                path.chmod(0o600)
                os.chflags(path, path.stat().st_flags | stat.UF_IMMUTABLE)
                locked.append(path)
            ready.rename(snapshot)
        except BaseException:
            for path in locked:
                os.chflags(path, path.stat().st_flags & ~stat.UF_IMMUTABLE)
            raise
    return snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This backup uses macOS bsdtar and immutable file flags.")
    try:
        print(backup(args.destination))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Backup failed: {exc}")

"""Stage GBW conversions with the built-in reader or an explicitly supplied ORCA tool."""

from concurrent.futures import CancelledError
import errno
import os
import stat
import subprocess
from tempfile import TemporaryFile
from time import monotonic

from orcaview.orca.gbw_molden import write_gbw_molden


def run_converter(raw, work, converter, cancel=None):
    if converter is None:
        return write_gbw_molden(raw, work / "wave.molden.input", cancel)
    (work / "wave.gbw").write_bytes(raw)
    with TemporaryFile() as log:
        with subprocess.Popen([str(converter), "wave", "-molden"], cwd=work, stdin=subprocess.DEVNULL,
                              stdout=log, stderr=subprocess.STDOUT) as process:
            deadline = monotonic() + 120
            try:
                while process.poll() is None:
                    if cancel is not None and cancel.is_set():
                        raise CancelledError()
                    if monotonic() >= deadline:
                        raise ValueError("orca_2mkl timed out while converting the GBW file.")
                    try:
                        process.wait(timeout=.15)
                    except subprocess.TimeoutExpired:
                        continue
            finally:
                if process.poll() is None:
                    process.kill()
        output = work / "wave.molden.input"
        if process.returncode or not output.is_file() or not output.stat().st_size:
            size = log.tell()
            log.seek(max(0, size - 1000))
            detail = log.read().decode(errors="replace").strip()
            message = "orca_2mkl could not convert the GBW. Check that the ORCA version matches the file."
            raise ValueError(message + ("\n" + detail if detail else ""))
    return output


def file_state(path, *, follow_links=False):
    try:
        entry = path.stat() if follow_links else path.lstat()
    except FileNotFoundError:
        return None
    return entry.st_dev, entry.st_ino, entry.st_ctime_ns, entry.st_size, entry.st_mode


def publish_molden(staged, target, expected):
    if file_state(target) != expected:
        raise ValueError("The destination changed during conversion. Reopen the GBW to choose which file to use.")
    if expected is None:
        # Atomic create-if-absent, including if another opener won the race.
        if os.name == "nt":
            staged.rename(target)
        else:
            try:
                os.link(staged, target)
            except OSError as exc:
                if exc.errno not in (errno.EPERM, errno.EOPNOTSUPP, errno.ENOSYS):
                    raise
                # Removable drives can lack hard links. Reserve the name exclusively
                # before renaming the complete file on the same filesystem.
                with target.open("xb"):
                    pass
                reserved = file_state(target)
                try:
                    staged.replace(target)
                except OSError:
                    if file_state(target) == reserved:
                        target.unlink()
                    raise
    elif stat.S_ISREG(expected[-1]):
        staged.replace(target)
    else:
        raise ValueError("Choose a regular Molden file to replace.")

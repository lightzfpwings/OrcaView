"""POSIX process group lifecycle for a driver launched in a new session."""

import os
from pathlib import Path
import signal
from subprocess import Popen
from time import monotonic, sleep


POLL_SECONDS = 0.05


def group_active(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    # On Linux, an orphan adopted by a slow init can remain in the group
    # as a zombie after all executable processes have stopped.
    proc = Path("/proc")
    if not (proc / "self" / "stat").is_file():
        return True
    try:
        entries = list(proc.iterdir())
    except OSError:
        return True
    found_zombie = False
    for entry in entries:
        if not entry.name.isdecimal():
            continue
        try:
            record = (entry / "stat").read_bytes()
        except OSError:
            continue
        fields = record.rpartition(b")")[2].split()
        if len(fields) >= 3 and fields[2] == str(pgid).encode("ascii"):
            if fields[0] not in (b"Z", b"X"):
                return True
            found_zombie = True
    # If /proc did not reveal any members, keep the conservative killpg result.
    if not found_zombie:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass
        return True
    return False


def terminate_group(process: Popen, grace_seconds: float) -> bool:
    """Escalate a live group and confirm that it has stopped executing."""
    for sig, delay in ((signal.SIGTERM, grace_seconds),
                       (signal.SIGKILL, max(grace_seconds, 1.0))):
        process.poll()
        if process.returncode is not None and not group_active(process.pid):
            return True
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            return False
        deadline = monotonic() + delay
        while monotonic() < deadline:
            if process.poll() is not None and not group_active(process.pid):
                return True
            sleep(POLL_SECONDS)
    return process.poll() is not None and not group_active(process.pid)

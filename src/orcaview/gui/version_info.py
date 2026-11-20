"""Version labels for the running desktop, independent of the Qt backend."""

import platform
import shlex
import sys
from pathlib import Path
from typing import NamedTuple

from orcaview import ORCA_INPUT_TARGET, __version__


class DesktopVersionInfo(NamedTuple):
    platform_name: str
    system_version: str
    software_version: str


def _linux_version():
    # PRETTY_NAME is provided even on systems without lsb_release. Reading
    # os-release directly also works on the project's minimum Python 3.9.
    fields = {}
    for path in (Path("/etc/os-release"), Path("/usr/lib/os-release")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            key, _, value = line.partition("=")
            if key in ("PRETTY_NAME", "NAME", "VERSION_ID"):
                try:
                    fields[key] = " ".join(shlex.split(value))
                except ValueError:
                    continue
        break
    name = fields.get("PRETTY_NAME") or fields.get("NAME") or "Linux"
    version = fields.get("VERSION_ID")
    if version and version not in name:
        return f"{name} {version}"
    if version or any(char.isdigit() for char in name):
        return name
    return f"{name} {platform.release()}"


def _windows_version():
    win = sys.getwindowsversion()
    major, minor, build = win.platform_version or win[:3]
    if win.product_type in (2, 3):  # Domain controller or server, not a client OS.
        name = "Windows Server"
    elif (major, minor) == (10, 0):
        name = "Windows 11" if build >= 22000 else "Windows 10"
    else:
        name = "Windows"
    return f"{name} ({major}.{minor}.{build})"


def desktop_version_info():
    if sys.platform == "darwin":
        name = "macOS"
        version = platform.mac_ver()[0]
        system = f"macOS {version}" if version else f"Darwin {platform.release()}"
    elif sys.platform == "win32":
        name, system = "Windows", _windows_version()
    elif sys.platform.startswith("linux"):
        name, system = "Linux", _linux_version()
    else:
        name = platform.system() or sys.platform
        system = f"{name} {platform.release()}".strip()
    return DesktopVersionInfo(name, system, f"{__version__}/orca{ORCA_INPUT_TARGET}")

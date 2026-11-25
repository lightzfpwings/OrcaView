"""Prepare an update from a verified DMG and replace the installed app on exit."""

import ctypes
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory, mkdtemp
from weakref import finalize

from .update_download import UpdateDownloadError, _check_asset, _check_cancelled, _publish_directory, _read_verified


def _bundle_version(app):
    if app.is_symlink() or not app.is_dir():
        return None
    try:
        with (app / "Contents/Info.plist").open("rb") as fp:
            info = plistlib.load(fp)
        if (info.get("CFBundleIdentifier") == "org.orcaview.desktop"
                and info.get("CFBundleExecutable") == "OrcaView"
                and os.access(app / "Contents/MacOS/OrcaView", os.X_OK)):
            return info.get("CFBundleVersion")
    except (OSError, ValueError, plistlib.InvalidFileException):
        pass
    return None


def current_macos_installation():
    """Use Finder installation when running from a read-only disk image or translocation."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return None
    binary = Path(sys.executable)
    if binary.name != "OrcaView" or binary.parent.name != "MacOS" or binary.parents[1].name != "Contents":
        return None
    app = binary.parents[2]
    if ("AppTranslocation" in app.parts or not _bundle_version(app)
            or not os.access(app.parent, os.W_OK)
            or os.statvfs(app.parent).f_flag & os.ST_RDONLY):
        return None
    return app


def _exchange(first, second):
    # macOS RENAME_SWAP keeps both complete bundles on the same filesystem,
    # including during a second updater's attempt or an unexpected shutdown.
    swap = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True).renamex_np
    swap.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    swap.restype = ctypes.c_int
    if swap(os.fsencode(first), os.fsencode(second), 0x00000002):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def _system(*args):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise UpdateDownloadError(result.stderr.decode(errors="replace").strip() or
                                  "Could not prepare the macOS app update.")


class PreparedMacUpdate:
    def __init__(self, workspace, target, old_identity):
        self.workspace = workspace
        self.target = target
        self.old_identity = old_identity
        self._cleanup = finalize(self, shutil.rmtree, workspace, True)

    def discard(self):
        # A replaced administrator-owned bundle may keep some old files in
        # the private staging directory even after the new app has launched.
        self._cleanup()

    def install_on_exit(self, *, relaunch=True):
        import fcntl

        staged = self.workspace / "OrcaView.app"
        # Lock the parent directory itself. Two app instances cannot exchange
        # the target between the identity check and relaunch.
        fd = os.open(self.target.parent, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (self.target.stat().st_dev, self.target.stat().st_ino) != self.old_identity:
                raise UpdateDownloadError("The installation has changed. Check for updates again.")
            _exchange(staged, self.target)
            try:
                if relaunch:
                    _system("/usr/bin/open", "-n", str(self.target))
            except (OSError, UpdateDownloadError):
                try:
                    _exchange(staged, self.target)
                except OSError as exc:
                    self._cleanup.detach()
                    raise UpdateDownloadError(f"Could not restore the application. The previous version is at {staged}") from exc
                raise
        finally:
            os.close(fd)
        self.discard()


def _stage_app(asset, archive, staged, *, cancelled=None):
    _check_asset(asset)
    suffix = "-macOS-arm64.dmg"
    if not asset.name.endswith(suffix):
        raise UpdateDownloadError("Choose a macOS arm64 disk image.")
    expected = asset.name[len("OrcaView-"):-len(suffix)]
    with TemporaryDirectory(prefix="orcaview-image-") as temp:
        image = Path(temp) / "verified.dmg"
        mount = Path(temp) / "mount"
        mount.mkdir()
        with Path(archive).open("rb") as src, image.open("xb") as dest:
            _read_verified(asset, src, sink=dest, cancelled=cancelled)
        _system("/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-noautoopen",
                "-mountpoint", str(mount), str(image))
        try:
            _check_cancelled(cancelled)
            source = mount / "OrcaView.app"
            if _bundle_version(source) != expected:
                raise UpdateDownloadError("The app version in the disk image does not match the release.")
            _system("/usr/bin/ditto", str(source), str(staged))
        finally:
            _system("/usr/bin/hdiutil", "detach", str(mount))
        _system("/usr/bin/codesign", "--verify", "--deep", "--strict", str(staged))
        _check_cancelled(cancelled)


def prepare_macos_update(asset, archive, target, *, cancelled=None):
    target = Path(target)
    if not _bundle_version(target):
        raise UpdateDownloadError("Could not identify the OrcaView app to replace.")
    old = target.stat()
    workspace = Path(mkdtemp(prefix=".orcaview-update-", dir=target.parent))
    try:
        _stage_app(asset, archive, workspace / "OrcaView.app", cancelled=cancelled)
        return PreparedMacUpdate(workspace, target, (old.st_dev, old.st_ino))
    except BaseException:
        shutil.rmtree(workspace, ignore_errors=True)
        raise


def install_macos(asset, archive, directory):
    """Install the verified bundle into the specified directory without opening Finder."""
    directory = Path(directory)
    target = directory if directory.suffix.lower() == ".app" else directory / "OrcaView.app"
    if os.path.lexists(target):
        prepared = prepare_macos_update(asset, archive, target)
        try:
            prepared.install_on_exit(relaunch=False)
        finally:
            prepared.discard()
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".orcaview-install-", dir=target.parent) as temp:
            staged = Path(temp) / "OrcaView.app"
            _stage_app(asset, archive, staged)
            _publish_directory(staged, target)
    return target

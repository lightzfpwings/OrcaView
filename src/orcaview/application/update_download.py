"""Download verified OrcaView Releases and install the portable desktop bundles."""

from dataclasses import dataclass
import hashlib
import json
from http.client import HTTPException
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory, mkdtemp
import time
from urllib.error import HTTPError
from urllib.request import Request
import zipfile
from uuid import uuid4

from . import portable_replace
from .portable_replace import current_portable_installation
from .updates import RELEASES_URL, UpdateAsset, open_update_url


class UpdateDownloadError(RuntimeError):
    """An update could not be downloaded, verified or installed."""


class UpdateCancelled(UpdateDownloadError):
    """The user cancelled the active operation."""


_BLOCK = 256 * 1024
_PACKAGE = re.compile(r"OrcaView-([A-Za-z0-9.+_-]+)-(?:macOS-arm64\.dmg|Windows-x64(?:-portable)?\.zip|Linux-x86_64\.tar\.gz)")
_BAD_ASSET = "The update package information is invalid."
_BAD_HASH = "The installer's SHA-256 does not match the release."
_BAD_SIZE = "The installer size does not match the release."
_BAD_ARCHIVE = "The portable package contents are invalid."
_FILE_EXISTS = "A file with this name already exists. Choose another folder."
_INSTALL_EXISTS = "An installation folder with this name already exists. Choose another folder."


def _check_cancelled(cancelled):
    if cancelled is not None and cancelled():
        raise UpdateCancelled("Update canceled.")


def _check_asset(asset):
    match = _PACKAGE.fullmatch(asset.name)
    if not match or asset.size <= 0 or not re.fullmatch(r"[0-9a-fA-F]{64}", asset.sha256):
        raise UpdateDownloadError(_BAD_ASSET)
    version = match[1]
    if asset.url not in (f"{RELEASES_URL}/download/{version}/{asset.name}",
                         f"{RELEASES_URL}/download/v{version}/{asset.name}"):
        raise UpdateDownloadError(_BAD_ASSET)


def _read_verified(asset, source, *, sink=None, progress=None, cancelled=None):
    digest = hashlib.sha256()
    received = 0
    if progress:
        progress(0, asset.size)
    # A single socket read keeps the cancel button responsive on slow transfers.
    read_chunk = getattr(source, "read1", source.read)
    while True:
        _check_cancelled(cancelled)
        chunk = read_chunk(_BLOCK)
        if not chunk:
            break
        received += len(chunk)
        if received > asset.size:
            raise UpdateDownloadError(_BAD_SIZE)
        digest.update(chunk)
        if sink is not None:
            sink.write(chunk)
        if progress:
            progress(received, asset.size)
    if received != asset.size:
        raise UpdateDownloadError(_BAD_SIZE)
    if digest.hexdigest() != asset.sha256.lower():
        raise UpdateDownloadError(_BAD_HASH)


def verify_download(asset: UpdateAsset, archive: Path, *, progress=None, cancelled=None):
    """Recheck the on-disk package before handing it to the system installer."""
    _check_asset(asset)
    try:
        with Path(archive).open("rb") as source:
            _read_verified(asset, source, progress=progress, cancelled=cancelled)
    except OSError as exc:
        raise UpdateDownloadError("Cannot read the downloaded installer.") from exc


def download_update(asset: UpdateAsset, directory: Path, *, progress=None, cancelled=None) -> Path:
    """Publish a complete verified asset, reusing an identical previous download."""
    _check_asset(asset)
    _check_cancelled(cancelled)
    directory = Path(directory)
    target = directory / asset.name
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise UpdateDownloadError(_FILE_EXISTS)
        if target.exists():
            if not target.is_file() or target.stat().st_size != asset.size:
                raise UpdateDownloadError(_FILE_EXISTS)
            try:
                verify_download(asset, target, progress=progress, cancelled=cancelled)
            except UpdateCancelled:
                raise
            except UpdateDownloadError as exc:
                raise UpdateDownloadError(_FILE_EXISTS) from exc
            return target

        request = Request(asset.url, headers={"User-Agent": "OrcaView-Updater", "Accept": "application/octet-stream"})
        with TemporaryDirectory(prefix=".orcaview-download-", dir=directory) as temp:
            staged = Path(temp) / "download.part"
            with open_update_url(request, timeout=15) as response, staged.open("xb") as dest:
                _read_verified(asset, response, sink=dest, progress=progress, cancelled=cancelled)
            _check_cancelled(cancelled)
            # Reserve the final name exclusively, even on volumes without hard links.
            try:
                target.touch(exist_ok=False)
            except FileExistsError as exc:
                raise UpdateDownloadError(_FILE_EXISTS) from exc
            try:
                os.replace(staged, target)
            except OSError:
                target.unlink()
                raise
        return target
    except (OSError, HTTPException) as exc:
        if isinstance(exc, HTTPError):
            exc.close()
        raise UpdateDownloadError("Cannot download or save the installer. Check your network connection and the selected folder.") from exc


def _member_path(name, stage, root):
    parts = name.removesuffix("/").split("/")
    if parts[0] != root or any(
        not part or part in (".", "..") or part.endswith((".", " "))
        or re.search(r'[\\:<>"|?*\x00-\x1f]', part)
        or re.match(r"^(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", part, re.I)
        for part in parts
    ):
        raise UpdateDownloadError(_BAD_ARCHIVE)
    return stage.joinpath(*parts)


def _unpack_file(source, target, cancelled):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as dest:
        while True:
            _check_cancelled(cancelled)
            chunk = source.read(_BLOCK)
            if not chunk:
                break
            dest.write(chunk)


def _unpack_windows(source, stage, root, cancelled):
    flat = root.endswith("-Windows-x64-portable")
    files = set()
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            _check_cancelled(cancelled)
            name = item.filename
            if flat:
                if name not in ("OrcaView.exe", "LICENSE", "Examples/") and not name.startswith("Examples/"):
                    raise UpdateDownloadError(_BAD_ARCHIVE)
                if not item.is_dir():
                    files.add(name)
                name = root + "/" + name
            path = _member_path(name, stage, root)
            kind = stat.S_IFMT(item.external_attr >> 16)
            if item.is_dir() and kind in (0, stat.S_IFDIR):
                path.mkdir(parents=True, exist_ok=True)
            elif not item.is_dir() and kind in (0, stat.S_IFREG):
                with archive.open(item) as contents:
                    _unpack_file(contents, path, cancelled)
            else:
                raise UpdateDownloadError(_BAD_ARCHIVE)
    if flat:
        manifest = portable_replace.windows_inventory(stage / root)
        if manifest is None or files != {"OrcaView.exe", *manifest}:
            raise UpdateDownloadError(_BAD_ARCHIVE)
        for name, digest in manifest.items():
            _check_cancelled(cancelled)
            if portable_replace._digest(stage / root / name) != digest:
                raise UpdateDownloadError(_BAD_ARCHIVE)


def _unpack_linux(source, stage, root, cancelled):
    links = []
    with tarfile.open(fileobj=source, mode="r|gz") as archive:
        for item in archive:
            _check_cancelled(cancelled)
            path = _member_path(item.name, stage, root)
            if item.isdir():
                path.mkdir(parents=True, exist_ok=True)
            elif item.isfile():
                with archive.extractfile(item) as contents:
                    _unpack_file(contents, path, cancelled)
                if item.mode & 0o111:
                    path.chmod(0o755)
            elif item.issym():
                links.append((path, item.linkname))
            else:
                raise UpdateDownloadError(_BAD_ARCHIVE)

    # Resolve links only after regular files are complete. The bundled Python
    # aliases refer to files inside the same version's installation directory.
    for path, link in links:
        _check_cancelled(cancelled)
        if not link or Path(link).is_absolute() or "\\" in link or ":" in link:
            raise UpdateDownloadError(_BAD_ARCHIVE)
        target = (path.parent / link).resolve()
        if not target.is_relative_to(stage / root) or not target.is_file():
            raise UpdateDownloadError(_BAD_ARCHIVE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(link)


def _publish_directory(staged, target):
    # POSIX rename would replace an existing empty directory. Reserve it with
    # mkdir first. On Windows rename itself rejects every existing destination.
    if os.name == "nt":
        staged.rename(target)
    else:
        target.mkdir()
        try:
            staged.replace(target)
        except OSError:
            target.rmdir()
            raise


def _bundle(asset):
    if asset.name.endswith(".zip"):
        return asset.name.removesuffix(".zip"), "OrcaView.exe", _unpack_windows
    if asset.name.endswith(".tar.gz"):
        return asset.name.removesuffix(".tar.gz"), "OrcaView", _unpack_linux
    raise UpdateDownloadError("Choose a Windows or Linux portable package.")


def _extract(asset, archive, stage, cancelled):
    root, launcher, unpack = _bundle(asset)
    with Path(archive).open("rb") as source:
        _read_verified(asset, source, cancelled=cancelled)
        source.seek(0)
        unpack(source, stage, root, cancelled)
    entry = stage / root / launcher
    if entry.is_symlink() or not entry.is_file() or (launcher == "OrcaView" and not os.access(entry, os.X_OK)):
        raise UpdateDownloadError(_BAD_ARCHIVE)
    _check_cancelled(cancelled)
    return entry


@dataclass(frozen=True)
class PreparedPortableUpdate:
    staged: Path
    target: Path
    backup: Path
    windows: bool
    expected: list

    def discard(self):
        # If activation had a filesystem failure during rollback its only
        # complete copy of the original files may still be inside this workdir.
        if (portable_replace.valid_workdir(self.staged.parent, self.target)
                and not (self.staged.parent / "previous").exists() and not (self.staged.parent / "ready").exists()):
            shutil.rmtree(self.staged.parent, ignore_errors=True)


def prepare_portable_update(asset, archive, target, *, cancelled=None):
    """Verify and extract in the destination filesystem; leave the active installation intact."""
    _check_asset(asset)
    _check_cancelled(cancelled)
    root, launcher, _ = _bundle(asset)
    windows = launcher == "OrcaView.exe"
    target = Path(target)
    if not portable_replace.installation(target, windows):
        raise UpdateDownloadError("The selected folder is not an existing OrcaView installation.")
    target = target.resolve()
    backup = target.with_name(target.name + ".previous")
    work = None
    try:
        expected = portable_replace.fingerprint(target, windows)
        work = Path(mkdtemp(prefix=".orcaview-install-", dir=target.parent))
        _extract(asset, archive, work, cancelled)
        if not portable_replace.installation(work / root, windows):
            raise UpdateDownloadError(_BAD_ARCHIVE)
        return PreparedPortableUpdate(work / root, target, backup, windows, expected)
    except BaseException as exc:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)
        if isinstance(exc, (OSError, EOFError, zipfile.BadZipFile, tarfile.TarError)):
            raise UpdateDownloadError("Cannot extract the installer. Check the available disk space and the selected folder.") from exc
        raise


def schedule_portable_update(prepared):
    """Arm a detached helper and return after it has acquired a handle on this process."""
    work = prepared.staged.parent
    if (work / "ready").exists():
        return
    runtime = prepared.target / "python"
    pid = os.getpid()
    if prepared.windows and portable_replace.windows_inventory(prepared.target) is not None:
        # The Windows launcher unpacks a private runtime and holds the public
        # EXE until the GUI has quit and that runtime has been removed.
        if current_portable_installation() != prepared.target:
            raise UpdateDownloadError("The selected folder is not an existing OrcaView installation.")
        runtime = Path(sys.executable).parent
        try:
            pid = int(os.environ["ORCAVIEW_PORTABLE_PID"])
            if pid <= 0:
                raise ValueError
        except (KeyError, ValueError) as exc:
            raise UpdateDownloadError("The update helper failed to start.") from exc
    tool = Path(mkdtemp(prefix="orcaview-update-helper-"))
    worker = None
    try:
        # The running GUI, the distlib launcher AND a helper using either
        # bundled interpreter can all keep Windows binaries locked. Bring a
        # small private interpreter outside both the live and staged roots.
        shutil.copytree(runtime, tool / "python", symlinks=True,
                        ignore=shutil.ignore_patterns("site-packages", "ThirdParty", "__pycache__", "orcaview-files.json"))
        source = Path(portable_replace.__file__)
        program = tool / ("replace" + source.suffix)
        shutil.copyfile(source, program)
        binary = Path("pythonw.exe") if prepared.windows else Path("bin/python3")
        plan = work / "update.json"
        token = uuid4().hex
        (tool / ".orcaview-helper-token").write_text(token)
        data = {"helper_token": token,"target": str(prepared.target), "backup": str(prepared.backup),
                "package": prepared.staged.name, "windows": prepared.windows, "expected": prepared.expected}
        plan.write_text(json.dumps(data), encoding="utf-8")
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        with (tool / "helper.log").open("ab") as log:
            worker = subprocess.Popen([str(tool / "python" / binary), "-I", "-S", "-B", str(program),
                                       str(plan), str(pid)], stdin=subprocess.DEVNULL, stdout=log,
                                      stderr=log, cwd=tool, close_fds=True, **options)
        deadline = time.monotonic() + 15
        while not (work / "ready").exists():
            if worker.poll() is not None or time.monotonic() > deadline:
                raise OSError("The update helper failed to start.")
            time.sleep(.05)
    except (OSError, ValueError) as exc:
        if worker is not None and worker.poll() is None:
            worker.terminate()
            worker.wait(timeout=5)
        shutil.rmtree(tool, ignore_errors=True)
        (work / "ready").unlink(missing_ok=True)
        raise UpdateDownloadError(f"Could not start the update helper: {exc}") from exc


def install_portable(asset: UpdateAsset, archive: Path, directory: Path, *, cancelled=None) -> Path:
    """Install into a new versioned folder, or update an explicitly selected installation in place."""
    _check_asset(asset)
    _check_cancelled(cancelled)
    root, launcher, _ = _bundle(asset)
    directory = Path(directory)
    windows = launcher == "OrcaView.exe"
    target = directory / root
    if portable_replace.installation(directory, windows):
        target = directory
    if portable_replace.installation(target, windows):
        if current_portable_installation() == target.resolve():
            raise UpdateDownloadError("Use Download and replace for the running installation, then save your project and quit.")
        pending = prepare_portable_update(asset, archive, target, cancelled=cancelled)
        try:
            _check_cancelled(cancelled)
            return portable_replace.activate(pending.staged, pending.target, pending.backup, windows, pending.expected)
        except (OSError, ValueError) as exc:
            raise UpdateDownloadError(f"Could not update the installation: {exc}") from exc
        finally:
            pending.discard()
    directory = directory.resolve()
    target = directory / root
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(target):
            raise UpdateDownloadError(_INSTALL_EXISTS)
        with TemporaryDirectory(prefix=".orcaview-install-", dir=directory) as temp:
            stage = Path(temp)
            _extract(asset, archive, stage, cancelled)
            try:
                _publish_directory(stage / root, target)
            except FileExistsError as exc:
                raise UpdateDownloadError(_INSTALL_EXISTS) from exc
        return target / launcher
    except UpdateDownloadError:
        raise
    except (tarfile.TarError, zipfile.BadZipFile, EOFError, RuntimeError) as exc:
        raise UpdateDownloadError(_BAD_ARCHIVE) from exc
    except OSError as exc:
        raise UpdateDownloadError("Cannot extract the installer. Check the available disk space and the selected folder.") from exc

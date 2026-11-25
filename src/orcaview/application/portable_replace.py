"""Replace the managed contents of a portable installation, also as a standalone helper."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
import zipfile


MANIFEST = Path("python/orcaview-files.json")
_BACKUP_MARK = ".orcaview-previous.json"
_BACKUP_EXE_DIGEST = ".orcaview-previous-exe.sha256"
_MIGRATED_EXAMPLES = ".orcaview-example-folders-v1"
_EXAMPLE_CATEGORIES = (("crystal.cif", "Structure-import"), ("water-wb97m2.inp", "ORCA-inputs"))


# Exact UTF-8 directory name used by pre-English packages without a manifest.
_LEGACY_EXAMPLES = b"\xe7\xa4\xba\xe4\xbe\x8b".decode("utf-8")


def _linked(path):
    return path.is_symlink() or getattr(os.path, "isjunction", lambda p: False)(path)


def _real_file(path):
    return not _linked(path) and path.is_file()


def windows_inventory(root):
    """Read the identity and example checksums embedded in the Windows launcher."""
    launcher = root / "OrcaView.exe"
    if _linked(root) or not _real_file(launcher):
        return None
    try:
        with launcher.open("rb") as stream:
            if stream.read(2) != b"MZ":
                return None
            with zipfile.ZipFile(stream) as payload:
                info = payload.getinfo("orcaview-windows.json")
                if info.file_size > 1024 * 1024:
                    return None
                data = json.loads(payload.read(info))
        files = data["files"]
        if (data["format"] != "orcaview-windows-portable-v1" or not isinstance(files, dict)
                or not isinstance(data["version"], str) or "LICENSE" not in files or len(files) < 2):
            return None
        if all((key == "LICENSE" or key.startswith("Examples/")) and isinstance(value, str)
               and re.fullmatch(r"[0-9a-f]{64}", value) for key, value in files.items()):
            return files
    except (KeyError, TypeError, ValueError, OSError, RuntimeError, zipfile.BadZipFile):
        pass
    return None


def installation(root, windows):
    """Identify a bundled application even when its enclosing directory was renamed."""
    runtime = root / "python"
    launcher = root / ("OrcaView.exe" if windows else "OrcaView")
    sites = [runtime / "Lib/site-packages"] if windows else (runtime / "lib").glob("python*/site-packages")
    if windows and windows_inventory(root) is not None:
        return True
    if _linked(root) or _linked(runtime) or not _real_file(launcher):
        return False
    return any(_real_file(site / "orcaview/__init__.pyc") for site in sites)


def current_portable_installation():
    if sys.platform not in ("win32", "linux"):
        return None
    exe = Path(sys.executable).resolve()
    windows = sys.platform == "win32"
    if windows and (host := os.environ.get("ORCAVIEW_PORTABLE_EXE")):
        launcher = Path(host)
        if (launcher.is_absolute() and launcher.name.lower() == "orcaview.exe"
                and windows_inventory(launcher.parent) is not None):
            return launcher.parent.resolve()
    runtime = exe.parent if windows else exe.parent.parent
    root = runtime.parent
    if runtime.name.lower() == "python" and installation(root, windows):
        return root
    return None


def fingerprint(root, windows):
    marker = root / ("OrcaView.exe" if windows else "OrcaView")
    info = marker.stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]


def _manifest(root):
    file = root / MANIFEST
    if _linked(root / "python") or not _real_file(file):
        return {}
    value = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
        raise ValueError("The portable package contents are invalid.")
    return value


def _digest(file):
    result = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(256 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _copy_custom(old, new, root, inventory, *, examples):
    """Carry custom data forward without mixing obsolete runtime modules into a new installation."""
    if _linked(old):
        if not os.path.lexists(new) and (examples or inventory):
            if getattr(os.path, "isjunction", lambda p: False)(old):
                raise OSError(f"Cannot copy directory junction: {old}")
            new.symlink_to(os.readlink(old), target_is_directory=old.is_dir())
        return
    if old.is_dir():
        if _linked(new) or (new.exists() and not new.is_dir()):
            return  # The complete old entry remains recoverable in the backup.
        new.mkdir(exist_ok=True)
        for child in old.iterdir():
            name = child.name
            # Infer renamed example categories from their unique sample file.
            # This maps the old translated paths without imposing them on users.
            if examples and old.parent == root and new.name == "Examples" and not _linked(child) and child.is_dir():
                for sample, category in _EXAMPLE_CATEGORIES:
                    old_key = (child / sample).relative_to(root).as_posix()
                    if old_key in inventory and (new / category / sample).is_file():
                        name = category
                        break
            _copy_custom(child, new / name, root, inventory, examples=examples)
        if not any(new.iterdir()) and not examples:
            new.rmdir()
        return
    relative = old.relative_to(root).as_posix()
    if not old.is_file() or relative == MANIFEST.as_posix():
        return
    known = inventory.get(relative)
    if known and (not examples or _digest(old) == known):
        return
    if os.path.lexists(new):
        if not examples or not _real_file(new):
            return
    elif not examples and not inventory:
        # A legacy runtime has no file inventory. Do not resurrect a retired
        # module/plugin. Its complete contents stay in the legacy backup.
        return
    shutil.copy2(old, new)


@contextmanager
def _exclusive(target, *, wait=False):
    lock = target.with_name("." + target.name + ".update-lock")
    if _linked(lock):
        raise OSError("The update lock path is invalid.")
    with lock.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if not stream.tell():
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield  # Closing the file releases the OS lock even if the helper dies.


def _move(source, destination):
    # Windows may still be finishing its launcher or releasing a loaded DLL.
    deadline = time.monotonic() + (12 if os.name == "nt" else 0)
    while True:
        try:
            source.rename(destination)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.2)


def _retire_backup(previous, target, windows=True):
    """Drop only pristine managed files; preserve local changes in an older backup."""
    inventory = windows_inventory(previous) if windows else None
    exe_digest = previous / _BACKUP_EXE_DIGEST
    if inventory is not None and _real_file(exe_digest):
        inventory["OrcaView.exe"] = exe_digest.read_text(encoding="ascii")
        exe_digest.unlink()
    if inventory is None:
        inventory = _manifest(previous)
    if inventory:
        # Only visit real directories. A user-created junction or symlink
        # must never turn this cleanup into a traversal outside the backup.
        def prune(directory):
            for path in directory.iterdir():
                key = path.relative_to(previous).as_posix()
                if _linked(path):
                    if key in ("python/bin/python", "python/bin/python3") and path.is_symlink():
                        other = target / key
                        if other.is_symlink() and os.readlink(path) == os.readlink(other):
                            path.unlink()
                elif path.is_dir():
                    prune(path)
                    if not any(path.iterdir()):
                        path.rmdir()
                elif path.is_file():
                    expected = inventory.get(key)
                    if key == MANIFEST.as_posix() or (expected and _digest(path) == expected):
                        path.unlink()

        prune(previous)
    done = previous / _MIGRATED_EXAMPLES
    if _real_file(done) and done.read_bytes() == b"1":
        done.unlink()
    (previous / _BACKUP_MARK).unlink(missing_ok=True)
    if any(previous.iterdir()):
        retained = target.with_name(target.name + ".previous-preserved-" + uuid4().hex[:10])
        _move(previous, retained)
    else:
        previous.rmdir()


def activate(staged, target, backup, windows, expected, *, relaunch=False):
    """Swap only managed entries. Current documents beside the application stay in place."""
    work = staged.parent
    launcher = "OrcaView.exe" if windows else "OrcaView"
    with _exclusive(target):
        if not installation(target, windows) or fingerprint(target, windows) != expected:
            raise ValueError("The installation has changed. Check for updates again.")
        if os.path.lexists(backup):
            mark = backup / _BACKUP_MARK
            if (_linked(backup) or not _real_file(mark)
                    or json.loads(mark.read_text(encoding="utf-8")) != str(target)):
                raise ValueError(f"The backup path is already in use: {backup}")
        inventory = windows_inventory(target) if windows else None
        old_flat = inventory is not None
        if inventory is None:
            inventory = _manifest(target)
        new_flat = windows and windows_inventory(staged) is not None
        names = [launcher]
        if not old_flat or not new_flat:
            names.append("python")
        if old_flat or new_flat:
            names.append("LICENSE")
        if not old_flat and not (target / MANIFEST).exists():
            names.extend(["ThirdParty", "LICENSE.txt"] + (["OrcaView-cli.exe"] if windows else []))
        old_examples = "Examples" if old_flat or any(key.startswith("Examples/") for key in inventory) else _LEGACY_EXAMPLES
        examples = "Examples" if (staged / "Examples").is_dir() else _LEGACY_EXAMPLES
        names.extend(dict.fromkeys((old_examples, examples)))
        for name in names:
            if name not in ("Examples", _LEGACY_EXAMPLES, "python"):
                continue
            old = target / name
            new = staged / ("python" if name == "python" else examples)
            if old.is_dir() and not _linked(old) and new.is_dir():
                _copy_custom(old, new, target, inventory, examples=name != "python")
        saved = work / "previous"
        saved.mkdir()
        (saved / _BACKUP_MARK).write_text(json.dumps(str(target)), encoding="utf-8")
        (saved / _MIGRATED_EXAMPLES).write_bytes(b"1")
        if old_flat:
            (saved / _BACKUP_EXE_DIGEST).write_text(_digest(target / launcher), encoding="ascii")
        moved_old, moved_new = [], []
        prior = work / "prior-backup"
        try:
            for name in names:
                if os.path.lexists(target / name):
                    _move(target / name, saved / name)
                    moved_old.append(name)
                if os.path.lexists(staged / name):
                    _move(staged / name, target / name)
                    moved_new.append(name)
            if backup.exists():
                _move(backup, prior)
            _move(saved, backup)
            if relaunch:
                subprocess.Popen([str(target / launcher)], cwd=target, close_fds=True)
        except BaseException:
            # If rollback itself fails, leave the original data in 'previous'
            # for manual recovery. Its directory must never be auto-deleted.
            if not saved.exists():
                _move(backup, saved)
            for name in reversed(moved_new):
                _move(target / name, staged / name)
            for name in reversed(moved_old):
                _move(saved / name, target / name)
            if prior.exists():
                _move(prior, backup)
            shutil.rmtree(saved)
            raise
        if prior.exists():
            try:
                _retire_backup(prior, target, windows)
            except (OSError, ValueError):
                # Installation has succeeded; conservatively retain unreadable files.
                _move(prior, target.with_name(target.name + ".previous-preserved-" + uuid4().hex[:10]))
    return target / launcher


def _merge_examples(source, dest, relative, expected):
    """Move examples into position, leaving genuine conflicts at the source."""
    if not os.path.lexists(dest):
        _move(source, dest)
        return
    if _linked(source) or _linked(dest):
        return
    if source.is_dir() and dest.is_dir():
        for child in source.iterdir():
            _merge_examples(child, dest / child.name, relative / child.name, expected)
        if not any(source.iterdir()):
            source.rmdir()
    elif _real_file(source) and _real_file(dest):
        before, after = _digest(source), _digest(dest)
        stock = expected.get(relative.as_posix())
        if before == after or before == stock:
            source.unlink()
        elif after == stock:
            os.replace(source, dest)


def _recover_conflict(source, examples, name):
    if os.path.lexists(source):
        # A new, private directory cannot collide with a user's chosen name.
        recovered = Path(tempfile.mkdtemp(prefix="Recovered-", dir=examples))
        _move(source, recovered / name)


def _restore_linux_seed(target, backup, inventory, current):
    dest = target / "Examples"
    old = backup / _LEGACY_EXAMPLES
    if not any(key.startswith(_LEGACY_EXAMPLES + "/") for key in inventory):
        return False
    seed = target / "python/orcaview-examples.zip"
    if not _real_file(seed) or _digest(seed) != current.get("python/" + seed.name):
        raise ValueError("The bundled examples could not be verified.")
    expected = {key.removeprefix("Examples/"): digest for key, digest in current.items() if key.startswith("Examples/")}
    with tempfile.TemporaryDirectory(prefix=".orcaview-examples-", dir=target) as tmp:
        staged = Path(tmp) / "Examples"
        with zipfile.ZipFile(seed) as archive:
            if not expected or set(archive.namelist()) != set(expected):
                raise ValueError("The bundled example inventory is incomplete.")
            for name, digest in expected.items():
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("The bundled example path is invalid.")
                data = archive.read(name)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError("The bundled example file could not be verified.")
                output = staged / path
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)
        if not _linked(old) and old.is_dir():
            custom = Path(tmp) / "previous-content"
            _copy_custom(old, custom, backup, inventory, examples=True)
            renamed = _renamed_categories(inventory, old.name, expected)
            for entry in custom.iterdir():
                category = renamed.get(entry.name, entry.name)
                _merge_examples(entry, staged / category, Path(category), expected)
                _recover_conflict(entry, staged, category)
        if not os.path.lexists(dest):
            _move(staged, dest)
        else:
            _merge_examples(staged, dest, Path(), expected)
            _recover_conflict(staged, dest, "Examples")
    return True


def _renamed_categories(old_inventory, old_root, expected):
    renamed = {}
    for sample, category in _EXAMPLE_CATEGORIES:
        if f"{category}/{sample}" not in expected:
            continue
        for key in old_inventory:
            parts = key.split("/")
            if (len(parts) == 3 and parts[0] == old_root and parts[2] == sample
                    and parts[1] != category and not parts[1].isascii() and Path(parts[1]).name == parts[1]):
                renamed[parts[1]] = category
    return renamed


def _restore_windows_categories(dest, old_inventory, current):
    expected = {key.removeprefix("Examples/"): val for key, val in current.items() if key.startswith("Examples/")}
    renamed = _renamed_categories(old_inventory, "Examples", expected)
    for previous_name, category in renamed.items():
        source = dest / previous_name
        if not os.path.lexists(source):
            continue
        # The frozen a43 updater copied the custom files and old category
        # directories alongside the newly extracted English folders.
        _merge_examples(source, dest / category, Path(category), expected)
        _recover_conflict(source, dest, category)
    return bool(renamed)


def restore_examples_after_update(target, *, windows):
    """Reconcile the sample folders once after a verified a42/a43 upgrade."""
    if _linked(target):
        return
    target = target.resolve()
    dest = target / "Examples"
    backup = target.with_name(target.name + ".previous")
    mark, done = backup / _BACKUP_MARK, backup / _MIGRATED_EXAMPLES
    if (_linked(backup) or not _real_file(mark) or os.path.lexists(done)
            or _linked(dest) or (dest.exists() and not dest.is_dir())
            or (windows and not dest.is_dir())):
        return
    with _exclusive(target, wait=True):
        if (_linked(backup) or not _real_file(mark) or os.path.lexists(done)
                or json.loads(mark.read_text(encoding="utf-8")) != str(target)):
            return
        if windows:
            current, old = windows_inventory(target), windows_inventory(backup)
            repaired = current and old and _restore_windows_categories(dest, old, current)
        else:
            repaired = _restore_linux_seed(target, backup, _manifest(backup), _manifest(target))
        if repaired:
            with done.open("xb") as stream:
                stream.write(b"1")


def restore_examples_on_launch():
    if sys.platform == "win32":
        name = os.environ.get("ORCAVIEW_PORTABLE_EXE", "")
        exe = Path(name)
        if not exe.is_absolute() or exe.name.lower() != "orcaview.exe":
            return
        target = exe.parent
    elif sys.platform.startswith("linux"):
        runtime = Path(sys.executable).parent.parent
        if runtime.name != "python":
            return
        target = runtime.parent
    else:
        return
    try:
        restore_examples_after_update(target, windows=sys.platform == "win32")
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        # An unavailable file or simultaneous update may be retried next time.
        if sys.stderr is not None:
            print(f"Could not restore examples: {error}", file=sys.stderr)


def valid_workdir(work, target):
    return (work.name.startswith(".orcaview-install-") and not _linked(work)
            and work.parent == target.parent and work != target)


def _wait_parent(pid, ready):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            ready.touch()
            kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            kernel.WaitForSingleObject.restype = wintypes.DWORD
            if kernel.WaitForSingleObject(handle, 0xffffffff) != 0:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel.CloseHandle(handle)
    else:
        ready.touch()
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(.25)


def run_helper(plan, pid):
    work = plan.parent
    data = json.loads(plan.read_text(encoding="utf-8"))
    target, backup = Path(data["target"]), Path(data["backup"])
    package = data["package"]
    relaunch = data.get("relaunch", True)
    if not (plan.name == "update.json" and valid_workdir(work, target)
            and isinstance(relaunch, bool)
            and package.startswith("OrcaView-") and Path(package).name == package
            and backup == target.with_name(target.name + ".previous")
            and installation(work / package, data["windows"])):
        raise ValueError("The portable package contents are invalid.")
    try:
        _wait_parent(pid, work / "ready")
        activate(work / package, target, backup, data["windows"], data["expected"], relaunch=relaunch)
    except Exception as exc:
        message = f"OrcaView update failed.\n{exc}\nInstallation: {target}\nBackup: {backup}\nUpdate log: {work}"
        (work / "update-error.txt").write_text(message, encoding="utf-8")
        if not relaunch:
            return 1
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "OrcaView", 0x10)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", "OrcaView", message], check=False)
        return 1
    shutil.rmtree(work, ignore_errors=True)
    return 0


def cleanup_interpreter(plan, tool):
    # Windows holds the helper's interpreter open until the process exits.
    marker = tool / ".orcaview-helper-token"
    if (not tool.name.startswith("orcaview-update-helper-") or _linked(tool)
            or tool.parent.resolve() != Path(tempfile.gettempdir()).resolve()
            or not _real_file(marker) or marker.read_text() != plan["helper_token"]):
        return
    if os.name != "nt":
        shutil.rmtree(tool, ignore_errors=True)
        return
    # Use the OS command processor, independent of the installed application.
    # Only the random ASCII basename enters the command. The user's temporary
    # path, which can contain spaces and shell metacharacters, is passed as cwd.
    if not re.fullmatch(r"orcaview-update-helper-[a-z0-9_]+", tool.name):
        return
    shell = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
    ping = shell.with_name("ping.exe")
    command = (f'for /L %i in (1,1,30) do @if exist {tool.name} '
               f'(rd /s /q {tool.name} 2>nul & if exist {tool.name} '
               f'"{ping}" -n 2 127.0.0.1 >nul)')
    subprocess.Popen(f'"{shell}" /d /q /v:off /c {command}', executable=str(shell), cwd=tool.parent,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)


if __name__ == "__main__":
    plan = Path(sys.argv[1])
    configuration = json.loads(plan.read_text(encoding="utf-8"))
    try:
        result = run_helper(plan, int(sys.argv[2]))
    finally:
        cleanup_interpreter(configuration, Path(__file__).parent)
    raise SystemExit(result)

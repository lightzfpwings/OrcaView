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
        raise ValueError("便携安装包的内容无效。")
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
                raise OSError(f"无法复制目录联接：{old}")
            new.symlink_to(os.readlink(old), target_is_directory=old.is_dir())
        return
    if old.is_dir():
        if _linked(new) or (new.exists() and not new.is_dir()):
            return  # The complete old entry remains recoverable in the backup.
        new.mkdir(exist_ok=True)
        for child in old.iterdir():
            _copy_custom(child, new / child.name, root, inventory, examples=examples)
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
def _exclusive(target):
    lock = target.with_name("." + target.name + ".update-lock")
    if _linked(lock):
        raise OSError("更新锁路径无效。")
    with lock.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if not stream.tell():
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
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
            raise ValueError("安装目录已变更，请重新检查更新。")
        if os.path.lexists(backup):
            mark = backup / _BACKUP_MARK
            if (_linked(backup) or not _real_file(mark)
                    or json.loads(mark.read_text(encoding="utf-8")) != str(target)):
                raise ValueError(f"备份路径已被其他文件占用：{backup}")
        inventory = windows_inventory(target) if windows else None
        old_flat = inventory is not None
        if inventory is None:
            inventory = _manifest(target)
        new_flat = windows and windows_inventory(staged) is not None
        names = [launcher]
        if not old_flat or not new_flat:
            names.extend(["python", "示例"])
        if old_flat or new_flat:
            names.extend(["LICENSE", "Examples"])
        if not old_flat and not (target / MANIFEST).exists():
            names.extend(["ThirdParty", "LICENSE.txt"] + (["OrcaView-cli.exe"] if windows else []))
        examples = "Examples" if new_flat else "示例"
        for name in names:
            if name not in ("Examples", "示例", "python"):
                continue
            old = target / name
            new = staged / ("python" if name == "python" else examples)
            if old.is_dir() and not _linked(old) and new.is_dir():
                _copy_custom(old, new, target, inventory, examples=name != "python")
        saved = work / "previous"
        saved.mkdir()
        (saved / _BACKUP_MARK).write_text(json.dumps(str(target)), encoding="utf-8")
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
    if not (plan.name == "update.json" and valid_workdir(work, target)
            and package.startswith("OrcaView-") and Path(package).name == package
            and backup == target.with_name(target.name + ".previous")
            and installation(work / package, data["windows"])):
        raise ValueError("便携安装包的内容无效。")
    try:
        _wait_parent(pid, work / "ready")
        activate(work / data["package"], target, backup, data["windows"], data["expected"], relaunch=True)
    except Exception as exc:
        message = f"OrcaView 更新失败。\n{exc}\n安装目录：{target}\n备份位置：{backup}\n更新记录：{work}"
        (work / "update-error.txt").write_text(message, encoding="utf-8")
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

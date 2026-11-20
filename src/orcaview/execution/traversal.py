"""Optional Traversal discovery and a scoped ORCA executable preflight."""

import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

from orcaview.core._validation import Versioned, finite_number
from orcaview.core.tasks import ErrorInfo

from ._process import group_active, terminate_group


TRAVERSAL_VERSION = "0.1.2"
_VERSION_BANNER = re.compile(r"\bProgram Version\s+(\d+(?:\.\d+)+)(?=\s|$)")
_VERSION_OUTPUT_LIMIT = 64 * 1024
_VERSION_STOP_GRACE = 0.2
ExecutableFingerprint = tuple[int, int, int, int, int]


@dataclass(frozen=True)
class OrcaPreflight(Versioned):
    executable: Optional[Path]
    version: Optional[str] = None
    version_output: Optional[str] = None
    error: Optional[ErrorInfo] = None
    executable_fingerprint: Optional[ExecutableFingerprint] = None

    @property
    def ready(self) -> bool:
        return self.executable is not None and self.version is not None and self.error is None

    def matches_executable(self) -> bool:
        """Check that the path still denotes the file observed during the probe."""

        if self.executable is None or self.executable_fingerprint is None:
            return False
        try:
            return _fingerprint(self.executable.stat()) == self.executable_fingerprint
        except (OSError, ValueError):
            return False


def probe_orca(
    executable: Optional[Path], *, timeout_seconds: float = 10.0
) -> OrcaPreflight:
    """Check an explicit ORCA path and read its version in an isolated directory."""

    timeout = finite_number(timeout_seconds, "版本探测超时")
    if timeout <= 0:
        raise ValueError("版本探测超时必须大于 0")

    if executable is None:
        return _failure(None, "orca_path_required", "请提供 ORCA 可执行文件的绝对路径")
    path = Path(executable)
    try:
        path = path.expanduser()
        if not path.is_absolute():
            return _failure(path, "orca_path_not_absolute", "ORCA 可执行文件必须使用绝对路径")
        path = path.resolve(strict=True)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK):
            return _failure(path, "orca_not_executable", f"ORCA 路径不是可执行文件 {path}")
    except FileNotFoundError:
        return _failure(path, "orca_not_found", f"找不到 ORCA 可执行文件 {path}")
    except (OSError, RuntimeError, ValueError) as exc:
        return _failure(path, "orca_path_unavailable", f"无法核对 ORCA 可执行文件 {path}。{exc}")
    if os.name != "posix":
        return _failure(path, "orca_platform_unsupported", "ORCA 本地执行需要 POSIX 进程组")

    try:
        with tempfile.TemporaryDirectory(prefix="orcaview-orca-probe-") as directory:
            with tempfile.TemporaryFile(dir=directory) as output_file:
                process = subprocess.Popen(
                    [str(path), "--version"],
                    cwd=directory,
                    stdin=subprocess.DEVNULL,
                    stdout=output_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                timed_out = False
                try:
                    return_code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    return_code = None
                if timed_out or group_active(process.pid):
                    stopped = terminate_group(process, _VERSION_STOP_GRACE)
                    output = _read_output(output_file)
                    if not stopped:
                        return _failure(
                            path, "orca_version_stop_unconfirmed", "无法确认版本探测进程组已停止",
                            output, retryable=False,
                        )
                    if timed_out:
                        return _failure(path, "orca_version_timeout", "ORCA 版本探测超时", output)
                    return _failure(
                        path,
                        "orca_version_child_remaining",
                        "版本探测主进程退出后仍有活动的子进程",
                        output,
                    )
                output = _read_output(output_file)
    except (OSError, ValueError) as exc:
        return _failure(path, "orca_version_probe_failed", f"ORCA 版本探测失败。{exc}")

    match = _VERSION_BANNER.search(output or "")
    if match is None:
        return _failure(path, "orca_version_missing", "未识别到 ORCA Program Version 横幅", output)
    # Traversal v0.1.2 accepts exit 2 only with the expected ORCA banner.
    if return_code not in (0, 2):
        return _failure(path, "orca_version_exit", f"ORCA 版本探测退出码为 {return_code}", output)
    result = OrcaPreflight(path, match[1], output, executable_fingerprint=_fingerprint(info))
    if not result.matches_executable():
        return _failure(path, "orca_executable_changed", "ORCA 可执行文件在版本探测期间发生变化", output)
    return result


def _fingerprint(info: os.stat_result) -> ExecutableFingerprint:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read_output(output_file: BinaryIO) -> Optional[str]:
    content = os.pread(output_file.fileno(), _VERSION_OUTPUT_LIMIT, 0)
    return content.decode("utf-8", errors="replace").strip() or None


def _failure(
    executable: Optional[Path], code: str, reason: str, output: Optional[str] = None,
    *, retryable: Optional[bool] = None,
) -> OrcaPreflight:
    return OrcaPreflight(executable, version_output=output, error=ErrorInfo(code, reason, retryable))


class TraversalUnavailableError(RuntimeError):
    """The optional, pinned Traversal capability could not be loaded."""


class TraversalAdapter:
    """Use the public Traversal facade without exposing Traversal types."""

    @staticmethod
    def _load():
        try:
            from chem_traversal import Traversal, __version__
            from chem_traversal.modules import DiscoveryConfig, PreflightConfig
        except ImportError as exc:
            raise TraversalUnavailableError(
                f"当前 Python 环境无法导入 chem-traversal {TRAVERSAL_VERSION}"
            ) from exc
        if __version__ != TRAVERSAL_VERSION:
            raise TraversalUnavailableError(
                f"Traversal 适配器需要 chem-traversal {TRAVERSAL_VERSION}，当前为 {__version__}"
            )
        return Traversal(), DiscoveryConfig, PreflightConfig

    @property
    def unavailable_reason(self) -> Optional[str]:
        try:
            self._load()
        except TraversalUnavailableError as exc:
            return str(exc)
        return None

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    def discover(self, root: Path, *, recursive: bool = True) -> tuple[Path, ...]:
        """List existing .inp file paths for review, without submitting jobs."""

        traversal, discovery_config, _ = self._load()
        results = traversal.discover(discovery_config(root, (".inp",), recursive=recursive))
        return tuple(item.path for item in results)

    def preflight(
        self, executable: Optional[Path] = None, *, timeout_seconds: float = 10.0
    ) -> OrcaPreflight:
        """Reuse Traversal's executable discovery and check the version locally."""

        try:
            traversal, _, preflight_config = self._load()
        except TraversalUnavailableError as exc:
            return _failure(None, "traversal_unavailable", str(exc))
        try:
            if executable is not None:
                executable = Path(executable).expanduser()
                if not executable.is_absolute():
                    return _failure(
                        executable, "orca_path_not_absolute", "ORCA 可执行文件必须使用绝对路径"
                    )
            located = traversal.check_environment(
                preflight_config("orca", executable=executable, check_version=False)
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return _failure(executable, "orca_path_unavailable", f"无法核对 ORCA 可执行文件。{exc}")
        if not located.ready or located.executable is None:
            return _failure(located.executable or executable, f"orca_{located.status.value}", located.message)
        return probe_orca(located.executable, timeout_seconds=timeout_seconds)


__all__ = ["OrcaPreflight", "TraversalAdapter", "TraversalUnavailableError", "probe_orca"]

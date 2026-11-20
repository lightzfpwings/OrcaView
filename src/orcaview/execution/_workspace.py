"""Materialize and verify one attempt's frozen ORCA input files."""

from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Iterator, Optional, Tuple, Union

from ..orca.input import InputSnapshot


ATTEMPT_METADATA = ".orcaview"
INPUT_MANIFEST = "input-manifest.json"
_ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_METADATA_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}")


@contextmanager
def _open_directory(
    path: Union[Path, str], *, parent_fd: Optional[int] = None
) -> Iterator[int]:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        yield fd
    finally:
        os.close(fd)


def _snapshot_files(snapshot: InputSnapshot) -> Tuple[Tuple[str, str, bytes, str], ...]:
    return (
        (snapshot.main_input_path, "main_input", snapshot.input_bytes, snapshot.input_sha256),
        *((file.relative_path, file.role, file.content, file.sha256)
          for file in snapshot.companions),
    )


def _manifest_bytes(snapshot: InputSnapshot) -> bytes:
    ref = snapshot.geometry_ref
    manifest = {
        "manifest_version": 1,
        "input_snapshot_version": snapshot.contract_version,
        "snapshot_digest": snapshot.snapshot_digest,
        "content_digest": snapshot.content_digest,
        "target_orca_version": snapshot.target_orca_version,
        "encoding": snapshot.encoding,
        "geometry_ref": {
            "contract_version": ref.contract_version,
            "document_id": ref.document_id,
            "revision": ref.revision,
            "frame_id": ref.frame_id,
            "snapshot_id": ref.snapshot_id,
        },
        "geometry_content_hash": snapshot.geometry.content_hash,
        "files": [
            {"relative_path": path, "role": role, "sha256": digest, "size_bytes": len(content)}
            for path, role, content, digest in _snapshot_files(snapshot)
        ],
    }
    return (json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("ascii")


def _write_file(directory_fd: int, name: str, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)


def _require_private_file(info: os.stat_result, name: str) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f"尝试目录需使用独立的普通文件：{name}")


def _verify_sha256(directory_fd: int, name: str, expected: str) -> None:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(name, flags, dir_fd=directory_fd)
    try:
        _require_private_file(os.fstat(fd), name)
        digest = sha256()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    finally:
        os.close(fd)
    if digest.hexdigest() != expected:
        raise ValueError(f"尝试目录中的文件与冻结内容不符：{name}")


def stage_attempt(root: Path, attempt_id: str, snapshot: InputSnapshot) -> Path:
    """Exclusively stage one attempt. Retain any evidence if staging fails."""
    if not isinstance(attempt_id, str) or not _ATTEMPT_ID.fullmatch(attempt_id):
        raise ValueError("无效的尝试 ID")
    if not isinstance(snapshot, InputSnapshot):
        raise ValueError("尝试目录需要 M3 InputSnapshot")
    root = root.absolute()
    root.mkdir(parents=True, exist_ok=True)
    with _open_directory(root) as root_fd:
        os.mkdir(attempt_id, 0o700, dir_fd=root_fd)
        with _open_directory(attempt_id, parent_fd=root_fd) as attempt_fd:
            os.mkdir(ATTEMPT_METADATA, 0o700, dir_fd=attempt_fd)
            with _open_directory(ATTEMPT_METADATA, parent_fd=attempt_fd) as metadata_fd:
                _write_file(metadata_fd, INPUT_MANIFEST, _manifest_bytes(snapshot))
            for path, _, content, _ in _snapshot_files(snapshot):
                _write_file(attempt_fd, path, content)
    directory = root / attempt_id
    verify_attempt_inputs(directory, snapshot)
    return directory


def verify_attempt_inputs(
    directory: Path, snapshot: InputSnapshot, *, allowed_metadata: Tuple[str, ...] = ()
) -> None:
    """Recheck the fresh workspace and its manifest before launching ORCA."""
    if any(not isinstance(name, str) or not _METADATA_NAME.fullmatch(name)
           for name in allowed_metadata):
        raise ValueError("无效的尝试元数据文件名")
    files = _snapshot_files(snapshot)
    with _open_directory(directory) as attempt_fd:
        expected = {path for path, _, _, _ in files} | {ATTEMPT_METADATA}
        actual = set(os.listdir(attempt_fd))
        if actual != expected:
            changed = ", ".join(sorted(actual ^ expected))
            raise ValueError(f"尝试目录中的文件与冻结清单不一致：{changed}")
        for path, _, _, expected_digest in files:
            _verify_sha256(attempt_fd, path, expected_digest)
        with _open_directory(ATTEMPT_METADATA, parent_fd=attempt_fd) as metadata_fd:
            extras = set(os.listdir(metadata_fd)) - {INPUT_MANIFEST}
            unexpected = extras.difference(allowed_metadata)
            if unexpected:
                changed = ", ".join(sorted(unexpected))
                raise ValueError(f"尝试目录含未预期的元数据：{changed}")
            for name in extras:
                _require_private_file(os.stat(name, dir_fd=metadata_fd, follow_symlinks=False), name)
            _verify_sha256(metadata_fd, INPUT_MANIFEST, sha256(_manifest_bytes(snapshot)).hexdigest())

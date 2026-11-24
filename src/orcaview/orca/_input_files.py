"""Immutable companion files and portable destinations for ORCA input."""

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import re
from typing import Tuple, Union

from ..core._validation import Versioned, require_tuple


_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}")
_RESERVED_DEVICE = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])")
_COMPANION_EXTENSIONS = {"external_xyz": ".xyz", "initial_gbw": ".gbw"}


def _validate_destination(relative_path: str, extension: str) -> None:
    if not isinstance(relative_path, str) or not _BASENAME.fullmatch(relative_path):
        raise ValueError("The target path must be a portable ASCII file name in the working directory")
    folded = relative_path.lower()
    if not folded.endswith(extension):
        raise ValueError(f"The target file name must end in {extension}")
    if _RESERVED_DEVICE.fullmatch(folded.split(".", 1)[0]):
        raise ValueError("The target file name uses a reserved system name")


def validate_main_input_path(relative_path: str) -> None:
    _validate_destination(relative_path, ".inp")


def _validate_companion_path(role: str, relative_path: str) -> None:
    if not isinstance(role, str) or role not in _COMPANION_EXTENSIONS:
        raise ValueError("The companion file role must be external_xyz or initial_gbw")
    _validate_destination(relative_path, _COMPANION_EXTENSIONS[role])


@dataclass(frozen=True)
class InputCompanionFile(Versioned):
    """File bytes captured independently of their original source path."""

    role: str
    relative_path: str
    content: bytes = field(repr=False)
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_companion_path(self.role, self.relative_path)
        if type(self.content) is not bytes or not self.content:
            raise ValueError("Companion file content must be nonempty immutable bytes")
        object.__setattr__(self, "sha256", sha256(self.content).hexdigest())

    @classmethod
    def from_path(cls, role: str, relative_path: str, source: Union[str, Path]) -> "InputCompanionFile":
        """Read an explicitly supplied source file and keep its bytes."""
        _validate_companion_path(role, relative_path)
        path = Path(source)
        try:
            if not path.is_file():
                raise ValueError(f"The companion file is missing or not a regular file: {path}")
            content = path.read_bytes()
        except OSError as exc:
            raise ValueError(f"Could not read the companion file: {path}") from exc
        return cls(role, relative_path, content)


def validate_companion_manifest(
    main_input_path: str, companions: Tuple[InputCompanionFile, ...]
) -> Tuple[InputCompanionFile, ...]:
    """Validate all destinations together and return them in canonical order."""
    validate_main_input_path(main_input_path)
    require_tuple(companions, "Companion file manifest")
    main_folded = main_input_path.lower()
    main_stem = main_folded.rsplit(".", 1)[0]
    seen_paths = {main_folded}
    seen_roles = set()
    for companion in companions:
        if not isinstance(companion, InputCompanionFile):
            raise ValueError("The companion file manifest must use InputCompanionFile")
        path = companion.relative_path.lower()
        stem = path.rsplit(".", 1)[0]
        if path in seen_paths:
            raise ValueError(f"Input file target path conflict: {companion.relative_path}")
        if stem == main_stem or stem.startswith(main_stem + "_"):
            raise ValueError(f"The companion file conflicts with the ORCA output name: {companion.relative_path}")
        if companion.role in seen_roles:
            raise ValueError(f"Duplicate companion file role: {companion.role}")
        seen_paths.add(path)
        seen_roles.add(companion.role)
    return tuple(sorted(companions, key=lambda companion: companion.relative_path.lower()))

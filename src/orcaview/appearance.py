"""Molecular display preferences and locally installed element color packs."""

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import re
from orcaview.io.atomic_file import write_bytes
from orcaview.preferences import data_directory, read_preferences, write_preferences

from orcaview.core.elements import ATOMIC_NUMBERS, ELEMENT_COLORS
from orcaview.core.geometry import DEFAULT_BOND_DISTANCE_FACTOR


MODEL_LABELS = {
    "ball-and-stick": "Matte ball-and-stick",
    "space-filling": "Space-filling",
    "stick": "Stick",
    "wireframe": "Wireframe",
}
SCALE_RANGE = (0.25, 3.0)
BOND_DISTANCE_RANGE = (0.5, 2.0)
_PACK_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}")
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_PACK_LIMIT = 64 * 1024
_PREFERENCE_KEY = "molecularAppearance"


@dataclass(frozen=True)
class AppearanceSettings:
    model: str = "ball-and-stick"
    atom_scale: float = 1.0
    bond_scale: float = 1.0
    bond_distance_factor: float = DEFAULT_BOND_DISTANCE_FACTOR
    palette_id: str = "default"

    def __post_init__(self):
        if not isinstance(self.model, str) or self.model not in MODEL_LABELS:
            raise ValueError("Unknown molecular display model")
        if not isinstance(self.palette_id, str) or not _PACK_ID.fullmatch(self.palette_id):
            raise ValueError("Invalid color pack ID")
        for value, (minimum, maximum) in ((self.atom_scale, SCALE_RANGE), (self.bond_scale, SCALE_RANGE),
                                         (self.bond_distance_factor, BOND_DISTANCE_RANGE)):
            if type(value) not in (int, float) or not minimum <= value <= maximum:
                raise ValueError("Molecular display scale is outside the supported range")


@dataclass(frozen=True)
class ColorPack:
    id: str
    name: str
    colors: dict

    def __post_init__(self):
        if not isinstance(self.id, str) or not _PACK_ID.fullmatch(self.id) or self.id == "default":
            raise ValueError("Invalid or reserved color pack ID")
        if (not isinstance(self.name, str) or not 1 <= len(self.name.strip()) <= 80
                or not self.name.isprintable()):
            raise ValueError("Invalid color pack name")
        if not isinstance(self.colors, dict) or not self.colors:
            raise ValueError("A color pack needs at least one element")
        normalized = {}
        for key, value in self.colors.items():
            symbol = key.capitalize() if isinstance(key, str) and key.isascii() else ""
            if symbol not in ATOMIC_NUMBERS or symbol in normalized:
                raise ValueError("Unknown or repeated element in the color pack")
            if not isinstance(value, str) or not _HEX_COLOR.fullmatch(value):
                raise ValueError("Each element color must use #RRGGBB")
            normalized[symbol] = value.upper()
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "colors", normalized)


def _distinct_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key in the color pack")
        result[key] = value
    return result


def read_palette(path):
    """Read a UTF-8 JSON pack without installing or activating it."""
    path = Path(path)
    if not path.is_file():
        raise OSError(f"Cannot read color pack: {path}")
    with path.open("rb") as stream:
        raw = stream.read(_PACK_LIMIT + 1)
    if len(raw) > _PACK_LIMIT:
        raise ValueError("Color packs must be at most 64 KiB")
    try:
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_distinct_keys)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Invalid UTF-8 JSON color pack") from error
    if not isinstance(data, dict) or data.keys() != {"id", "name", "colors"}:
        raise ValueError("A color pack needs id, name and colors")
    return ColorPack(**data)


class AppearanceStore:
    """Keep preferences in the same user settings as the interface language."""

    def __init__(self, *, settings=None, directory=None):
        self.settings = settings
        self.directory = Path(directory) if directory is not None else data_directory() / "color-packs"

    def _installed(self, palette_id):
        if (not isinstance(palette_id, str) or not _PACK_ID.fullmatch(palette_id)
                or palette_id == "default"):
            return None
        try:
            pack = read_palette(self.directory / f"pack-{palette_id}.json")
        except (OSError, ValueError):
            return None
        return pack if pack.id == palette_id else None

    def palettes(self):
        result = {"default": "OrcaView default"}
        for path in sorted(self.directory.glob("pack-*.json")):
            pack = self._installed(path.stem[5:])
            if pack:
                result[pack.id] = pack.name
        return result

    def overrides(self, palette_id):
        pack = self._installed(palette_id)
        return pack.colors if pack else {}

    def colors(self, palette_id):
        return {**ELEMENT_COLORS, **self.overrides(palette_id)}

    def install_palette(self, pack):
        """Atomically install or replace a validated pack after the user accepts."""
        pack = ColorPack(pack.id, pack.name, pack.colors)
        self.directory.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(asdict(pack), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        write_bytes(self.directory / f"pack-{pack.id}.json", data)
        return pack.id

    def import_palette(self, path):
        return self.install_palette(read_palette(path))

    def load(self):
        try:
            raw = read_preferences("appearance", {_PREFERENCE_KEY: "{}"}, self.settings)[_PREFERENCE_KEY]
            current = AppearanceSettings(**json.loads(raw))
        except (TypeError, ValueError, RecursionError):
            return AppearanceSettings()
        if current.palette_id != "default" and not self._installed(current.palette_id):
            return replace(current, palette_id="default")
        return current

    def save(self, settings):
        if settings.palette_id != "default" and not self._installed(settings.palette_id):
            raise ValueError("The selected color pack is unavailable")
        write_preferences("appearance", {_PREFERENCE_KEY: json.dumps(asdict(settings))}, self.settings)

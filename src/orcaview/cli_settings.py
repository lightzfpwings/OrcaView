"""Read and edit the same personal preferences used by the desktop."""

from dataclasses import asdict, replace
import json
from pathlib import Path

from orcaview.appearance import AppearanceSettings, AppearanceStore, MODEL_LABELS, read_palette
from orcaview.i18n import discover_languages
from orcaview.preferences import language_preferences, write_preferences


def register(sub):
    settings = sub.add_parser("settings", help="Read or set persistent desktop and CLI preferences")
    groups = settings.add_subparsers(dest="group", required=True)
    appearance = groups.add_parser("appearance", help="Show, change or reset the molecular display preferences")
    appearance.add_argument("--model", choices=MODEL_LABELS)
    appearance.add_argument("--atom-scale", type=float)
    appearance.add_argument("--bond-scale", type=float)
    appearance.add_argument("--bond-distance-factor", type=float)
    color = appearance.add_mutually_exclusive_group()
    color.add_argument("--palette", help="Select an installed color pack by ID")
    color.add_argument("--import-palette", type=Path, metavar="JSON", help="Install and select an external color pack")
    appearance.add_argument("--reset", action="store_true", help="Start from the built-in defaults")
    appearance.set_defaults(handler=_appearance)
    language = groups.add_parser("language", help="List language packs or select a language and pack directory")
    language.add_argument("--directory", type=Path)
    language.add_argument("--locale")
    language.set_defaults(handler=_language)


def _appearance(args):
    store = AppearanceStore()
    current = AppearanceSettings() if args.reset else store.load()
    changes = {field: getattr(args, field) for field in ("model", "atom_scale", "bond_scale", "bond_distance_factor")
               if getattr(args, field) is not None}
    pack = read_palette(args.import_palette) if args.import_palette else None
    if pack is not None or args.palette is not None:
        changes["palette_id"] = pack.id if pack else args.palette
    current = replace(current, **changes)
    if pack:
        store.install_palette(pack)
    if args.reset or changes:
        store.save(current)
    print(json.dumps({"settings": asdict(current), "palettes": store.palettes(),
                      "overrides": store.overrides(current.palette_id)}, ensure_ascii=False, indent=2))
    return 0


def _language(args):
    current = language_preferences()
    directory = (args.directory or Path(current["languageDirectory"])).expanduser().resolve()
    packs, failures = discover_languages(directory)
    locale = args.locale or current["language"]
    if args.directory is not None or args.locale is not None:
        if args.directory is not None and not directory.is_dir():
            raise ValueError(f"Language pack directory does not exist: {directory}")
        if locale not in packs:
            raise ValueError(f"Language pack is unavailable in {directory}: {locale}")
        write_preferences("language", {"languageDirectory": str(directory), "language": locale})
    print(json.dumps({"locale": locale if locale in packs else "en", "directory": str(directory),
                      "available": {key: pack.name for key, pack in packs.items()},
                      "invalid_files": failures}, ensure_ascii=False, indent=2))
    return 0

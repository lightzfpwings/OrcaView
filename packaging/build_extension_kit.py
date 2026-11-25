"""Build the two optional release ZIPs, each with its own offline install guide."""

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from build_language_packs import LANGUAGE_GROUPS, qt_translations_directory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from orcaview import __version__
from orcaview.appearance import read_palette
from orcaview.i18n import discover_languages


def language_files(translations):
    source = ROOT / "language-packs"
    packs, failures = discover_languages(source)
    locales = {locale: qt for group in LANGUAGE_GROUPS.values() for locale, qt in group.items()}
    if failures or set(packs) != {"en", *locales}:
        raise ValueError(f"Unexpected release languages: {sorted(packs)}, invalid files: {failures}")
    files = {}
    for locale, qt in locales.items():
        catalog = f"qtbase_{qt}.qm"
        files[f"languages/{locale}.json"] = (source / f"{locale}.json").read_bytes()
        files[f"languages/{catalog}"] = (translations / catalog).read_bytes()
    messages = {key: key for pack in packs.values() for key in pack.messages}
    if "Project navigation" not in messages:
        raise ValueError("Missing source catalog for the language template")
    messages["Project navigation"] = "Project browser"
    template = {"locale": "en-GB", "name": "English (author template)", "messages": messages}
    files["authoring/en-GB.json"] = (json.dumps(template, ensure_ascii=False, sort_keys=True, indent=2)
                                      + "\n").encode("utf-8")
    files["THIRD_PARTY_NOTICES.md"] = (ROOT / "THIRD_PARTY_NOTICES.md").read_bytes()
    return files


def color_files():
    files = {}
    for path in sorted((ROOT / "color-packs").glob("*.json")):
        pack = read_palette(path)
        if path.stem != pack.id:
            raise ValueError(f"Color file must be named for its palette ID: {path}")
        files[f"colors/{path.name}"] = path.read_bytes()
    if not files:
        raise ValueError("Missing release color packs")
    return files


def build(output, translations=None):
    guides = ROOT / "docs/extensions"
    bundles = (("01-Language", "language", language_files(translations or qt_translations_directory())),
               ("02-Color", "color", color_files()))
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as temporary:
        for title, kind, files in bundles:
            files["INSTALL.md"] = (guides / f"install-{kind}.md").read_bytes()
            schema = f"{kind}-pack.schema.json"
            files[f"authoring/{schema}"] = (guides / schema).read_bytes()
            files["LICENSE"] = (ROOT / "LICENSE").read_bytes()
            archive = Path(temporary) / f"OrcaView-Extensions-{title}-{__version__}.zip"
            with ZipFile(archive, "w") as bundle:
                for name in sorted(files):
                    item = ZipInfo(name)
                    item.create_system = 3
                    item.external_attr = 0o100644 << 16
                    bundle.writestr(item, files[name], compress_type=ZIP_DEFLATED)
            print(archive.replace(output / archive.name))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/extensions" / __version__)
    parser.add_argument("--qt-translations", type=Path, help="Directory of matching Qt 6.8.3 translations")
    args = parser.parse_args()
    build(args.output, args.qt_translations)

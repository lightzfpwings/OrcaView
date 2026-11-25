"""Build optional language extensions with matching Qt standard-control translations."""

import argparse
import json
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from orcaview import __version__

LANGUAGE_GROUPS = {"Chinese": {"zh-Hans": "zh_CN", "zh-Hant": "zh_TW"},
                   "German": {"de": "de"}, "Japanese": {"ja": "ja"}}


def qt_translations_directory():
    from PySide6.QtCore import QLibraryInfo, qVersion
    if qVersion() != "6.8.3":
        raise ValueError("Build the packs with the same Qt version as the release (6.8.3).")
    return Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))


def build(translations, output):
    packs = ROOT / "language-packs"
    output.mkdir(parents=True, exist_ok=True)
    for name, locales in LANGUAGE_GROUPS.items():
        archive = output / f"OrcaView-{__version__}-{name}-language-pack.zip"
        with ZipFile(archive.with_suffix(".part"), "w", ZIP_DEFLATED) as bundle:
            for locale, qt_locale in locales.items():
                path = packs / (locale + ".json")
                data = json.loads(path.read_bytes())
                if data["locale"] != locale or not data["messages"]:
                    raise ValueError(f"Invalid language extension: {path}")
                bundle.write(path, path.name)
                qt = translations / f"qtbase_{qt_locale}.qm"
                bundle.write(qt, qt.name)
            bundle.write(ROOT / "LICENSE", "OrcaView-LICENSE.txt")
            bundle.write(ROOT / "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md")
        archive.with_suffix(".part").replace(archive)
        print(archive)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qt-translations", type=Path, help="Qt 6.8.3 translations directory")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/languages" / __version__)
    args = parser.parse_args()
    build(args.qt_translations or qt_translations_directory(), args.output)

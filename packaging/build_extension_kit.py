"""Build the importable color pack and the language and color authoring kit."""

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from orcaview import __version__
from orcaview.appearance import read_palette
from orcaview.i18n import discover_languages


def build(output):
    packs, failures = discover_languages(ROOT / "language-packs")
    if failures:
        raise ValueError(f"Invalid language files: {failures}")
    messages = {key: key for pack in packs.values() for key in pack.messages}
    if "Project navigation" not in messages:
        raise ValueError("Missing source catalog for the language template")
    messages["Project navigation"] = "Project browser"
    template = {"locale": "en-GB", "name": "English (author template)", "messages": messages}
    guides = ROOT / "docs/extensions"
    palette = ROOT / "color-packs/contrast.json"
    read_palette(palette)
    members = {name: (guides / name).read_bytes() for name in
               ("README.md", "language-pack.schema.json", "color-pack.schema.json")}
    members["languages/en-GB.json"] = (json.dumps(template, ensure_ascii=False, sort_keys=True, indent=2)
                                      + "\n").encode("utf-8")
    members["colors/contrast.json"] = palette.read_bytes()
    members["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as temporary:
        stage = Path(temporary)
        kit = stage / f"OrcaView-{__version__}-extension-kit.zip"
        with ZipFile(kit, "w") as archive:
            for name, data in members.items():
                item = ZipInfo(name)
                item.create_system = 3
                item.external_attr = 0o100644 << 16
                archive.writestr(item, data, compress_type=ZIP_DEFLATED)
        color = stage / f"OrcaView-{__version__}-Contrast-color-pack.json"
        color.write_bytes(members["colors/contrast.json"])
        for asset in (kit, color):
            print(asset.replace(output / asset.name))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/extensions" / __version__)
    build(parser.parse_args().output)

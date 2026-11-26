"""Check extension assets with the packaged app on its native operating system."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from orcaview.application.updates import _version_key


@contextmanager
def open_package(assets, prefix, work):
    if sys.platform == "darwin":
        mount = work / "disk"
        mount.mkdir()
        dmg, = (path for path in assets.glob(prefix + "?macOS-arm64.dmg") if path.is_file())
        subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-noautoopen", "-mountpoint", mount, dmg],
                       check=True)
        try:
            app = mount / "OrcaView.app"
            subprocess.run(["codesign", "--verify", "--deep", "--strict", app], check=True)
            yield app / "Contents/MacOS/OrcaView", mount / "Examples"
        finally:
            subprocess.run(["hdiutil", "detach", mount], check=True)
    elif sys.platform == "win32":
        with ZipFile(assets / (prefix + "-Windows-x64-portable.zip")) as archive:
            assert {path.split("/")[0] for path in archive.namelist()} == {"OrcaView.exe", "LICENSE", "Examples"}
            archive.extractall(work)
        yield work / "OrcaView.exe", work / "Examples"
    elif sys.platform.startswith("linux"):
        name = prefix + "-Linux-x86_64"
        with tarfile.open(assets / (name + ".tar.gz")) as archive:
            archive.extractall(work, filter="data")
        yield work / name / "OrcaView", work / name / "Examples"
    else:
        raise ValueError(f"Unknown release platform: {sys.platform}")


def check(assets, version):
    prefix = "OrcaView-" + version
    manifest = "SHA256UMS.txt"
    checksums = {name: digest for digest, name in
                 (line.split("  ", 1) for line in (assets / manifest).read_text().splitlines())}
    for path in assets.iterdir():
        if path.is_file() and path.name != manifest:
            with path.open("rb") as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == checksums[path.name], path.name
    with TemporaryDirectory(prefix="orcaview-release-") as temporary:
        work = Path(temporary)
        for title in ("01-Language", "02-Color"):
            dest = work / title
            with ZipFile(assets / f"OrcaView-Extensions-{title}-{version}.zip") as bundle:
                assert bundle.testzip() is None and b"orcaview settings" in bundle.read("INSTALL.md")
                bundle.extractall(dest)
        languages = work / "01-Language/languages"
        qt_locales = ("zh_CN", "zh_TW", "de", "ja")
        assert {p.name for p in languages.glob("*.qm")} == {f"qtbase_{loc}.qm" for loc in qt_locales}
        colors = work / "02-Color/colors"
        assert {p.stem for p in colors.glob("*.json")} == {"contrast", "pastel", "grayscale"}
        env = dict(os.environ, ORCAVIEW_CONFIG_DIR=str(work / "preferences"), ORCAVIEW_HEADLESS="1")
        with open_package(assets, prefix, work) as (binary, examples):
            def run(*args):
                result = subprocess.run([binary, *args], cwd=work, env=env, capture_output=True,
                                        encoding="utf-8", errors="replace", timeout=180)
                if result.returncode:
                    raise RuntimeError(f"{args}: {result.returncode}\n{result.stdout}\n{result.stderr}")
                return result.stdout

            assert run("--version").strip() == version
            if _version_key(version) >= _version_key("0.1.0a63"):
                dimer = work / "water-dimer.xyz"
                dimer.write_text("6\nWater dimer\nO 0 0 0\nH .96 0 0\nH -.25 .92 0\n"
                                 "O 4 .7 0\nH 4.65 1.4 0\nH 4.50 -.12 0\n", encoding="utf-8")
                steps = [
                    {"op": "set-bond", "atom_a": 2, "atom_b": 4, "order": 1, "style": "hydrogen_bond"},
                    {"op": "optimize-hbonds", "distance": 1.90, "angle": 170},
                    {"op": "measure", "atom_ids": [2, 4]},
                ]
                recipe = work / "hydrogen-bond.json"
                recipe.write_text(json.dumps(steps), encoding="utf-8")
                operations = json.loads(run("design", dimer, "--script", recipe))["operations"]
                assert operations[1]["force_field"] in ("MMFF94", "UFF"), operations
                assert abs(operations[2]["value"] - 1.90) < .05, operations
                print(f"Water dimer H···O distance: {operations[2]['value']:.3f} angstrom.")
            spectrum = ("spectrum", examples / "water-raman.out", "--table", "ir", "--format", "png")
            run(*spectrum, "-o", "ir-grid.png")
            run(*spectrum, "--no-grid", "-o", "ir-no-grid.png")
            with_grid, without_grid = ((work / name).read_bytes() for name in ("ir-grid.png", "ir-no-grid.png"))
            for image in (with_grid, without_grid):
                assert image[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", image[16:24]) == (1800, 1100)
            assert with_grid != without_grid
            hydroxyl = examples / "hydroxyl-populations.out"
            spins = run("results", hydroxyl, "--dataset", "mulliken-spin", "--format", "csv")
            assert ",1.024339,available" in spins and ",-0.024339,available" in spins
            run("render", hydroxyl, "spin.png", "--population", "mulliken-spin",
                "--population-scale", "bwr", "--population-symmetric")
            for table in ("1", "2"):
                run("spectrum", examples / "water-nmr.out", "--table", table, "--format", "png",
                    "-o", f"nmr-{table}.png")
            for name in ("spin.png", "nmr-1.png", "nmr-2.png"):
                assert (work / name).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", name
            water = examples / "water.xyz"
            assert "* xyz -1 2" in run("preview", water, "--charge", "-1", "--multiplicity", "2").splitlines()
            edited = work / "edited.inp"
            edited.write_text("! pbe0 def2-svp sp pal8\n%maxcore=2048\n* XYZ 0 1\nO 0 0 0\nH 0 1 0\nH 1 0 0\n*\n")
            normalized = run("preview", water, "--edit-input", edited)
            run("project", water, "--edit-input", edited, "-o", "edited.oview.json")
            assert "PBE0" in normalized and "nprocs 8" in normalized and "%maxcore 2048" in normalized
            assert run("preview", "edited.oview.json") == normalized
            run("gui", water, "--screenshot", "english.png")
            for locale in ("de", "ja", "zh-Hant", "zh-Hans"):
                selected = json.loads(run("settings", "language", "--directory", languages, "--locale", locale))
                assert set(selected["available"]) == {"en", "zh-Hans", "zh-Hant", "de", "ja"}
                assert selected["locale"] == locale and not selected["invalid_files"]
                assert json.loads(run("settings", "language")) == selected
            run("gui", water, "--screenshot", "chinese.png")
            english, chinese = ((work / name).read_bytes() for name in ("english.png", "chinese.png"))
            assert english[:8] == chinese[:8] == b"\x89PNG\r\n\x1a\n" and english != chinese
            render = ("--model", "space-filling", "--width", "240", "--height", "180", "--scale", "1")
            run("render", water, "default.bmp", *render)
            original = (work / "default.bmp").read_bytes()
            for palette in sorted(colors.glob("*.json")):
                installed = json.loads(run("settings", "appearance", "--import-palette", palette))
                assert installed["settings"]["palette_id"] == palette.stem
                assert installed["overrides"] == json.loads(palette.read_bytes())["colors"]
                run("render", water, "installed.bmp", *render)
                run("settings", "appearance", "--palette", "default")
                run("render", water, "one-off.bmp", *render, "--color-pack", palette)
                recolored, once = ((work / name).read_bytes() for name in ("installed.bmp", "one-off.bmp"))
                assert original[:2] == recolored[:2] == once[:2] == b"BM" and original != recolored == once
    print(f"Verified OrcaView {version} on {sys.platform}: spectrum PNGs, editable input, four locales and three color palettes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument("version")
    args = parser.parse_args()
    check(args.assets.resolve(), args.version.removeprefix("v"))

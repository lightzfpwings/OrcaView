"""Check extension assets with the packaged app on its native operating system."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from zipfile import ZipFile


@contextmanager
def open_package(assets, prefix, work):
    if sys.platform == "darwin":
        mount = work / "disk"
        mount.mkdir()
        dmg = assets / (prefix + "-macOS-arm64.dmg")
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
    checksums = {name: digest for digest, name in
                 (line.split("  ", 1) for line in (assets / "SHA256SUMS.txt").read_text().splitlines())}
    for path in assets.iterdir():
        if path.is_file() and path.name != "SHA256SUMS.txt":
            with path.open("rb") as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == checksums[path.name], path.name
    with TemporaryDirectory(prefix="orcaview-release-") as temporary:
        work = Path(temporary)
        languages = work / "external languages"
        for group in ("Chinese", "German", "Japanese"):
            with ZipFile(assets / f"{prefix}-{group}-language-pack.zip") as archive:
                for name in archive.namelist():
                    if name.endswith((".json", ".qm")):
                        archive.extract(name, languages)
        with ZipFile(assets / f"{prefix}-extension-kit.zip") as kit:
            (languages / "en-GB.json").write_bytes(kit.read("languages/en-GB.json"))
            palette = assets / f"{prefix}-Contrast-color-pack.json"
            assert kit.read("colors/contrast.json") == palette.read_bytes()
        env = dict(os.environ, ORCAVIEW_CONFIG_DIR=str(work / "preferences"), ORCAVIEW_HEADLESS="1")
        with open_package(assets, prefix, work) as (binary, examples):
            def run(*args):
                result = subprocess.run([binary, *args], cwd=work, env=env, capture_output=True,
                                        encoding="utf-8", errors="replace", timeout=180)
                if result.returncode:
                    raise RuntimeError(f"{args}: {result.returncode}\n{result.stdout}\n{result.stderr}")
                return result.stdout

            assert run("--version").strip() == version
            water = examples / "water.xyz"
            assert "* xyz -1 2" in run("preview", water, "--charge", "-1", "--multiplicity", "2").splitlines()
            run("gui", water, "--screenshot", "english.png")
            selected = json.loads(run("settings", "language", "--directory", languages, "--locale", "zh-Hans"))
            assert set(selected["available"]) == {"en", "en-GB", "zh-Hans", "zh-Hant", "de", "ja"}
            assert selected["locale"] == "zh-Hans" and not selected["invalid_files"]
            assert json.loads(run("settings", "language")) == selected
            run("gui", water, "--screenshot", "chinese.png")
            english, chinese = ((work / name).read_bytes() for name in ("english.png", "chinese.png"))
            assert english[:8] == chinese[:8] == b"\x89PNG\r\n\x1a\n" and english != chinese
            render = ("--model", "space-filling", "--width", "240", "--height", "180", "--scale", "1")
            run("render", water, "default.bmp", *render)
            installed = json.loads(run("settings", "appearance", "--import-palette", palette))
            assert installed["settings"]["palette_id"] == "contrast"
            assert installed["overrides"] == json.loads(palette.read_bytes())["colors"]
            run("render", water, "installed.bmp", *render)
            run("settings", "appearance", "--palette", "default")
            run("render", water, "one-off.bmp", *render, "--color-pack", palette)
            original, recolored, once = ((work / name).read_bytes() for name in
                                         ("default.bmp", "installed.bmp", "one-off.bmp"))
            assert original[:2] == recolored[:2] == once[:2] == b"BM" and original != recolored == once
    print(f"Verified OrcaView {version} on {sys.platform}: languages, persistent color pack and one-off export.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument("version")
    args = parser.parse_args()
    check(args.assets.resolve(), args.version.removeprefix("v"))

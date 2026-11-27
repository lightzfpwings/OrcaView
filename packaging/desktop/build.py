"""Assemble relocatable x86-64 releases using verified target-native runtimes."""

import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCK = json.loads((HERE / "dependencies.json").read_text())
PYTHON = "3.13"
sys.path.insert(0, str(HERE.parent))
from release_examples import install_examples
from release_language import check_release_sources

LINUX_ENTRY = """#!/bin/sh
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
if [ "$#" -eq 0 ]; then set -- gui; fi
exec "$root/python/bin/python3" -I -m orcaview "$@"
"""


def dependency(entry, cache):
    path = cache / entry["name"]
    if not path.exists():
        with TemporaryDirectory(dir=cache) as temp:
            download = Path(temp) / "download"
            with urlopen(entry["url"], timeout=180) as response, download.open("wb") as out:
                shutil.copyfileobj(response, out)
            verify(download, entry["sha256"])
            download.replace(path)
    else:
        verify(path, entry["sha256"])
    return path


def verify(path, expected):
    with path.open("rb") as stream:
        if file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError(f"SHA-256 mismatch: {path}")


def runtime_member(member):
    parts = Path(member.name).parts
    if parts[0] != "python":
        raise ValueError(f"Unexpected runtime path: {member.name}")
    # Qt provides the GUI. Exclude compiler headers, pip, Tk tooling and tests.
    if any(p in {"__pycache__", "test", "tests", "tkinter", "idlelib",
                 "tcl", "include", "ensurepip", "site-packages", "pkgconfig", "terminfo"} for p in parts):
        return False
    if parts[:2] == ("python", "bin"):
        return len(parts) == 2 or parts[-1] in {"python", "python3", "python3.13"}
    return True


def wheel_runtime_member(name):
    """Omit SDK inputs and standalone development tools from the desktop runtime."""
    parts = Path(name).parts
    if len(parts) > 1 and parts[0] == "PySide6":
        if name.endswith(".qm"):
            return False
        if parts[1] in {"doc", "glue", "include", "scripts", "typesystems"}:
            return False
        if len(parts) == 2 or parts[1:3] == ("Qt", "libexec"):
            return Path(parts[-1]).stem not in {
                "assistant", "designer", "linguist", "lrelease", "lupdate", "qmlcachegen",
                "qmlformat", "qmlimportscanner", "qmllint", "qmlls", "qmltyperegistrar",
                "rcc", "svgtoqml", "uic",
            }
    if parts[0] == "openbabel":
        if "include" in parts or "cmake" in parts:
            return False
        if len(parts) == 3 and parts[1] == "bin" and parts[2].startswith("ob"):
            return Path(parts[2]).suffix not in ("", ".exe")
    return True


def install_wheel(path, site):
    with ZipFile(path) as wheel:
        for info in wheel.infolist():
            if not wheel_runtime_member(info.filename):
                continue
            # All locked wheels use the site-packages layout directly.
            target = Path(wheel.extract(info, site))
            if info.external_attr >> 16 & 0o111 and not target.is_dir():
                target.chmod(0o755)


def write_zip_file(archive, path, root, compression=ZIP_DEFLATED):
    # Use release-independent timestamps/modes even for the ZIP inside the PE.
    info = ZipInfo(path.relative_to(root).as_posix())
    info.compress_type = compression
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    with path.open("rb") as src, archive.open(info, "w") as dest:
        shutil.copyfileobj(src, dest)


def windows_package(bundle, archive, version):
    go = shutil.which("go")
    if not go:
        raise RuntimeError("Install Go 1.23 or later to compile the Windows launcher.")
    env = dict(os.environ, CGO_ENABLED="0", GOOS="windows", GOARCH="amd64", GOAMD64="v1",
               GOTOOLCHAIN="local", GO111MODULE="on", GOWORK="off")
    executable = bundle / "OrcaView.exe"
    # Building a Go package includes its Windows resource object; building a .go file skips it.
    if not (HERE / "resources_windows_amd64.syso").is_file():
        raise FileNotFoundError("Windows launcher icon resources are missing.")
    subprocess.run([go, "build", "-trimpath", "-buildvcs=false", "-ldflags=-s -w -H=windowsgui -buildid=",
                    "-o", str(executable.resolve()), "."], cwd=HERE, env=env, check=True)
    goroot = Path(subprocess.check_output([go, "env", "GOROOT"], env=env, text=True).strip())
    licenses = bundle / "python/ThirdParty"
    shutil.copyfile(goroot / "LICENSE", licenses / "Go-LICENSE.txt")
    shutil.copyfile(goroot / "PATENTS", licenses / "Go-PATENTS.txt")
    license_file = bundle / "LICENSE"
    license_file.write_bytes(b"\n\n".join((ROOT / file).read_bytes() for file in ("LICENSE", "THIRD_PARTY_NOTICES.md"))
                             + b"\n\nGo runtime license\n\n" + (goroot / "LICENSE").read_bytes())
    examples = sorted(p for p in (bundle / "Examples").rglob("*") if p.is_file())
    managed = {}
    for path in [license_file, *examples]:
        with path.open("rb") as source:
            managed[path.relative_to(bundle).as_posix()] = file_digest(source, "sha256").hexdigest()
    with ZipFile(executable, "a") as payload:
        manifest = {"format": "orcaview-windows-portable-v1", "version": version, "files": managed}
        payload.writestr(ZipInfo("orcaview-windows.json"), json.dumps(manifest, ensure_ascii=False).encode("utf-8"))
        for path in sorted((bundle / "python").rglob("*")):
            if path.is_file():
                write_zip_file(payload, path, bundle)
    with ZipFile(archive, "w") as release:
        write_zip_file(release, executable, bundle, ZIP_STORED)
        for path in [license_file, *examples]:
            write_zip_file(release, path, bundle)


def install_app(site):
    source = ROOT / "src/orcaview"
    # A checked source hash and a stable filename make bytecode independent of
    # the build directory. Sibling .pyc modules also work in a read-only install.
    for path in sorted(source.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        dest = site / "orcaview" / path.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".py":
            py_compile.compile(str(path), str(dest.with_suffix(".pyc")),
                               "orcaview/" + path.relative_to(source).as_posix(),
                               doraise=True, invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
        elif path.suffix in {".json", ".png", ".svg"} or path.parent == source / "results/data":
            shutil.copyfile(path, dest)


def assemble(target, bundle, cache, version):
    runtime, *wheels = [dependency(entry, cache) for entry in LOCK[target]]
    third_party = bundle / "python/ThirdParty"
    third_party.mkdir(parents=True)
    shutil.copyfile(ROOT / "LICENSE", third_party / "OrcaView-LICENSE.txt")
    shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", third_party / "THIRD_PARTY_NOTICES.md")
    shutil.copyfile(ROOT / "packaging/licenses/GPL-3.0.txt", third_party / "GPL-3.0.txt")
    shutil.copyfile(ROOT / "packaging/licenses/wgpu-native-MIT.txt", third_party / "wgpu-native-MIT.txt")
    sources = (HERE / "SOURCES.txt").read_text(encoding="utf-8").replace("@VERSION@", version)
    (third_party / "SOURCES.txt").write_bytes(sources.encode("utf-8"))
    install_examples(ROOT, bundle / "Examples")
    with tarfile.open(runtime) as tar:
        tar.extractall(bundle, members=(m for m in tar if runtime_member(m)), filter="data")
    if target == "windows":
        site = bundle / "python/Lib/site-packages"
    else:
        site = bundle / "python/lib/python3.13/site-packages"
        entry = bundle / "OrcaView"
        entry.write_text(LINUX_ENTRY, encoding="utf-8")
        entry.chmod(0o755)
    site.mkdir(parents=True, exist_ok=True)
    for wheel in wheels:
        install_wheel(wheel, site)
    if target == "windows":
        # The official wheel looks for force-field files in the Unix-style
        # share path, although it installs its Windows data next to obabel.exe.
        from orcaview.io.babel_worker import prepare_windows_babel_data
        babel = site / "openbabel"
        prepare_windows_babel_data(babel / "bin/data", babel / "share/openbabel/3.2.0")
    install_app(site)
    if target == "windows":
        return  # The single-file launcher carries its own external-file inventory.
    # Up to a43 the Linux updater installs only the former example directory.
    # Carry a compact seed through its runtime swap for the first launch.
    with ZipFile(bundle / "python/orcaview-examples.zip", "w") as seed:
        for path in sorted((bundle / "Examples").rglob("*")):
            if path.is_file():
                write_zip_file(seed, path, bundle / "Examples")
    files = {}
    for path in sorted(bundle.rglob("*")):
        if not path.is_symlink() and path.is_file():
            with path.open("rb") as stream:
                files[path.relative_to(bundle).as_posix()] = file_digest(stream, "sha256").hexdigest()
    (bundle / "python/orcaview-files.json").write_text(
        json.dumps(files, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def release_member(member):
    """Keep the build machine's user and group out of public archives."""
    member.uid = member.gid = 0
    member.uname = member.gname = ""
    return member


def build(target, output, cache):
    sys.path.insert(0, str(ROOT / "src"))
    from orcaview import __version__
    check_release_sources(ROOT)
    dest = output / target / __version__
    dest.mkdir(parents=True, exist_ok=True)
    label, ext = ("Windows-x64-portable", ".zip") if target == "windows" else ("Linux-x86_64", ".tar.gz")
    name = f"OrcaView-{__version__}-{label}"
    final = dest / (name + ext)
    with TemporaryDirectory(dir=dest) as temp:
        work = Path(temp)
        bundle = work / name
        assemble(target, bundle, cache, __version__)
        archive = work / final.name
        if target == "windows":
            windows_package(bundle, archive, __version__)
        else:
            with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
                tar.add(bundle, arcname=name, filter=release_member)
        os.replace(archive, final)
    print(final, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("windows", "linux", "both"))
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--cache", type=Path, help="Reuse verified downloads in this directory")
    args = parser.parse_args()
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 13):
        parser.error(f"Use CPython {PYTHON} to match the target's bytecode format.")
    with TemporaryDirectory() as temp:
        cache = args.cache or Path(temp)
        cache.mkdir(parents=True, exist_ok=True)
        for target in (("linux", "windows") if args.target == "both" else (args.target,)):
            build(target, args.output, cache)


if __name__ == "__main__":
    main()

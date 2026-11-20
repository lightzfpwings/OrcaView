"""Build in an arm64 venv containing PyInstaller and the project's GUI dependency."""

from hashlib import sha256
from importlib.metadata import distribution
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen


_BABEL_ARCHIVE = "openbabel-3.2.0.tar.gz"
_BABEL_SOURCE = ("https://files.pythonhosted.org/packages/29/67/"
                 "7e1c86fa3a932bba8d8c9dcef040687f1bce1f2903a29acd4fb5337bbea8/" + _BABEL_ARCHIVE)
_BABEL_SHA256 = "332e6038146e0b69f9c32b8d71d6de153a095d98dce4663972c4a45e55449d01"


def include_openbabel_sources(root, image_root):
    """Ship the unmodified sources matching the embedded Open Babel wheel."""
    package = distribution("openbabel")
    if package.version != "3.2.0":
        raise ValueError("请在打包环境安装 openbabel==3.2.0。")
    third_party = image_root / "第三方软件" / "Open Babel"
    third_party.mkdir(parents=True)
    archive = third_party / _BABEL_ARCHIVE
    cached = root / "dist" / "cache" / _BABEL_ARCHIVE
    if cached.is_file():
        shutil.copyfile(cached, archive)
    else:
        with urlopen(_BABEL_SOURCE, timeout=120) as response, archive.open("wb") as dest:
            shutil.copyfileobj(response, dest)
    if sha256(archive.read_bytes()).hexdigest() != _BABEL_SHA256:
        raise ValueError("Open Babel 源码包 SHA-256 与官方发布不符。")
    for entry in package.files:
        if entry.name in ("COPYING", "AUTHORS") and "licenses" in entry.parts:
            shutil.copy2(package.locate_file(entry), third_party / entry.name)


def main():
    packaging_dir = Path(__file__).resolve().parent
    root = packaging_dir.parents[1]
    sys.path.insert(0, str(root / "src"))
    from orcaview import __version__

    output = root / "dist" / "macos" / __version__
    output.mkdir(parents=True, exist_ok=True)
    app = output / "OrcaView.app"
    dmg = output / f"OrcaView-{__version__}-macOS-arm64.dmg"
    if app.exists() or dmg.exists():
        raise SystemExit(f"请先移走上次构建的应用和镜像，再运行打包：{output}")

    # Keep intermediate files on the destination filesystem for final renames.
    with TemporaryDirectory(prefix=".build-", dir=output) as directory:
        work = Path(directory)
        env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / "cache"),
                   PYTHONPATH=str(root / "src"), PYTHONDONTWRITEBYTECODE="1")
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--distpath", str(work / "frozen"),
            "--workpath", str(work / "work"), str(packaging_dir / "OrcaView.spec"),
        ], env=env, check=True)
        image_root = work / "image"
        samples = image_root / "示例"
        samples.mkdir(parents=True)
        include_openbabel_sources(root, image_root)
        bundle = image_root / app.name
        (work / "frozen" / app.name).rename(bundle)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", bundle], check=True)
        (image_root / "Applications").symlink_to("/Applications")
        shutil.copy2(root / "examples" / "water.xyz", samples)
        shutil.copytree(root / "examples" / "structure_import", samples / "文件导入")
        shutil.copy2(root / "examples" / "m5_orca" / "water-sp.out", samples)
        logs = root / "artifacts" / "public" / "validation" / "results-0.1.0a12"
        for source, name in (("raman/water.out", "water-raman.out"),
                             ("nmr/water-shield.out", "water-nmr.out"),
                             ("tdcd/peroxide.out", "peroxide-uv-cd.out")):
            shutil.copy2(logs / source, samples / name)
        shutil.copytree(root / "examples" / "native_methods", samples / "原生计算输入")
        shutil.copy2(root / "LICENSE", image_root / "LICENSE.txt")
        shutil.copy2(root / "THIRD_PARTY_NOTICES.md", image_root)
        shutil.copy2(packaging_dir / "试用说明.txt", image_root)
        shutil.copy2(root / "tools" / "check_orca611.sh", samples)
        image = work / dmg.name
        subprocess.run([
            "hdiutil", "create", "-volname", "OrcaView", "-fs", "HFS+",
            "-format", "UDZO", "-srcfolder", image_root, image,
        ], check=True)
        subprocess.run(["hdiutil", "verify", image], check=True)
        bundle.rename(app)
        image.rename(dmg)
    print(app)
    print(dmg)


if __name__ == "__main__":
    main()

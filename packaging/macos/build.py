"""Build in an arm64 venv containing PyInstaller and the project's GUI dependency."""

import os
from pathlib import Path
from shutil import which
import subprocess
import sys
from tempfile import TemporaryDirectory


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_examples import install_examples
from release_language import check_release_sources


def main():
    packaging_dir = Path(__file__).resolve().parent
    root = packaging_dir.parents[1]
    sys.path.insert(0, str(root / "src"))
    from orcaview import __version__

    check_release_sources(root)
    output = root / "dist" / "macos" / __version__
    output.mkdir(parents=True, exist_ok=True)
    app = output / "OrcaView.app"
    dmg = output / f"OrcaView-{__version__}-macOS-arm64.dmg"
    if app.exists() or dmg.exists():
        raise SystemExit(f"Move the previous app and disk image before rebuilding: {output}")

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
        install_examples(root, image_root / "Examples")
        bundle = image_root / app.name
        (work / "frozen" / app.name).rename(bundle)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", bundle], check=True)
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
    git = which("git")
    if git and (root / ".git").exists():
        setting = subprocess.run([git, "-C", root, "config", "--local", "--path", "--get",
                                  "orcaview.backupDirectory"], capture_output=True, text=True)
        destination = setting.stdout.rstrip("\n")
        if setting.returncode == 0 and destination:
            result = subprocess.run([sys.executable, "-B", root / "tools/backup_workspace_macos.py",
                                     "--destination", destination])
            if result.returncode:
                print("The app and disk image are ready. The workspace backup failed. "
                      f"Retry the workspace backup to {destination}.", file=sys.stderr)


if __name__ == "__main__":
    main()

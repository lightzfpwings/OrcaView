"""Run the regression archive and the checkout's new or updated tests."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "artifacts" / "public" / "OrcaView-verification-0.1.0a44.zip"


def main():
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT / "src"), env.get("PYTHONPATH"))))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    with TemporaryDirectory(prefix="orcaview-tests-") as temp:
        work = Path(temp)
        with ZipFile(ARCHIVE) as archive:
            archive.extractall(work)
        if (ROOT / "tests").is_dir():
            shutil.copytree(ROOT / "tests", work / "tests", dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copytree(ROOT / "examples", work / "examples")
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", *sys.argv[1:]]
        return subprocess.run(command, env=env, cwd=work).returncode


if __name__ == "__main__":
    raise SystemExit(main())

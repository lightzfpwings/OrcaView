"""Run the archived regression suite against the current checkout."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "artifacts" / "public" / "OrcaView-verification-0.1.0a24.zip"


def main():
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT / "src"), env.get("PYTHONPATH"))))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    with TemporaryDirectory(prefix="orcaview-tests-") as temp:
        work = Path(temp)
        with ZipFile(ARCHIVE) as archive:
            archive.extractall(work)
        shutil.copytree(ROOT / "examples", work / "examples")
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", *sys.argv[1:]]
        return subprocess.run(command, env=env, cwd=work).returncode


if __name__ == "__main__":
    raise SystemExit(main())

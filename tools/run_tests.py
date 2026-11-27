"""Run the regression suite from this checkout with isolated default preferences."""

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


def main():
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(ROOT / "src"), env.get("PYTHONPATH"))))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    with TemporaryDirectory(prefix="orcaview-tests-") as temp:
        env.setdefault("ORCAVIEW_CONFIG_DIR", temp)
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", *sys.argv[1:]]
        return subprocess.run(command, env=env, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())

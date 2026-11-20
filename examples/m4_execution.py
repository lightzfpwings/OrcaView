"""Run a frozen input through the M4 lifecycle using an explicit fake ORCA executable."""

from hashlib import sha256
from pathlib import Path
import shlex
import sys
from tempfile import TemporaryDirectory

from orcaview.application.session import Session
from orcaview.core.models import CalculationSpec
from orcaview.core.tasks import ResourceBudget
from orcaview.execution import LocalOrcaRunner
from orcaview.orca.input import InputCompanionFile, freeze_input


def install_fake_orca(directory: Path) -> Path:
    script = directory / "fake_driver.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "if len(sys.argv) == 1 or sys.argv[1] in ('--version', '-v'):\n"
        "    print('Program Version 6.1.1')\n"
        "    raise SystemExit(2)\n"
        "assert Path(sys.argv[1]).is_file()\n"
        "assert Path('water.xyz').is_file()\n"
        "print('Synthetic process read the frozen input and XYZ.')\n"
        "print('ORCA TERMINATED NORMALLY')\n",
        encoding="utf-8",
    )
    executable = directory / "fake orca"
    executable.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} \"$@\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


def main() -> None:
    xyz = Path(__file__).with_name("water.xyz")
    session = Session()
    session.open_xyz(xyz)
    snapshot = freeze_input(
        session.document.head,
        CalculationSpec(cores=1, maxcore_mb=128),
        companions=(InputCompanionFile.from_path("external_xyz", "water.xyz", xyz),),
    )
    with TemporaryDirectory(prefix="orcaview-m4-") as temp:
        workspace = Path(temp).resolve()
        runner = LocalOrcaRunner(workspace / "attempts", budget=ResourceBudget(1, 1, 128))
        started = runner.start(snapshot, install_fake_orca(workspace), timeout_seconds=10)
        attempt = runner.wait(started.attempt_id, timeout=15)
        if attempt.state != "succeeded":
            raise RuntimeError(f"Synthetic process failed with {attempt.error}")

        print("M4 synthetic process demo (no ORCA calculation)")
        print(f"reported_version={attempt.tool_version} exit_code={attempt.exit_code}")
        print(f"state={attempt.state} normal_termination={attempt.normal_termination}")
        package = [(snapshot.main_input_path, snapshot.input_sha256)]
        package.extend((file.relative_path, file.sha256) for file in snapshot.companions)
        for relative_path, expected in package:
            observed = sha256((attempt.directory / relative_path).read_bytes()).hexdigest()
            if observed != expected:
                raise ValueError(f"Staged input digest mismatch for {relative_path}")
            print(f"Verified {relative_path} sha256={observed}")
        stages = [event.stage for event in runner.events(attempt.attempt_id) if event.kind == "state"]
        print("State events " + " -> ".join(stages))
        print(Path(attempt.output.path_hint).read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()

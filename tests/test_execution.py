"""Exercise execution lifecycle with a fake ORCA driver and real OS processes."""

from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import sys
import tempfile
import textwrap
from threading import Event
import time
import unittest

from orcaview.application.document import MoleculeDocument
from orcaview.core.models import Atom, CalculationSpec, Molecule
from orcaview.core.tasks import ResourceBudget, TaskEvent
from orcaview.execution import LocalOrcaRunner, probe_orca
from orcaview.execution._workspace import stage_attempt, verify_attempt_inputs
from orcaview.orca.input import InputCompanionFile, freeze_input


NORMAL_MARKER = b"ORCA TERMINATED NORMALLY"
WATER_XYZ = b"3\nwater fixture\nO 0 0 0\nH 1 0 0\nH -0.25 1 0\n"
SYNTHETIC_GBW = b"\x00synthetic GBW bytes\xff"


@unittest.skipUnless(os.name == "posix", "Local ORCA process groups require POSIX")
class ExecutionTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix="orcaview execution tests ")
        self.addCleanup(workspace.cleanup)
        self.workspace = Path(workspace.name).resolve()
        self.runs = self.workspace / "attempts"
        self.invocations = self.workspace / "calculation.started"
        self.executable = self.workspace / "fake orca"
        molecule = Molecule(
            "water", (Atom("O", 0, 0, 0), Atom("H", 1, 0, 0), Atom("H", -0.25, 1, 0))
        )
        self.geometry = MoleculeDocument.from_molecule(molecule).head
        self.spec = CalculationSpec(cores=1, maxcore_mb=128)
        self.input = freeze_input(self.geometry, self.spec)
        self.budget = ResourceBudget(processes=1, threads_per_process=1, total_memory_mb=128)
        self.runner = LocalOrcaRunner(self.runs, budget=self.budget, terminate_grace_seconds=0.15)

    def install_driver(self, calculation, version="6.1.1", version_exit=2):
        # Keep the fake executable path valid even when the test interpreter path contains spaces.
        script = self.workspace / "driver.py"
        script.write_text(
            "import os, signal, subprocess, sys, time\n"
            "from pathlib import Path\n"
            "if len(sys.argv) == 1 or sys.argv[1] in ('--version', '-v'):\n"
            f"    print('Program Version {version}', flush=True)\n"
            f"    raise SystemExit({version_exit})\n"
            f"with Path({str(self.invocations)!r}).open('a') as trace:\n"
            "    trace.write(str(Path.cwd()) + '\\n')\n"
            "if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():\n"
            "    raise SystemExit(22)\n"
            + textwrap.dedent(calculation).lstrip(),
            encoding="utf-8",
        )
        self.executable.write_text(
            f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} \"$@\"\n",
            encoding="utf-8",
        )
        self.executable.chmod(0o700)

    def frozen_files(self):
        original_xyz = self.workspace / "original.xyz"
        original_gbw = self.workspace / "original.gbw"
        original_xyz.write_bytes(WATER_XYZ)
        original_gbw.write_bytes(SYNTHETIC_GBW)
        bundle = freeze_input(
            self.geometry,
            self.spec,
            companions=(
                InputCompanionFile.from_path("external_xyz", "water.xyz", original_xyz),
                InputCompanionFile.from_path("initial_gbw", "guess.gbw", original_gbw),
            ),
        )
        original_xyz.write_bytes(b"XYZ changed after freeze")
        original_gbw.unlink()
        return bundle

    def wait_for(self, predicate, limit=5):
        deadline = time.monotonic() + limit
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("Timed out waiting for test process evidence")
            time.sleep(0.01)

    def start(self, snapshot=None, **options):
        attempt = self.runner.start(self.input if snapshot is None else snapshot,
                                    self.executable, **options)
        self.addCleanup(self.cancel_if_active, attempt.attempt_id)
        return attempt

    def cancel_if_active(self, attempt_id):
        self.runner.cancel(attempt_id)
        self.runner.wait(attempt_id, timeout=5)

    def finish(self, attempt):
        return self.runner.wait(attempt.attempt_id, timeout=8)

    def active(self, pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        # Linux can retain terminated orphans as zombies until init reaps them.
        if Path("/proc/self/stat").is_file():
            try:
                status = (Path("/proc") / str(pid) / "stat").read_bytes()
            except FileNotFoundError:
                return False
            return status.rpartition(b")")[2].split()[0] != b"Z"
        return True

    def stop_child(self, pid):
        if self.active(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def test_stages_exact_frozen_files_and_retries_in_an_independent_directory(self):
        snapshot = self.frozen_files()
        self.install_driver(f"""
            assert Path('water.xyz').read_bytes() == {WATER_XYZ!r}
            assert Path('guess.gbw').read_bytes() == {SYNTHETIC_GBW!r}
            assert os.environ['OMP_NUM_THREADS'] == '1'
            assert os.environ['OPENBLAS_NUM_THREADS'] == '1'
            print('merged stderr evidence', file=sys.stderr, flush=True)
            print('ORCA TERMINATED NORMALLY', flush=True)
            sys.exit(7)
        """)
        first = self.finish(self.start(snapshot, job_id="shared-job"))
        self.assertEqual(first.state, "failed")
        self.assertEqual(first.tool_version, "6.1.1")
        self.assertEqual(first.exit_code, 7)
        self.assertIs(first.normal_termination, True)
        self.assertEqual((first.directory / snapshot.main_input_path).read_bytes(), snapshot.input_bytes)
        for dependency in snapshot.companions:
            self.assertEqual((first.directory / dependency.relative_path).read_bytes(), dependency.content)
        manifest = json.loads((first.directory / ".orcaview" / "input-manifest.json").read_text())
        self.assertEqual(manifest["snapshot_digest"], snapshot.snapshot_digest)
        self.assertEqual(manifest["geometry_ref"]["snapshot_id"], snapshot.geometry_ref.snapshot_id)
        self.assertEqual(
            {item["relative_path"]: item["sha256"] for item in manifest["files"]},
            {snapshot.main_input_path: snapshot.input_sha256,
             **{item.relative_path: item.sha256 for item in snapshot.companions}},
        )
        output = Path(first.output.path_hint)
        original_output = output.read_bytes()
        self.assertIn(b"merged stderr evidence", original_output)
        self.assertIn(NORMAL_MARKER, original_output)
        self.assertEqual(first.output.sha256, sha256(original_output).hexdigest())

        first_asset = first.directory / "guess.gbw"
        first_asset.write_bytes(b"changed first attempt")
        self.install_driver("print('this run emits no terminal marker', flush=True)")
        retry = self.runner.retry(first.attempt_id)
        self.addCleanup(self.cancel_if_active, retry.attempt_id)
        second = self.finish(retry)
        self.assertEqual(second.job_id, first.job_id)
        self.assertNotEqual(second.attempt_id, first.attempt_id)
        self.assertNotEqual(second.directory, first.directory)
        self.assertEqual((second.directory / "guess.gbw").read_bytes(), SYNTHETIC_GBW)
        self.assertEqual(first_asset.read_bytes(), b"changed first attempt")
        self.assertEqual(output.read_bytes(), original_output)
        self.assertEqual(second.state, "needs_review")
        self.assertEqual(second.error.code, "missing_termination")
        self.assertEqual(second.exit_code, 0)
        self.assertIs(second.normal_termination, False)

    def test_nonzero_exit_preserves_diagnostic_output(self):
        self.install_driver("""
            print('diagnostic', file=sys.stderr, flush=True)
            sys.exit(7)
        """)
        attempt = self.finish(self.start())
        self.assertEqual(attempt.state, "failed")
        self.assertEqual(attempt.exit_code, 7)
        self.assertIs(attempt.normal_termination, False)
        self.assertIsNotNone(attempt.error)
        self.assertIn(b"diagnostic", Path(attempt.output.path_hint).read_bytes())

    def test_missing_executable_and_wrong_version_do_not_launch_calculation(self):
        missing = self.finish(self.start())
        self.install_driver("print('unexpected execution')", version="6.0.1")
        incompatible = self.finish(self.start())
        for attempt in (missing, incompatible):
            with self.subTest(attempt=attempt.attempt_id):
                self.assertEqual(attempt.state, "failed")
                self.assertIsNone(attempt.exit_code)
                self.assertIsNotNone(attempt.error)
        self.assertFalse(self.invocations.exists())

    def test_budget_mismatch_stops_launch(self):
        self.install_driver("print('unexpected execution')")
        oversized = freeze_input(self.geometry, CalculationSpec(cores=2, maxcore_mb=128))
        attempt = self.finish(self.start(oversized))
        self.assertEqual(attempt.state, "failed")
        self.assertIsNone(attempt.exit_code)
        self.assertIsNotNone(attempt.error)
        self.assertFalse(self.invocations.exists())

    def test_staging_rejects_reuse_tampering_and_stale_output(self):
        snapshot = self.frozen_files()
        directory = stage_attempt(self.runs, "base", snapshot)
        with self.assertRaises(FileExistsError):
            stage_attempt(self.runs, "base", snapshot)
        for attempt_id, filename, replacement in (
            ("changed", "guess.gbw", b"wrong bytes"),
            ("missing", "guess.gbw", None),
            ("stale", "job.out", NORMAL_MARKER),
        ):
            with self.subTest(attempt=attempt_id):
                workspace = stage_attempt(self.runs, attempt_id, snapshot)
                changed = workspace / filename
                if replacement is None:
                    changed.unlink()
                else:
                    changed.write_bytes(replacement)
                with self.assertRaises(ValueError):
                    verify_attempt_inputs(workspace, snapshot)
        self.assertEqual((directory / "guess.gbw").read_bytes(), SYNTHETIC_GBW)
        self.assertFalse(self.invocations.exists())

    def test_input_changed_during_preflight_prevents_launch(self):
        self.install_driver("print('unexpected execution')")

        def change_staged_input(executable):
            directory, = self.runs.iterdir()
            (directory / "guess.gbw").write_bytes(b"changed during preflight")
            return probe_orca(executable)

        self.runner = LocalOrcaRunner(self.runs, budget=self.budget, preflight=change_staged_input)
        attempt = self.finish(self.start(self.frozen_files()))
        self.assertEqual(attempt.state, "failed")
        self.assertIsNone(attempt.exit_code)
        self.assertIsNotNone(attempt.error)
        self.assertEqual((attempt.directory / "guess.gbw").read_bytes(), b"changed during preflight")
        self.assertFalse(self.invocations.exists())

    def test_executable_changed_after_probe_prevents_launch(self):
        self.install_driver("print('unexpected execution')")

        def change_executable(executable):
            probe = probe_orca(executable)
            with executable.open("a", encoding="utf-8") as stream:
                stream.write("\n# changed after version check\n")
            return probe

        self.runner = LocalOrcaRunner(self.runs, budget=self.budget, preflight=change_executable)
        attempt = self.finish(self.start())
        self.assertEqual(attempt.state, "failed")
        self.assertEqual(attempt.error.code, "orca_executable_changed")
        self.assertIsNone(attempt.exit_code)
        self.assertFalse(self.invocations.exists())

    def test_cancel_during_preflight_prevents_launch(self):
        self.install_driver("print('unexpected execution')")
        entered = Event()
        release = Event()

        def blocked_probe(executable):
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError("Test did not release preflight")
            return probe_orca(executable)

        self.runner = LocalOrcaRunner(self.runs, budget=self.budget, preflight=blocked_probe)
        started = self.start()
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(timeout=5))
        self.assertTrue(self.runner.cancel(started.attempt_id))
        self.assertEqual(self.runner.get(started.attempt_id).state, "cancelling")
        release.set()
        attempt = self.finish(started)
        self.assertEqual(attempt.state, "cancelled")
        self.assertIsNone(attempt.exit_code)
        self.assertFalse(self.invocations.exists())

    def test_incremental_log_events_and_observational_recovery_before_completion(self):
        self.install_driver("""
            print('first chunk', flush=True)
            while not Path('release').exists():
                time.sleep(0.02)
            print('second chunk', flush=True)
            print('ORCA TERMINATED NORMALLY', flush=True)
        """)
        started = self.start(timeout_seconds=10)
        attempt_id = started.attempt_id
        log = started.directory / ".orcaview" / "orca-output.log"
        self.wait_for(lambda: log.exists() and b"first chunk" in log.read_bytes())
        self.wait_for(lambda: any(event.kind == "log" for event in self.runner.events(attempt_id)))
        observed_events = self.runner.events(attempt_id)
        self.assertEqual(self.runner.get(attempt_id).state, "running")
        self.assertNotIn(b"second chunk", log.read_bytes())
        with self.assertRaises(TimeoutError):
            self.runner.wait(attempt_id, timeout=0.01)

        reopened = LocalOrcaRunner(self.runs, budget=self.budget)
        pending, = reopened.recover()
        self.assertEqual(pending["attempt_id"], attempt_id)
        self.assertEqual(pending["state"], "needs_review")
        self.assertIsNone(pending.get("exit_code"))
        self.assertEqual(self.invocations.read_text().splitlines(), [str(started.directory)])

        (started.directory / "release").touch()
        complete = self.finish(started)
        events = self.runner.events(attempt_id)
        new_events = self.runner.events(attempt_id, after_sequence=observed_events[-1].sequence)
        self.assertEqual(complete.state, "succeeded", complete.error)
        self.assertIn(b"second chunk", log.read_bytes())
        self.assertEqual(new_events, events[len(observed_events):])
        self.assertTrue(new_events)
        for previous, current in zip(events, events[1:]):
            self.assertIsInstance(current, TaskEvent)
            self.assertEqual(current.attempt_id, attempt_id)
            current.check_after(previous)
        done, = reopened.recover()
        self.assertEqual(done["state"], "succeeded")
        self.assertEqual(done["exit_code"], 0)

    def test_frozen_ten_decimal_attempt_survives_recovery_and_new_staging(self):
        # Both fixtures were staged by the previous ten-decimal renderer.
        fixture = Path(__file__).parent / "fixtures" / "legacy-inline-a25"
        legacy = self.runs / "legacy-a25"
        metadata = legacy / ".orcaview"
        metadata.mkdir(parents=True)
        old_manifest = metadata / "input-manifest.json"
        old_input = legacy / "job.inp"
        shutil.copyfile(fixture / "job.inp", old_input)
        shutil.copyfile(fixture / "input-manifest.json", old_manifest)
        recovered, = self.runner.recover()
        self.assertEqual(recovered["attempt_id"], "legacy-a25")
        current = stage_attempt(self.runs, "current", self.input)
        self.assertIn(b"  H  -0.25000000  1.00000000  0.00000000\n",
                      (current / self.input.main_input_path).read_bytes())
        self.assertEqual(old_input.read_bytes(), (fixture / "job.inp").read_bytes())
        self.assertEqual(old_manifest.read_bytes(), (fixture / "input-manifest.json").read_bytes())
        legacy_digest = json.loads(old_manifest.read_text())["files"][0]["sha256"]
        self.assertEqual(legacy_digest, sha256(old_input.read_bytes()).hexdigest())
        self.assertNotEqual(legacy_digest, self.input.input_sha256)

    def test_recovery_does_not_invent_exit_code_from_stale_output(self):
        workspace = stage_attempt(self.runs, "partial", self.input)
        metadata = workspace / ".orcaview"
        (metadata / "execution.json").write_text('{"schema_version":')
        (metadata / "orca-output.log").write_bytes(NORMAL_MARKER)
        report, = self.runner.recover()
        self.assertEqual(report["state"], "needs_review")
        self.assertEqual(report["attempt_id"], "partial")
        self.assertIsNone(report.get("exit_code"))
        self.assertFalse(self.invocations.exists())

    def test_execution_deadline_preserves_partial_log(self):
        self.install_driver("""
            print('partial output before timeout', flush=True)
            time.sleep(60)
        """)
        attempt = self.finish(self.start(timeout_seconds=0.8))
        self.assertEqual(attempt.state, "failed")
        self.assertEqual(attempt.error.code, "timeout")
        self.assertIn(b"partial output before timeout", Path(attempt.output.path_hint).read_bytes())

    def test_cancel_confirms_a_term_resistant_descendant_has_stopped(self):
        child = textwrap.dedent("""
            import signal
            import time
            from pathlib import Path
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            Path('child-ready').touch()
            time.sleep(60)
        """)
        self.install_driver(f"""
            child = subprocess.Popen([sys.executable, '-c', {child!r}])
            Path('child-pid.tmp').write_text(str(child.pid))
            Path('child-pid.tmp').rename('child-pid')
            print('parent and child started', flush=True)
            child.wait()
        """)
        started = self.start(timeout_seconds=10)
        pid_file = started.directory / "child-pid"
        self.wait_for(pid_file.exists)
        pid = int(pid_file.read_text())
        self.addCleanup(self.stop_child, pid)
        self.wait_for((started.directory / "child-ready").exists)
        output = started.directory / ".orcaview" / "orca-output.log"
        self.wait_for(lambda: output.exists() and b"parent and child started" in output.read_bytes())
        self.assertTrue(self.active(pid))
        self.assertTrue(self.runner.cancel(started.attempt_id))
        attempt = self.finish(started)
        self.assertEqual(attempt.state, "cancelled", attempt.error)
        self.assertFalse(self.runner.cancel(attempt.attempt_id))
        self.wait_for(lambda: not self.active(pid))
        self.assertIn(b"parent and child started", Path(attempt.output.path_hint).read_bytes())
        events = self.runner.events(attempt.attempt_id)
        stages = [event.stage for event in events if event.kind == "state"]
        self.assertIn("cancelling", stages)
        self.assertEqual(stages[-1], "cancelled")
        evidence = json.loads((attempt.directory / ".orcaview" / "execution.json").read_text())
        self.assertEqual(evidence["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()

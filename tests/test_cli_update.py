"""Batch updates use verified release assets and never relaunch a desktop session."""

import contextlib
from io import BytesIO, StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from orcaview import cli_update
from orcaview.application import portable_replace
from orcaview.application.updates import UpdateError, UpdateRelease
from orcaview.cli import main
from test_update_download import VERSION, package, windows_zip


class UpdateCliTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.data = windows_zip()
        self.asset = package("Windows-x64.zip", self.data)
        self.release = UpdateRelease(VERSION, "https://example.invalid", self.asset)
        self.check = self.enter_patch(patch.object(cli_update, "check_for_update", return_value=self.release))

    def enter_patch(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def call(self, *args, code=0):
        stdout, stderr = StringIO(), StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(["update", *map(str, args)])
        self.assertEqual(status, code, stderr.getvalue())
        if code:
            self.assertEqual(stdout.getvalue(), "")
            return stderr.getvalue()
        return json.loads(stdout.getvalue())

    def test_check_and_offline_errors_have_machine_readable_outcomes(self):
        self.check.return_value = None
        self.assertEqual(self.call("check")["status"], "current")
        self.check.return_value = self.release
        self.assertEqual(self.call("check")["asset"]["sha256"], self.asset.sha256)
        self.check.return_value = UpdateRelease(VERSION, self.release.page_url, None)
        self.assertIn("no verifiable", self.call("install", self.root, code=2))
        self.check.side_effect = UpdateError("offline")
        self.assertIn("offline", self.call("check", code=2))

    def test_download_then_install_reuses_and_verifies_the_specified_archive(self):
        with patch("orcaview.application.update_download.open_update_url", return_value=BytesIO(self.data)):
            download = self.call("download", self.root)
        self.assertEqual(download["sha256"], self.asset.sha256)
        archive = Path(download["path"])
        with patch("orcaview.application.update_download.open_update_url") as fetch:
            result = self.call("install", self.root / "new", "--archive", archive)
            self.assertEqual(result["status"], "installed")
            self.assertEqual(Path(result["path"]).read_bytes(), b"exe")
            archive.write_bytes(self.data[::-1])
            self.assertIn("SHA-256", self.call("install", self.root / "broken", "--archive", archive, code=2))
            fetch.assert_not_called()

    def test_replace_current_returns_scheduled_instead_of_relaunching_or_claiming_success(self):
        prepared = Mock(target=self.root, backup=self.root / "old", staged=self.root / "stage" / "OrcaView")
        with patch.object(cli_update, "current_portable_installation", return_value=self.root), \
                patch.object(cli_update, "prepare_portable_update", return_value=prepared) as prepare, \
                patch.object(cli_update, "schedule_portable_update") as schedule:
            report = self.call("replace-current", "--archive", self.root / "archive")
            self.assertEqual(report["status"], "scheduled")
            self.assertEqual(Path(report["error_file"]), prepared.staged.parent / "update-error.txt")
            prepare.assert_called_once_with(self.asset, self.root / "archive", self.root)
            schedule.assert_called_once_with(prepared, relaunch=False)
            prepared.discard.assert_not_called()

    def test_headless_helper_failure_creates_an_error_file_without_a_desktop_notification(self):
        target = self.root / "existing"
        work = self.root / ".orcaview-install-test"
        work.mkdir()
        plan = work / "update.json"
        plan.write_text(json.dumps({"target": str(target), "backup": str(self.root / "existing.previous"),
                                     "windows": False, "package": "OrcaView-new", "expected": [], "relaunch": False}))
        with patch.object(portable_replace, "installation", return_value=True), \
                patch.object(portable_replace, "_wait_parent"), \
                patch.object(portable_replace, "activate", side_effect=OSError("failed")) as activate, \
                patch.object(portable_replace.subprocess, "run") as notify:
            self.assertEqual(portable_replace.run_helper(plan, 17), 1)
            self.assertIn("failed", (work / "update-error.txt").read_text())
            self.assertFalse(activate.call_args.kwargs["relaunch"])
            notify.assert_not_called()

import hashlib
from pathlib import Path
import plistlib
import sys
from tempfile import TemporaryDirectory, mkdtemp
import unittest
from unittest.mock import patch

from orcaview.application import macos_update as update
from orcaview.application.updates import RELEASES_URL, UpdateAsset


def make_bundle(parent, version):
    app = parent / "OrcaView.app"
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    executable = contents / "MacOS/OrcaView"
    executable.write_text("test launcher")
    executable.chmod(0o755)
    with (contents / "Info.plist").open("wb") as fp:
        plistlib.dump({"CFBundleIdentifier": "org.orcaview.desktop", "CFBundleExecutable": "OrcaView",
                       "CFBundleVersion": version}, fp)
    return app


@unittest.skipUnless(sys.platform == "darwin", "macOS atomic bundle swap")
class MacInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = make_bundle(self.root, "0.1.0a40")
        self.project = self.root / "工作项目.oview.json"
        self.project.write_text("user work")

    def staged(self):
        temp = Path(mkdtemp(dir=self.root))
        make_bundle(temp, "0.1.0a42")
        stat = self.app.stat()
        return update.PreparedMacUpdate(temp, self.app, (stat.st_dev, stat.st_ino))

    def test_atomic_exchange_keeps_location_and_external_project(self):
        staged = self.staged()
        with patch.object(update, "_system") as launch:
            staged.install_on_exit()
        self.assertEqual(update._bundle_version(self.app), "0.1.0a42")
        launch.assert_called_once_with("/usr/bin/open", "-n", str(self.app))
        self.assertEqual(self.project.read_text(), "user work")
        self.assertFalse(staged.workspace.exists())

    def test_relaunch_failure_rolls_back_and_intervening_update_is_rejected(self):
        failed, competing = self.staged(), self.staged()
        with patch.object(update, "_system", side_effect=update.UpdateDownloadError("failed")):
            with self.assertRaisesRegex(update.UpdateDownloadError, "failed"):
                failed.install_on_exit()
        self.assertEqual(update._bundle_version(self.app), "0.1.0a40")
        with patch.object(update, "_system"):
            failed.install_on_exit()
            with self.assertRaisesRegex(update.UpdateDownloadError, "installation has changed"):
                competing.install_on_exit()
        competing.discard()
        self.assertEqual(update._bundle_version(self.app), "0.1.0a42")
        self.assertEqual(self.project.read_text(), "user work")

    def test_bad_download_and_wrong_bundle_do_not_reach_installation(self):
        name = "OrcaView-0.1.0a42-macOS-arm64.dmg"
        path = self.root / name
        path.write_bytes(b"abcd")
        asset = UpdateAsset(name, f"{RELEASES_URL}/download/v0.1.0a42/{name}", 4,
                            hashlib.sha256(b"1234").hexdigest())
        with patch.object(update, "_system") as system:
            with self.assertRaisesRegex(update.UpdateDownloadError, "SHA-256"):
                update.prepare_macos_update(asset, path, self.app)
            system.assert_not_called()
            path.write_bytes(b"1234")
            with self.assertRaisesRegex(update.UpdateDownloadError, "app version in the disk image"):
                update.prepare_macos_update(asset, path, self.app)
        self.assertEqual(update._bundle_version(self.app), "0.1.0a40")
        self.assertEqual(self.project.read_text(), "user work")

    def test_unavailable_rollback_preserves_old_bundle_for_recovery(self):
        prepared = self.staged()
        swap = update._exchange
        count = 0

        def swap_once(first, second):
            nonlocal count
            count += 1
            if count == 2:
                raise PermissionError("volume is now read-only")
            swap(first, second)

        with patch.object(update, "_system", side_effect=OSError("launch failed")), \
             patch.object(update, "_exchange", side_effect=swap_once):
            with self.assertRaisesRegex(update.UpdateDownloadError, "previous version is at"):
                prepared.install_on_exit()
        prepared.discard()
        self.assertEqual(update._bundle_version(prepared.workspace / "OrcaView.app"), "0.1.0a40")
        self.assertEqual(self.project.read_text(), "user work")

"""Exercise the explicit update action, cancellation and installer handoffs."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog
    from orcaview.gui import update_dialog
    from orcaview.gui.main_window import MainWindow
    from orcaview.application.updates import RELEASES_URL, UpdateAsset, UpdateError, UpdateRelease
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


@unittest.skipUnless(QApplication, "Requires PySide6")
class UpdateWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.check = self.enter_patch(patch.object(update_dialog, "check_for_update", return_value=None))
        self.open_url = self.enter_patch(patch.object(update_dialog.QDesktopServices, "openUrl", return_value=True))
        self.window = MainWindow()
        self.window.show()
        self.addCleanup(self.close_window)

    def enter_patch(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def close_window(self):
        self.window.close()
        QThreadPool.globalInstance().waitForDone(3000)
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 4
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "Update worker did not reach the expected state")

    def open_check(self):
        self.window.update_action.trigger()
        dialog = self.window._update_dialog
        self.wait_for(lambda: dialog._task is None)
        return dialog

    @staticmethod
    def release(name=None):
        tag = "v9.0.0"
        asset = UpdateAsset(name, f"{RELEASES_URL}/download/{tag}/{name}", 1600, "a" * 64) if name else None
        return UpdateRelease("9.0.0", f"{RELEASES_URL}/tag/{tag}", asset)

    def test_only_explicit_checks_and_retry_after_failure(self):
        self.check.assert_not_called()
        self.check.side_effect = [UpdateError("offline"), None, self.release()]
        dialog = self.open_check()
        self.assertIn("offline", dialog.status.text())
        self.assertTrue(dialog.check_button.isVisible())
        self.window.update_action.trigger()
        self.assertEqual(self.check.call_count, 1)
        dialog.check_button.click()
        self.wait_for(lambda: dialog._task is None)
        self.assertIn("No newer version", dialog.status.text())
        dialog.close()
        self.assertIs(self.open_check(), dialog)
        self.assertIn("9.0.0", dialog.status.text())
        self.assertIn("no verifiable installer for this system", dialog.status.text())
        self.assertFalse(dialog.install_button.isVisible())
        dialog.page_button.click()
        self.assertEqual(self.open_url.call_args.args[0].toString(), self.release().page_url)

    def test_cancel_and_close_check_discard_a_late_result(self):
        entered, resume = Event(), Event()

        def slow_check(version, *, cancelled):
            entered.set()
            resume.wait(4)
            return self.release("example.dmg")

        self.addCleanup(resume.set)
        self.check.side_effect = slow_check
        self.window.update_action.trigger()
        dialog = self.window._update_dialog
        self.wait_for(entered.is_set)
        self.window.update_action.trigger()
        self.assertEqual(self.check.call_count, 1)
        dialog.cancel_button.click()
        self.assertFalse(dialog.cancel_button.isEnabled())
        dialog.reject()
        self.check.side_effect = None
        self.open_check()
        resume.set()
        self.assertTrue(QThreadPool.globalInstance().waitForDone(3000))
        self.app.processEvents()
        self.assertIn("No newer version", dialog.status.text())
        self.assertFalse(dialog.install_button.isVisible())
        self.open_url.assert_not_called()

    def test_downloads_verified_dmg_and_opens_it_from_gui(self):
        release = self.release("OrcaView-9.0.0-macOS-arm64.dmg")
        self.check.return_value = release
        dialog = self.open_check()
        with TemporaryDirectory() as folder:
            base = Path(folder)
            destination = base / release.asset.name
            gate = Event()
            gui_thread = get_ident()

            def download(asset, directory, *, progress, cancelled):
                self.assertNotEqual(get_ident(), gui_thread)
                self.assertEqual((asset, directory), (release.asset, base))
                progress(1200, 1600)
                gate.wait(4)
                return destination

            with patch.object(QFileDialog, "getExistingDirectory", side_effect=["", folder]), \
                 patch.object(update_dialog, "download_update", side_effect=download) as fetch, \
                 patch.object(update_dialog, "install_portable") as unpack:
                dialog.install_button.click()
                fetch.assert_not_called()
                self.assertTrue(dialog.install_button.isVisible())
                dialog.install_button.click()
                try:
                    self.wait_for(lambda: dialog.progress.value() == 75)
                finally:
                    gate.set()
                self.wait_for(lambda: dialog._task is None)
                unpack.assert_not_called()
            self.assertEqual(self.open_url.call_args.args[0].toLocalFile(), str(destination))
            self.assertIn(str(destination), dialog.status.text())

    def test_portable_installation_error_and_retry(self):
        release = self.release("OrcaView-9.0.0-Windows-x64.zip")
        self.check.return_value = release
        dialog = self.open_check()
        with TemporaryDirectory() as folder:
            archive = Path(folder, release.asset.name)
            launcher = Path(folder, archive.stem, "OrcaView.exe")
            with patch.object(QFileDialog, "getExistingDirectory", return_value=folder), \
                 patch.object(update_dialog, "download_update", return_value=archive), \
                 patch.object(update_dialog, "install_portable", side_effect=[OSError("disk full"), launcher]) as unpack:
                dialog.install_button.click()
                self.wait_for(lambda: dialog._task is None)
                self.assertIn("disk full", dialog.status.text())
                self.assertTrue(dialog.install_button.isVisible())
                self.open_url.assert_not_called()
                dialog.install_button.click()
                self.wait_for(lambda: dialog._task is None)
                self.assertEqual(unpack.call_args.args, (release.asset, archive, Path(folder)))
                self.assertEqual(self.open_url.call_args.args[0].toLocalFile(), str(launcher.parent))
                self.assertIn(launcher.name, dialog.status.text())

    def test_current_portable_update_uses_same_directory_and_waits_for_normal_exit(self):
        release = self.release("OrcaView-9.0.0-Windows-x64.zip")
        self.check.return_value = release
        target = Path("/tmp/current OrcaView")
        prepared = Mock()
        with patch.object(update_dialog, "current_portable_installation", return_value=target), \
             patch.object(QFileDialog, "getExistingDirectory") as choose, \
             patch.object(update_dialog, "download_update", side_effect=lambda asset, folder, **kw: folder / asset.name), \
             patch.object(update_dialog, "prepare_portable_update", return_value=prepared) as prepare, \
             patch.object(update_dialog, "schedule_portable_update") as schedule:
            dialog = self.open_check()
            self.assertIn(str(target), dialog.status.text())
            self.assertTrue(dialog.manual_button.isVisible())
            dialog.install_button.click()
            self.wait_for(lambda: dialog._task is None)
            choose.assert_not_called()
            self.assertEqual(prepare.call_args.args[2], target)
            schedule.assert_not_called()
            self.assertTrue(self.window.isVisible() and dialog.restart_button.isVisible())
            with patch.object(self.window, "_guard_discard", return_value=False) as guard:
                dialog.restart_button.click()
                guard.assert_called_once()
            self.assertTrue(self.window.isVisible())
            schedule.assert_not_called()
            dialog.restart_button.click()
            schedule.assert_called_once_with(prepared)
            self.assertFalse(self.window.isVisible())
            self.open_url.assert_not_called()

    def test_mac_install_waits_for_save_guard_and_survives_reopening_update_window(self):
        release = self.release("OrcaView-9.0.0-macOS-arm64.dmg")
        self.check.return_value = release
        target = Path("/tmp/Applications/OrcaView.app")
        prepared = Mock(spec=update_dialog.PreparedMacUpdate)
        with patch.object(update_dialog, "current_macos_installation", return_value=target), \
             patch.object(update_dialog, "download_update", return_value=Path("/tmp/verified.dmg")), \
             patch.object(update_dialog, "prepare_macos_update", return_value=prepared):
            dialog = self.open_check()
            dialog.install_button.click()
            self.wait_for(lambda: dialog._task is None)
            dialog.close()
            self.open_check()
            self.assertEqual(self.check.call_count, 1)
            with patch.object(self.window, "_guard_discard", return_value=False):
                dialog.restart_button.click()
            prepared.install_on_exit.assert_not_called()
            self.assertTrue(self.window.isVisible())
            dialog.restart_button.click()
            prepared.install_on_exit.assert_called_once()
            self.assertFalse(self.window.isVisible())

    def test_prepared_update_cancelled_before_delivery_discards_staging(self):
        release = self.release("OrcaView-9.0.0-Windows-x64.zip")
        self.check.return_value = release
        preparing, resume = Event(), Event()
        prepared = Mock()

        def prepare(*args, **kwargs):
            preparing.set()
            resume.wait(4)
            return prepared

        with patch.object(update_dialog, "current_portable_installation", return_value=Path("/tmp/OrcaView")), \
             patch.object(update_dialog, "download_update", return_value=Path("/tmp/package")), \
             patch.object(update_dialog, "prepare_portable_update", side_effect=prepare), \
             patch.object(update_dialog, "schedule_portable_update") as schedule:
            dialog = self.open_check()
            dialog.install_button.click()
            try:
                self.wait_for(preparing.is_set)
                dialog.cancel_button.click()
            finally:
                resume.set()
            self.wait_for(lambda: dialog._task is None)
            schedule.assert_not_called()
            prepared.discard.assert_called_once()
            self.assertTrue(dialog.install_button.isVisible())

    def test_close_window_during_download_does_not_open_installer(self):
        release = self.release("test.dmg")
        self.check.return_value = release
        dialog = self.open_check()
        entered, resume = Event(), Event()
        cancellation = []

        def slow_download(asset, directory, *, progress, cancelled):
            entered.set()
            resume.wait(4)
            cancellation.append(cancelled())
            return directory / asset.name

        with TemporaryDirectory() as folder, \
             patch.object(QFileDialog, "getExistingDirectory", return_value=folder), \
             patch.object(update_dialog, "download_update", side_effect=slow_download):
            dialog.install_button.click()
            try:
                self.wait_for(entered.is_set)
                self.window.close()
            finally:
                resume.set()
            self.assertTrue(QThreadPool.globalInstance().waitForDone(3000))
            self.app.processEvents()
            self.assertEqual(cancellation, [True])
            self.open_url.assert_not_called()

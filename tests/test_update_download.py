"""GitHub downloads, atomic publication and safe portable installation."""

from dataclasses import replace
import hashlib
from io import BytesIO
import os
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from orcaview.application.update_download import (
    UpdateCancelled, UpdateDownloadError, download_update, install_portable, verify_download,
)
from orcaview.application.updates import UpdateAsset


VERSION = "0.1.0a99"


def package(suffix, data):
    name = f"OrcaView-{VERSION}-{suffix}"
    url = f"https://github.com/lightzfpwings/OrcaView/releases/download/v{VERSION}/{name}"
    return UpdateAsset(name, url, len(data), hashlib.sha256(data).hexdigest())


def windows_zip(extra=None):
    root = f"OrcaView-{VERSION}-Windows-x64"
    data = BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(root + "/OrcaView.exe", b"exe")
        if extra:
            archive.writestr(root + "/" + extra, b"unrelated")
    return data.getvalue()


def linux_tar(link="python3.13"):
    root = f"OrcaView-{VERSION}-Linux-x86_64"
    data = BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        for filename in ["OrcaView", "python/bin/python3.13"]:
            entry = tarfile.TarInfo(root + "/" + filename)
            entry.mode = 0o755
            entry.size = len(b"contents")
            archive.addfile(entry, BytesIO(b"contents"))
        entry = tarfile.TarInfo(root + "/python/bin/python3")
        entry.type, entry.linkname = tarfile.SYMTYPE, link
        archive.addfile(entry)
    return data.getvalue()


class UpdateDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def test_download_reports_progress_and_reuses_verified_file(self):
        data = b"OrcaView" * 90000
        asset = package("macOS-arm64.dmg", data)
        samples = []
        cached = []
        with patch("orcaview.application.update_download.open_update_url", return_value=BytesIO(data)) as transport:
            path = download_update(asset, self.work, progress=lambda n, total: samples.append((n, total)))
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(download_update(asset, self.work, progress=lambda n, total: cached.append(n)), path)
            self.assertEqual(transport.call_count, 1)
        self.assertEqual(samples[0], (0, len(data)))
        self.assertEqual(samples[-1], (len(data), len(data)))
        self.assertEqual((cached[0], cached[-1]), (0, len(data)))
        self.assertEqual(samples, sorted(samples))
        verify_download(asset, path)

    def test_integrity_errors_cancellation_and_remote_error_clean_up(self):
        data = b"OrcaView" * 90000
        asset = package("macOS-arm64.dmg", data)
        for broken in (data[:-1], data + b"x", data[::-1]):
            with self.subTest(size=len(broken)), patch(
                "orcaview.application.update_download.open_update_url", return_value=BytesIO(broken)
            ):
                with self.assertRaises(UpdateDownloadError):
                    download_update(asset, self.work)
                self.assertEqual(list(self.work.iterdir()), [])
        with patch("orcaview.application.update_download.open_update_url", return_value=BytesIO(data)):
            samples = []
            with self.assertRaises(UpdateCancelled):
                download_update(asset, self.work, progress=lambda n, total: samples.append(n),
                                cancelled=lambda: bool(samples and samples[-1] > 0))
        with patch("orcaview.application.update_download.open_update_url", side_effect=TimeoutError):
            with self.assertRaises(UpdateDownloadError):
                download_update(asset, self.work)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_refuses_invalid_asset_and_preserves_existing_different_file(self):
        asset = package("macOS-arm64.dmg", b"real")
        target = self.work / asset.name
        target.write_bytes(b"mine")
        with patch("orcaview.application.update_download.open_update_url") as transport:
            for invalid in (replace(asset, name="../bad"), replace(asset, url="http://example.org/?"),
                            replace(asset, sha256=""), asset):
                with self.assertRaises(UpdateDownloadError):
                    download_update(invalid, self.work)
            transport.assert_not_called()
        self.assertEqual(target.read_bytes(), b"mine")

    def install(self, suffix, data, **kwargs):
        asset = package(suffix, data)
        archive = self.work / asset.name
        archive.write_bytes(data)
        directory = self.work / "installs"
        return install_portable(asset, archive, directory, **kwargs)

    def test_zip_installs_beside_previous_version_and_preserves_existing_destinations(self):
        data = windows_zip()
        launcher = self.install("Windows-x64.zip", data)
        self.assertEqual(launcher.name, "OrcaView.exe")
        self.assertEqual(launcher.read_bytes(), b"exe")
        launcher.write_bytes(b"my file")
        with self.assertRaises(UpdateDownloadError):
            self.install("Windows-x64.zip", data)
        self.assertEqual(launcher.read_bytes(), b"my file")

    def test_windows_paths_cannot_escape_or_alias_the_installation(self):
        for name in ("../outside", "/relative", "C:/bad", "path\\bad", "NUL.txt", "OrcaView.exe:bad"):
            with self.subTest(name=name), self.assertRaises(UpdateDownloadError):
                self.install("Windows-x64.zip", windows_zip(name))
            self.assertEqual(list((self.work / "installs").iterdir()), [])

    @unittest.skipIf(os.name == "nt", "Linux bundle requires POSIX symlinks")
    def test_tar_preserves_python_alias_and_executable(self):
        launcher = self.install("Linux-x86_64.tar.gz", linux_tar())
        python = launcher.parent / "python" / "bin" / "python3"
        self.assertTrue(python.is_symlink())
        self.assertEqual(python.read_bytes(), b"contents")
        self.assertTrue(os.access(launcher, os.X_OK))

    def test_tar_rejects_escaping_symlink(self):
        with self.assertRaises(UpdateDownloadError):
            self.install("Linux-x86_64.tar.gz", linux_tar("../../../../outside"))
        self.assertEqual(list((self.work / "installs").iterdir()), [])

    def test_install_rechecks_digest_and_cancellation_discards_staging(self):
        data = windows_zip()
        asset = package("Windows-x64.zip", data)
        archive = self.work / asset.name
        archive.write_bytes(data[::-1])
        directory = self.work / "installs"
        with self.assertRaisesRegex(UpdateDownloadError, "SHA-256"):
            install_portable(asset, archive, directory)
        archive.write_bytes(data)
        with self.assertRaises(UpdateCancelled):
            install_portable(asset, archive, directory,
                             cancelled=lambda: any(candidate.is_file() for candidate in directory.rglob("OrcaView.exe")))
        self.assertEqual(list(directory.iterdir()), [])


class PortableReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.target = self.work / "自定义 软件"
        self.target.mkdir()
        self.init = Path("python/Lib/site-packages/orcaview/__init__.pyc")
        self.backup = self.target.with_name(self.target.name + ".previous")

    def bundle(self, version):
        import json
        content = {"OrcaView.exe": version.encode(), self.init.as_posix(): version.encode(),
                   "python/managed.dll": version.encode(), "示例/water.xyz": version.encode(),
                   "示例/imports/ethanol.mol": version.encode()}
        hashes = {p: hashlib.sha256(v).hexdigest() for p, v in content.items()}
        content["python/orcaview-files.json"] = json.dumps(hashes).encode()
        name = f"OrcaView-{version}-Windows-x64"
        data = BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            for path, payload in content.items():
                archive.writestr(name + "/" + path, payload)
        binary = data.getvalue()
        dest = self.work / (name + ".zip")
        dest.write_bytes(binary)
        url = f"https://github.com/lightzfpwings/OrcaView/releases/download/v{version}/{dest.name}"
        return UpdateAsset(dest.name, url, len(binary), hashlib.sha256(binary).hexdigest()), dest

    def seed(self, legacy=False):
        asset, path = self.bundle("0.1.0a40")
        (self.target).rmdir()
        install_portable(asset, path, self.work).parent.rename(self.target)
        if legacy:
            (self.target / "python/orcaview-files.json").unlink()
            (self.target / "ThirdParty").mkdir()
            (self.target / "ThirdParty/SOURCES.txt").write_text("legacy")
            (self.target / "OrcaView-cli.exe").write_text("legacy")
            (self.target / "LICENSE.txt").write_text("legacy")

    def test_legacy_upgrade_reuses_named_directory_and_retains_private_projects(self):
        self.seed(legacy=True)
        (self.target / "my project.ov").write_text("project")
        (self.target / "示例/water.xyz").write_text("user-edited example")
        asset, path = self.bundle("0.1.0a42")
        self.assertEqual(install_portable(asset, path, self.target), self.target / "OrcaView.exe")
        self.assertEqual((self.target / self.init).read_text(), "0.1.0a42")
        self.assertEqual((self.target / "my project.ov").read_text(), "project")
        self.assertEqual((self.backup / self.init).read_text(), "0.1.0a40")
        self.assertFalse((self.target / "ThirdParty").exists())
        self.assertTrue((self.backup / "ThirdParty/SOURCES.txt").is_file())
        self.assertEqual((self.target / "示例/water.xyz").read_text(), "user-edited example")
        self.assertEqual((self.target / "示例/imports/ethanol.mol").read_text(), "0.1.0a40")

    def test_rotates_one_backup_preserving_only_local_edits(self):
        self.seed()
        (self.target / "示例/water.xyz").write_text("custom")
        (self.target / "示例/my input.inp").write_text("input")
        (self.target / "python/extra-data").write_text("user addition")
        for version in ("0.1.0a42", "0.1.0a43", "0.1.0a44"):
            asset, path = self.bundle(version)
            install_portable(asset, path, self.target)
            self.assertEqual((self.target / "示例/water.xyz").read_text(), "custom")
            self.assertEqual((self.target / "示例/imports/ethanol.mol").read_text(), version)
            self.assertEqual((self.target / "python/extra-data").read_text(), "user addition")
            self.assertEqual((self.target / "示例/my input.inp").read_text(), "input")
        self.assertEqual((self.backup / self.init).read_text(), "0.1.0a43")
        for preserved in self.work.glob("*.previous-preserved-*"):
            self.assertFalse((preserved / self.init).exists())
            self.assertEqual((preserved / "示例/water.xyz").read_text(), "custom")

    def test_relaunch_failure_rolls_back_and_pending_cancellation_leaves_installation_untouched(self):
        from orcaview.application import portable_replace
        from orcaview.application.update_download import prepare_portable_update
        self.seed()
        asset, path = self.bundle("0.1.0a42")
        pending = prepare_portable_update(asset, path, self.target)
        pending.discard()
        self.assertFalse(pending.staged.parent.exists())
        self.assertFalse(self.backup.exists())
        pending = prepare_portable_update(asset, path, self.target)
        with patch.object(portable_replace.subprocess, "Popen", side_effect=OSError("nt loader")):
            with self.assertRaisesRegex(OSError, "nt loader"):
                portable_replace.activate(pending.staged, self.target, pending.backup, True,
                                          pending.expected, relaunch=True)
        self.assertEqual((self.target / self.init).read_text(), "0.1.0a40")
        self.assertFalse(self.backup.exists())
        pending.discard()
        self.assertFalse(pending.staged.parent.exists())

    def test_stale_preparations_and_unrelated_backups_are_left_alone(self):
        from orcaview.application import portable_replace
        from orcaview.application.update_download import prepare_portable_update
        self.seed()
        asset, path = self.bundle("0.1.0a42")
        pending = prepare_portable_update(asset, path, self.target)
        install_portable(asset, path, self.target)
        with self.assertRaisesRegex(ValueError, "安装目录已变更"):
            portable_replace.activate(pending.staged, self.target, pending.backup, True, pending.expected)
        pending.discard()
        (self.backup / ".orcaview-previous.json").unlink()
        with self.assertRaisesRegex(UpdateDownloadError, "备份路径"):
            install_portable(asset, path, self.target)
        self.assertEqual((self.backup / self.init).read_text(), "0.1.0a40")
        self.assertEqual((self.target / self.init).read_text(), "0.1.0a42")

    @unittest.skipIf(os.name == "nt", "symlink creation needs Windows developer privileges")
    def test_old_backup_runtime_symlink_cannot_change_an_external_directory(self):
        from orcaview.application import portable_replace
        self.seed()
        external = self.work / "external"
        external.mkdir()
        marker = external / "orcaview-files.json"
        marker.write_text("{}")
        previous = self.work / "previous"
        previous.mkdir()
        (previous / "python").symlink_to(external, target_is_directory=True)
        (previous / ".orcaview-previous.json").write_text("marker")
        portable_replace._retire_backup(previous, self.target)
        self.assertTrue(marker.is_file())
        retained, = self.work.glob("*.previous-preserved-*")
        self.assertTrue((retained / "python").is_symlink())

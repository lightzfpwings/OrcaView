import unittest
from types import SimpleNamespace
from unittest.mock import patch

from orcaview import ORCA_INPUT_TARGET, __version__
from orcaview.gui import version_info


class DesktopVersionInfoTests(unittest.TestCase):
    def test_macos_product_version_and_target(self):
        with patch.object(version_info.sys, "platform", "darwin"), \
                patch.object(version_info.platform, "mac_ver", return_value=("15.4.1", (), "arm64")):
            info = version_info.desktop_version_info()
        self.assertEqual(info.platform_name, "macOS")
        self.assertEqual(info.system_version, "macOS 15.4.1")
        self.assertEqual(info.software_version, f"{__version__}/orca{ORCA_INPUT_TARGET}")

    def test_windows_client_and_server_builds(self):
        for product, build, label in ((1, 19045, "Windows 10"), (1, 22631, "Windows 11"),
                                      (2, 26100, "Windows Server"), (3, 26100, "Windows Server")):
            version = SimpleNamespace(product_type=product, platform_version=(10, 0, build))
            with self.subTest(product=product, build=build), \
                    patch.object(version_info.sys, "platform", "win32"), \
                    patch.object(version_info.sys, "getwindowsversion", return_value=version, create=True):
                info = version_info.desktop_version_info()
                self.assertEqual(info.system_version, f"{label} (10.0.{build})")
                self.assertEqual(info.platform_name, "Windows")

    def test_linux_distro_and_kernel_fallback(self):
        cases = ((['PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"'], "Debian GNU/Linux 12 (bookworm)"),
                 ([OSError(), 'NAME="Linux Mint"\nVERSION_ID="22"'], "Linux Mint 22"),
                 ([OSError(), OSError()], "Linux 6.8.0"))
        for reads, expected in cases:
            with self.subTest(expected=expected), patch.object(version_info.sys, "platform", "linux"), \
                    patch.object(version_info.Path, "read_text", side_effect=reads), \
                    patch.object(version_info.platform, "release", return_value="6.8.0"):
                info = version_info.desktop_version_info()
                self.assertEqual(info.system_version, expected)
                self.assertEqual(info.platform_name, "Linux")

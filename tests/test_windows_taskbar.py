"""Read the portable GUI's relaunch identity from the real Windows shell."""
import ctypes
import os
import sys
import unittest
from unittest.mock import patch

from orcaview.gui import windows_taskbar as taskbar


def window_properties(hwnd):
    store = ctypes.c_void_p()
    get_store = ctypes.windll.shell32.SHGetPropertyStoreForWindow
    get_store.argtypes = [ctypes.c_void_p, ctypes.POINTER(taskbar._GUID), ctypes.POINTER(ctypes.c_void_p)]
    get_store.restype = ctypes.HRESULT
    get_store(hwnd, ctypes.byref(taskbar._PROPERTY_STORE), ctypes.byref(store))
    read = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.POINTER(taskbar._PropertyKey),
                              ctypes.POINTER(taskbar._PropVariant))(5, "GetValue")
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong)(2, "Release")
    values = []
    try:
        for pid in (2, 3, 4, 5):
            key = taskbar._PropertyKey(taskbar._APP_MODEL, pid)
            value = taskbar._PropVariant()
            read(store, ctypes.byref(key), ctypes.byref(value))
            try:
                values.append((value.vt, value.text if value.vt == 31 else None))
            finally:
                ctypes.windll.ole32.PropVariantClear(ctypes.byref(value))
    finally:
        release(store)
    return values


@unittest.skipUnless(sys.platform == "win32", "Requires the Windows shell")
class WindowsTaskbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        if cls.app.platformName() != "windows":
            raise unittest.SkipTest("Requires Qt's native Windows backend")

    def test_portable_window_pins_the_launcher_and_clears_properties_before_close(self):
        from PySide6.QtWidgets import QApplication
        from orcaview.gui.main_window import launch

        launcher = r"C:\Apps with spaces\分子\OrcaView.exe"
        windows = []

        def inspect():
            window, = windows
            hwnd = int(window.winId())
            self.assertTrue(window.isVisible())
            self.assertFalse(window.windowIcon().isNull())
            send = ctypes.windll.user32.SendMessageW
            send.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
            send.restype = ctypes.c_ssize_t
            for icon_size in (0, 1):  # WM_GETICON, ICON_SMALL and ICON_BIG
                self.assertTrue(send(hwnd, 0x007F, icon_size, 0))
            try:
                actual = window_properties(hwnd)
            except OSError as exc:
                if (exc.winerror == -2147467263 and  # E_NOTIMPL
                        hasattr(ctypes.windll.ntdll, "wine_get_version")):
                    window.close()
                    self.skipTest("Wine does not implement reading the window property store")
                raise
            self.assertEqual(actual, [
                (31, f'"{launcher}"'), (31, f"{launcher},-1"),
                (31, f"@{launcher},-1"), (31, "OrcaView.Desktop"),
            ])
            cleared = []
            window.closing.connect(lambda: cleared.extend(window_properties(hwnd)))
            self.assertTrue(window.close())
            self.assertEqual(cleared, [(0, None)] * 4)
            return 0

        with patch.dict(os.environ, ORCAVIEW_PORTABLE_EXE=launcher), patch.object(QApplication, "exec", staticmethod(inspect)):
            self.assertEqual(launch(configure=windows.append), 0)

    def test_unavailable_property_store_allows_the_window_to_open(self):
        from orcaview.gui.main_window import MainWindow
        window = MainWindow()
        # A real SHGetPropertyStoreForWindow request for an unsupported interface.
        with patch.object(taskbar, "_PROPERTY_STORE", taskbar._GUID()), self.assertLogs(taskbar.__name__, "WARNING"):
            with taskbar.portable_taskbar(window, r"C:\OrcaView.exe"):
                window.show()
                self.assertTrue(window.isVisible())
                self.assertTrue(window.close())

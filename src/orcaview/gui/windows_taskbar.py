"""Bind the portable Qt window and its pinned shortcut to the permanent launcher."""

from contextlib import ExitStack, contextmanager
import ctypes
import logging
from uuid import UUID


_APP_ID = "OrcaView.Desktop"
_GUID = ctypes.c_ubyte * 16
_APP_MODEL = _GUID.from_buffer_copy(UUID("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3").bytes_le)
_PROPERTY_STORE = _GUID.from_buffer_copy(UUID("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99").bytes_le)


class _PropertyKey(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_uint32)]


class _PropVariant(ctypes.Structure):
    # VT_LPWSTR and VT_EMPTY use the same native union (two pointers wide).
    _fields_ = [("vt", ctypes.c_uint16), ("reserved", ctypes.c_uint16 * 3),
                ("text", ctypes.c_wchar_p), ("padding", ctypes.c_void_p)]


def _attach(window, launcher, cleanup):
    shell = ctypes.windll.shell32
    shell.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(_APP_ID))
    store = ctypes.c_void_p()
    get_store = shell.SHGetPropertyStoreForWindow
    get_store.argtypes = [ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    get_store.restype = ctypes.HRESULT
    get_store(int(window.winId()), ctypes.byref(_PROPERTY_STORE), ctypes.byref(store))
    if not store:
        raise OSError("The shell returned no window property store.")

    # IPropertyStore extends IUnknown. These are the standard SetValue and
    # Release slots, with ctypes supplying the COM 'this' argument.
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong)(2, "Release")
    cleanup.callback(release, store)
    set_value = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(_PropertyKey),
                                   ctypes.POINTER(_PropVariant))(6, "SetValue")
    empty = _PropVariant()  # VT_EMPTY releases the window's copy of a property.
    # Explorer reads the relaunch information when it receives the ID. Both
    # the application's display-name string and its launcher icon have ID 1.
    for pid, text in ((2, f'"{launcher}"'), (3, f"{launcher},-1"),
                      (4, f"@{launcher},-1"), (5, _APP_ID)):
        key = _PropertyKey(_APP_MODEL, pid)
        value = _PropVariant(vt=31, text=text)  # VT_LPWSTR
        result = set_value(store, ctypes.byref(key), ctypes.byref(value))
        if result < 0:
            raise ctypes.WinError(result)
        cleanup.callback(set_value, store, ctypes.byref(key), ctypes.byref(empty))


@contextmanager
def portable_taskbar(window, launcher):
    with ExitStack() as cleanup:
        try:
            _attach(window, launcher, cleanup)
        except (AttributeError, OSError, ValueError) as exc:
            cleanup.close()
            logging.getLogger(__name__).warning("Could not configure the Windows taskbar: %s", exc)
        window.closing.connect(cleanup.close)
        try:
            yield
        finally:
            window.closing.disconnect(cleanup.close)

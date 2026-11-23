"""Windows wheel resource layout, byte-offset tables and worker isolation."""

import ctypes
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orcaview.io.babel_worker import _windows_resources, prepare_windows_babel_data


class WindowsBabelResourceTests(unittest.TestCase):
    def test_packed_fragments_match_index_offsets_and_preserve_the_wheel(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bin" / "data"
            source.mkdir(parents=True)
            table = b"fragment\r\n6 1 0 0\r\nnext\r\n8 2 0 0\r\n"
            (source / "rigid-fragments.txt").write_bytes(table)
            index = b"fragment 9\r\nnext 22\r\n"
            (source / "rigid-fragments-index.txt").write_bytes(index)
            packed = root / "share" / "openbabel" / "3.2.0"
            prepare_windows_babel_data(source, packed)
            with (packed / "rigid-fragments.txt").open("rb") as stream:
                for line, expected in zip(index.splitlines(), (b"6 1 0 0\n", b"8 2 0 0\n")):
                    stream.seek(int(line.split()[1]))
                    self.assertEqual(stream.readline(), expected)
            self.assertEqual((packed / "rigid-fragments-index.txt").read_bytes(), index)
            self.assertEqual((source / "rigid-fragments.txt").read_bytes(), table)

    def test_worker_loads_unicode_plugins_and_restores_cwd_after_a_failed_operation(self):
        with TemporaryDirectory() as directory:
            package = Path(directory) / "化学 工具" / "openbabel"
            plugins = package / "bin"
            data = plugins / "data"
            data.mkdir(parents=True)
            forcefield = plugins / "plugin_forcefields.obf"
            forcefield.touch()
            (data / "rigid-fragments.txt").write_bytes(b"fragment\r\n6 1 0 0\r\n")
            ob = SimpleNamespace(__file__=str(package / "openbabel.py"), OBReleaseVersion=lambda: "3.2.0")
            before = Path.cwd()
            with patch.object(sys, "platform", "win32"), \
                 patch.dict(sys.modules, {"openbabel": SimpleNamespace(openbabel=ob)}), \
                 patch.object(ctypes, "WinDLL", create=True) as load, \
                 self.assertRaisesRegex(ValueError, "test failure"):
                with _windows_resources() as handles:
                    working = Path.cwd()
                    self.assertNotEqual(working, data)
                    self.assertEqual((working / "rigid-fragments.txt").read_bytes(), b"fragment\n6 1 0 0\n")
                    load.assert_called_once_with(str(forcefield.resolve()))
                    self.assertEqual(handles, [load.return_value])
                    raise ValueError("test failure")
            self.assertEqual(Path.cwd(), before)
            self.assertFalse(working.exists())
            self.assertIn(b"\r\n", (data / "rigid-fragments.txt").read_bytes())

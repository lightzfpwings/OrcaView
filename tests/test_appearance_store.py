"""Portable element palette files and persistence across desktop sessions."""

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import orcaview.appearance as appearance
from orcaview.appearance import AppearanceSettings, AppearanceStore, read_palette
from orcaview.core.elements import ATOMIC_NUMBERS, ELEMENT_COLORS


class ColorPackTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "scheme.json"
        self.data = {"id": "paper", "name": " My colors ", "colors": {"cl": "#AABBcc", "Og": "#120034"}}

    def write(self, **changes):
        self.source.write_text(json.dumps({**self.data, **changes}), encoding="utf-8-sig")
        return self.source

    def test_all_element_symbols_and_sample(self):
        spec = Path(appearance.__file__).resolve().parents[2] / "color-packs/contrast.json"
        self.assertIn("O", read_palette(spec).colors)
        loaded = read_palette(self.write())
        self.assertEqual((loaded.id, loaded.name), ("paper", "My colors"))
        self.assertEqual(loaded.colors, {"Cl": "#AABBCC", "Og": "#120034"})
        all_colors = {symbol: f"#{number:06X}" for symbol, number in ATOMIC_NUMBERS.items()}
        self.assertEqual(read_palette(self.write(colors=all_colors)).colors, all_colors)

    def test_invalid_packs(self):
        for changes in ({"id": "../foreign"}, {"id": "default"}, {"id": "a/b"}, {"id": 1},
                        {"name": ""}, {"name": "two\nlines"}, {"colors": {}}, {"colors": []},
                        {"colors": {"D": "#000000"}}, {"colors": {"H": "pink"}},
                        {"colors": {"O": "#fff"}}, {"colors": {"C": "#010101", "c": "#020202"}},
                        {"unexpected": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                read_palette(self.write(**changes))
        duplicate = b'{"id":"one","id":"two","name":"Two","colors":{"O":"#ABCDEF"}}'
        for raw in (duplicate, b'\xff', b" " * (64 * 1024 + 1)):
            self.source.write_bytes(raw)
            with self.assertRaises(ValueError):
                read_palette(self.source)

    def test_invalid_settings(self):
        for changes in ({"model": []}, {"model": "new"}, {"palette_id": "../paper"},
                        {"atom_scale": 0}, {"bond_scale": float("nan")}, {"bond_distance_factor": True},
                        {"bond_distance_factor": 2.01}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                AppearanceSettings(**changes)

    def test_install_reimport_persist_and_recover_from_removed_or_damaged_pack(self):
        try:
            from PySide6.QtCore import QSettings
        except ImportError:
            self.skipTest("Requires PySide6")

        def store():
            return AppearanceStore(directory=self.root / "packs",
                                   settings=QSettings(str(self.root / "user.ini"), QSettings.Format.IniFormat))

        current = store()
        self.assertEqual(current.load(), AppearanceSettings())
        self.assertEqual(current.palettes(), {"default": "OrcaView default"})
        current.import_palette(self.write())
        self.source.unlink()
        self.assertEqual(current.palettes()["paper"], "My colors")
        self.assertEqual(current.overrides("paper"), {"Cl": "#AABBCC", "Og": "#120034"})
        self.assertEqual(current.colors("paper")["O"], ELEMENT_COLORS["O"])
        self.assertEqual(current.colors("default"), ELEMENT_COLORS)
        prefs = AppearanceSettings("wireframe", 1.25, 0.5, 1.52, "paper")
        current.save(prefs)
        self.assertEqual(store().load(), prefs)
        current.import_palette(self.write(name="Updated", colors={"H": "#123456"}))
        self.assertEqual(store().overrides("paper"), {"H": "#123456"})
        with self.assertRaises(ValueError):
            current.import_palette(self.write(colors={"Fe": "invalid"}))
        copy = next(current.directory.iterdir())
        self.assertEqual(current.palettes()["paper"], "Updated")
        copy.write_text("{", encoding="utf-8")
        self.assertEqual(current.palettes(), {"default": "OrcaView default"})
        self.assertEqual(store().load(), replace(prefs, palette_id="default"))
        copy.unlink()
        with self.assertRaises(ValueError):
            current.save(prefs)
        self.assertEqual(current.overrides("paper"), {})

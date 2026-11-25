"""A display preference spans the workspaces and the exported sketch."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication, QComboBox
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication, "Requires PySide6")
class AppearanceWorkspacesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_menu_applies_across_pages_exports_and_relaunch(self):
        from orcaview.appearance import AppearanceSettings, AppearanceStore
        from orcaview.gui.appearance_dialog import AppearanceDialog
        from orcaview.gui.main_window import MainWindow
        from orcaview.gui.structure_export import save_structure_image

        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            ini = str(directory / "prefs.ini")

            def open_window():
                store = AppearanceStore(settings=QSettings(ini, QSettings.Format.IniFormat),
                                        directory=directory / "packs")
                window = MainWindow(appearance_store=store)
                self.addCleanup(window.close)
                return window

            window = open_window()
            self.assertEqual(window.appearance, AppearanceSettings())
            pack = directory / "example.json"
            pack.write_text(json.dumps({"name": "My colors", "id": "custom",
                                        "colors": {"C": "#BB17EE"}}), encoding="utf-8")
            window.appearance_store.import_palette(pack)
            window.design_panel._select([0, 1])
            camera = window.viewport.camera_transform(1, 2, 3)
            head = window.session.document.head
            preview = window.input_preview.toPlainText()
            viewports = (window.viewport, window.design_panel.viewport, window.foundation_panel.viewport)
            original_bonds = [view.bonds for view in viewports]
            canvas = window.design_panel.canvas
            canvas.resize(450, 320)
            sketch = directory / "sketch.png"

            def exported_sketch():
                save_structure_image(canvas, sketch, "png", canvas.width(), canvas.height(), True)
                return QImage(str(sketch))

            default_sketch = exported_sketch()

            def choose(dialog):
                choices = dialog.findChildren(QComboBox)
                for value in ("wireframe", "custom"):
                    combo = next(box for box in choices if box.findData(value) >= 0)
                    combo.setCurrentIndex(combo.findData(value))
                dialog.accept()
                return dialog.result()

            with patch.object(AppearanceDialog, "exec", choose):
                window.appearance_action.trigger()

            self.assertEqual(window.appearance.model, "wireframe")
            self.assertEqual(window.appearance.palette_id, "custom")
            for view, bonds in zip(viewports, original_bonds):
                self.assertEqual(view.appearance, window.appearance)
                self.assertEqual(view.bonds, bonds)
            self.assertEqual(window.viewport.camera_transform(1, 2, 3), camera)
            self.assertEqual(window.design_panel.viewport.selected, [0, 1])
            self.assertEqual(window.session.document.head, head)
            self.assertEqual(window.input_preview.toPlainText(), preview)
            self.assertFalse(window.dirty)
            colored = exported_sketch()
            self.assertNotEqual(colored, default_sketch)
            carbon = canvas.atom_position(0).toPoint()
            self.assertTrue(any(colored.pixelColor(x, y) == QColor("#BB17EE")
                                for x in range(carbon.x() - 12, carbon.x() + 13)
                                for y in range(carbon.y() - 12, carbon.y() + 13)))
            window.close()
            reopened = open_window()
            self.assertEqual(reopened.appearance, window.appearance)
            self.assertEqual(reopened.design_panel.viewport.appearance, window.appearance)

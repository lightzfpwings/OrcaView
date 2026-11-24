"""File-menu routing and format-specific controls for structure image export."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QFileDialog
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication, "Requires PySide6")
class StructureImageDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from orcaview.gui.main_window import MainWindow
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.window.close)

    def sketch_dialog(self, width, height):
        from orcaview.gui.design_canvas import DesignCanvas
        from orcaview.gui.structure_image_dialog import StructureImageDialog
        canvas = DesignCanvas()
        self.addCleanup(canvas.close)
        canvas.resize(width, height)
        canvas.set_molecule(self.window.session.molecule, fit=True)
        dialog = StructureImageDialog([("Sketch", canvas)], "molecule", self.window)
        self.addCleanup(dialog.close)
        return dialog

    def test_design_export_starts_as_png_and_preserves_alpha_preference_across_formats(self):
        from orcaview.gui.structure_image_dialog import StructureImageDialog
        w = self.window
        w.workspace_tabs.setCurrentWidget(w.design_panel)
        self.app.processEvents()
        head = w.session.document.head.ref
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "view.png")

            def interact(dialog):
                self.assertEqual(dialog.source.count(), 2)
                self.assertEqual(dialog.format_choice.currentData(), "png")
                self.assertFalse(dialog.advanced.isChecked())
                self.assertEqual(dialog.scale_box.currentData(), 2)
                self.assertEqual(dialog.preview.canvas, (w.design_panel.canvas.size() * 2).toTuple())
                dialog.advanced.click()
                dialog.width_box.setValue(701)
                dialog.height_box.setValue(581)
                dialog.source.setCurrentIndex(1)
                self.assertEqual(dialog.preview.canvas, (701, 581))
                source_size = w.design_panel.viewport.size()
                dialog.scale_box.setCurrentIndex(dialog.scale_box.findData(3))
                self.assertEqual(dialog.preview.canvas, (701 + source_size.width(), 581 + source_size.height()))
                dialog.scale_box.setCurrentIndex(dialog.scale_box.findData(2))
                self.assertEqual(dialog.preview.canvas, (701, 581))
                dialog.transparent.click()
                for fmt in ("bmp", "jpg"):
                    dialog.format_choice.setCurrentIndex(dialog.format_choice.findData(fmt))
                    self.assertFalse(dialog.transparent.isEnabled())
                    self.assertFalse(dialog.preview.transparent)
                    dialog.format_choice.setCurrentIndex(dialog.format_choice.findData("pdf"))
                    self.assertTrue(dialog.transparent.isEnabled())
                    self.assertTrue(dialog.preview.transparent)
                dialog.format_choice.setCurrentIndex(dialog.format_choice.findData("png"))
                self.assertTrue(dialog.preview.transparent)
                with patch.object(QFileDialog, "exec", return_value=1), patch.object(
                        QFileDialog, "selectedFiles", return_value=[str(path)]):
                    dialog.save_button.click()
                self.assertEqual(dialog.output_path, path)
                return dialog.result()

            with patch.object(StructureImageDialog, "exec", interact):
                w.structure_image_action.trigger()
            image = QImage(str(path))
            self.assertEqual(image.size().toTuple(), (701, 581))
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(w.session.document.head.ref, head)

    def test_scale_and_canvas_are_independent_in_preview_and_export(self):
        from orcaview.gui import structure_image_dialog as module
        dialog = self.sketch_dialog(400, 400)
        dialog.show()
        self.app.processEvents()
        self.assertTrue(dialog.scale_box.isVisible())
        self.assertEqual([dialog.scale_box.itemData(i) for i in range(dialog.scale_box.count())], list(range(1, 9)))
        self.assertEqual(dialog.preview.canvas, (800, 800))
        dialog.scale_box.setCurrentIndex(dialog.scale_box.findData(4))
        self.assertEqual(dialog.dimensions.text(), "1600 × 1600 px")
        dialog.advanced.click()
        self.assertEqual((dialog.width_box.value(), dialog.height_box.value()), (1600, 1600))
        dialog.width_box.setValue(1800)
        with patch.object(module, "paint_structure_canvas", wraps=module.paint_structure_canvas) as draw:
            dialog.preview.grab()
            self.assertEqual(draw.call_args.args[2:], (1800, 1600))
            self.assertEqual(draw.call_args.kwargs, {"scale": 4})
        dialog.scale_box.setCurrentIndex(dialog.scale_box.findData(3))
        self.assertEqual(dialog.preview.canvas, (1400, 1200))
        dialog.advanced.click()
        self.assertEqual(dialog.preview.canvas, (1200, 1200))
        dialog.scale_box.setCurrentIndex(dialog.scale_box.findData(4))
        self.assertEqual(dialog.preview.canvas, (1600, 1600))
        dialog.advanced.click()
        self.assertEqual(dialog.preview.canvas, (1800, 1600))
        dialog.format_choice.setCurrentIndex(dialog.format_choice.findData("bmp"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "structure.bmp")
            with patch.object(QFileDialog, "exec", return_value=1), patch.object(
                    QFileDialog, "selectedFiles", return_value=[str(path)]), patch.object(
                    module, "save_structure_image", wraps=module.save_structure_image) as save:
                dialog.save_button.click()
                save.assert_called_once_with(dialog.snapshot, path, "bmp", 1800, 1600, transparent=False, scale=4)
            self.assertEqual(path.read_bytes()[:2], b"BM")
            image = QImage(str(path))
            self.assertEqual(image.size().toTuple(), (1800, 1600))
            self.assertEqual(image.pixelColor(0, 0).getRgb(), (255, 255, 255, 255))

    def test_scale_changes_display_unexportable_dimensions_without_clamping(self):
        dialog = self.sketch_dialog(2400, 400)
        dialog.scale_box.setCurrentIndex(dialog.scale_box.findData(8))
        self.assertEqual(dialog.preview.canvas, (19200, 3200))
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertTrue(dialog.error.text())
        dialog.advanced.click()
        self.assertEqual(dialog.width_box.value(), 19200)
        dialog.width_box.setValue(1200)
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.scale_box.setCurrentIndex(dialog.scale_box.findData(1))
        # A crop of 18000 px at 8× cannot fit the smaller 1× view.
        self.assertEqual(dialog.width_box.value(), -15600)
        self.assertFalse(dialog.save_button.isEnabled())
        dialog.preview.grab()
        dialog.advanced.click()
        self.assertEqual(dialog.preview.canvas, (2400, 400))
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.advanced.click()
        dialog.scale_box.setCurrentIndex(dialog.scale_box.findData(8))
        self.assertEqual(dialog.preview.canvas, (1200, 3200))
        self.assertTrue(dialog.save_button.isEnabled())

    def test_result_source_is_selected_frame_and_hidden_geometry_cannot_export(self):
        from orcaview.gui.foundation_demo import build_foundation_demo
        w = self.window
        self.assertEqual([view for _, view in w._structure_image_views()], [w.viewport])
        session = build_foundation_demo()
        w.open_result_session(session, mark_dirty=False)
        frame = next(s for s in session.document.records()[0] if s.ref.frame_id is not None)
        w.foundation_panel.view_geometry(frame.ref)
        self.assertIs(w._structure_image_views()[0][1], w.foundation_panel.viewport)
        self.assertEqual(w.foundation_panel.viewport.molecule, frame.molecule)
        w.foundation_panel.geometry_pane.hide()
        with patch("orcaview.gui.main_window.StructureImageDialog") as dialog:
            w.export_structure_image()
            dialog.assert_not_called()
        w._update_structure_image_action()
        self.assertFalse(w.structure_image_action.isEnabled())

    def test_invalid_raster_size_cannot_save_or_overwrite_a_file(self):
        from orcaview.gui.structure_image_dialog import StructureImageDialog
        w = self.window
        dialog = StructureImageDialog(w._structure_image_views(), w.session.molecule.name, w)
        dialog.advanced.click()
        dialog.width_box.setValue(12000)
        dialog.height_box.setValue(12000)
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertTrue(dialog.error.text())
        dialog.format_choice.setCurrentIndex(dialog.format_choice.findData("pdf"))
        self.assertTrue(dialog.save_button.isEnabled())
        with patch.object(QFileDialog, "exec", return_value=0):
            dialog.save_button.click()
        self.assertIsNone(dialog.output_path)

"""Interactive broadening, image export and measured stick values."""

import csv
import os
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import patch

from orcaview.orca.log_spectra import SpectrumTable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from orcaview.gui.file_dialogs import set_document_directory
    from orcaview.gui.spectrum_image_dialog import SpectrumImageDialog
    from orcaview.gui.spectrum_preview import SpectrumPreview
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


@unittest.skipUnless(QApplication, "Requires Qt")
class SpectrumPlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.preview = SpectrumPreview()
        self.addCleanup(self.preview.close)
        self.data = SpectrumTable("cd", "Electronic CD",
                                  ("Wavelength (nm)", "Rotatory strength (10⁻⁴⁰ cgs)"),
                                  ((200., 6.), (217., -4.), (240., 3.)), 15)
        self.preview.set_spectrum(self.data)
        self.preview.plot_button.click()
        self.dialog = self.preview._dialog
        self.addCleanup(self.preview.set_spectrum, None)

    def export_from_ui(self, path, configure=None, action=None):
        def save(options):
            if configure:
                configure(options)
            options.save_button.click()
            return options.result()

        with patch.object(SpectrumImageDialog, "exec", save), patch.object(
                QFileDialog, "exec", return_value=1), patch.object(
                QFileDialog, "selectedFiles", return_value=[str(path)]):
            (action or self.preview.export_image_button.click)()

    def export_image_from_preview(self, path, configure=None):
        self.export_from_ui(path, configure)
        image = QImage(str(path))
        self.assertFalse(image.isNull())
        return image

    def test_direct_image_export_preserves_current_plot_settings(self):
        dialog = self.dialog
        dialog.unit.setCurrentText("eV")
        dialog.normalize.setChecked(True)
        dialog.reverse.setChecked(True)
        dialog.grid.setChecked(False)
        dialog.layers.setCurrentIndex(dialog.layers.findData("curve"))
        dialog.stroke_width.setValue(4.0)
        dialog.close()
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory, "settings.png")
            dialog.save_export(reference, "png")
            initial = []
            def inspect(options):
                initial.append((options.format_choice.currentData(), options.scale_box.currentData(),
                                options.ratio_box.currentData(), options.grid.isChecked(),
                                options.transparent.isChecked(), options.preview.canvas))
            image = self.export_image_from_preview(Path(directory, "光谱.png"), inspect)
            self.assertEqual(initial, [("png", 2, "original", False, False, (1800, 1100))])
            self.assertEqual(image, QImage(str(reference)))
        self.assertFalse(dialog.isVisible())

    def test_direct_image_picker_uses_source_folder_and_png_suffix_without_opening_settings(self):
        preview = SpectrumPreview()
        self.addCleanup(preview.close)
        preview.set_spectrum(self.data)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            set_document_directory(preview, folder / "电子光谱.out")
            picker_settings = []

            def select_name(picker):
                picker_settings.append((Path(picker.selectedFiles()[0]).resolve(), picker.defaultSuffix()))
                picker.selectFile("我的光谱")
                return 1

            with patch.object(SpectrumImageDialog, "exec", lambda dialog: dialog.save_button.click()), patch.object(
                    QFileDialog, "exec", select_name):
                preview.export_image_button.click()
            self.assertEqual(picker_settings, [(folder / "Electronic CD.png", "png")])
            self.assertEqual(QImage(str(folder / "我的光谱.png")).size().toTuple(), (1800, 1100))
        self.assertIsNone(preview._dialog)

    def test_direct_image_cancel_and_write_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            set_document_directory(self.preview, root / "spectrum.out")
            with patch.object(SpectrumImageDialog, "exec", return_value=0), patch.object(QFileDialog, "exec") as picker:
                self.preview.export_image_button.click()
                picker.assert_not_called()
            with patch.object(SpectrumImageDialog, "exec", lambda dialog: dialog.save_button.click()), patch.object(
                    QFileDialog, "exec", return_value=0), patch.object(QMessageBox, "warning") as warning:
                self.preview.export_image_button.click()
                warning.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])
            with patch.object(QMessageBox, "warning") as warning:
                self.export_from_ui(root / "missing" / "plot.png")
                warning.assert_called_once()
            self.assertEqual(list(root.iterdir()), [])
            self.assertTrue(self.preview.export_image_button.isEnabled())

    def test_direct_image_for_mode_positions_and_nmr_depends_on_displayed_data(self):
        cases = (
            ("vibrations", "Modes", ("Mode", "Frequency (cm⁻¹)"),
             ((1, 600), (2, 670), (3, 750)), ((1, 600), (2, 630), (3, 750))),
            ("nmr", "NMR", ("Nucleus", "Element", "Shielding (ppm)"),
             ((1, "H", 5.5),), ((1, "H", 8.25),)),
        )
        with tempfile.TemporaryDirectory() as directory:
            for kind, title, columns, before, after in cases:
                with self.subTest(kind=kind):
                    images = []
                    grid_states = []
                    def transparent(options):
                        grid_states.append((options.grid.isHidden(), options.grid.isChecked()))
                        options.transparent.setChecked(True)
                    for rows in (before, after):
                        self.preview.set_spectrum(SpectrumTable(kind, title, columns, rows, 15))
                        self.assertTrue(self.preview.export_image_button.isVisible())
                        self.assertTrue(self.preview.export_image_button.isEnabled())
                        images.append(self.export_image_from_preview(Path(directory, f"{kind}.png"), transparent))
                    self.assertEqual(images[0].size(), images[1].size())
                    self.assertNotEqual(images[0], images[1])
                    self.assertEqual(images[0].pixelColor(5, 5).alpha(), 0)
                    self.assertEqual([state[0] for state in grid_states], [kind == "nmr"] * 2)
                    if kind == "vibrations":
                        self.assertFalse(grid_states[0][1])
                        def with_grid(options):
                            options.transparent.setChecked(True)
                            options.grid.setChecked(True)
                        with_lines = self.export_image_from_preview(Path(directory, "modes-grid.png"), with_grid)
                        self.assertNotEqual(with_lines, images[1])
        self.preview.set_spectrum(None)
        self.assertFalse(self.preview.export_image_button.isVisible())

    def test_export_grid_is_independent_and_ratio_changes_plot_area(self):
        preview_images = []
        def set_appearance(options, grid):
            options.ratio_box.setCurrentIndex(options.ratio_box.findData("4:3"))
            options.scale_box.setCurrentIndex(options.scale_box.findData(1))
            options.transparent.setChecked(True)
            options.grid.setChecked(grid)
            preview_images.append(options.preview.grab().toImage())

        with tempfile.TemporaryDirectory() as directory:
            off = self.export_image_from_preview(Path(directory, "off.png"),
                                                 lambda opts: set_appearance(opts, False))
            self.assertTrue(self.dialog.grid.isChecked())
            self.assertTrue(self.preview._style.grid)
            path = Path(directory, "on.png")
            detailed_action = self.dialog.export_button.menu().actions()[0]
            self.export_from_ui(path, lambda opts: set_appearance(opts, True), detailed_action.trigger)
            on = QImage(str(path))
            self.assertEqual(off.size().toTuple(), (900, 675))
            self.assertEqual(on.size(), off.size())
            self.assertNotEqual(preview_images[0], preview_images[1])
            self.assertEqual(off.pixelColor(3, 3).alpha(), 0)
            # The horizontal axis follows the taller plot's lower edge.
            self.assertTrue(all(off.pixelColor(x, 590).alpha() > 50 for x in range(80, 860, 10)))
            # Turning off the grid removes ink inside the plot while preserving titles, axes and ticks.
            self.assertNotEqual(on.copy(75, 105, 780, 470), off.copy(75, 105, 780, 470))
            self.assertEqual(on.copy(0, 0, 900, 97), off.copy(0, 0, 900, 97))
            self.assertEqual(on.copy(0, 600, 900, 75), off.copy(0, 600, 900, 75))

    def test_ratio_scale_custom_bounds_and_size_validation(self):
        dimensions = []
        def inspect(options):
            for ratio in ("original", "1:1", "4:3", "16:9"):
                options.ratio_box.setCurrentIndex(options.ratio_box.findData(ratio))
                dimensions.append(options.preview.canvas)
            options.scale_box.setCurrentIndex(options.scale_box.findData(1))

        with tempfile.TemporaryDirectory() as directory:
            base = self.export_image_from_preview(Path(directory, "wide.png"), inspect)
            self.assertEqual(dimensions, [(1800, 1100), (1800, 1800), (1800, 1350), (1920, 1080)])
            self.assertEqual(base.size().toTuple(), (960, 540))
            states = []
            def custom(options):
                options.ratio_box.setCurrentIndex(options.ratio_box.findData("16:9"))
                options.scale_box.setCurrentIndex(options.scale_box.findData(1))
                options.advanced.setChecked(True)
                options.width_box.setValue(8000)
                options.height_box.setValue(8000)
                states.append((options.save_button.isEnabled(), bool(options.error.text())))
                options.width_box.setValue(880)
                options.height_box.setValue(500)
                states.append((options.save_button.isEnabled(), bool(options.error.text())))
            crop = self.export_image_from_preview(Path(directory, "crop.png"), custom)
            self.assertEqual(states, [(False, True), (True, False)])
            self.assertEqual(crop, base.copy(40, 20, 880, 500))

    def test_formats_use_supported_background_and_vector_pdf_page(self):
        choice_states = []
        with tempfile.TemporaryDirectory() as directory:
            for fmt in ("jpg", "bmp", "pdf"):
                with self.subTest(fmt=fmt):
                    def select_format(options):
                        options.transparent.setChecked(True)
                        options.format_choice.setCurrentIndex(options.format_choice.findData(fmt))
                        choice_states.append((fmt, options.transparent.isEnabled(), options.transparent.isChecked()))
                    path = Path(directory, f"spectrum.{fmt}")
                    self.export_from_ui(path, select_format)
                    if fmt == "pdf":
                        raw = path.read_bytes()
                        box = re.search(rb"/MediaBox\s*\[0 0 ([\d.]+) ([\d.]+)\]", raw)
                        self.assertIsNotNone(box)
                        self.assertEqual(tuple(map(float, box.groups())), (675., 412.5))
                        self.assertNotIn(b"/Subtype /Image", raw)
                        self.assertIn(b"/Type /Font", raw)
                    else:
                        image = QImage(str(path))
                        self.assertEqual(image.size().toTuple(), (1800, 1100))
                        self.assertEqual(image.pixelColor(0, 0).getRgb(), (255, 255, 255, 255))
        self.assertEqual(choice_states, [("jpg", False, False), ("bmp", False, False), ("pdf", True, True)])

    def test_profiles_range_axis_normalization_and_export(self):
        dialog = self.dialog
        self.assertTrue(dialog.isVisible())
        self.assertIs(self.preview._profile, dialog.figure.profile)
        self.assertGreater(len(dialog.figure.profile.curve), 100)
        dialog.shape.setCurrentIndex(dialog.shape.findData("pseudo-voigt"))
        dialog.mix.setValue(75)
        dialog.width.setValue(12.5)
        dialog.reverse.setChecked(True)
        dialog.normalize.setChecked(True)
        dialog.auto_range.setChecked(False)
        dialog.xmin.setValue(195)
        dialog.xmax.setValue(242)
        profile = self.preview._profile
        self.assertEqual((profile.shape, profile.fwhm, profile.mix), ("pseudo-voigt", 12.5, .75))
        self.assertEqual(profile.limits, (195., 242.))
        self.assertTrue(dialog.figure.style.reverse)
        self.assertEqual(self.data.rows, ((200., 6.), (217., -4.), (240., 3.)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("png", "curve", "sticks"):
                dialog.save_export(root / name, name)
            image = QImage(str(root / "png"))
            self.assertEqual((image.width(), image.height()), (1800, 1100))
            with (root / "curve").open(encoding="utf-8", newline="") as file:
                rows = list(csv.reader(file))
            self.assertEqual(rows[0], ["Wavelength (nm)", "Relative height"])
            ys = [float(y) for _, y in rows[1:]]
            self.assertAlmostEqual(max(map(abs, ys)), 1.)
            self.assertLess(min(ys), 0)
            with (root / "sticks").open(encoding="utf-8", newline="") as file:
                rows = list(csv.reader(file))
            self.assertEqual(tuple((float(x), float(y)) for x, y in rows[1:]), self.data.rows)
        dialog.xmax.setValue(180)
        self.assertFalse(dialog.export_button.isEnabled())
        self.assertFalse(self.preview.export_image_button.isEnabled())
        self.assertTrue(dialog.figure.error)
        dialog.unit.setCurrentText("eV")
        self.assertTrue(dialog.export_button.isEnabled())
        self.assertTrue(self.preview.export_image_button.isEnabled())
        self.assertTrue(dialog.auto_range.isChecked())
        self.assertEqual(self.preview._profile.source.unit, "eV")
        dialog.reset_button.click()
        self.assertEqual(self.preview._profile.source.unit, "nm")
        self.assertFalse(dialog.normalize.isChecked())

    def test_curve_width_updates_trace_legend_and_preview_without_broadening_again(self):
        dialog = self.dialog
        profile = self.preview._profile
        self.assertEqual((dialog.stroke_width.value(), dialog.stroke_width.suffix()), (2.0, " px"))
        dialog.layers.setCurrentIndex(dialog.layers.findData("sticks"))
        self.assertFalse(dialog.stroke_width.isEnabled())
        dialog.layers.setCurrentIndex(dialog.layers.findData("curve"))
        self.assertTrue(dialog.stroke_width.isEnabled())

        def curve_pixels(region):
            rgba = region.convertToFormat(QImage.Format.Format_RGBA8888)
            return bytes(rgba.constBits()).count(bytes.fromhex("365987ff"))

        with tempfile.TemporaryDirectory() as directory:
            counts = []
            for thickness in (0.5, 6.0):
                dialog.stroke_width.setValue(thickness)
                self.assertIs(self.preview._profile, profile)
                self.assertEqual(self.preview._style.stroke_width, thickness)
                self.assertEqual(dialog.width.value(), profile.fwhm)
                filename = Path(directory) / "profile.png"
                dialog.save_export(filename, "png")
                image = QImage(str(filename))
                traces = image.copy(0, 200, 1800, 730)
                legend = image.copy(0, 1040, 1800, 60)
                preview = self.preview.grab().toImage()
                counts.append(tuple(curve_pixels(region) for region in (traces, legend, preview)))
            for thin, thick in zip(*counts):
                self.assertGreater(thick, thin)
        dialog.reset_button.click()
        self.assertEqual(dialog.stroke_width.value(), 2.0)
        self.assertEqual(self.preview._style.stroke_width, 2.0)

    def test_dense_plot_runs_in_background_and_recovers_after_narrowing_range(self):
        rows = tuple((1000.0 + i * .04, float(1 + i % 7)) for i in range(5000))
        data = SpectrumTable("ir", "Dense IR", ("Wavenumber (cm⁻¹)", "IR intensity (km/mol)"), rows, 12)
        self.preview.set_spectrum(data)
        dialog = self.preview._dialog
        self.assertIsNotNone(self.preview._sampler.running)
        self.assertFalse(self.preview.export_image_button.isEnabled())
        dialog.shape.setCurrentIndex(dialog.shape.findData("lorentzian"))
        dialog.width.setValue(.000001)

        def settle():
            deadline = time.monotonic() + 15
            while self.preview._sampler.running is not None and time.monotonic() < deadline:
                QTest.qWait(20)
            self.assertIsNone(self.preview._sampler.running)

        settle()
        self.assertTrue(dialog.figure.error)
        self.assertFalse(dialog.export_button.isEnabled())
        self.assertFalse(self.preview.export_image_button.isEnabled())
        dialog.auto_range.setChecked(False)
        dialog.xmin.setValue(1010.)
        dialog.xmax.setValue(1010.04)
        dialog.sampling.setCurrentIndex(dialog.sampling.findData(401))
        settle()
        self.assertFalse(dialog.figure.error)
        self.assertTrue(dialog.export_button.isEnabled())
        self.assertTrue(self.preview.export_image_button.isEnabled())
        self.assertEqual(self.preview._profile.limits, (1010., 1010.04))
        self.assertTrue(any(y > 0 for _, y in self.preview._profile.curve))

    def test_changing_table_updates_open_plot_and_hides_it_for_nmr(self):
        ir = SpectrumTable("ir", "IR", ("Wavenumber (cm⁻¹)", "IR intensity (km/mol)"), ((1100., 9.),), 25)
        self.preview.set_spectrum(ir)
        new_dialog = self.preview._dialog
        self.assertFalse(self.dialog.isVisible())
        self.assertTrue(new_dialog.isVisible())
        self.assertIs(new_dialog.table, ir)
        self.assertTrue(new_dialog.reverse.isChecked())
        new_dialog.width.setValue(33.)
        self.preview.set_spectrum(ir)
        self.assertEqual(self.preview._profile.fwhm, 33.)
        self.preview.set_spectrum(SpectrumTable("nmr", "NMR", ("Nucleus", "Element", "Shielding (ppm)"),
                                                ((1, "H", 5.5),), 40))
        self.assertFalse(new_dialog.isVisible())
        self.assertTrue(self.preview.plot_button.isHidden())
        self.assertIn("5.5 ppm", self.preview.accessibleDescription())
        self.preview.set_spectrum(None)
        self.assertTrue(self.preview.isHidden())

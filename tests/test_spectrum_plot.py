"""Interactive broadening, image export and measured stick values."""

import csv
import os
from pathlib import Path
import tempfile
import time
import unittest

from orcaview.orca.log_spectra import SpectrumTable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
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
        self.assertTrue(dialog.figure.error)
        dialog.unit.setCurrentText("eV")
        self.assertTrue(dialog.export_button.isEnabled())
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
        dialog.auto_range.setChecked(False)
        dialog.xmin.setValue(1010.)
        dialog.xmax.setValue(1010.04)
        dialog.sampling.setCurrentIndex(dialog.sampling.findData(401))
        settle()
        self.assertFalse(dialog.figure.error)
        self.assertTrue(dialog.export_button.isEnabled())
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

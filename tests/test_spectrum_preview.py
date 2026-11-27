"""Check the sidebar's miniature spectra against printed ORCA values."""

import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from orcaview.orca.log_spectra import SpectrumTable, parse_log_spectra

try:
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.spectrum_preview import SpectrumPreview
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False
else:
    HAS_QT = True

FIXTURES = Path(__file__).resolve().parents[1] / "artifacts" / "public" / "validation" / "results-0.1.0a12"


@unittest.skipUnless(HAS_QT, 'Optional Qt dependency is not installed')
class SpectrumPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.preview = SpectrumPreview()
        self.preview.resize(180, self.preview.height())
        self.addCleanup(self.preview.close)

    def sticks(self):
        if self.preview.plot_button.isVisibleTo(self.preview):
            self.preview.open_plot()
            dialog = self.preview._dialog
            dialog.layers.setCurrentIndex(dialog.layers.findData("sticks"))
            dialog.close()
            self.app.processEvents()
        image = self.preview.grab().toImage()
        ratio = image.devicePixelRatio()
        positive, negative = [], []
        for x in range(image.width()):
            for y in range(int(44 * ratio), int(80 * ratio)):
                color = image.pixelColor(x, y)
                point = (x / ratio, y / ratio)
                if color.red() - color.green() > 34:
                    positive.append(point)
                if color.green() - color.red() > 28:
                    negative.append(point)
        return positive, negative

    def test_signed_cd_peaks_have_opposite_directions_and_null_strength_is_omitted(self):
        table = SpectrumTable("cd", 'Electronic circular dichroism (CD)', ('Wavelength (nm)', 'Rotatory strength (10⁻⁴⁰ cgs)'),
                              ((200., 5.), (225., None), (250., -5.)), 1)
        self.assertTrue(self.preview.isHidden())
        self.preview.set_spectrum(table)
        self.assertFalse(self.preview.isHidden())
        positive, negative = self.sticks()
        self.assertGreater(len(positive), 6)
        self.assertGreater(len(negative), 6)
        self.assertLess(min(y for _, y in positive), min(y for _, y in negative) - 8)
        self.assertGreater(max(y for _, y in negative), max(y for _, y in positive) + 8)
        self.assertGreater(min(x for x, _ in negative), max(x for x, _ in positive) + 30)
        self.assertNotIn("225", self.preview.accessibleDescription())
        self.preview.set_spectrum(None)
        self.assertTrue(self.preview.isHidden())
        self.assertEqual(self.preview.accessibleDescription(), "")

    def test_ir_reversed_axis_places_the_larger_wave_number_left_and_preserves_zero(self):
        table = SpectrumTable("ir", 'Infrared spectrum', ('Wavenumber (cm⁻¹)', 'IR intensity (km/mol)'),
                              ((1000., 0.), (2000., 40.)), 1)
        self.preview.set_spectrum(table)
        positive, _ = self.sticks()
        left = [y for x, y in positive if x < self.preview.width() / 2]
        right = [y for x, y in positive if x > self.preview.width() / 2]
        self.assertGreater(max(left) - min(left), 22)
        self.assertLessEqual(max(right) - min(right), 5)
        self.assertIn("1000 cm⁻¹   0", self.preview.accessibleDescription())

    def test_narrow_single_position_and_only_wave_number_or_zero_is_visible(self):
        self.preview.resize(74, self.preview.height())
        vib = SpectrumTable("vibrations", 'Vibrational frequencies (wavenumbers only)', ('Vibrational mode', 'Wavenumber (cm⁻¹)'),
                            ((1, -49.2), (2, -49.2)), 1)
        self.preview.set_spectrum(vib)
        ticks, _ = self.sticks()
        self.assertGreater(len(ticks), 1)
        self.assertLess(max(y for _, y in ticks) - min(y for _, y in ticks), 12)
        self.assertIn("-49.2 cm⁻¹", self.preview.accessibleDescription())
        all_zero = SpectrumTable("raman", 'Raman spectrum', ('Wavenumber (cm⁻¹)', 'Raman activity (Å⁴/amu)'), ((4000., 0.),), 1)
        self.preview.set_spectrum(all_zero)
        dots, _ = self.sticks()
        self.assertGreater(len(dots), 0)
        self.assertLess(max(y for _, y in dots) - min(y for _, y in dots), 5)

    def test_real_nmr_values_are_visible_as_nuclear_labels_with_original_units(self):
        shield, coupling = parse_log_spectra((FIXTURES / "nmr" / "water-shield.out").read_text())
        self.preview.set_spectrum(shield)
        self.assertIn('Isotropic shielding / ppm', self.preview.accessibleDescription())
        self.assertIn("0 O   347.078 ppm", self.preview.accessibleDescription())
        self.assertFalse(self.preview.grab().isNull())
        self.preview.set_spectrum(coupling)
        self.assertIn("1 H – 2 H   -15.538 Hz", self.preview.accessibleDescription())
        self.assertNotIn("ppm", self.preview.accessibleDescription())

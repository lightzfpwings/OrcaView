"""Numerical checks for displayed ORCA spectral line shapes and axis conversions."""

from pathlib import Path
import unittest

from orcaview.orca.log_spectra import SpectrumTable, parse_log_spectra
from orcaview.results.broadening import broaden_spectrum, spectrum_range, stick_spectrum
from orcaview.results.nmr import coupling_pairs, plot_source, shielding_elements


class PrintedSticksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = Path(__file__).resolve().parents[1] / "artifacts/public/validation/results-0.1.0a12"

    def test_real_ir_raman_keep_their_own_intensities_on_wavenumber_axis(self):
        ir, raman = parse_log_spectra((self.fixtures / "raman/water.out").read_text())
        ir, raman = stick_spectrum(ir), stick_spectrum(raman)
        self.assertEqual((ir.peaks[0], raman.peaks[0]), ((1791.17, 80.58), (1791.17, 5.602782)))
        self.assertTrue(ir.reversed_axis)
        self.assertFalse(raman.reversed_axis)
        self.assertEqual(ir.units, ("cm⁻¹",))

    def test_both_gauges_use_printed_optical_coordinates_and_signed_strengths(self):
        spectra = parse_log_spectra((self.fixtures / "tdcd/peroxide.out").read_text())
        absorption, _, cd_length, cd_velocity = spectra
        self.assertEqual(stick_spectrum(absorption).peaks[0], (207.2, 0.000062162))
        for unit, expected_center in (("nm", 207.2), ("eV", 5.984650), ("cm⁻¹", 48269.5)):
            self.assertEqual(stick_spectrum(cd_length, unit).peaks[0], (expected_center, -0.70219))
            self.assertEqual(stick_spectrum(cd_velocity, unit).peaks[0], (expected_center, 22.94792))

    def test_unmeasured_nmr_and_mode_intensity_are_not_invented(self):
        for t in parse_log_spectra((self.fixtures / "nmr/water-shield.out").read_text()):
            self.assertIsNone(stick_spectrum(t))
        for kind in ("vibrations", "continuous"):
            self.assertIsNone(stick_spectrum(SpectrumTable(kind, "", ("x", "y"), ((5, 12),), 1)))

    def test_nmr_reference_counts_and_signed_pairs_from_real_orca(self):
        shield, coupling = parse_log_spectra((self.fixtures / "nmr/water-shield.out").read_text())
        self.assertEqual(shielding_elements(shield), ("H", "O"))
        source = plot_source(shield)
        self.assertEqual(source.peaks, ((31.130, 2),))
        self.assertFalse(source.reversed_axis)
        oxygen = plot_source(shield, element="o", reference=346.078)
        self.assertEqual(oxygen.peaks, ((-1., 1),))
        self.assertTrue(oxygen.reversed_axis)
        self.assertEqual(coupling_pairs(coupling), (("1 H", "2 H", -15.538),))
        with self.assertRaises(ValueError):
            plot_source(coupling, reference=1)
        with self.assertRaisesRegex(ValueError, "Available elements"):
            plot_source(shield, element="C")

    def test_nmr_legacy_columns_missing_values_and_zero_reference(self):
        table = SpectrumTable("nmr", "", ("核", "元素", "屏蔽（ppm）"),
                              ((0, "F", 0.), (1, "F", None), (2, "F", -5.), (3, "F", 0.), (4, "F", 4.)), 1)
        self.assertEqual(plot_source(table, reference=0).peaks, ((-4., 1), (0., 2), (5., 1)))
        for value in (float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                plot_source(table, reference=value)
        pairs = SpectrumTable("nmr", "", ("1", "2", "J (Hz)"),
                              (("0 F", "1 F", 0.), ("1 F", "2 F", None), ("2 F", "3 F", -2.)), 1)
        self.assertEqual(coupling_pairs(pairs), (("0 F", "1 F", 0.), ("2 F", "3 F", -2.)))

    def test_legacy_state_columns_convert_missing_energy_and_skip_missing_strengths(self):
        table = SpectrumTable("uvvis", "", ("State", "Wavenumber (cm⁻¹)", "Wavelength (nm)",
                                            "Oscillator strength"), ((1, 20000, 500, 0.5),
                                                                    (2, 40000, 250, None)), 1)
        (x, y), = stick_spectrum(table, "eV").peaks
        self.assertAlmostEqual(x, 2.4796839687, places=9)
        self.assertEqual(y, 0.5)

    def test_legacy_localized_columns_require_no_translation_to_plot(self):
        table = SpectrumTable("cd", "", ("波长（nm）", "旋光强度（10⁻⁴⁰ cgs）"),
                              ((200, -1), (225, None), (300, 3)), 1)
        self.assertEqual(stick_spectrum(table).peaks, ((200, -1), (300, 3)))
        # The source row remains available in the original file and project.
        self.assertEqual(len(table.rows), 3)


class BroadeningTests(unittest.TestCase):
    def test_all_profiles_have_prescribed_width_and_peak_height(self):
        for kind in ("gaussian", "lorentzian", "pseudo-voigt"):
            with self.subTest(shape=kind):
                ys = dict(broaden_spectrum(((0, -2),), 2, shape=kind, x_range=(-4, 4), points=17))
                self.assertEqual(ys[0], -2)
                self.assertAlmostEqual(ys[-1], -1)
                self.assertAlmostEqual(ys[1], -1)
                expected = {"gaussian": -2 / 16, "lorentzian": -2 / 5,
                            "pseudo-voigt": -1 / 16 - 1 / 5}[kind]
                self.assertAlmostEqual(ys[2], expected)
                self.assertAlmostEqual(ys[-2], expected)

    def test_signed_sum_shared_positions_normalization_and_zero_spectrum(self):
        peaks = ((0, 1), (0, -1), (2, -2), (4, 1))
        raw = dict(broaden_spectrum(peaks, 2, x_range=(0, 4), points=41))
        norm = dict(broaden_spectrum(peaks, 2, normalize=True, x_range=(0, 4), points=41))
        self.assertAlmostEqual(raw[2], -2 + 1/16)
        self.assertAlmostEqual(raw[4], 1 - 2/16)
        self.assertEqual(max(map(abs, norm.values())), 1.)
        self.assertAlmostEqual(norm[0], raw[0] / max(map(abs, raw.values())))
        self.assertEqual({y for _, y in broaden_spectrum(((0, 0),), 1, normalize=True)}, {0})
        self.assertEqual(broaden_spectrum((), 1), ())

    def test_crop_keeps_wings_from_external_lines_and_narrow_line_centers(self):
        curve = dict(broaden_spectrum(((2.112, -1), (3, 10)), 0.01, shape="lorentzian",
                                      x_range=(0, 2.5), points=100))
        self.assertEqual((min(curve), max(curve)), (0, 2.5))
        self.assertLess(curve[2.112], -0.99)
        self.assertGreater(curve[2.5], 0)
        self.assertEqual(list(curve), sorted(curve))
        low, high = spectrum_range(((5, 1),), 2)
        self.assertLess(low, 4)
        self.assertGreater(high, 6)

    def test_narrow_lorentzian_has_samples_in_its_wings_on_a_wide_axis(self):
        curve = broaden_spectrum(((0.1, 1.0),), 0.001, shape="lorentzian",
                                 x_range=(0, 20), points=5)
        # Half height and the physically decaying tail must survive a coarse base
        # grid. A single straight segment from the peak core to 5 would fill in
        # far more intensity than the actual Lorentzian near x=0.2.
        center = 0.1
        self.assertAlmostEqual(dict(curve)[center + 0.0005], 0.5)
        left, right = next((a, b) for a, b in zip(curve, curve[1:]) if a[0] <= .2 < b[0])
        t = (.2 - left[0]) / (right[0] - left[0])
        self.assertLess((1-t) * left[1] + t * right[1], 3e-5)

    def test_dense_request_can_be_retried_with_a_smaller_visible_range(self):
        peaks = tuple((i, 1) for i in range(2500))
        with self.assertRaisesRegex(ValueError, "narrow|dense"):
            broaden_spectrum(peaks, 0.001, shape="lorentzian", x_range=(0, 2500))
        zoomed = dict(broaden_spectrum(peaks, 0.001, shape="lorentzian", x_range=(900, 905), points=101))
        self.assertGreater(zoomed[901], 1)
        self.assertEqual((min(zoomed), max(zoomed)), (900, 905))

    def test_invalid_numeric_settings(self):
        for args, kw in [(((), 0), {}), ((((2, float("inf")),), 2), {}),
                         ((((2, 3),), 2), {"shape": "unknown"}),
                         ((((2, 3),), 2), {"x_range": (2, 1)}),
                         ((((2, 3),), 2), {"points": 1}),
                         ((((2, 3),), 2), {"mix": 1.1})]:
            with self.subTest(kwargs=kw), self.assertRaises(ValueError):
                broaden_spectrum(*args, **kw)

"""Regression tests for printed spectroscopy data in ORCA logs."""

from pathlib import Path
from textwrap import dedent
import unittest

from orcaview.orca.log_spectra import parse_log_spectra


ARCHIVE = Path(__file__).resolve().parents[1] / "artifacts" / "public" / "validation" / "ORCA-6.1.1-macOS-arm64"
REPORT_FIXTURES = ARCHIVE.parent / "results-0.1.0a12"


class LogSpectraTests(unittest.TestCase):
    def test_real_optfreq_keeps_original_mode_numbers_intensities_and_units(self):
        lines = (ARCHIVE / "optfreq" / "job.out").read_text().splitlines(keepends=True)
        table, = parse_log_spectra(lines)
        self.assertEqual(table.kind, "ir")
        self.assertEqual(lines[table.source_line - 1].strip(), "IR SPECTRUM")
        self.assertEqual(table.rows[0], (6, 1637.65, 0.010942, 55.30, 0.002085, 0., -0., 0.045662))
        self.assertEqual([row[0] for row in table.rows], [6, 7, 8])
        self.assertIn("cm⁻¹", table.columns[1])
        self.assertIn("km/mol", table.columns[3])

    def test_real_eom_electric_absorption_preserves_all_three_moment_tables(self):
        text = (ARCHIVE / "eom" / "job.out").read_text()
        tables = parse_log_spectra(text)
        self.assertEqual([t.kind for t in tables], ["uvvis"] * 3)
        self.assertEqual(len({t.title for t in tables}), 3)
        self.assertEqual([t.source_line for t in tables], sorted(t.source_line for t in tables))
        for t in tables:
            self.assertIn("ABSORPTION SPECTRUM", text.splitlines()[t.source_line - 1])
            self.assertEqual(len(t.rows), 2)
            self.assertEqual(t.rows[0][:4], ("0-1A -> 1-1A", 8.183046, 66000.7, 151.5))
            self.assertEqual(t.rows[1][4], 0.0)
        self.assertEqual([t.rows[0][4] for t in tables], [0.020541380, 0.021501486, 0.021015951])

    def test_real_tddft_distinguishes_absorption_and_cd_and_their_two_gauges(self):
        lines = (REPORT_FIXTURES / "tdcd" / "peroxide.out").read_text().splitlines()
        tables = parse_log_spectra(lines)
        self.assertEqual([t.kind for t in tables], ["uvvis", "uvvis", "cd", "cd"])
        self.assertEqual([len(t.rows) for t in tables], [4, 4, 4, 4])
        length, velocity = tables[2:]
        self.assertIn("ELECTRIC", lines[length.source_line - 1])
        self.assertIn("VELOCITY", lines[velocity.source_line - 1])
        self.assertIn("10⁻⁴⁰ cgs", length.columns[4])
        self.assertEqual(length.rows[0], ("0-1A -> 1-1A", 5.98465, 48269.5, 207.2, -0.70219, -0.04723, -0.06686, -0.11567))
        self.assertEqual(velocity.rows[0][4], 22.94792)

    def test_real_raman_and_nmr_complete_logs(self):
        ir, raman = parse_log_spectra((REPORT_FIXTURES / "raman" / "water.out").read_text())
        self.assertEqual((ir.kind, raman.kind), ("ir", "raman"))
        self.assertEqual(raman.rows[-1], (8, 4046.70, 36.571053, 0.75))
        shield, coupling = parse_log_spectra((REPORT_FIXTURES / "nmr" / "water-shield.out").read_text())
        self.assertEqual(shield.rows[-1], (0, "O", 347.078, 37.771))
        self.assertEqual(coupling.rows, (("1 H", "2 H", -15.538),))

    def test_frequency_only_fallback_is_scoped_to_its_job(self):
        lines = (ARCHIVE / "optfreq" / "job.out").read_text().splitlines()
        full_ir, = parse_log_spectra(lines)
        # An interrupted calculation can finish harmonic modes before the IR table.
        partial = lines[:full_ir.source_line - 1]
        modes, = parse_log_spectra(partial)
        self.assertEqual(modes.kind, "vibrations")
        self.assertEqual(modes.columns, ('Vibrational mode', 'Wavenumber (cm⁻¹)'))
        self.assertEqual(modes.rows, tuple(enumerate([0.] * 6 + [1637.65, 3787.02, 3882.00])))
        self.assertEqual(lines[modes.source_line - 1].strip(), "VIBRATIONAL FREQUENCIES")
        self.assertEqual([t.kind for t in parse_log_spectra(partial + lines)], ["vibrations", "ir"])

    def test_negative_and_zero_wave_numbers_survive_without_intensity(self):
        modes, = parse_log_spectra(dedent("""\
            VIBRATIONAL FREQUENCIES
            -----------------------
            0:  0.00 cm**-1
            1: -138.59 cm**-1 ***imaginary mode***
        """))
        self.assertEqual(modes.rows, ((0, 0.), (1, -138.59)))

    def test_raman_zero_activity_and_reported_zero_depolarization(self):
        raman, = parse_log_spectra(dedent("""\
            RAMAN SPECTRUM
            --------------
              Mode    freq (cm**-1)   Activity   Depolarization
              -------------------------------------------------
                6:    1791.17  5.602782D+00   0.532757
                7:    3956.30  0.000000       0.000000
                8:    4046.70  36.571053      *****
        """))
        self.assertEqual(raman.kind, "raman")
        self.assertIn("Å⁴/amu", raman.columns[2])
        self.assertEqual(raman.rows, (
            (6, 1791.17, 5.602782, 0.532757), (7, 3956.30, 0., 0.), (8, 4046.70, 36.571053, None)
        ))

    def test_shielding_uses_printed_indices_and_j_matrix_deduplicates_across_blocks(self):
        text = dedent("""\
            CHEMICAL SHIELDING SUMMARY (ppm)
            --------------------------------

              Nucleus  Element    Isotropic     Anisotropy
              -------  -------  ------------   ------------
                  1       H           31.130          0.000
                  2       H           31.130         20.083
                  0       O          347.078         37.771

            SUMMARY OF ISOTROPIC COUPLING CONSTANTS J (Hz)
            ----------------------------------------------
                         0 O        1 H
                0 O    0.000    0.000
                1 H    0.000    0.000
                2 H       --  -15.538

                         2 H
                0 O       --
                1 H  -15.538
                2 H    0.000
        """)
        shield, coupling = parse_log_spectra(text)
        self.assertEqual((shield.kind, coupling.kind), ("nmr", "nmr"))
        self.assertIn('shielding', shield.title)
        self.assertIn("ppm", shield.columns[2])
        self.assertEqual(shield.rows, ((1, "H", 31.13, 0.), (2, "H", 31.13, 20.083), (0, "O", 347.078, 37.771)))
        self.assertIn("Hz", coupling.columns[-1])
        self.assertEqual(coupling.rows, (("0 O", "1 H", 0.), ("0 O", "2 H", None), ("1 H", "2 H", -15.538)))
        self.assertIn("ISOTROPIC COUPLING", text.splitlines()[coupling.source_line - 1])

    def test_shielding_requires_a_finite_isotropic_value_and_accepts_missing_anisotropy(self):
        heading = "CHEMICAL SHIELDING SUMMARY (ppm)\nNucleus Element Isotropic Anisotropy\n"
        self.assertEqual(parse_log_spectra(heading + "0 O NaN 100\n"), ())
        table, = parse_log_spectra(heading + "0 O NaN 100\n1 H 0.0 ****\n2 H 24.86 5.77")
        self.assertEqual(table.rows, ((1, "H", 0., None), (2, "H", 24.86, 5.77)))

    def test_velocity_gauge_with_separate_symmetry_labels(self):
        table, = parse_log_spectra(dedent("""\
            ABSORPTION SPECTRUM VIA TRANSITION VELOCITY DIPOLE MOMENTS
            --------------------------------------------------------------------------
             Transition Energy Energy Wavelength fosc(P2) P2 PX PY PZ
                         (eV) (cm-1) (nm)               (au**2) (au) (au) (au)
            --------------------------------------------------------------------------
             0-1 Ag ->  4-1 B3u   4.973431 40113.4 249.3 0.292852326 0.08029 -0.28335 0.00000 -0.00002
        """))
        self.assertIn('Velocity', table.title)
        self.assertIn("P²", table.columns[5])
        self.assertEqual(table.rows[0][:5], ("0-1 Ag -> 4-1 B3u", 4.973431, 40113.4, 249.3, 0.292852326))

    def test_legacy_absorption_preserves_spin_forbidden_annotation_and_missing_values(self):
        table, = parse_log_spectra(dedent("""\
            ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
            ----------------------------------------------------------
            State Energy Wavelength fosc T2 TX TY TZ
                  (cm-1) (nm)            (au**2) (au) (au) (au)
            ----------------------------------------------------------
              1 28000.0 357.1 0.0 0.0 0.0 0.0 0.0
              2 35000.0 285.7 spin forbidden (mult=3)
        """))
        self.assertEqual(table.rows[0], (1, 28000.0, 357.1, 0., 0., 0., 0., 0., None))
        self.assertEqual(table.rows[1], (2, 35000.0, 285.7, None, None, None, None, None, "spin forbidden (mult=3)"))

    def test_legacy_ir_keeps_original_strength_convention(self):
        table, = parse_log_spectra(dedent("""\
            IR SPECTRUM
            Mode freq (cm**-1) T**2 TX TY TZ
            --------------------------------
            6: 1278.77 6.157280 (-2.481387 -0.000010 -0.000287)
        """))
        self.assertIn("km/mol", table.columns[2])
        self.assertEqual(table.rows, ((6, 1278.77, 6.157280, -2.481387, -0.000010, -0.000287),))

    def test_input_echo_run_flags_empty_tables_and_other_spectra_are_not_results(self):
        self.assertEqual(parse_log_spectra((ARCHIVE / "smd" / "job.out").read_text()), ())
        non_results = dedent("""\
            |  1> ! NMR NUMFREQ
            |  2> IR SPECTRUM
            |  3> Mode freq (cm**-1) T**2 TX TY TZ
            |  4>   6: 1800.0 1.2 (0.0 0.0 1.0)
            IR spectrum ... YES
            Chemical shifts ... NO
            RAMAN SPECTRUM
            Mode freq (cm**-1) Activity Depolarization
            ------------------------------------------
            CHEMICAL SHIELDING SUMMARY (ppm)
            Nucleus Element Isotropic Anisotropy
            0 O nan 100
            | 48> CD SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
            | 49> Transition Energy Energy Wavelength R MX MY MZ
            | 50> 0-1A -> 1-1A 3.2 25810 387.5 5.1 0.1 0.2 0.3
            VIBRATIONAL FREQUENCIES
              Scaling factor for frequencies = 1.0
            ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
            Transition Energy Energy Wavelength fosc(D2) D2 DX DY DZ
            0-1A -> 1-1A 8.0 65000.0
        """)
        self.assertEqual(parse_log_spectra(non_results), ())

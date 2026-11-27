"""ORCA energy curves keep job, cycle, SCF warning and final-evaluation provenance."""

from importlib.util import find_spec
from dataclasses import replace
import os
from pathlib import Path
import unittest

from orcaview.core.provenance import ArtifactRef
from orcaview.orca.log_report import parse_log_report
from orcaview.results.optimization import optimization_runs


def report(text):
    source = ArtifactRef.from_bytes(text.encode(), "orca-out")
    return parse_log_report(text, source)


def runs(text):
    return optimization_runs(report(text))


def validation_log(path):
    fixture = Path(__file__).resolve().parents[1] / "artifacts/public/validation" / path
    return fixture.read_text(encoding="utf-8")


def water_log():
    return validation_log("ORCA-6.1.1-macOS-arm64/optfreq/job.out")


class OptimizationHistoryTests(unittest.TestCase):
    def test_real_water_history_preserves_uphill_step_and_separate_endpoint(self):
        (run,) = runs(water_log())
        self.assertEqual([p.step for p in run.points], [1, 2, 3, 4, None])
        self.assertEqual([p.line for p in run.points], [880, 1317, 1757, 2196, 2941])
        self.assertGreater(run.points[3].energy, run.points[2].energy)
        self.assertEqual(run.points[-1].energy, -76.321268537024)

    def test_job_boundaries_scf_warning_and_restarted_optimization(self):
        histories = runs("COMPOUND JOB 1\nGEOMETRY OPTIMIZATION CYCLE 1\nFINAL SINGLE POINT ENERGY -3\n"
                         "GEOMETRY OPTIMIZATION CYCLE 3\nFINAL SINGLE POINT ENERGY -4\n"
                         "FINAL ENERGY EVALUATION AT THE STATIONARY POINT\nFINAL SINGLE POINT ENERGY -4.1\n"
                         "FINAL SINGLE POINT ENERGY -6\n"
                         "COMPOUND JOB 2\nFINAL SINGLE POINT ENERGY -20\n"
                         "GEOMETRY OPTIMIZATION CYCLE 1\nFINAL SINGLE POINT ENERGY -8\n"
                         "GEOMETRY OPTIMIZATION CYCLE 2\n"
                         "FINAL SINGLE POINT ENERGY -7.9 (Wavefunction not fully converged!)\n"
                         "GEOMETRY OPTIMIZATION CYCLE 1\nFINAL SINGLE POINT ENERGY -11\n")
        self.assertEqual([run.job for run in histories], ["Job 1", "Job 2", "Job 2"])
        self.assertEqual([[p.energy for p in run.points] for run in histories],
                         [[-3., -4., -4.1], [-8., -7.9], [-11.]])
        self.assertEqual([p.step for p in histories[0].points], [1, 3, None])
        self.assertTrue(histories[1].points[1].scf_warning)
        self.assertFalse(histories[1].points[0].scf_warning)

    def test_no_curve_without_a_reported_geometry_cycle_energy(self):
        self.assertEqual(optimization_runs(None), ())
        self.assertEqual(runs(" | 12> GEOMETRY OPTIMIZATION CYCLE 2\nFINAL SINGLE POINT ENERGY -10\n"
                              "GEOMETRY OPTIMIZATION CYCLE 1\nTOTAL SCF ENERGY\n"
                              "Total Energy : -1.2 Eh\n"), ())

    def test_numerical_frequency_displacements_cannot_supply_missing_optimization_energies(self):
        numerical = validation_log("results-0.1.0a12/raman/water.out")
        self.assertEqual(runs(numerical), ())
        # ORCA's default output redirects the displaced SCF details to .lastscf.
        # Include an energy in this excerpt to exercise logs with those details.
        start = numerical.index("ORCA NUMERICAL FREQUENCIES")
        end = numerical.index("<< Calculating gradient on displaced geometry", start)
        frequency = numerical[start:numerical.index("\n", end)] + "\nFINAL SINGLE POINT ENERGY -99\n"
        for missing in ("GEOMETRY OPTIMIZATION CYCLE 2",
                        "*** FINAL ENERGY EVALUATION AT THE STATIONARY POINT ***"):
            with self.subTest(missing=missing):
                parsed = report("GEOMETRY OPTIMIZATION CYCLE 1\nFINAL SINGLE POINT ENERGY -7\n"
                                + missing + "\n" + frequency)
                (curve,) = optimization_runs(parsed)
                self.assertEqual([(p.step, p.energy) for p in curve.points], [(1, -7)])
                (displaced,) = [prop for prop in parsed.properties if prop.value == -99]
                self.assertEqual(displaced.context, "")

    def test_convergence_and_next_task_end_an_unfinished_cycle(self):
        for end in ("*** THE OPTIMIZATION HAS CONVERGED ***", "SCF HESSIAN",
                    "* Single Point Calculation *", "****ORCA TERMINATED NORMALLY****", "$new_job"):
            with self.subTest(end=end):
                text = f"GEOMETRY OPTIMIZATION CYCLE 1\n{end}\nFINAL SINGLE POINT ENERGY -2\n"
                self.assertEqual(runs(text), ())

    def test_old_saved_report_with_repeated_last_cycle_keeps_one_observation(self):
        parsed = report("GEOMETRY OPTIMIZATION CYCLE 1\nFINAL SINGLE POINT ENERGY -2\n"
                        "ORCA NUMERICAL FREQUENCIES\nFINAL SINGLE POINT ENERGY -9\n")
        legacy = replace(parsed, properties=tuple(replace(prop, context="Optimization step 1")
                                                  for prop in parsed.properties))
        (curve,) = optimization_runs(legacy)
        self.assertEqual([(p.step, p.energy) for p in curve.points], [(1, -2)])


@unittest.skipUnless(find_spec("PySide6"), "requires Qt")
class OptimizationCurveUiTests(unittest.TestCase):
    def test_selecting_plot_points_and_switching_units(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from orcaview.gui.optimization_curve import OptimizationCurveDialog
        app = QApplication.instance() or QApplication([])
        dialog = OptimizationCurveDialog(runs(water_log()))
        self.addCleanup(dialog.close)
        dialog.show()
        app.processEvents()
        self.assertEqual(dialog.table.rowCount(), 5)
        locations = dialog.plot.locations
        self.assertEqual(len(locations), 5)
        self.assertGreater(locations[2].y(), locations[3].y())  # Step 4 goes up on screen.
        QTest.mouseClick(dialog.plot, Qt.MouseButton.LeftButton, pos=locations[1].toPoint())
        self.assertEqual(dialog.table.currentRow(), 1)
        self.assertEqual(dialog.table.item(1, 3).text(), "1317")
        dialog.units.setCurrentIndex(1)
        app.processEvents()
        self.assertTrue(dialog.plot.relative)
        self.assertEqual(dialog.table.item(0, 2).text(), "0")
        self.assertFalse(dialog.warning.isVisible())

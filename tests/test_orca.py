'ORCA input syntax and summaries of native and synthetic outputs.'

from pathlib import Path
import unittest

from orcaview.core.models import Atom, CalculationSpec, Molecule
from orcaview.orca.input import render_input
from orcaview.orca.output import parse_output


class InputTests(unittest.TestCase):
    def setUp(self):
        self.molecule = Molecule("helium", (Atom("He", 0, 0, 0),))

    def test_resource_and_geometry_contract(self):
        text = render_input(self.molecule, CalculationSpec(cores=8, maxcore_mb=1500))
        self.assertIn("! B3LYP def2-SVP SP\n", text)
        self.assertIn("%pal\n  nprocs 8\nend\n", text)
        self.assertIn("%maxcore 1500\n", text)
        self.assertIn("* xyz 0 1\n", text)
        self.assertTrue(text.endswith("*\n"))

    def test_job_mapping(self):
        for job_type, keywords in (("SP", "SP"), ("OPT", "Opt"), ("FREQ", "Freq"), ("OPT_FREQ", "Opt Freq")):
            with self.subTest(job_type=job_type):
                text = render_input(self.molecule, CalculationSpec(job_type=job_type))
                self.assertIn(f"! B3LYP def2-SVP {keywords}\n", text)

    def test_electronic_state_invalidates_export(self):
        with self.assertRaises(ValueError):
            render_input(Molecule("H radical", (Atom("H", 0, 0, 0),)), CalculationSpec())


class OutputTests(unittest.TestCase):
    def test_real_orca611_single_jobs_with_compound_author_credit(self):
        archive = Path(__file__).resolve().parents[1] / "artifacts/public/validation/ORCA-6.1.1-macOS-arm64"
        for case, job_type, status, energy in (
            ("pal4", "SP", "completed", -76.332753194122),
            ("optfreq", "OPT_FREQ", "needs_review", -76.321268537024),
        ):
            with self.subTest(case=case):
                summary = parse_output((archive / case / "job.out").read_text(), job_type)
                self.assertEqual(summary.status, status)
                self.assertEqual(summary.final_energy_hartree, energy)
                self.assertFalse(any('multi-job' in warning for warning in summary.warnings))
                if job_type == "OPT_FREQ":
                    self.assertTrue(summary.optimization_converged)
                    self.assertTrue(any('frequenc' in warning for warning in summary.warnings))

    def test_compound_job_headings_and_echoed_directives_need_review(self):
        for marker in (
            "                                COMPOUND JOB MainJOB ",
            "                                COMPOUND JOB  1 ",
            "**** COMPOUND JOB ****",
            "|  8>  %compound",
            "| 20>  $new_job",
        ):
            with self.subTest(marker=marker):
                text = f"{marker}\nSCF CONVERGED AFTER 3 CYCLES\nFINAL SINGLE POINT ENERGY -75\nORCA TERMINATED NORMALLY"
                self.assertEqual(parse_output(text).status, "needs_review")

    def test_absent_evidence_stays_unknown(self):
        summary = parse_output("")
        self.assertFalse(summary.normal_termination)
        self.assertIsNone(summary.scf_converged)
        self.assertIsNone(summary.optimization_converged)
        self.assertIsNone(summary.final_energy_hartree)
        self.assertEqual(summary.status, "incomplete")

    def test_single_point_evidence(self):
        text = "SCF CONVERGED AFTER 12 CYCLES\nFINAL SINGLE POINT ENERGY -75.12345\n**** ORCA TERMINATED NORMALLY ****"
        summary = parse_output(text)
        self.assertTrue(summary.normal_termination)
        self.assertTrue(summary.scf_converged)
        self.assertEqual(summary.final_energy_hartree, -75.12345)
        self.assertEqual(summary.status, "completed")

    def test_normal_termination_is_not_optimization_convergence(self):
        summary = parse_output("ORCA TERMINATED NORMALLY", "OPT")
        self.assertIsNone(summary.optimization_converged)
        self.assertEqual(summary.status, "needs_review")
        self.assertTrue(summary.warnings)

    def test_explicit_nonconvergence_is_preserved(self):
        summary = parse_output("SCF NOT CONVERGED\nTHE OPTIMIZATION HAS NOT CONVERGED\nORCA TERMINATED NORMALLY", "OPT")
        self.assertFalse(summary.scf_converged)
        self.assertFalse(summary.optimization_converged)
        self.assertEqual(summary.status, "unconverged")

    def test_last_energy_and_convergence_evidence(self):
        text = "SCF NOT CONVERGED\nFINAL SINGLE POINT ENERGY -70\nSCF CONVERGED AFTER 4 CYCLES\nFINAL SINGLE POINT ENERGY -7.5D+01\nTHE OPTIMIZATION HAS CONVERGED\nORCA TERMINATED NORMALLY"
        summary = parse_output(text, "OPT")
        self.assertTrue(summary.scf_converged)
        self.assertTrue(summary.optimization_converged)
        self.assertEqual(summary.final_energy_hartree, -75.0)
        self.assertEqual(summary.status, "completed")

    def test_later_scf_failure_overrides_earlier_success(self):
        summary = parse_output("SCF CONVERGED AFTER 3 CYCLES\nSCF DID NOT CONVERGE\nORCA TERMINATED NORMALLY")
        self.assertFalse(summary.scf_converged)
        self.assertEqual(summary.status, "unconverged")

    def test_frequency_is_not_fully_validated(self):
        summary = parse_output("SCF CONVERGED AFTER 3 CYCLES\nFINAL SINGLE POINT ENERGY -75\nORCA TERMINATED NORMALLY", "FREQ")
        self.assertEqual(summary.status, "needs_review")
        self.assertTrue(any('frequenc' in warning for warning in summary.warnings))

    def test_unknown_job_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_output("", "TS")

    def test_overflow_energy_is_not_a_result(self):
        summary = parse_output("SCF CONVERGED AFTER 3 CYCLES\nFINAL SINGLE POINT ENERGY -1E999\nORCA TERMINATED NORMALLY")
        self.assertIsNone(summary.final_energy_hartree)
        self.assertEqual(summary.status, "needs_review")

    def test_multiple_jobs_are_not_claimed_as_validated(self):
        summary = parse_output("SCF CONVERGED AFTER 3 CYCLES\nFINAL SINGLE POINT ENERGY -75\nORCA TERMINATED NORMALLY\nORCA TERMINATED NORMALLY")
        self.assertEqual(summary.status, "needs_review")

    def test_error_after_earlier_normal_termination_is_failed(self):
        text = "SCF CONVERGED AFTER 3 CYCLES\nFINAL SINGLE POINT ENERGY -75\nORCA TERMINATED NORMALLY\nORCA finished by error termination in ORCA_SCF"
        summary = parse_output(text)
        self.assertTrue(summary.normal_termination)
        self.assertEqual(summary.status, "failed")

    def test_multiple_banners_with_unfinished_tail_need_review(self):
        text = "* O   R   C   A *\nSCF CONVERGED AFTER 3 CYCLES\nFINAL SINGLE POINT ENERGY -75\nORCA TERMINATED NORMALLY\n* O   R   C   A *\nSCF ITERATIONS"
        self.assertEqual(parse_output(text).status, "needs_review")

    def test_new_job_without_completion_needs_review(self):
        text = "SCF CONVERGED AFTER 3 CYCLES\nFINAL SINGLE POINT ENERGY -75\nORCA TERMINATED NORMALLY\n$new_job\n"
        self.assertEqual(parse_output(text).status, "needs_review")

    def test_trailing_calculation_without_banner_needs_review(self):
        text = "SCF CONVERGED AFTER 3 CYCLES\nFINAL SINGLE POINT ENERGY -75\nORCA TERMINATED NORMALLY\nSCF ITERATIONS"
        self.assertEqual(parse_output(text).status, "needs_review")


if __name__ == "__main__":
    unittest.main()

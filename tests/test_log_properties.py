"""Source-level regression tests for ordinary ORCA calculation properties."""

from pathlib import Path
import unittest

from orcaview.orca.log_properties import LogProperty, parse_log_properties, property_series_key, ranked_properties


REAL = Path(__file__).resolve().parents[1] / "artifacts" / "public" / "validation" / "ORCA-6.1.1-macOS-arm64"


class LogPropertiesTests(unittest.TestCase):
    def test_real_optfreq_orders_final_geometry_and_reports_thermochemistry(self):
        lines = (REAL / "optfreq" / "job.out").read_text().splitlines()
        props = parse_log_properties(lines)
        self.assertEqual((props[0].label, props[0].value), ('Final single-point energy', -76.321268537024))
        energies = [p for p in props if p.label == 'Final single-point energy']
        self.assertEqual(len(energies), 5)
        self.assertIn('Final', energies[0].context)
        self.assertEqual(len({property_series_key(p) for p in energies}), 1)
        last_by_label = {p.label: p for p in props if p.group == 'Thermochemistry'}
        for name, expected in [('Zero-point vibrational energy ZPE', .02120216), ('Internal energy U', -76.29723107),
                               ('Enthalpy H', -76.29628686), ('Entropy term T·S', .02144408),
                               ('Gibbs free energy G', -76.31773094), ('Gibbs energy correction G−E(el)', .00353759)]:
            prop = last_by_label[name]
            self.assertEqual((prop.value, prop.unit), (expected, "Eh"))
            self.assertIn("298.15 K", prop.context)
            self.assertIn("1 atm", prop.context)
            self.assertIn(f"{expected:.8f}", lines[prop.line-1])
            self.assertLess(props.index(prop), props.index(energies[1]))

    def test_dipole_retains_distinct_densities_and_original_axes(self):
        lines = (REAL / "eom" / "job.out").read_text().splitlines()
        props = parse_log_properties(lines)
        mu = [p for p in props if p.label == 'Dipole magnitude']
        self.assertEqual({p.value for p in mu}, {2.133130098, 2.017258167})
        self.assertEqual(len({property_series_key(p) for p in mu}), 2)
        for p in mu:
            self.assertEqual(p.unit, "Debye")
            self.assertIn("Magnitude (Debye)", lines[p.line-1])
            components = [q for q in props if q.context == p.context and q.label in ('Dipole moment X', 'Dipole moment Y', 'Dipole moment Z')]
            self.assertEqual(len(components), 3)
            self.assertTrue(all(q.unit == "a.u." and "Total Dipole Moment" in lines[q.line-1] for q in components))
        self.assertEqual(next(p.value for p in props if p.label == 'Coupled-cluster correlation energy'), -.210815426)
        self.assertEqual(next(p.value for p in props if p.label == 'T1 diagnostic'), .005958523)

    def test_solvent_terms_and_correlated_energies_are_distinct(self):
        result = parse_log_properties((REAL / "smd" / "job.out").read_text())
        self.assertEqual({p.label: p.value for p in result if p.group == 'Solvation'},
                         {'CPCM dielectric energy': -.01599948544432, 'SMD nonelectrostatic CDS term': .00230091695023})
        ri = parse_log_properties((REAL / "rimp2" / "job.out").read_text())
        self.assertEqual(next(p.value for p in ri if p.label == 'RI-MP2 correlation energy'), -.193642659)
        self.assertEqual(next(p.value for p in ri if p.label == "HOMO"), -13.5477)
        self.assertAlmostEqual(next(p.value for p in ri if p.label == 'HOMO–LUMO gap'), 18.3365)

    def test_real_raman_cartesian_polarizability_and_rotational_constants(self):
        path = REAL.parent / "results-0.1.0a12" / "raman" / "water.out"
        lines = path.read_text().splitlines()
        props = parse_log_properties(lines)
        polar = {p.label:p for p in props if p.group == 'Static polarizability'}
        self.assertEqual(len(polar), 10)
        self.assertEqual(polar['Isotropic static polarizability'].value, 4.93117)
        self.assertEqual([polar[f"Static polarizability α{axis}{axis}"].value for axis in "XYZ"],
                         [6.827456281, 2.980906466, 4.985150303])
        for p in polar.values():
            self.assertEqual(p.unit, "a.u.")
            self.assertIn("SCF", p.context)
            source = lines[p.line-1]
            if p.label.startswith('Static polarizability α'):
                self.assertEqual(p.value, float(source.split()["XYZ".index(p.label[-1])]))
            else:
                self.assertIn("Isotropic polarizability", source)
        rotational_a = [p for p in props if p.label == 'Rotational constant A']
        self.assertEqual(len({property_series_key(p) for p in rotational_a}), 3)
        self.assertEqual({(p.value,p.unit) for p in rotational_a},
                         {(820486.379297,"MHz"), (27.368480,"cm⁻¹"), (27.368503,"cm⁻¹")})
        self.assertTrue(all("Rotational constants in" in lines[p.line-1] for p in rotational_a))
        truncated = """STATIC POLARIZABILITY TENSOR (Dipole/Dipole)
The raw cartesian tensor (atomic units):
1 0 0
0 2 0
diagonalized tensor:
9 9 9"""
        self.assertEqual(parse_log_properties(truncated), ())

    def test_unrestricted_spin_tables_with_irreps_and_partial_blocks(self):
        text = """ORBITAL ENERGIES
---------
SPIN UP ORBITALS
 NO OCC E(Eh) E(eV) Irrep
  0 1 -0.5 -13.60 1-A
  1 0  0.1   2.72 2-A

SPIN DOWN ORBITALS
 NO OCC E(Eh) E(eV) Irrep
  0 1 -0.4 -10.88 1-A
  1 0  0.2   5.44 2-A"""
        props = parse_log_properties(text)
        self.assertEqual({p.context:p.value for p in props if p.label == "HOMO"}, {'α spin':-13.6, 'β spin':-10.88})
        self.assertTrue(all(p.unit == "eV" for p in props))
        self.assertTrue(all(p.line in (5, 6, 10, 11) for p in props))
        # An absent virtual row, a gap in MO indexes, fractional occupations, and a non-Aufbau
        # electron distribution each prevent a conventional frontier claim for that spin table.
        for errors in ["  0 2 -.5 -13.6", "  0 2 -.5 -13.6\n2 0 .1 2.72",
                       "0 .5 -.5 -13.6\n1 .5 .1 2.72", "0 0 -.5 -13.6\n1 1 .1 2.72",
                       "0 2 -.5 -13.6\n1 0 .1 1e999", "0 2 -.5 -13.6\n1 0 .1 #"]:
            with self.subTest(errors=errors):
                self.assertEqual(parse_log_properties("ORBITAL ENERGIES\nNO OCC E(Eh) E(eV)\n" + errors), ())

    def test_echoes_unrelated_blocks_and_malformed_numbers_do_not_create_values(self):
        lines = ["| 4> FINAL SINGLE POINT ENERGY -999", "# FINAL SINGLE POINT ENERGY -3",
                 "Total Energy : -50 Eh", "Magnitude (Debye) : 3", "FINAL SINGLE POINT ENERGY 5.0blah",
                 "FINAL SINGLE POINT ENERGY 1e999", "FINAL SINGLE POINT ENERGY -3 eV",
                 "THERMOCHEMISTRY AT 298.15 K", "GIBBS FREE ENERGY", "Final Gibbs free energy ... 8 kcal/mol"]
        self.assertEqual(parse_log_properties(lines), ())
        values = parse_log_properties(["DIPOLE MOMENT", "Method : SCF", "Total Dipole Moment : 0 0",
                                       "DIPOLE MOMENT", "Method : MDCI", "Magnitude (Debye) : 1.5"])
        self.assertEqual(len(values), 1)
        self.assertEqual((values[0].value, values[0].context, values[0].line), (1.5, "MDCI", 6))

    def test_multiple_temperatures_and_series_identity(self):
        lines = []
        for temp, energy in ((273.15, -1.0), (398.15, -2.0)):
            lines.extend([f"THERMOCHEMISTRY AT {temp}K", "Pressure ... 1.00 atm", "GIBBS FREE ENERGY",
                          f"Final Gibbs free energy ... {energy} Eh"])
        props = parse_log_properties(lines)
        self.assertEqual(len(props), 2)
        self.assertEqual(len({property_series_key(p) for p in props}), 2)
        p = LogProperty('Frontier orbitals', "HOMO", -1, "eV", 222, 'Compound job 2 · Optimization step 3 · β spin')
        self.assertEqual(property_series_key(p), ('Frontier orbitals', "HOMO", 'Compound job 2 · β spin'))

    def test_compound_job_ranking_uses_source_line_instead_of_input_order(self):
        early = LogProperty('Electronic energy', 'Final single-point energy', -1, "Eh", 10, 'Job 1 · Optimization step 1')
        final = LogProperty('Electronic energy', 'Final single-point energy', -2, "Eh", 20, 'Job 1 · Final optimization energy evaluation')
        other = LogProperty('Electronic energy', 'Final single-point energy', -3, "Eh", 50, 'Job 2')
        gibbs = LogProperty('Thermochemistry', 'Gibbs free energy G', -1.5, "Eh", 30, 'Job 1 · 298.15 K')
        self.assertEqual(ranked_properties(iter((other, final, gibbs, early))), (other, final, gibbs, early))

    def test_explicit_nonconvergence_and_fortran_exponents(self):
        lines = ["FINAL SINGLE POINT ENERGY -1.5D+01 (Wavefunction not fully converged!)",
                 "Expectation value of <S**2> : 0.752", "Edisp/kcal,au: -0.5 -0.0008"]
        props = parse_log_properties(lines)
        self.assertEqual([(p.value, p.unit) for p in props], [(-15, "Eh"), (.752, "ℏ²"), (-.0008, "Eh")])
        self.assertIn('not fully converged', props[0].context)


if __name__ == "__main__":
    unittest.main()

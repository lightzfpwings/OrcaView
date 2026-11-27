# OrcaView release validation

## 0.1.0a76

**Orbital files.** ORCA 6.1.1 generated GBW, QRO, UCO, UNO and UNSO files for the hydroxyl radical as well as localized orbitals and MP2 and CCSD natural orbitals for water. For all eight inputs, the built-in converter agreed with the matching official converter to within 5.1 × 10⁻¹³ in the orbital coefficients. Occupations matched to the precision of the official Molden output. The 24 MP2 and 24 CCSD natural occupations also agreed with all digits printed in the ORCA logs. [Hydroxyl input](../examples/orbitals/OH.inp) · [UNO example](../examples/orbitals/OH.uno.molden.input) · [UNSO example](../examples/orbitals/OH.unso.molden.input)

**Orbital composition.** On all 24 water orbitals, Mulliken, Löwdin and NAO results summed by atom and angular momentum agreed with independent PySCF 2.12.1 calculations within 10⁻¹⁰ percentage points. For hydroxyl UNO 2, a separate PySCF grid with 100 radial points and 590 Lebedev angular points per atom reproduced the Becke and Hirshfeld atomic shares to within 0.001 percentage points, using the same radii and reference densities. The oxygen p contribution by NAO is 69.570%. [Numerical regression tests](../tests/test_natural_orbitals.py) · [Decomposition methods](ORBITALS.md#orbital-decomposition)

**Desktop and packages.** The native macOS interface was exercised through the conversion dialog, orbital selection, method switching and project reopening. Six real-valued input files (QRO, UCO, UNSO, localized orbitals, MP2 and CCSD natural orbitals) produced pixel-identical screenshots from the checkout and the macOS executable. The Windows and Linux packages include all 29 examples and the same atomic reference data. The release workflow runs the downloaded packages and orbital tests on macOS, Windows and Ubuntu. [Desktop tests](../tests/test_orbital_workspace.py) · [Release workflow](../.github/workflows/release-extensions.yml)

Run the 821 regression tests from the repository root with `python tools/run_tests.py`. The suite uses the versioned [test sources](../tests/) and [public ORCA reference outputs](../artifacts/public/validation/). The [fixture manifest](../artifacts/public/validation/public-fixtures.json) identifies the original and public SHA-256 digests.

See [validation through a75](history/validation-a24-a75.md) for earlier releases.

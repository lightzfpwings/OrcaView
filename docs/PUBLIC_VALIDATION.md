# OrcaView release validation

## 0.1.0a78

**Orbital surfaces.** A synthetic Molden wavefunction combines two compact Gaussians near one another with a distant diffuse fragment. The standard, smooth and best grids resolve the compact lobe to within 0.008 Å of its analytic radius. The test counts two incident faces on every mesh edge and checks that the three settings progressively increase the number of vertices on the lobe. [Gaussian surface tests](../tests/test_molden_orbitals.py) · [Cube surface tests](../tests/test_cube_orbitals.py)

**Molecular depth.** A plane passing through an atom sphere and an inclined bond tests both visible and hidden regions. The CPU renderer and vector painter check the same points at two display scales. The test also runs on hardware when available. The native Apple Silicon check exercised the Metal renderer. [Rendering and workspace tests](../tests/test_orbital_workspace.py)

**Decomposition layout.** The method and grouping sit below the orbital list, with contributions to the right of the surface. The OH example was checked in English, German, Japanese, Simplified Chinese and Traditional Chinese at three window sizes. Its orbital 2 oxygen p contribution by NAO is 69.570%. [Example wavefunction](../examples/orbitals/OH.uno.molden.input) · [Workspace screenshot](images/orbital-decomposition-zh-Hans.png)

Run the 824 regression tests from the repository root with `python tools/run_tests.py`. The [release workflow](../.github/workflows/release-extensions.yml) checks the published packages on macOS, Windows and Ubuntu. The [fixture manifest](../artifacts/public/validation/public-fixtures.json) records the SHA-256 digests of the public ORCA reference outputs.

## 0.1.0a76

The [a76 validation record](history/validation-a76.md) covers agreement with ORCA's converters, comparison with PySCF and packaged orbital analysis. Earlier checks are in the [validation history through a75](history/validation-a24-a75.md).

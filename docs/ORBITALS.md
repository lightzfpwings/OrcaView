# Orbital sets and composition

Open an ORCA orbital file, then choose **Convert and open**. OrcaView reads real, spherical-basis ORCA 6.1.1 files with its built-in converter. Each set gets its own Molden file, e.g. `job.molden.input`, `job.uno.molden.input` and `job.unso.molden.input`. An existing file can be reopened or explicitly replaced. The converted file records the orbital type and can be moved or renamed. For a different ORCA binary layout, **Browse…** selects a matching official converter. [ORCA wavefunction types](https://www.faccts.de/docs/orca/6.1/manual/contents/modelchemistries/hftype.html) · [ORCA converters](https://www.faccts.de/docs/orca/6.1/manual/contents/utilitiesvisualization/utilities.html)

| Source | Orbitals and occupations shown |
| --- | --- |
| `.gbw` | File orbitals with energies, occupations and separate spin channels when present. A complete orbital set also offers natural orbitals of the total density. |
| `.uno` | ORCA's unrestricted natural orbitals with their fractional occupations. |
| `.unso` | Natural orbitals of the spin density. Occupations retain their sign and sum to the spin-density trace. |
| `.uco` | Natural orbitals of the spin-summed density by default. The orbital-set menu also exposes the original alpha and beta corresponding orbitals. |
| `.qro` | Natural orbitals of the density encoded in the QRO file. Use the orbital-set menu for the original QROs and their quasi-restricted energies. Open the companion UNO to recover the original unrestricted fractional occupations. |
| `.loc`, `.loc.gbw` | Natural orbitals of the supplied density, with the localized orbital set available in the same menu. |
| `.nat`, `.mp2nat`, `.mdcinat` | The natural orbitals and occupation eigenvalues saved by the electronic-structure calculation. |

Select an orbital to draw both phases of its wavefunction. The orbital and atom indices in this panel start at zero, following ORCA. The sign of an isosurface represents orbital phase. The sign of an UNSO occupation is a separate property of the spin density. An UNSO file alone supplies no total electronic charge. Check the charge and multiplicity before reusing that geometry for an ORCA input. Within a subspace of equal occupation, several choices of natural orbitals give the same density.

## Orbital decomposition

Expand **Orbital decomposition** below the orbital list. Selecting another orbital updates the contributions and the surface together. Each percentage is the share of the selected orbital under the chosen method. The value is independent of the isovalue used to draw the surface.

| Methods | Definition and grouping |
| --- | --- |
| Mulliken | Splits overlap terms equally between the two basis functions. Group by atom, by angular momentum (s, p, d, f, g, h), or by both. |
| Löwdin | Squared projections onto symmetrically orthogonalized basis functions. Offers the same three groupings. |
| Ros–Schuit (SCPA) | Squared AO coefficients normalized to their sum. Offers all three groupings. |
| Stout–Politzer, Bickelhaupt | Split overlap terms using local squared coefficients of the selected orbital or occupation-weighted coefficients across the electron-density set, respectively. Both offer all three groupings. |
| Natural atomic orbitals (NAO) | Projects onto orthonormal atomic orbitals obtained from the total density, including core, valence and Rydberg functions. Requires known effective charges and spherical d and higher shells. Offers all three groupings. |
| Hirshfeld | Integrates the squared orbital amplitude using stockholder weights from spherical neutral-atom reference densities (H through Lr). Reports atomic shares. |
| Becke | Integrates the squared orbital amplitude over size-adjusted, overlapping atomic regions. Reports atomic shares. |

Overlap-based analyses can report signed atomic or shell contributions. Bickelhaupt and NAO require the complete electron-density set. Wavefunction-based real-space integrals are checked against the analytic orbital norm and successive grid refinements. Each method runs offline. [Population and orbital-composition definitions, Multiwfn manual §§3.9–3.10](https://web.mit.edu/multiwfn_v3.4/Manual_3.4.pdf) · [NAO construction in PySCF](https://pyscf.org/_modules/pyscf/lo/nao.html) · [Hirshfeld reference data](https://doi.org/10.5281/zenodo.21291022)

For an orbital-amplitude **Cube**, select a dataset and confirm **This Cube field is an orbital amplitude**. Becke and Hirshfeld report atomic shares of the squared amplitude within that grid. Cube coordinates and field values alone supply neither AO coefficients nor occupation numbers.

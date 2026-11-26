# OrcaView

OrcaView is a desktop and command-line workbench for ORCA. It connects molecular design, input preparation and analysis of calculation outputs. An energy can be traced to its optimization step and log line, and an atomic property can be displayed on the geometry to which it belongs.

**OrcaView 0.1.0a63** is an alpha release targeting ORCA 6.1.1. [Release notes and downloads](https://github.com/lightzfpwings/OrcaView/releases/tag/v0.1.0a63)

## Install

| Platform | Package | Launch |
| --- | --- | --- |
| Windows x64 | [Portable ZIP](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/OrcaView-0.1.0a63-Windows-x64-portable.zip) | Extract into a dedicated folder and open `OrcaView.exe`. |
| macOS on Apple Silicon | [Disk image](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/OrcaView-0.1.0a63.macOS-arm64.dmg) | Drag `OrcaView.app` into Applications. Copy `Examples/` to a writable folder. |
| Linux x86-64 | [Portable tar.gz](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/OrcaView-0.1.0a63-Linux-x86_64.tar.gz) | Extract and run `./OrcaView` from the extracted folder on a graphical desktop. |

All three packages include Python, Qt, Open Babel and 21 example files. Drawing structures, generating inputs and reading existing results work offline. Running a new calculation requires a separate ORCA installation. The local job runner supports macOS and Linux. The macOS app uses an ad hoc signature. [SHA-256 checksums](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/SHA256UMS.txt) · [macOS opening instructions](https://support.apple.com/en-us/102445)

English is built in. The language pack adds German, Japanese, Simplified Chinese and Traditional Chinese. The color pack provides Contrast, Pastel and Grayscale element palettes. [Language pack](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/OrcaView-Extensions-01-Language-0.1.0a63.zip) · [Color pack](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/OrcaView-Extensions-02-Color-0.1.0a63.zip) · [Installation and authoring](docs/extensions/README.md)

## Molecular structures and geometry

- **Structure import.** Read molecular coordinates and connectivity from XYZ and extended XYZ, MOL/SDF, MOL2, PDB, SMILES and InChI. Extract geometries from supported ORCA, Gaussian, Q-Chem and NWChem inputs, and from Molden, formatted checkpoint and other supported wavefunction files. ORCA GBW import uses the external `orca_2mkl` utility. CIF and VASP structures with a periodic cell can be imported as finite structures.
- **Sketching and measurement.** Build and edit molecules in linked 2D and 3D views. Add atoms, hydrogens and ring templates, edit bond orders and stereochemical or coordination bonds, and select individual atoms or groups. Edit Cartesian coordinates and bond lengths, measure distances, angles and dihedrals, and inspect the estimated point group and principal axis. Cleaning up a 2D sketch preserves the Cartesian geometry used for the calculation.
- **Complexes and pre-optimization.** Rotate, translate, copy and paste individual molecules while preserving their internal geometry. Mark intra- or intermolecular hydrogen bonds between an explicit hydrogen and an acceptor. Open Babel provides MMFF94 or UFF pre-optimization for supported neutral singlets, with optional distance and angle restraints on marked hydrogen bonds. Fragment edits and pre-optimization can be undone and redone. [Molecular design guide](docs/CLI_DESIGN.md)

## ORCA inputs and local calculations

- **Methods and jobs.** The a63 catalog contains 568 named presets in 45 method families and 417 selectable orbital basis sets. It covers Hartree–Fock and DFT, semiempirical and tight-binding methods, perturbation theory, coupled cluster, multireference methods and excited states. Available job types depend on the method and include single points, geometry and transition-state optimization, frequencies, combined optimization and frequencies, and intrinsic reaction coordinates. [Method catalog and job coverage](docs/ORCA_METHODS.md)
- **Calculation settings.** Set charge, multiplicity, reference wavefunction, orbital and auxiliary basis sets, integral approximations, dispersion, solvation, SCF convergence, process count and memory per process. Method-specific controls expose active spaces, excited-state roots and local-correlation thresholds where applicable. Advanced input blocks expose additional settings for the selected method and job.
- **Input editing.** The editable ORCA preview keeps supported single-job keywords, coordinates and panel settings in sync. The editor reports entries it cannot map to the panel. A separate native input editor can open, edit and save custom decks. The manual index locates ORCA 6.1.1 sections by topic or keyword.
- **Local execution.** On macOS and Linux, the command-line runner stages a fixed copy of the input and its companion files in a separate directory for each attempt. It runs a user-supplied ORCA executable and records output and execution status. It supports time limits and cancellation. Resource inspection reports processor and memory limits and recommended settings for the host. [Execution and resource options](docs/CLI.md)

## Calculation results and atomic properties

- **Output inspection.** Read ORCA logs and outputs to inspect job context, termination status, reported coordinates and scalar properties. Repeated observations retain their units, job or optimization step and source line. Recognized properties include SCF, final and selected correlation energies, the T1 diagnostic, frontier orbital energies and gaps, dipole moments, static polarizabilities, rotational constants, thermochemical quantities and selected solvation terms. A log can be inspected even when it has no usable molecular geometry. [ORCA output coverage](docs/ORCA_LOG_COVERAGE.md)
- **Atomic populations.** Display atom-resolved electron populations, spin populations and charges for the Mulliken, Löwdin, Hirshfeld and MBIS analyses available in the output, plus CHELPG fitted charges. Each dataset retains its atom identities, geometry and source records. Numeric labels and atom coloring can be enabled separately, with an optional scale legend.
- **Color scales.** Choose red–white–blue, blue–white–red, rainbow or black–white. Edit or reverse colors, set decimal precision and choose automatic, zero-symmetric or manual limits with an adjustable midpoint. Reusable presets let several structures share the same scale. [Results and data export](docs/CLI_RESULTS.md)

## Vibrational, electronic and NMR spectra

- **Vibrational and electronic spectra.** Inspect mode frequencies, IR intensities and Raman activities. Plot UV/visible absorption from oscillator strengths and circular dichroism from signed rotatory strengths. Choose a printed table when the output contains multiple spectra. Optical plots support wavelength, electronvolts and wavenumbers.
- **Line shapes and axes.** Show sticks, a broadened curve or both. Controls include Gaussian, Lorentzian and pseudo-Voigt profiles, width, sampling density, normalization, axis range and direction. Numerical exports include the original table, stick positions and strengths, or the sampled curve.
- **NMR.** Inspect isotropic shielding and anisotropy by nucleus. Plot one element at a time on an absolute shielding scale, or supply a reference shielding to obtain chemical shifts. Coincident signals are weighted by the number of nuclei. The one-dimensional profile represents uncoupled sites. Printed spin–spin couplings are available separately as signed J values by atom pair in hertz. [Spectral data and plotting options](docs/CLI_RESULTS.md#spectra)

## Projects, figures and batch processing

- **Project history.** A project preserves calculation settings, geometry revisions, atom identities, bonds, the independent 2D sketch, imported result datasets and source records. Saved revisions and result geometries can be brought back into the editor for further work. A project whose history contains hydrogen-bond annotations requires a63 or later.
- **Structure and spectrum figures.** Choose ball-and-stick, space-filling, stick or wireframe models, adjust atom and bond sizes, and control labels, element colors and viewing orientation. Export a 2D sketch, 3D view or spectrum as PNG, JPEG, BMP or vector PDF. Structure export also offers image size, framing and transparent-background settings.
- **Command line.** Create or convert projects, export XYZ, apply sequences of geometry edits, generate ORCA inputs, run local jobs and read results in batch. JSON preserves dataset metadata and source records. CSV and TSV expose coordinates, atomic values and property series for downstream analysis. Offscreen rendering produces structure figures and spectrum PNGs on machines with the Qt rendering dependencies. [Batch commands](docs/CLI.md) · [Design operations](docs/CLI_DESIGN.md) · [Result formats](docs/CLI_RESULTS.md)

## Source and validation

The core and CLI support Python 3.9 and later. In a virtual environment, run the following commands from the repository root.

```sh
python -m pip install -e ".[gui]"
python -m orcaview gui
python tools/run_tests.py -q
```

The regression suite combines the archived test set with tests in this checkout. The validation record includes reference ORCA 6.1.1 outputs and package checks for individual releases. Desktop builds use CPython 3.13. Windows packaging requires Go 1.23 or later. On Apple Silicon, install PyInstaller 6.22.3 and run `python packaging/macos/build.py`. [Validation record](docs/PUBLIC_VALIDATION.md) · [Linux and Windows build instructions](packaging/desktop/README.md) · [Batch CLI guide](docs/CLI.md)

Use **Help → Check for Updates…** for subsequent releases. On macOS, versions through 0.1.0a55 require a one-time manual replacement from the DMG. On Windows, versions through 0.1.0a42 require a one-time manual installation of the single-file package.

For a paper using OrcaView, cite the software version used to prepare the inputs or figures and report the ORCA version and electronic-structure settings for the calculation. [Software citation](CITATION.cff)

OrcaView is distributed under the MIT license. Bundled third-party libraries have their own licenses. [License](LICENSE) · [Third-party notices and sources](THIRD_PARTY_NOTICES.md)

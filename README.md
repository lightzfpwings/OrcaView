# OrcaView

OrcaView is a desktop application and command-line interface for building molecular structures, preparing ORCA inputs and analyzing calculation results. It can display properties from an ORCA output alongside the geometry and log lines they came from.

**Version 0.1.0a63** adds independent rotation, translation and copying of molecules in a complex, plus hydrogen-bond restraints for geometry pre-optimization. [Release notes](https://github.com/lightzfpwings/OrcaView/releases/tag/v0.1.0a63)

## Install

| Platform | Package | Launch |
| --- | --- | --- |
| Windows x64 | [Portable ZIP](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/OrcaView-0.1.0a63-Windows-x64-portable.zip) | Extract into a dedicated folder and open `OrcaView.exe`. |
| macOS on Apple Silicon | [Disk image](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/OrcaView-0.1.0a63.macOS-arm64.dmg) | Drag `OrcaView.app` into Applications. Copy `Examples/` to a writable folder. |
| Linux x86-64 | [Portable tar.gz](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/OrcaView-0.1.0a63-Linux-x86_64.tar.gz) | Extract and run `./OrcaView` from the extracted folder on a graphical desktop. |

All three packages include Python, Qt, Open Babel and 21 example files. Drawing structures, generating inputs and reading existing results work offline. Running a new calculation requires a separate ORCA installation. The local job runner supports macOS and Linux. The macOS app uses an ad hoc signature. [SHA-256 checksums](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/SHA256UMS.txt) · [macOS opening instructions](https://support.apple.com/en-us/102445)

English is built in. The language pack adds German, Japanese, Simplified Chinese and Traditional Chinese. The color pack provides Contrast, Pastel and Grayscale element palettes. [Language pack](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/OrcaView-Extensions-01-Language-0.1.0a63.zip) · [Color pack](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a63/OrcaView-Extensions-02-Color-0.1.0a63.zip) · [Installation and authoring](docs/extensions/README.md)

## Molecular design and calculation setup

- **Structure editing.** Import XYZ, MOL/SDF, PDB and other formats, or build a molecule in the 2D sketch. Add atoms, bonds, rings and hydrogens, inspect the 3D geometry and pre-optimize it with MMFF94 or UFF. [Design guide](docs/CLI_DESIGN.md)
- **Molecular complexes.** Select an atom and hold Alt (Option on macOS). Drag with the left button to rotate its molecule or the right button to translate it. Ctrl+C and Ctrl+V (⌘C and ⌘V on macOS) copy and paste the whole molecule.
- **Hydrogen bonds.** Mark an explicit hydrogen and its acceptor, then set the target H···A distance and D–H···A angle for pre-optimization of a neutral singlet. Projects with hydrogen-bond annotations in their history require OrcaView 0.1.0a63 or later.
- **ORCA input.** Choose the method, basis set, charge and multiplicity in the calculation panel, or edit the input directly and press Tab to apply it. The editor supports simple keywords such as `MiniPrint` and `NoAutoStart` as well as ORCA input blocks. [Supported methods and input blocks](docs/ORCA_METHODS.md) · [Example inputs](examples/native_methods/)

## Results and analysis

- **Geometry and energy.** Review optimization steps, inspect molecular coordinates and trace each reported energy to its line in the original output. [Water optimization example](artifacts/public/validation/ORCA-6.1.1-macOS-arm64/optfreq/)
- **Atomic populations.** Display electron or spin populations and atomic charges as atom labels or colors. Choose among the analyses present in the log, including Mulliken, Löwdin, Hirshfeld and MBIS. Set color limits and a midpoint to compare structures on the same scale. The bundled hydroxyl radical example gives Mulliken spin populations of +1.024339 on O and −0.024339 on H. [Example output](examples/populations/hydroxyl.out) · [Population definitions](docs/ORCA_LOG_COVERAGE.md)
- **Vibrational and electronic spectra.** Plot IR, Raman, UV/Vis and circular dichroism spectra. Adjust units, broadening and stick overlays, export numerical data as CSV, or save a plot as PNG, JPEG, BMP or vector PDF. [Spectrum and export commands](docs/CLI_RESULTS.md)
- **NMR.** Plot shieldings by element, supply a reference shielding to obtain chemical shifts, or inspect signed spin–spin coupling constants by atom pair. In the bundled water example, two equivalent protons contribute to a single shielding peak at 31.130 ppm. [Water NMR output](artifacts/public/validation/results-0.1.0a12/nmr/water-shield.out)

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

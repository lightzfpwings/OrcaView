# Linux and Windows portable builds

Run this from the repository root with CPython 3.13. Windows builds require Go 1.23 or later on PATH. The launcher uses only the Go standard library and is cross-compiled for Windows x64. The build verifies the checksums of the target-native Python, Qt, Shiboken, Open Babel, imageio-ffmpeg, NumPy and WebGPU distributions before assembly.

```shell
python3.13 packaging/desktop/build.py both
```

Use `linux` or `windows` for a single target. Pass `--cache <directory>` to reuse verified downloads. Finished packages are in `dist/<platform>/<version>/`. Each package includes an English interface and examples in `Examples/`. Open the Molden wavefunctions or the water HOMO Cube in `Examples/Orbitals/` to use the Orbitals tab. The bundled FFmpeg executable exports vibrational modes from `water-opt-freq.out` as animated GIF or H.264 MP4.

Build both optional extensions with `python packaging/build_extension_kit.py` from an environment with Qt 6.8.3. Run `python packaging/build_encoder_sources.py` to assemble the FFmpeg source materials in `dist/sources/<version>/`. Once all three platform builds, the extensions and the source archive are present, run `python packaging/stage_release.py` to collect the downloads and their SHA-256 manifest.

- **Windows x64**. Extract the ZIP into a dedicated folder. Its contents are `OrcaView.exe`, `LICENSE` and `Examples`. Double-click the EXE or run `.\OrcaView.exe --version`. Each launch expands the embedded runtime into a private temporary directory and removes it on normal exit.
- **Linux x86-64**. Extract the tarball and launch `./OrcaView` on a graphical desktop. Qt requires glibc 2.28 or newer and desktop libraries including `libxcb-cursor0` and `libxkbcommon-x11-0` on Debian/Ubuntu. Run `./OrcaView --version` to check the launcher. The runtime contains the required third-party notices.

The runtime includes licenses and source references for the bundled dependencies. The app can process structures, prepare input and import results on both platforms. The local ORCA job runner uses POSIX process control. [Third-party notices and sources](../../THIRD_PARTY_NOTICES.md)

# Linux and Windows portable builds

Run this from the repository root with CPython 3.13. Windows builds require Go 1.23 or later on PATH. The launcher uses only the Go standard library and is cross-compiled for Windows x64. The build verifies the checksums of the target-native Python, Qt, Shiboken and Open Babel distributions before assembly.

```shell
python3.13 packaging/desktop/build.py both
```

Use `linux` or `windows` for a single target. Pass `--cache <directory>` to reuse verified downloads. Finished packages are in `dist/<platform>/<version>/`. Each a61 package includes an English interface and 21 files in `Examples/`. Build both optional extensions with `python packaging/build_extension_kit.py` from an environment with Qt 6.8.3. Once all three platform builds and the extensions are present, run `python packaging/stage_release.py` to collect the downloads and their SHA-256 manifest.

- **Windows x64**. Extract the ZIP into a dedicated folder. Its contents are `OrcaView.exe`, `LICENSE` and `Examples`. Double-click the EXE or run `.\OrcaView.exe --version`. Each launch expands the embedded runtime into a private temporary directory and removes it on normal exit.
- **Linux x86-64**. Extract the tarball and launch `./OrcaView` on a graphical desktop. Qt requires glibc 2.28 or newer and desktop libraries including `libxcb-cursor0` and `libxkbcommon-x11-0` on Debian/Ubuntu. Run `./OrcaView --version` to check the launcher. The runtime contains the required third-party notices.

The runtime includes a link to the shared [third-party source and notice bundle](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a43/OrcaView-0.1.0a43-third-party-sources.zip). The app can process structures, prepare input and import results on both platforms. The local ORCA job runner uses POSIX process control.

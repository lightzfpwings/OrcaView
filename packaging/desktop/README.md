# Linux and Windows portable builds

Run this from the repository root with CPython 3.13. Windows builds require Go 1.23 or later on PATH. The launcher uses only the Go standard library and is cross-compiled for Windows x64. The build verifies the checksums of the target-native Python, Qt, Shiboken and Open Babel distributions before assembly.

```shell
python3.13 packaging/desktop/build.py both
```

Use `linux` or `windows` for a single target. Pass `--cache <directory>` to reuse verified downloads. Finished packages are in `dist/<platform>/<version>/`. Each includes an English interface and 20 files in `Examples`. Build optional interface extensions with `python packaging/build_language_packs.py` from an environment with Qt 6.8.3.

- **Windows x64**. Extract the ZIP into a dedicated folder. Its contents are `OrcaView.exe`, `LICENSE` and `Examples`. Double-click the EXE or run `.\OrcaView.exe --version`. Each launch expands the embedded runtime into a private temporary directory and removes it on normal exit.
- **Linux x86-64**. Extract the tarball and launch `./OrcaView` on a graphical desktop. Qt requires glibc 2.28 or newer and desktop libraries including `libxcb-cursor0` and `libxkbcommon-x11-0` on Debian/Ubuntu. Run `./OrcaView --version` to check the launcher. The runtime contains the required third-party notices.

The source and notice attachment on the release page provides the corresponding third-party sources. The app can process structures, prepare input and import results on both platforms. The local ORCA job runner uses POSIX process control.

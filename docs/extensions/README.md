# Language and element color extensions

OrcaView reads UTF-8 JSON on macOS, Windows and Linux. The release includes language ZIPs ready to extract, an importable Contrast color pack and an extension kit for authors. The kit contains the two schemas, an editable English message catalog in `languages/en-GB.json` and a working palette in `colors/contrast.json`.

## Interface languages

Extract one or more language ZIPs into the same folder. In **View → Interface language…**, choose this folder, reload the list, select a language and save. Restart the desktop app to load it. The command line uses the same preferences.

```sh
orcaview settings language --directory ./languages --locale zh-Hans
orcaview settings language
orcaview settings language --locale en
```

To create a language, give your JSON file a distinct locale and a display name. Map OrcaView's English messages to their translations. For example, this file changes two labels.

```json
{
  "locale": "fr",
  "name": "Français",
  "messages": {
    "Project navigation": "Navigation du projet",
    "Results for {source}": "Résultats pour {source}"
  }
}
```

Keep one JSON file per locale at the top level of the chosen folder. Omitted messages use English. OrcaView reserves `en` for its built-in interface. Keep source keys, punctuation and format fields intact, including their conversions and numeric formats. Fields can move in the translation. The loader reports invalid files in the language dialog and in the CLI's `invalid_files` output. The catalog and schemas in the kit are kept in separate locations so that only language files are discovered.

An optional `qtbase_<locale>.qm` alongside the JSON translates Qt's standard controls. The current builds use Qt 6.8.3. For Simplified and Traditional Chinese the filenames are `qtbase_zh_CN.qm` and `qtbase_zh_TW.qm`. The official ZIPs include the matching files. [Language file schema](language-pack.schema.json)

## Element colors

Choose **View → Molecular appearance… → Import color pack…**, select the JSON file and save. OrcaView keeps a personal copy and applies it to the current structure. Import a revised file with the same ID to update that palette. Select **OrcaView default** to restore the built-in colors.

```json
{
  "id": "violet-carbon",
  "name": "Violet carbon",
  "colors": {"C": "#8049A8"}
}
```

List only the elements you want to change. Other elements keep their colors in each view. IDs start with a lowercase ASCII letter and can contain up to 48 lowercase letters, digits, hyphens or underscores. The built-in palette reserves `default`. Use a printable display name of 1–80 characters after trimming, and a file of up to 64 KiB. Element symbols and six-digit RGB values accept either case. A symbol may appear only once.

```sh
orcaview settings appearance --import-palette ./colors/contrast.json
orcaview settings appearance --palette default
orcaview render molecule.xyz figure.png --color-pack ./colors/contrast.json
```

The first command installs and selects a palette. The last applies a file to one image. The schemas describe the JSON structure for editors. OrcaView also validates translation placeholders, element symbols, duplicate palette fields and file size when reading a pack. [Color file schema](color-pack.schema.json)

The examples use the `orcaview` command from a Python installation. With the packaged apps, use `./OrcaView` on Linux, `.\OrcaView.exe` in Windows PowerShell, or `/Applications/OrcaView.app/Contents/MacOS/OrcaView` on macOS. Set `ORCAVIEW_CONFIG_DIR` to a separate directory to test packs with their own preferences.

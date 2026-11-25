# Install the OrcaView color extension · 安装配色扩展

Extract the ZIP and choose a file from **colors**.

| File | Palette |
| --- | --- |
| `contrast.json` | Contrast · 高对比。Recolors carbon, nitrogen, oxygen, sulfur and chlorine. |
| `pastel.json` | Pastel · 柔和。Softer colors for ten common elements. |
| `grayscale.json` | Grayscale · 灰阶。Neutral grays for all 118 elements. |

## Desktop

1. Open **View → Molecular appearance… → Import color pack…** and select one JSON file from **colors**.
2. Click **Save** to apply it to the molecule and its image exports. Repeat for any other palette you want to install.
3. Switch between installed palettes in the same dialog. **OrcaView default** restores the original element colors. OrcaView keeps a personal copy of each installed palette.

**中文**　解压 ZIP，打开 **View → Molecular appearance… → Import color pack…**，选择 **colors** 文件夹中的一个 JSON 文件，点 **Save**。可以分别导入多种方案，以后在同一窗口切换。选择 **OrcaView default** 可恢复默认配色。

## Command line · 命令行

Run the following commands from the folder containing this guide to install a palette, render one image with another palette, or restore the default.

```sh
orcaview settings appearance --import-palette ./colors/contrast.json
orcaview render molecule.xyz figure.png --color-pack ./colors/grayscale.json
orcaview settings appearance --palette default
```

Replace `molecule.xyz` with your structure path. With a packaged app, use the path to its executable in place of `orcaview`, for example `/Applications/OrcaView.app/Contents/MacOS/OrcaView`, `/path/to/OrcaView`, or `& 'C:\Apps\OrcaView\OrcaView.exe'` in PowerShell.

自定义方案可从 `colors/` 下的示例开始，格式定义在 `authoring/color-pack.schema.json`。To create another palette, copy a JSON file and edit its ID, name and element colors. Import it with the same steps.

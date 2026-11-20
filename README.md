# OrcaView

OrcaView 是面向 ORCA 的开源桌面前后处理工具。可以打开分子结构、编辑和导出 ORCA 输入，并从已有计算日志查看能量、电荷、分子轨道和光谱结果。

当前试用版 **0.1.0a24**，输入模板按 **ORCA 6.1.1** 编制。

![从 ORCA 输出查看计算结果、结构及坐标](artifacts/public/results.png)

## 下载

| 平台 | 下载与启动方式 |
|---|---|
| Windows x64 | [下载 Windows ZIP](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a24/OrcaView-0.1.0a24-Windows-x64.zip)，完整解压后双击 `OrcaView.exe`。 |
| Linux x86-64 | [下载 Linux tar.gz](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a24/OrcaView-0.1.0a24-Linux-x86_64.tar.gz)，解压后进入程序目录，在图形桌面中运行 `./OrcaView`。 |
| macOS（Apple Silicon，arm64） | [下载 macOS DMG](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a24/OrcaView-0.1.0a24-macOS-arm64.dmg)，打开后将 `OrcaView.app` 拖入「应用程序」。 |

三个平台的发行包均内置 Python、Qt 和 Open Babel。浏览结构、生成输入及查看已有计算结果可直接离线使用。运行新的量子化学计算需另行安装 ORCA。Windows 版支持生成和导出输入，应用内的本地作业运行器当前使用 POSIX 进程控制。[发行页与 SHA-256 校验清单](https://github.com/lightzfpwings/OrcaView/releases/tag/v0.1.0a24)

macOS 试用版使用临时签名，未经 Apple 公证。首次打开下载的应用时如出现系统提示，请参阅 [Apple 的打开说明](https://support.apple.com/zh-cn/102445)。

### 在 Windows 上试用

1. 完整解压 ZIP，在解压后的程序目录中双击 `OrcaView.exe`。同目录的 `python` 文件夹需要随主程序一起保留。
2. 打开[水分子 XYZ 示例](examples/water.xyz)，从 GitHub 下载原始文件。在 OrcaView 中按 **Ctrl+O** 选取它。视口应显示一个氧原子和两个氢原子，底部「ORCA 输入预览」可查看原生输入。
3. 要测试结果导入，可下载[手写单点计算日志](examples/m5_orca/water-sp.out)，同样通过 **Ctrl+O** 打开。在「结果」页可核对示例单点能 −76.123456789012 Eh、Mulliken 电荷与原子坐标。

若要检查解压版本，在程序目录打开 PowerShell 并运行 `.\OrcaView-cli.exe --version`，应显示 `0.1.0a24`。本版本的 Windows x64 文件已在 Wine 下测试，Linux 版已在 Linux 虚拟机中测试。

## 支持的工作流

- **分子结构**：支持 XYZ、MOL/SDF、MOL2、PDB、CML、CDXML、SMILES、InChI 等格式。二维结构可通过内置 Open Babel 生成三维构象。识别到周期性结构时，程序会询问是否去掉周期性。
- **量子化学文件**：支持 Gaussian、ORCA、Q-Chem 和 NWChem 输入；可从 Molden、FCHK、WFN、WFX、MWFN 等文件读取原子坐标。读取 ORCA 二进制 GBW 需匹配版本的 `orca_2mkl`。
- **结构视图**：显示哑光球棍和几何点群，默认将最高阶旋转轴对齐显示坐标系的 z 轴；原子表与导出文件保留源坐标。在结果页选中两个原子可查看键长。
- **计算输入**：配置方法、基组、计算任务、电荷和自旋多重度，可编辑高级输入块、预览和导出原生 `.inp`。[计算方法说明](docs/ORCA_METHODS.md)
- **计算结果**：从 ORCA `.out` 或 `.log` 中提取实际打印的能量、HOMO/LUMO、偶极矩、布居电荷、振动和 NMR 等数据。只读结果表可复制，详情可回查源文件及行号。

## 界面语言

内置简体中文、繁体中文、日语、英语及德语。打开 **视图 → 界面语言…** 选择语言，保存并重启即可切换。

要安装或更新外部语言包，解压下载的语言包，将 JSON 文件直接放在所选目录下。在同一对话框点击 **刷新语言包**，选择语言、保存并重启。外部语言包可以只覆盖一部分词条。[独立语言包下载](https://github.com/lightzfpwings/OrcaView/releases/download/v0.1.0a24/OrcaView-0.1.0a24-languages.zip) · [语言包源文件](src/orcaview/languages)

## 源码、构建与测试

核心与命令行支持 Python 3.9 及以上版本。使用 CPython 3.13、在虚拟环境中安装桌面依赖即可运行完整应用或重建发行包。

```shell
python -m pip install -e ".[gui]"
python -m orcaview gui
```

在项目根目录用下面的命令预览示例输入、运行回归测试或构建 Linux 和 Windows 发行包。打包需要下载清单中锁定版本的依赖并校验 SHA-256。[跨平台打包说明](packaging/desktop/README.md)

```shell
python -m orcaview preview examples/water.xyz --job OPT_FREQ
python tools/run_tests.py -q
python packaging/desktop/build.py both
```

在 Apple Silicon Mac 的 arm64 CPython 3.13 虚拟环境中，可用以下命令生成同版本的 `.app` 和 DMG。成品位于 `dist/macos/0.1.0a24/`。

```shell
python -m pip install '.[gui]' 'PyInstaller==6.22.3'
python packaging/macos/build.py
```

## 开源许可

OrcaView 自有源码采用 [MIT 许可证](LICENSE)。发行包所含 Python、Qt、Open Babel 等组件分别遵循其上游许可。组件清单和对应源码获取方式见[第三方说明](THIRD_PARTY_NOTICES.md)。平台测试环境、语言包和验证样例见[发行验证记录](docs/PUBLIC_VALIDATION.md)。

# OrcaView validation history

## 0.1.0a56 alpha测试版

All 658 regression tests passed. The editable input tests cover mouse leave and keyboard commits, invalid text recovery, atom identity and precision, and applying the same input through the command line. All 568 method templates passed a render–read–render check. [Editable input tests](../tests/test_edit_input_preview.py)

All 143 OrcaView Python modules matched the source in each of the three desktop packages. Both extension ZIPs rebuilt byte for byte. A read-only mount of the macOS DMG passed code signature verification. Its executable saved an edited input to a project and reproduced the normalized input on reopening. It loaded all four interface languages and rendered water with each of the three external palettes. For every palette, installing it and passing it to a single render produced identical BMPs. [Release package checks](../packaging/check_release_extensions.py)

## 0.1.0a54 prerelease

All 648 regression tests passed. Six design tests exercise keyboard deletion and undo, atom and bond targeting, overlapping atoms, dragging and placement depth after rotation. They also compare exported images before and during hover. In a native macOS window using the packaged code, deleting a selected benzene atom reduced the atom count from 12 to 11. Undo restored all 12. [Design interaction tests](../tests/test_design_targets.py)

All 141 OrcaView Python modules in each desktop package matched the source. The four language dictionaries and their Qt translation files matched the release inputs. The extension kit contained 1,787 message keys and reproduced byte for byte. [Native package checks](../.github/workflows/release-extensions.yml)

## 0.1.0a53 prerelease

All 642 regression tests passed from a checkout of the release files. All 140 frozen OrcaView Python modules in the macOS app matched that source. The Windows and Linux packages contained the same modules and the same application image asset. The four shipped translation dictionaries and their Qt catalogs matched the files used to prepare the release.

The signed macOS app ran from a read-only mount of the release DMG. It loaded the external language catalog after restart and produced different English and Chinese window images. Installing the Contrast palette and passing the same file to a single render produced identical BMPs. Both differed from the built-in palette. The extension kit rebuilt byte for byte and its language template contained 1,786 source messages. [Extension guide](extensions/README.md) · [Native package checks](../.github/workflows/release-extensions.yml)

## 0.1.0a46 prerelease

Structure image export offers integer scale factors from 1× to 8× and defaults to 2×. In the native Cocoa dialog, a 400 × 400 benzene view exported at 4× measured 1600 × 1600 pixels. Its atom labels and bonds retained their relative positions. Enlarging the canvas to 1801 × 1621 preserved the complete 1600 × 1600 region pixel for pixel. The BMP header identifies an uncompressed 24-bit image with a white background. PNG and BMP recorded the 384 dpi density of the 4× export.

Vector PDF retains the printed structure size across multipliers. At 7× the tests also check fractional page dimensions and cross-reference offsets. [Export tests](../tests/test_structure_export.py) · [Dialog tests](../tests/test_structure_image_dialog.py)

All 585 regression tests passed. The signed macOS arm64 application opened from the mounted disk image and its 124 frozen modules matched the checkout. The Windows executable made 36 exports under Wine across English, Simplified Chinese and Traditional Chinese. The Linux package's extracted code made the same 36 exports with the host's offscreen Qt. Native Linux desktop rendering remains unverified.

## 0.1.0a45 local preview

All 581 regression tests passed. The structure export tests exercise both Design views, the Input viewport and the selected Result frame, including transparent backgrounds, camera and label settings, canvas padding, cropping and vector PDF page sizes. The tests also cover cancellation and write failures. [Export tests](../tests/test_structure_export.py) · [Rendering tests](../tests/test_structure_rendering.py) · [File menu and dialog tests](../tests/test_structure_image_dialog.py)

The mounted macOS arm64 image passed code-signature and native Cocoa startup checks. All 124 frozen OrcaView modules matched the checkout. Extending a transparent benzene export by 203 × 143 pixels preserved every original pixel. The 784 × 599 canvas produced a 588 × 449.25 pt PDF. Poppler rendered that PDF at 96 dpi, and the structure occupied the same bounds as the PNG.

The Windows EXE ran under Wine with the English interface and each optional Chinese locale. It exported both Design views and the Input and Result geometries. Enlarging the canvas by 101 × 81 pixels preserved the original image. The Linux archive's extracted application modules passed the same export checks with host Qt; a native Linux desktop was unavailable.

## 0.1.0a44 local preview

The English desktop builds include 20 examples. The Chinese extension provides Simplified and Traditional Chinese for both OrcaView and the standard Qt controls. An installation with a saved Chinese language preference and no extension opens in English.

The spectroscopy checks use real ORCA 6.1.1 IR, Raman, UV/Vis and CD output. The plotted CD spectrum retains the signs of the printed transitions. Tests cover the full width at half maximum, height normalization, coincident transitions, electronic-axis conversion, plotted limits, and separate exports of the curve and original sticks. An existing a43 project opens with its original input and peak data. [Figure and drawing controls](../artifacts/public/spectrum-plot.png) · [Broadening tests](../tests/test_spectral_broadening.py) · [Plot and export tests](../tests/test_spectrum_plot.py)

All 568 regression tests passed. The mounted macOS arm64 image passed code-signature, native Cocoa startup and frozen-module checks. The plotted figure and CSV exports were checked with a real log. On Wine, the packaged Windows EXE opened in English, Simplified Chinese and Traditional Chinese. In each language the test changed the CD profile to pseudo-Voigt with a 6.5 nm FWHM, 70% Lorentzian fraction, 2,401 base samples and a 3.5 px stroke, then exported a 1,800 × 1,100 PNG. All 20 Windows examples opened. The Windows ZIP contains exactly `OrcaView.exe`, `LICENSE` and `Examples/` at its root.

The Linux x86-64 archive's application code, executable permissions and all 3,062 inventoried files were verified on macOS. The published a43 portable updater was exercised against both final archives. Existing user examples and independently edited versions of the same example survived replacement and a second launch or recovery pass. Linux GUI execution on a native desktop remains unverified.

## 0.1.0a43 Windows 单文件发行包

Windows ZIP 第一层为 `OrcaView.exe`、`LICENSE` 和 `Examples/`。对照源码核验了独立 EXE 内的 OrcaView 编译模块和资源、Open Babel 环构象库的 4,647 项索引，以及 20 份示例的文件清单与校验值。

在 Wine 的 Windows 图形后端，从含中文和空格的目录启动发行包的 EXE。通过图形界面和命令行验证启动、版本显示、水分子的输入预览和示例读取。环己烷的二维草图规整后，Open Babel 的 MMFF94 生成椅式构象，UFF 完成 MgOH 预优化。

原位覆盖测试以本地安装包提供更新数据，实际的 EXE 完成准备、退出、文件替换和同一路径重启。核对了个人项目、修改过的示例、自建示例以及同级旧版备份。程序正常退出后，临时运行库和更新助手目录均被清除。另用正式 0.1.0a42 Windows 客户端验证，旧更新器发现单文件版后可通过 **GitHub 发布页** 进入新版下载页。

macOS 验证了挂载镜像中的签名、原生 Cocoa 启动、二维和三维操作及 20 份示例。Linux 在 macOS 上核对归档内文件、清单、符号链接及应用代码，本轮未在 Linux 图形桌面启动。全套 550 项回归测试通过。[发行附件与 SHA-256 清单](https://github.com/lightzfpwings/OrcaView/releases/tag/v0.1.0a43)

Windows 最终 ZIP 大小为 90,862,579 字节，SHA-256 为 `88ea0bd0d10935639d0ad8266815dec71919c2ee7825424dc6c382ecf697e5b9`。

## 0.1.0a42 精简安装包与原位置覆盖更新

三个安装包都附有相同的 20 份示例文件，可直接打开结构、ORCA 输入和输出。macOS 镜像可见内容为 `OrcaView.app` 和「示例」。Windows 与 Linux 归档在单层版本目录中提供启动器、`python` 运行库和「示例」。许可证随软件提供，Open Babel 上游源文件已移到独立的第三方源码 ZIP，附有 SHA-256 清单。

用新版更新器将已发布的 0.1.0a40 Windows 和 Linux 安装目录升级到原位置，核对旧版备份，同时读取留在原处的个人项目及改过的示例。另用原版 0.1.0a40 发行包内的更新器字节码解压新的两个便携包，验证旧版仍可按原有方式完成首次安装。

Windows 最终 ZIP 在 Wine 11.21 的 Qt Windows 后端验证。用临时目录启动实际 `OrcaView.exe`，在更新窗口提供本地最终 ZIP 作为测试下载源，完成校验、暂存、正常退出、进程替换并在同一个含中文及空格的目录重启。新进程成功打开窗口，个人项目、自建示例和修改过的官方示例逐字节保留。Linux 验证了解压、原位置替换、运行库权限、符号链接及应用文件。另在 POSIX 环境运行了助手的等待、替换和重启流程。此次未在原生 Linux 图形桌面启动。

macOS 在临时中文目录中安装 0.1.0a40 副本，使用最终 0.1.0a42 应用内的冻结更新代码和已校验的 DMG 原位覆盖，系统从同一路径重启新版，旁边的个人项目保持原样。已只读挂载最终 DMG，核对代码签名、Cocoa 原生窗口及 20 个示例的读取。

全套回归测试 548 项通过。三个平台均比对了全部 120 个 OrcaView 编译模块与源码。Windows 和 Linux 归档内的文件清单逐项通过 SHA-256 校验。[便携覆盖测试](../tests/test_update_download.py) · [macOS 覆盖测试](../tests/test_macos_update.py) · [更新窗口测试](../tests/test_updates_gui.py)

| 发行包 | SHA-256 |
|---|---|
| Windows x64 ZIP | `a3d5ded05ac5d4ef6257821588b510a2fa92cfa80feb7d79d29846365c7af404` |
| macOS arm64 DMG | `171a3fcebc66be4359ac94cddae77beeb43a2ddbeecbfff8d87c43eac19aefe2` |
| Linux x86-64 tar.gz | `2c2dbd489fbb5fb18a58a72dbc4ac41878a0404bb49f66e7d1216a3fc697c25d` |

## 0.1.0a41 独立二维草图与 Windows 三维预优化

在 Wine 11.21 的 Qt Windows 后端复现了 0.1.0a40 的两种故障。英文路径下，平面六元碳环在准备三维构象时读取了错误的片段数据。Windows wheel 的构象库文件使用 CRLF 换行，索引按 LF 字节位置生成。含中文和空格的路径下，原生插件发现还会失败。新版安装包校正了片段表的换行，包内 4,647 条索引均指向对应片段的第一行坐标。Windows worker 使用宽字符路径加载随包插件，并从独立工作目录读取数据。[Windows 资源回归测试](../tests/test_babel_worker_resources.py)

将最终 Windows ZIP 分别解压至英文目录和含中文与空格的目录，使用包内 Windows Python、Qt 和 Open Babel 操作设计页。补氢得到 C₆H₁₂ 后依次点击「整理 2D」「优化 3D」「整理 2D」。三维步骤使用 MMFF94 形成椅式，六个环内二面角交替为约 ±55°，原二维草图逐点一致。两次二维操作前后的 ORCA 输入均逐字节相同。另一含镁测试结构实际使用 UFF，Mg–O 距离从 2.60 Å 优化至约 2.00 Å。

536 项回归测试全部通过。覆盖单键直链的 120° 锯齿、规则六元环、二维整理前后 ORCA 输入逐字节相同、三维优化保留草图、两项操作交替、撤销重做、后台任务过期及项目保存重开。[结构整理与力场测试](../tests/test_structure_optimization.py) · [建模按钮测试](../tests/test_design_modeling_actions.py) · [草图持久化测试](../tests/test_sketch_coordinates.py)

macOS arm64 DMG 通过镜像与严格临时签名校验。从只读镜像启动原生 Cocoa 窗口，用包内模块和 Open Babel 子进程完成甲烷的二维、三维操作及环己烷的三维预优化，并保存重开 schema 11 项目。

| 本地试用包 | SHA-256 |
|---|---|
| Windows x64 ZIP | `dc99b3a24db71d6b82423a459c7ced787243a71100dfe202440ff2322e462014` |
| macOS arm64 DMG | `6d785e8e09157ab9d75787d82b715f532ced00d8facde55f3d2123509bc08b48` |

## 0.1.0a40 Windows 中文字体与缩放

在同一套 Wine 11.21 环境中启动 0.1.0a37 与 0.1.0a40 的 Windows x64 发行包。使用 Qt Windows 后端和 100% 缩放，侧栏与主标题的实际字重均从 600 降到 400。新版在 100%、125% 和 150% 下的 1120 × 780 逻辑窗口分别生成 1120 × 780、1400 × 975 和 1680 × 1170 像素的截图。三档下均能渲染中文和显示底部三个页签。兼容环境缺少微软雅黑，中文由 Arial Unicode MS 回退绘制，输入预览使用 Courier New。原生 Windows 的微软雅黑与 ClearType 观感仍待实机确认。

全部 524 项回归测试通过。另用 macOS 已安装的苹方细体运行 Windows 字体策略，核对正文实际绘制的中文字形为 300 字重，标题和表头为 400。三档缩放下的页签文字完整，输入预览保留等宽排版。[字体回归测试](../tests/test_windows_typography.py) · [页签布局测试](../tests/test_sidebar_visibility.py)

从只读挂载的 macOS arm64 DMG 原生启动应用，在五种界面语言下核对输入预览、结果摘要和日志页签，冗余标题行的实际高度为 0。118 个冻结的应用模块与源码一致。应用通过严格签名校验，DMG 通过镜像校验。

Linux x86-64 便携包通过应用内更新器完成校验和解压安装。118 个编译模块及 5 份翻译或图标资源与源码一致，3,682 项运行环境文件、目录和链接与公开的 0.1.0a37 一致。本次未在 Linux 图形桌面启动。

| 发行包 | SHA-256 |
|---|---|
| Windows x64 ZIP | `399cf2254f138ea78562562e3cd2dd31b16a2b2d0173704ca62014eda049d761` |
| macOS arm64 DMG | `d615de1fa2400536c3437fbf6fea49dfa39fd2d67526cb578d85cfd971e67624` |
| Linux x86-64 tar.gz | `22c248d89ce7d0688c590e0d993ed3201ec02ef5a25288bfa8dac1a159fc8f8c` |

## 0.1.0a39 底部页签与标题行

输入页恢复「ORCA 输入预览」「结果摘要」「消息与日志」三个常驻页签。macOS 原生布局实测标题控件高度为 0，页签上沿与底部面板上沿重合。左右侧栏继续显示标题。通过只读挂载的 Apple Silicon 镜像启动应用，并用包内冻结模块在五种语言下点击三个页签，检查实时预览、读取摘要和操作日志。切换工作区后返回输入页，原选中的页签仍可使用。[布局测试](../tests/test_sidebar_visibility.py)

520 项回归测试通过。应用通过严格签名校验，DMG 通过镜像校验，SHA-256 为 `deb0d6ccc0a69647a8c0162b2ce3124249ee540d13d1f74e2a58326272048a25`。

## 0.1.0a38 移除常驻的「输入与结果」底栏

在 macOS 原生窗口中以 1120 × 780 的简体中文界面对比两个版本，输入页的分子视图区高度从 356 增至 573 个逻辑像素。用新镜像内的冻结模块检查了全部五种语言，「输入」「设计」「结果」三个工作区都延伸至状态栏。通过「视图」打开输入预览后，更改核心数可同步看到将要导出的输入。纯文本摘要单独显示，含计算性质的日志进入结果页，仍可从菜单再次查看摘要。

520 项回归测试通过。Apple Silicon 应用从只读挂载的 DMG 启动并通过严格签名校验。镜像通过 `hdiutil verify`，SHA-256 为 `2368118db68c32b5114001af259b52bb68160a7583a716e30f8ca4a10e78244f`。

## 0.1.0a37 检查更新与安装

2026-11-21 在 0.1.0a37 发布前访问官方 GitHub Releases，当时最新公开版本为 `0.1.0a24`。本地 `0.1.0a37` 正确显示没有更新。在验证进程中将已安装版本设为 `0.1.0a23` 后，三个平台均找到对应的 `0.1.0a24` 安装包。实际下载了 79,747,661 字节的 macOS DMG，核对了 GitHub 的 SHA-256 并通过磁盘镜像校验。另将已保存的官方 Windows ZIP 和 Linux tar.gz 对照 GitHub 提供的摘要校验，解压到临时安装目录并核对启动器和 Linux 的 Python 符号链接。[官方发布记录](https://github.com/lightzfpwings/OrcaView/releases/tag/v0.1.0a24)

从只读挂载的新版 macOS 镜像启动程序，核对版本、签名与主窗口。使用包内冻结模块在 Cocoa 下验证了五种语言的帮助菜单与联网查询。在旧版本场景中触发「下载并安装」，确认传给系统的是校验完成的 DMG，并只读挂载该文件核对包内版本。Windows 与 Linux 的新包也通过了安装目录、启动器和应用文件比对，这两份新包的目标系统启动待验。

全部 519 项回归测试通过，覆盖版本排序、平台匹配、校验失败、取消、重试、关闭窗口和便携包安装。[版本检查](../tests/test_updates.py) · [下载安装](../tests/test_update_download.py) · [更新窗口](../tests/test_updates_gui.py)

| 本地安装包 | SHA-256 |
|---|---|
| macOS arm64 DMG | `552d8a6eb4a40ac4dccab02a7f4d977aa44c110a9c424a99c0475416aa5e3c72` |
| Windows x64 ZIP | `ed156b988ab4472320058177660e9c4cdf9194c5cc125a4a89460953afd0fbc1` |
| Linux x86-64 tar.gz | `fa388d4e9b3f11dc079f0427b871d2c30a7ad3872e8f898d9793117ebfe1877f` |

## 0.1.0a36 空草稿与工作区切换

在只读挂载的 macOS arm64 镜像中打开随项目提供的水分子 ORCA 单点输出，框选并删除全部原子。在五种界面语言下分别进入「输入」和「结果」，选择「是」均返回设计，选择「否」均留在目标页，计算设置、导出和结果选择均不可用。撤销清空后，原结构、原子 ID 和历史结果可再次查看。另将空草稿保存为 schema 10 项目并重开，应用直接显示设计页，放入首个原子后输入预览可再次导出。[工作区交接测试](../tests/test_workspace_handoff.py) · [设计页测试](../tests/test_design_marquee.py) · [编辑与持久化测试](../tests/test_editing.py)

496 项回归测试全部通过，冻结的 OrcaView 模块及内置翻译包与源码一致。应用通过严格签名校验，DMG 通过 `hdiutil verify`，SHA-256 为 `507915fd5c43dfcea312b0643ad78971058603489a73fc9fa753d22a5e365999`。

## 0.1.0a35 连续加氢、整分子补氢与键型菜单

在只读挂载的 macOS arm64 镜像中启动应用，使用冻结模块和应用自带的 Open Babel worker 检查五种界面语言。鼠标点选二维和三维中的不同碳原子，每次只接上一个 H。双击按钮将含两个显式 H 的芳香碳环补为 C₆H₆，撤销一次即可恢复。对已经具有六个 H 的坐标示例再次补氢，修订号保持不变。将六条环键改为 1.5 级后，保存并重开 schema 9 项目，键型、原子 ID 均逐项一致。该结构可完成 MMFF94 预优化。镜像内的配位键与 2.5 级键可进行二维整理，三维力场会给出不支持该键型的提示。

489 项回归测试全部通过。用例覆盖 17 个菜单选项、撤销重做、反向画环、画布边缘反复点加氢，以及萘、吡咯、呋喃等芳香体系的氢数。[键型菜单测试](../tests/test_bond_palette.py) · [加氢测试](../tests/test_design_hydrogens.py) · [设计页交互测试](../tests/test_design_modeling_actions.py)

冻结的 OrcaView 模块和四份翻译包已与本次源码逐项比对。应用通过严格签名校验，DMG 通过 `hdiutil verify`，SHA-256 为 `8204ab762ddb6c479dc224cfc0ba7caca897433023a05b6f982144b011490adf`。

## 0.1.0a34 环模板按钮

在只读挂载的 macOS arm64 镜像中启动应用，并使用镜像内的冻结模块验证五种语言的设计页。1120 × 780 窗口中，苯环按钮与元素下拉框均宽 51 个逻辑像素，简繁中文和日文界面高 37，英文和德文界面高 33，与同一行的其他按钮对齐。用鼠标选择五元碳环、用键盘选择苯环后，均可在起始碳上建环并撤销。另核对了苯环的三条交替双键，以及选定碳原子后点「+H」的结果。[环菜单交互测试](../tests/test_design_rings.py) · [工具栏布局测试](../tests/test_design_modeling_actions.py)

470 项回归测试全部通过。应用通过严格签名校验，DMG 通过 `hdiutil verify`，SHA-256 为 `5341a2bce41cec9064017ef1cc6cf907258a6348cfc1e600e3fb3729306dfb40`。

## 0.1.0a33 单原子加氢

在只读挂载的 macOS 镜像中启动应用，并在 Cocoa 下用镜像内的冻结模块点按「+H」。在五种内置语言的 1120 × 780 窗口中，按钮均在「环模板」右侧，相隔 4 个逻辑像素，同一行的 13 个控件顶端对齐且等高。选定碳原子后连续点击六次，每次增加一个 H 和一条单键，原选区及已有原子 ID 均保留。接上第五个 H 时，结构中保留五条 C–H 键，界面同时显示键级总和及电子态提示。撤销回 CH₄ 后提示消失，输入预览可导出。[界面与历史测试](../tests/test_design_modeling_actions.py) · [加氢测试](../tests/test_design_hydrogens.py) · [设计诊断测试](../tests/test_design_diagnostics.py)

469 项回归测试全部通过，包括逐个加氢后的环己烷三维预优化。只读镜像内的应用通过严格签名校验，DMG 通过 `hdiutil verify`，SHA-256 为 `0aa6e6b97c23c017416ee402cc358c9849a0adc41113ba3fba8fd9e473eb0daf`。

## 0.1.0a32 设计工作区、补氢与结构优化

465 项回归测试通过。验证了整分子与选区补氢、二维规整、MMFF94 优化和 UFF 回退、撤销重做及项目重开。环己烷模板补全为 C₆H₁₂ 后可得到椅式构象。带三维四面体手性的结构在二维无法表达时保留原结构，三维优化检查已识别的立体化学。后台计算期间改变坐标或打开另一文档，旧计算不会覆盖新编辑。[补氢测试](../tests/test_design_hydrogens.py) · [力场及二维布局测试](../tests/test_structure_optimization.py) · [设计操作测试](../tests/test_design_modeling_actions.py)

从只读挂载的 macOS arm64 镜像启动应用，并用镜像内的冻结模块和原生 worker 在 Cocoa 下验证设计按钮。五种语言在 1120 × 780 窗口中都可见。用苯环模板补入六个氢，整理二维结构，再做 MMFF94 三维预优化。界面导出单核 B3LYP/def2-SVP 输入，本机 ORCA 6.1.1 正常结束，所报单点能量为 −231.930504365984 Eh。结果页读取了三个数据集，可将计算几何送回设计。另验证了快速切换页签及撤销对历史结果帧的采纳。[工作区交接测试](../tests/test_workspace_handoff.py)

应用通过严格签名校验，DMG 通过 `hdiutil verify`。本地安装镜像 SHA-256 为 `24ce8f34352086bb3e427fc6e26eb521df253e4794d68309da3aa682bb54929a`。

## 0.1.0a31 分子设计框选

从只读挂载的 macOS 镜像启动应用，并用包内冻结模块在 Cocoa 下验证。五种语言在 1120 × 780 窗口内均已移除二维投影菜单。中心线从 7 个逻辑像素收窄为 1 个，鼠标命中宽度为 5 个。拖动后双击可恢复为 546 和 545 像素的等宽布局。对一个带氧取代基的碳环在二维中框选三个原子，再于三维追加一个原子，两侧和编辑器选区一致，几何修订保持不变。

436 项回归测试全部通过。设计页用鼠标从四个方向拖框，检查了替换、追加、去重和空框，以及二维和三维的选中原子是否一致。另核对了转动和平移三维视图后按当前投影框选、一次删除和撤销多个原子、二维拖动保持 Z 坐标。macOS arm64 安装镜像的 SHA-256 为 `cd04ff757b31994153d497cbf426425959a96b3501556e0e493f719ae6adafda`。[框选回归](../tests/test_design_marquee.py) · [设计页回归](../tests/test_design_workspace.py)

## 0.1.0a30 元素周期表和分子建模

在 Apple Silicon 上从只读挂载的 DMG 启动应用，校验版本、签名与镜像。DMG 的 SHA-256 为 `e72f31fbd2c3ff3c4bc61bdd2dd0c5157e3ef7db58a63e70436c91667ce63256`。

使用镜像内的冻结模块在 Cocoa 下操作设计页。在 1120 × 780 窗口中，五种语言的两栏初始宽度均为 543 和 542 像素。拖动后双击分隔线可恢复这两个宽度。弹出周期表时，118 个元素全部可见，输入 118 可选中 Og。从起始碳插入苯环后，接上一个氧原子并把 C–O 键调至 1.42 Å，实测显示 1.420000 Å。

Qt 离屏回归共 432 项，全部通过。新增用例检查了 118 个元素的位置和选择、设计页的等宽布局及双击复位、一笔建环后的稳定原子 ID 和键级、交换固定端后的整组平移、撤销以及环内键的测距。四种译文另核对了新增控件和错误提示。[周期表测试](../tests/test_design_elements.py) · [设计页测试](../tests/test_design_workspace.py) · [环模板测试](../tests/test_design_rings.py) · [键长测试](../tests/test_design_bond_length.py)

## 0.1.0a29 分子设计工作区

在 Apple Silicon 上从只读挂载的 DMG 启动 Cocoa 窗口，并使用镜像内的冻结模块核对「输入」「设计」「结果」三个页签、分子草图和三维预览。应用通过严格签名校验，DMG 的 SHA-256 为 `6062c0db29f27af3bbbe5114656461544b1827c0e90547e88280a1e700557568`。

422 项回归测试全部通过。设计页测试通过鼠标连续画出 C–C=O，逐笔撤销和重做，验证投影拖动、精确坐标、改键、保存重开及 ORCA 输入导出。另用已有的真实水分子 NMR 输出核对了编辑后的 schema 8 项目，重开后原始报告、三个数据集和几何历史均与保存前一致。五种界面语言在 1120 像素宽的窗口下均可使用设计工具。[设计页测试](../tests/test_design_workspace.py) · [显式键表和历史兼容测试](../tests/test_design_topology.py)

## 0.1.0a28 本地 macOS 构建

从只读挂载的 DMG 启动 macOS 窗口，确认「复位视图」右侧显示六个旋转图标，角度框显示 `15.00°`。五种界面语言均已核对图标的悬停提示和辅助名称。414 项回归测试全部通过。DMG 的 SHA-256 为 `ac1e2e90a8b65ae0223e47baf277b1a08c593b974d705371b896f0afbe14c4de`。

## 0.1.0a27 本地 macOS 构建

在 Apple Silicon 上从只读挂载的 DMG 启动 Cocoa 窗口，核对工具栏的六个方向按钮、角度输入和版本显示。应用通过严格签名校验，DMG 通过镜像校验，SHA-256 为 `c7d193e311e90d67e5b081667ca17b315709cb9a039a5db824e456ff88472d76`。

Qt 离屏回归共 413 项，全部通过。新用例在结构页和结果页输入 22.5° 并点击六个方向按钮，核对当前视图的旋转和坐标轴方向。测试也用鼠标事件核对左键旋转、右键平移、平移后选择原子、双击保持视角和按钮复位。视图操作前后的几何修订和 ORCA 输入预览一致。[视口测试](../tests/test_view_controls.py)

## 0.1.0a26 本地 macOS 构建

在 Apple Silicon 上从只读挂载的 DMG 打开高精度 XYZ，图形界面预览、导出的 `.inp` 和命令行预览中的坐标块逐字节一致。原子坐标固定保留 8 位小数，例如 `0.75860212567` 写为 `0.75860213`，`0` 写为 `0.00000000`。DMG 的 SHA-256 为 `356f5733d5f9d1253c7d8f2539e8d4a0dbe43352672e32228b093465a8e00a5c`。

使用 `python tools/run_tests.py -q` 运行 410 项回归测试，全部通过。

2026-11-20 在 Apple Silicon 上用当前源码生成水分子输入，使用本机 ORCA 6.1.1 重新运行三个作业。OrcaView 从新日志中均读出正常终止状态。B3LYP/SMD、正则化 RI-MP2、EOM-CCSD 的最终单点能量依次为 −76.332753194122、−76.154672366449、−75.871014784050 Eh，与存档日志打印的 12 位小数一致。可用[实算脚本](../tools/check_orca611.sh)复跑。

## 0.1.0a25 本地 macOS 构建

在 Apple Silicon 上从只读挂载的 DMG 启动应用，确认结构页和结果页初始均沿 +z 俯视，红色 x 箭头向右，绿色 y 箭头向上，蓝色圆环与中心点表示 +z 朝向观察者。拖动旋转后，点击「复位视图」或双击画布可恢复俯视。

该版本的 408 项回归测试全部通过。视口测试也检查了旋转后 z 箭头的两翼，以及原子坐标和导出的 ORCA 输入。DMG 的 SHA-256 为 `5ab79c111a0949890be5ff789ef32d342c0ca636d45f3e13aac9de4abe902ae6`。

## 0.1.0a24 公开发行版

Windows x64 和 Linux x86-64 便携包基于 CPython 3.13 构建。对两个包的 97 个 OrcaView 编译模块核对了源哈希，并逐字节核对随包图标与四种可下载的界面语言包。

macOS Apple Silicon 版从同一版本的源码构建，97 个冻结模块及四份语言包均已核对。DMG 为 79,747,661 字节，SHA-256 为 `9cebe3203682d4a94f9752dabf73139decb16d3cdc5b1d1f66404cef0bf2e133`。

| 检查 | 已验证的环境与结果 |
|---|---|
| Windows 启动 | Wine 11.21 的 x64 环境。解压至含空格的目录，运行 GUI 和 CLI 启动器、查看版本并渲染界面。原生 Windows 实机测试待进行。 |
| Linux 启动 | Linux 6.12.115 虚拟机、Debian 12 图形库及 Rosetta x86-64。验证了启动器、版本和离屏 Qt 窗口。 |
| macOS 启动与导入 | 在 macOS 27.3 只读挂载经 `hdiutil verify` 检查的 DMG，通过 LaunchServices 启动原生 Cocoa 窗口。应用和命令行均报告 0.1.0a24。严格签名校验通过，签名类型为 ad hoc。验证了四种外语、二维乙醇生成含 9 个原子的三维构象，以及真实水分子 NMR 日志的计算结果与化学屏蔽谱。 |
| 文件转换 | 两个平台均通过包内 Open Babel 子进程从乙醇 SMILES `CCO` 生成含 9 个原子的三维构象。 |
| 语言 | 两个平台均检查了四种外语界面的加载及 ORCA 输入预览。另在 macOS 逐语言比较六种计算方法，设置和原生输入文本一致。 |
| 回归 | 在 0.1.0a24 版本使用公开测试归档运行 406 项测试，全部通过。 |

公开的真实 ORCA 验证样例保留原始科学数值及行号。运行主机、工作目录、进程号和起始时间使用占位值，清单列出了原始与公开副本各自的校验值。[验证样例及清单](../artifacts/public/validation/public-fixtures.json)

可在 Windows 解压目录运行 `.\OrcaView-cli.exe --version` 检查版本，打开[水分子 XYZ](../examples/water.xyz)检查文件读取，再打开[手写 ORCA 示例](../examples/m5_orca/water-sp.out)检查结果导入。发行附件及 SHA-256 校验文件见[发行页](https://github.com/lightzfpwings/OrcaView/releases/tag/v0.1.0a24)。

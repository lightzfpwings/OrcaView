# OrcaView 0.1.0a24 验证记录

Windows x64 和 Linux x86-64 便携包基于 CPython 3.13 构建。对两个包的 97 个 OrcaView 编译模块核对了源哈希，并逐字节核对随包图标与四种可下载的界面语言包。

macOS Apple Silicon 版从同一版本的源码构建，97 个冻结模块及四份语言包均已核对。DMG 为 79,747,661 字节，SHA-256 为 `9cebe3203682d4a94f9752dabf73139decb16d3cdc5b1d1f66404cef0bf2e133`。

| 检查 | 已验证的环境与结果 |
|---|---|
| Windows 启动 | Wine 11.21 的 x64 环境。解压至含空格的目录，运行 GUI 和 CLI 启动器、查看版本并渲染界面。原生 Windows 实机测试待进行。 |
| Linux 启动 | Linux 6.12.115 虚拟机、Debian 12 图形库及 Rosetta x86-64。验证了启动器、版本和离屏 Qt 窗口。 |
| macOS 启动与导入 | 在 macOS 27.3 只读挂载经 `hdiutil verify` 检查的 DMG，通过 LaunchServices 启动原生 Cocoa 窗口。应用和命令行均报告 0.1.0a24。严格签名校验通过，签名类型为 ad hoc。验证了四种外语、二维乙醇生成含 9 个原子的三维构象，以及真实水分子 NMR 日志的计算结果与化学屏蔽谱。 |
| 文件转换 | 两个平台均通过包内 Open Babel 子进程从乙醇 SMILES `CCO` 生成含 9 个原子的三维构象。 |
| 语言 | 两个平台均检查了四种外语界面的加载及 ORCA 输入预览。另在 macOS 逐语言比较六种计算方法，设置和原生输入文本一致。 |
| 回归 | 使用公开测试归档运行 406 项测试，全部通过。可从仓库根目录执行 `python tools/run_tests.py -q`。 |

公开的真实 ORCA 验证样例保留原始科学数值及行号。运行主机、工作目录、进程号和起始时间使用占位值，清单列出了原始与公开副本各自的校验值。[验证样例及清单](../artifacts/public/validation/public-fixtures.json)

可在 Windows 解压目录运行 `.\OrcaView-cli.exe --version` 检查版本，打开[水分子 XYZ](../examples/water.xyz)检查文件读取，再打开[手写 ORCA 示例](../examples/m5_orca/water-sp.out)检查结果导入。发行附件及 SHA-256 校验文件见[发行页](https://github.com/lightzfpwings/OrcaView/releases/tag/v0.1.0a24)。

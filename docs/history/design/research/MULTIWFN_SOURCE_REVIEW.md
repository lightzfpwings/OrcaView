# Multiwfn 官方源码研究记录

核查日期：2026-11-12。本文记录来源、许可与源码结构，是 OrcaView 的集成研究材料；不表示已经实现后处理、嵌入 Multiwfn 代码或通过真实分析计算。

## 1. 来源与取得范围

本次先尝试官方 HTTPS 页面，遇到握手失败及网页抓取超时；随后通过官方站点的 HTTP 地址实际读取下载页与 Linux 源码压缩包。未以第三方 GitHub 镜像替代官方来源。

| 项目 | 本次实际核查记录 |
|---|---|
| 官方下载页 | http://sobereva.com/multiwfn/download.html |
| 下载页当前版本 | `2026.11.12`；页面注明发布日期与版本日期相同 |
| 官方 Linux 源码包 | http://sobereva.com/multiwfn/misc/Multiwfn_2026.11.12_src_Linux.zip |
| 永久源码链接 | http://sobereva.com/multiwfn/misc/Multiwfn_latest_src_Linux.zip；本次核查使用上面的日期固定链接 |
| 压缩包大小 | `3,635,867` 字节 |
| SHA256 | `f41897accb99d0a7bc1d156ef6a387075f6b2f21acdac0f775db3dccb8424503` |
| 压缩包根目录 | `Multiwfn_2026.11.12_src_Linux/` |
| 压缩包目录条目 | `78` 项 |
| 本次临时缓存 | `/tmp/orcaview-multiwfn-source-review-2026.11.12.zip`；未加入 OrcaView 源码树 |
| 下载页列出的手册 | `Multiwfn_manual_2026.11.3.pdf`，http://sobereva.com/multiwfn/misc/Multiwfn_manual_2026.11.3.pdf |

读取压缩包目录和若干源文件文本时使用 Python 的 `zipfile`；没有执行下载的程序、安装脚本、Makefile、编译器或二进制，也没有把第三方源码复制进 OrcaView。以下行号是对该压缩包内文件按文本逻辑行计数的结果，只适用于本次固定版本。

SHA256 记录本次取得的字节；HTTP 取得方式及本地哈希本身不构成官方数字签名验证。本记录中“当前版本”只指核查日下载页显示的内容。旧的 `3.8(dev)` 命名不应替代本次日期版本。

## 2. 官方下载页的许可条件

下载页的 `LICENSE INFORMATION` 为本次直接读取的一手许可来源。中文概括如下，后续分发时应重新核对实际所用版本的许可：

1. 官方称 Multiwfn 目前对学术与商业用途免费并公开源码，允许向他人分发原版或修改后的代码。
2. 允许把 Multiwfn 作为商业软件中的**免费组件**分发。
3. 售卖修改版可能获得许可，但需要事先取得原作者 Tian Lu 的同意。不能把“允许商业使用”自行扩大成“修改版可无条件收费销售”。
4. 使用 Multiwfn，或自己的代码纳入任何一部分 Multiwfn 代码时，必须在论文正文或代码中引用其 2012 年与 2024 年原始论文。
5. 官方不担保结果正确，也不承担使用后果。

必须保留的原始论文信息：

- Tian Lu, Feiwu Chen, *Multiwfn: A multifunctional wavefunction analyzer*, Journal of Computational Chemistry **33**, 580–592 (2012), DOI: `10.1002/jcc.22885`。
- Tian Lu, *A comprehensive electron wavefunction analysis toolbox for chemists, Multiwfn*, Journal of Chemical Physics **161**, 082503 (2024), DOI: `10.1063/5.0216272`。

这是有具体条件的官方自定义许可，不能自动按 MIT、BSD、GPL 或某个标准开源许可证处理。本次压缩包目录没有单独命名为 LICENSE 的文件，因此本记录明确以官方**下载页条款**作为许可证据，不能声称已找到压缩包内独立许可全文。

源码包还包含图形库静态归档和其他外部代码。若将来随 OrcaView 打包其程序、重新编译发行或抽取算法，应分别确认这些依赖的分发条件；Multiwfn 自身条款不能代替所有第三方依赖的许可。

## 3. 实现形态与构建证据

主体为 Fortran 源码，包含少量 C 接口及外部数值/图形组件。本次实际查看的构建入口生成独立可执行程序：

| 证据位置 | 所见内容 |
|---|---|
| `Multiwfn.f90:1` | 主程序入口为 `program multiwfn` |
| `Multiwfn.f90:39` | 程序自身输出版本 `2026.11.12`，与下载页一致 |
| `Makefile:3` | 默认选项含 OpenMP、MKL 和 Intel 相关选项 |
| `Makefile:12` | 默认 Fortran 编译器为 `ifort`；这不表示其他编译方式已被本次验证 |
| `Makefile:9` | GUI 链接 DISLIN 静态库及 Motif/X11/OpenGL 相关库 |
| `Makefile:14–15` | 两个程序名为 `Multiwfn`、`Multiwfn_noGUI` |
| `Makefile:46–50` | 提供 GUI 与 noGUI 的可执行文件构建目标 |
| `COMPILATION_METHOD.txt:29–31` | 说明 noGUI 构建保留非图形功能，不提供 GUI/绘图功能 |

压缩包的默认构建入口不是稳定的 Python 包或通用后处理共享库接口。未找到面向 OrcaView 这类宿主的、具有稳定性承诺的公共分析 API/ABI 文档。这个结论是本次核查范围内的观察，不能扩大成“任何形式的 API 永远不存在”。源码中的 C 互操作还包括外部函数及平台图形接口，不能据此视为完整的波函数分析 C API。

## 4. 主循环、输入与共享状态

| 文件与行号 | 结构证据 | 对集成的影响 |
|---|---|---|
| `Multiwfn.f90:24` | 从首个命令行参数获取输入文件路径 | 可以由外部进程参数传入分析对象 |
| `Multiwfn.f90:150` | 调用 `readinfile` 载入数据 | 文件是清楚的现有集成边界 |
| `Multiwfn.f90:275`、`:307` | 打印主菜单，再从标准输入读取选项 | 可研究受控 stdin 批处理；菜单脚本必须绑定版本 |
| `Multiwfn.f90:428`、`:446` | 分派 `topo_main`、`study3dim` | 拓扑与三维网格计算有独立功能入口 |
| `Multiwfn.f90:458`、`:470` | 分派 `population_main`、`bondorder_main` | 布居与键级分析可作为独立后处理任务 |
| `Multiwfn.f90:481`、`:487` | 分派 `plotspectrum`、`surfana` | 谱图与表面分析功能并非 Qt 数据模型 |
| `Multiwfn.f90:527`、`:539` | 分派 `excittrans_main`、`visweak_main` | 激发态与弱相互作用也经过菜单入口 |
| `define.f90:24` | `defvar` 共享模块 | 直接嵌入需要处理共享可变状态 |
| `define.f90:41`、`:264` | 全局网格 `cubmat` 和系统计数 | 不宜假定多任务可以无隔离地并发调用内部过程 |
| `define.f90:272`、`:276`、`:281` | 原子、MO 占据/能量和系数矩阵 | 原生状态结构与 OrcaView 的不可变契约不同 |

`population.f90:17–19` 等功能入口直接使用共享模块；谱图过程 `spectrum.f90:8–12` 还引用绘图模块。将内部 subroutine 用绑定工具暴露出来，并不自动获得无界面、可重入、可取消或版本稳定的库。

## 5. ORCA 文件路径与科学边界

| 文件与行号 | 已确认的过程/行为 |
|---|---|
| `fileIO.f90:2` | `readinfile(thisfilename, infomode)` 根据文件类型分派 |
| `fileIO.f90:58–60` | 识别 ORCA 常用的 `.molden.input` 后缀并调用 `readmolden` |
| `fileIO.f90:100–127` | `.gbw` 入口依赖配置的 `orca_2mkl`；转换后读取 Molden，并删除中间转换文件 |
| `fileIO.f90:314` | `loadORCAout` 从 ORCA 文本尝试读取几何信息 |
| `fileIO.f90:353` | 该几何读取过程在核电荷赋值处明确标注 ECP 不兼容问题；不能把几何入口当成完整波函数入口 |
| `fileIO.f90:391–405` | `gbw2molden` 通过外部 ORCA 工具完成转换；内部以拼接字符串调用系统命令 |
| `fileIO.f90:4121` | `readmolden` 波函数读取入口 |
| `fileIO.f90:4147–4168` | 有角动量函数次序转换；涉及 h 函数的历史兼容说明不能忽略或外推为所有新版都已验证 |
| `fileIO.f90:7703` | `outcube` 输出体数据的过程 |
| `settings.ini:114`、`:116` | 有 `orca_2mklpath` 与抑制自动弹图的 `isilent` 配置 |

因此可建立 `ORCA .gbw → 匹配版本的 orca_2mkl → Molden → Multiwfn → 数值表/Cube → OrcaView` 的后处理链。版本匹配、球谐/笛卡尔约定、ECP、单位、归一化、电子数和实际功能所需数据必须单独验证。仅有 XYZ 或 ORCA 几何文本不足以提供一般波函数分析需要的基函数与轨道系数。

OrcaView 应自己通过完整可执行路径与参数列表完成转换，在独立任务目录保存中间 Molden、命令参数、标准输出/错误、工具版本和哈希。原型已有的安全执行约束继续适用；不能直接照搬源码内部的字符串系统命令与自动删除中间文件行为。

## 6. 可定位的后处理功能模块

下表是源码定位清单，不是 OrcaView 当前功能表；是否适用于某个 ORCA 结果仍取决于输入格式、方法和各功能限制。

| 功能方向 | 本次源码入口 |
|---|---|
| 布居、电荷、ESP 拟合 | `population.f90:17 population_main`；`:1703 RESP`；`:2768 fitESP` |
| 键级 | `bondorder.f90:2 bondorder_main`；`:184 Mayerbndord` |
| 轨道组分 | `orbcomp.f90:16 orbcomp_main` |
| 三维性质网格 | `0123dim.f90:2364 study3dim` |
| 网格处理 | `procgriddata.f90:62 procgriddata` |
| 拓扑 | `topology.f90:2 topo_main` |
| 分子表面 | `surfana.f90:2 surfana` |
| 弱相互作用 | `visweak.f90:2 visweak_main`；`:369 IGM` |
| 激发态、空穴/电子、NTO | `excittrans.f90:58 excittrans_main`；`:1700 hole_electron`；`:3713 NTO` |
| 光谱 | `spectrum.f90:8 plotspectrum`；`:2975 loadtransdata` |

本次未逐一核查上述算法的数值正确性或 ORCA 所有版本的兼容性，也未真实执行其分析。尤其是激发态的跃迁系数、TDA/TDDFT 差异及 X/Y 数据等，不能因为找到入口名称就宣称全面支持。

## 7. 对 OrcaView 的集成建议

**analysis-design-2 的正式方向：复用 Fortran 计算核心，形成自带分析引擎。** 逐项把参数、状态、交互和结果与数值过程分离，保留 Multiwfn 的求值、积分、筛选和并行实现；通过新增 C ABI 加载到 OrcaView 自有 worker。桌面用户无需操作原版终端菜单。原版 Multiwfn 作为数值对照和可选兼容后端，菜单脚本不作为长期核心 API。

| 接法 | 可行性与代价 | 建议 |
|---|---|---|
| 复用 Fortran 过程 + 新 C ABI + 自有 worker | 处理共享状态、数值依赖、交互 I/O、错误路径与长期合并；保留算法计算体 | 正式研发主线，按 K0–K4 实施 |
| 原版程序 + 版本化 stdin profile + 产物适配 | 利用现有程序；需检测菜单漂移、输入等待与产物完整性 | 数值对照和可选兼容模式 |
| 在 OrcaView 独立重写科学算法 | 需要重新验证复杂积分与方法实现，失去现有数值实现的复用价值 | 不作为主线；只自行实现界面、通用数据处理及必要封装 |

完整手册筛选与非周期范围见 [MULTIWFN_MANUAL_MAP.md](MULTIWFN_MANUAL_MAP.md)。首批封装分子加载、批量点值/导数、网格与内部 ESP，并优先复用返回数组的 `calcMayerbndord`、`genHirshfeld`。每项绑定源码/引擎构建、ABI 和数值配置，按实际输入能力、输出类型与误差开放；NBO/GENNBO 等数据依赖见 [独立清单](MULTIWFN_EXTERNAL_DEPENDENCIES.md)。

进一步源码审查发现 `noGUI` 仍链接包含主程序、图形与周期对象的公共集合，并以 DISLIN 空桩满足符号，不能等同纯计算库。点值模块也混有周期、插值与其他数值依赖，最小构建须按可达过程整理。共享数组、`read(*)`、`stop/exit`、隐式转换和清理都需要边界改造。精确文件行号、ABI、线程/内存预算与验收见 [MULTIWFN_ENGINE_DESIGN.md](../MULTIWFN_ENGINE_DESIGN.md)。

执行成功必须同时检查进程状态、分析专属结束证据、产物可解析性和必要科学一致性。某些交互错误会等待继续输入或退出，退出码本身不充分。输出与中间文件保留来源，转换和分析任务互相可追溯；视图和动画不能修改源波函数或几何。

当前结论：内置 Multiwfn 来源计算核心值得作为正式方案推进，尤其应保留其积分和格点算法；工程工作集中于接口、状态、I/O、构建及科学数据适配。当前仍仅完成研究与设计，未引入产品数值实现、完成编译或开展性能/精度实测。

# Multiwfn 与 ORCA 后处理兼容性核查

核查日期：2026-11-12（Asia/Hong_Kong）。这是设计依据与兼容边界记录，**没有运行 ORCA、Multiwfn 或文件转换器，没有真实数值验证结果**。

## 资料范围与证据

- 官方发布页当前列出的程序/源码日期为 **2026.11.12**，PDF 手册日期为 **2026.11.3**。应采用日期版本与文件哈希建立 Profile，不把历史名称“3.8(dev)”当作可复现版本。
- 本次直接读取作者官网在线手册，以章节号定位。HTML 没有稳定页码；PDF 链接已确认，但本报告写入时下载尚未完成，**没有声称核对 PDF 页码或取得 PDF 哈希**。
- 官方源码包已经只读检查：`Multiwfn_2026.11.12_src_Linux.zip`，3,635,867 字节；SHA256：`f41897accb99d0a7bc1d156ef6a387075f6b2f21acdac0f775db3dccb8424503`。下文行号对应此包内文件。
- ORCA 依据为 6.1 官方手册。在线文档是可变资源；后续实现应把实际工具版本、二进制哈希、设置和样例输出一并固定。

官方来源：

1. [Multiwfn 发布页](http://sobereva.com/multiwfn/download.html)、[手册 PDF 2026.11.3](http://sobereva.com/multiwfn/misc/Multiwfn_manual_2026.11.3.pdf)、[源码 2026.11.12](http://sobereva.com/multiwfn/misc/Multiwfn_2026.11.12_src_Linux.zip)。
2. [§2.5 输入文件与波函数类型](http://sobereva.com/multiwfn/manual/sec-2-5-input-files-and-wavefunction-types/)、[第4章文件生成](http://sobereva.com/multiwfn/manual/sec-4-prologue-and-generation-of-input-files/)。
3. [§3.21.A.3 激发态输入](http://sobereva.com/multiwfn/manual/sec-3-21-electron-excitation-analysis/#321a3-input-files)。
4. [§5.2 静默运行](http://sobereva.com/multiwfn/manual/sec-5-2-running-multiwfn-in-silent-mode/)、[§5.3 批处理](http://sobereva.com/multiwfn/manual/sec-5-3-running-multiwfn-in-batch-mode/)。
5. [§6.4 ECP 内核密度](http://sobereva.com/multiwfn/manual/sec-6-4-details-about-supplying-inner-core-electron-density/)、[§6.5 波函数正确性检查](http://sobereva.com/multiwfn/manual/sec-6-5-check-sanity-of-wavefunction/)。
6. [ORCA §9.3 orca_2json](https://www.faccts.de/docs/orca/6.1/manual/contents/utilitiesvisualization/orca_2json.html)、[ORCA §9.1 轨道与密度](https://www.faccts.de/docs/orca/6.1/manual/contents/utilitiesvisualization/plots.html)、[ORCA §5.6 激发态](https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/tddft.html)。

## 文件通道与验证边界

建议由 OrcaView 显式管理转换链：

```text
原始 .gbw + 来源任务记录
  → 匹配 ORCA 安装的 orca_2mkl basename -molden
  → basename.molden.input
  → 元数据、电子数、轨道归一化检查
  → 可选 .mwfn 缓存
  → 具体 Multiwfn 分析
  → 数值表 / Cube / 临界点与路径 / 日志
```

第4章给出的官方转换命令是 `orca_2mkl XX -molden`，读取 `XX.gbw`，生成 `XX.molden.input`，不需要重命名扩展名。§2.5 推荐反复分析时转为更紧凑的 `.mwfn`。这是 Multiwfn 的导出步骤，不能把 ORCA 命令写成“直接输出 mwfn”。

Multiwfn 可以在 `settings.ini` 配置 `orca_2mklpath` 后直接接受 `.gbw`；这仍然是自动调用转换器。源码 `fileIO.f90:390–405` 的 `gbw2molden` 构造转换命令、调用外部程序，再加载 `.molden.input`。为保留错误输出、隔离文件写入并避免命令字符串路径问题，OrcaView 宜自行使用参数列表启动经过校验的转换器，把转换结果交给 Multiwfn；不依赖这一隐式转换作为唯一通道。

需记录并检查：

- **基组/轨道约定**：Multiwfn §2.5 支持 Cartesian 和球谐 Gaussian，最高到 h（l=5）；ORCA 能产生更高角动量，不能据此推定 Multiwfn 支持。保留壳类型、排序、相位、单位及程序来源，避免自行排列 MO 系数。
- **归一化**：§6.5 建议检查轨道归一化与电子密度积分。必须同时检查电子总数、α/β 电子数及占据和；ECP/EDF 是否计入核心电子会改变积分的期望值。
- **自旋/占据**：保留 α/β、RO 与分数占据语义；不按“所有占据都是2”重建密度。`.wfn/.wfx` 没有通用的完整虚轨道载体能力，涉及 LUMO 或激发态时优先 `.molden.input/.mwfn`。
- **ECP**：ORCA ≥6.0 的 Molden `[Pseudo]` 能提供有效核电荷，Multiwfn 会读取；标题必须保留 `orca` 标识。不要对这类文件套用旧教程的手工核电荷修改。§6.4 的 EDF 核密度补偿需要记录 `isupplyEDF/readEDF`；它不能补回 ELF 等依赖轨道的内核信息，也不改变 ESP 的有效核处理。
- **相关密度**：普通 SCF `.gbw` 或其 Molden 不能自动代表 MP2/CC 的相关密度。需要目标密度的自然轨道与占据，或受支持的目标密度通道；ORCA §9.3 支持 `.mp2nat/.uno/.qro` 等波函数文件，密度导出还涉及 `.densities`。必须保存方法、态和 relaxed/unrelaxed 标签；未验证前不承诺统一转换。

这些检查仅是后续适配器的验收要求，目前没有实现或获得通过结论。

## 功能与最小输入矩阵

下表用于拆分模块。波函数列中的“WF”表示包含几何、基组、MO 与正确占据/自旋的、已验证的 `.molden.input/.mwfn`，不是单独 XYZ 或日志。

| 功能 | 最小输入/额外条件 | 建议职责 |
|---|---|---|
| 能量、SCF/几何收敛、优化轨迹 | ORCA 输出、结构/轨迹、property JSON；任务与步骤必须关联 | OrcaView 原生结果适配 |
| 振动动画、IR/Raman | ORCA 频率、强度、正常模；`.hess`/结构化结果及原始日志 | 原生读取；谱线展宽独立 |
| NMR、UV-Vis/ECD 谱 | ORCA 对应性质与态表；需区分单位、强度定义、参考与展宽参数 | 原生读取优先；Multiwfn 谱图工具可选 |
| MO/密度等值面 | ORCA `orca_plot` 的 Cube，或 WF→Multiwfn 网格 | 共用 Cube/Surface 渲染；不重复科学引擎 |
| 原子电荷与键级 | WF；Hirshfeld/CM5/数值积分与 Mayer/Wiberg 的依赖不同 | 可选 Multiwfn 模块；保留算法与基组标签 |
| ESP、表面映射 | WF + 正确有效核电荷；表面定义及网格参数 | Multiwfn 计算，OrcaView 显示与导出 |
| RDG/NCI、IRI、IGMH | WF；需成对的等值面场和 sign(λ₂)ρ 等着色场；IGMH 需片段定义 | Multiwfn 计算，共用体数据渲染 |
| promolecular RDG、IGM/mIGM | 仅几何可行，采用原子密度近似；必须明确标记近似 | 独立近似任务；不冒充真实分子密度 |
| ELF/LOL | WF 与相应轨道信息；ECP 内核解释受限 | 后续 Multiwfn 体数据模块 |
| QTAIM | WF/受支持密度及导数；临界点搜索、路径、积分精度独立验收 | 后续拓扑模型；单个 Cube 不等于完整 QTAIM |
| hole–electron、CT、NTO | 参考态 WF + 对应激发态系数，常需 `.out + .json`；见下节 | 最后启用已验证态型与数据通道 |

依据章节：§3.9 电荷、§3.11 键级、§3.13 谱图、§3.14 拓扑、§3.15 表面、§3.21 激发态、§3.23 弱相互作用，以及 ORCA 对应性质章节。Wiberg 的 Löwdin 与 NAO 定义不同，不能合并为未注明定义的“Wiberg键级”；NBO 专有分析也不能仅因有 Multiwfn 就声称已实现。

## 激发态：当前 JSON 路径与降级行为

### 闭壳层常规 TDDFT 的官方准备步骤

Multiwfn 在线手册 §3.21.A.3 现在明确提供 ORCA TDDFT 的 JSON 路径：

1. 保留同一次 TDDFT 计算的 `TDDFT.out` 和 `TDDFT.gbw`。
2. 通过 `orca_2mkl TDDFT -molden` 得到参考态波函数 `TDDFT.molden.input`。
3. 在同目录创建 `TDDFT.json.conf`：

   ```json
   {
     "CIS": true,
     "CISNRoots": true
   }
   ```

4. 运行同套 ORCA 的 `orca_2json TDDFT.gbw`，生成 `TDDFT.json`。
5. Multiwfn 启动时加载参考态 Molden/MWFN；进入相关分析时指定 `TDDFT.out`。它会寻找同目录、同 basename 的 `TDDFT.json` 来加载构型系数。

ORCA §9.3.2.4 确认上述 `CIS/CISNRoots` 配置；§5.6.13 说明 TDDFT 振幅默认保存在 GBW。此 **ORCA 6.1 的文档路径没有要求单独 `.cis` 文件**。不能将旧版本的 `.cis` 依赖机械加入，也不能据此声称所有旧版本或其他激发态方法都不需旁文件。转换阶段应保留原任务相关文件并用实际工具验证。

这里的 `TDDFT.json` 是波函数/振幅导出，**不是** `TDDFT.property.json`；设置 `%output JSONPropFile true` 不能替代上述构型系数输出。也不能把某次任务的 Molden 与另一次任务的 JSON 组合使用。

### 源码支持范围

- `excittrans.f90:720–838`（`loadallexccoeff`）发现同名 JSON 后优先使用；`732–736` 在 `wfntype /= 0` 时回退到输出文本。
- `excittrans.f90:1217–1237`（`loadexccoeff`）有相同意图，但该保护还受 `ioutinfo == 1` 条件影响。因此 OrcaView 应在进入工具前自行限制已验证态型，不能根据有无一行警告推断安全。
- `excittrans.f90:761–802` 和 `1284–1307` 读取 X+Y 与 X−Y，再分别恢复 excitation X、de-excitation Y。`OrbWin`、`IRoot` 及轨道索引也参与读取；这不是任意 JSON 都能满足的接口。
- 首批兼容 Profile 应只将 **`wfntype == 0` 的闭壳层单行列式参考态**列为此通道的待验证对象，不能扩展成所有开壳层、RO、SF、SOC、相关参考态均可用。源码中的提示字符串有反向措辞，判断应依据条件与实际回退路径。

### 原始 `.out` 路径

对于 CIS/TDA，手册建议设置 `%tddft/%cis` 的 `TPrint 1E-8` 以保留足够构型。只有输出贡献的完整 TDDFT 文本不包含完整的分离 X/Y，缺 JSON 时不能当作与 JSON 路径等价的可靠输入；源码仍保留该文本回退，因此 OrcaView 需要显式拒绝或标记未验证，不能静默降级为科学成功。

SF-TDDFT 的 hole–electron 等少数功能与常规 TDDFT 是不同能力；手册明确排除该情形基于转移密度矩阵的 NTO。sTDA/sTDDFT 输出仅保留少数构型，TPrint 不改善此限制，需检查构型归一化。不要把三者共用一个“支持激发态”开关。

ORCA 本身支持 `DoNTO/NTOStates` 并输出 `.sN.nto`。原生 NTO 展示可独立实现，不需要先完成 Multiwfn 空穴电子全分析；NTO 双杂化 PT2、SOC 等适用范围仍按方法分别注明。

## 批处理与首批模块建议

§5.2/§5.3 确认可以将交互输入流送给 Multiwfn，并用 `-silent` 避免弹出图形。该机制是**交互菜单协议**，不是稳定 JSON API。Profile 应记录日期版本、二进制/设置/输入脚本哈希、期望提示与文件，以及完成证据。脚本应正确退出，不能把 EOF 引发的异常一概当作成功。

建议先后顺序：

1. 波函数导入/转换及验证，数值表和 Cube 结果契约；用小闭壳层全电子、开壳层、ECP、含高角动量基组构成独立样例组。
2. 电荷/键级表、MO/密度、ESP 表面，再接 IRI/RDG 的成对体数据。
3. ELF/LOL、IGMH、QTAIM 的方法与精度专项验收。
4. 闭壳层 TDDFT JSON、CIS/TDA，再分别研究其他激发态能力。

每个任务使用独立运行目录，保留标准输出、错误输出、输入流与设置副本，避免 Multiwfn 的固定产物名互相覆盖。取消、超时、提示漂移、缺失/陈旧产物应成为明确状态；退出码与“文件存在”都不足以单独证明分析完成。

本文件没有增加运行能力，也没有改变现有 OrcaView 基础输入模板。所有建议模块仍需真实 ORCA→转换器→Multiwfn 的端到端验收。

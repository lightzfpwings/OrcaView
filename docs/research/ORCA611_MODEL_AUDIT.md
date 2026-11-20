# ORCA 6.1.1 电子结构方法核对

网页和 PDF 都标识为 6.1.1。下表使用 PDF 阅读器从 1 开始的物理页码。例如，物理第 498 页的页脚是第 478 页。同一标题在两个版本中可能采用不同表号。[网页手册](https://orca-manual.mpi-muelheim.mpg.de/index.html) · [官方 PDF](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf)

## 逐项检查了哪些关键词

对照程序从网页关键词列读取 269 个条目，在指定章节的 PDF 页面上查找每个拼写，并核对软件目录、组合选项或专用输入。这个数字包括同义词和组合关键词。它表示表格条目数，不等于独立物理方法数。程序按关键词核查，公式和数值系数需另行核对。[对照程序](../../tools/audit_orca_models.py)

| 网页表 | 内容 | PDF 表 | PDF 物理页 | 网页关键词条目 |
|---|---|---|---:|---:|
| 3.1、3.2 | 局域泛函与（meta-）GGA | 同号 | 225–226 | 7、24 |
| 3.4、3.6 | 全局、范围分离杂化泛函 | 同号 | 229–230、233–234 | 25、16 |
| 3.8、3.9 | 全局、范围分离双杂化，含激发态专用参数化 | 同号 | 236–238 | 33、18 |
| 3.12 | `! LibXC(Keyword)` 简单输入 | 同号 | 242–244 | 117 |
| 3.22 | 半经验 NDO 简单输入 | 同号 | 261 | 8 |
| 3.47、3.48、3.49 | MCPDFT、srDFT、CI-DFT | 3.48、3.49、3.50 | 498、499、501–502 | 6、6、9 |

复核时可将官方 PDF 用 `pdftotext -layout orca.pdf manual-layout.txt` 提取，然后执行以下命令。`HTML_ROOT` 是包含 `contents/` 的手册镜像目录，维护脚本使用 lxml。

```sh
PYTHONPATH=src python tools/audit_orca_models.py "$HTML_ROOT" manual-layout.txt
```

## 输入生成与相互约束

- **双杂化基态能量**。新增 `PR2SCAN50`、`PR2SCAN69`、`KPR2SCAN`、`WB97X-2`、`WPR2SCAN50` 及两种历史 DSD-D3BJ 参数化。历史 DSD 会写出父泛函和 `D3BJ` 两个独立词。默认采用对应的相关拟合基组。32 个局域双杂化单点预设通过 `%mp2 DLPNO true end` 选择局域相关。κ 正则化方法保留常规或 RI-MP2 的算法限制。参见 PDF 物理页 235–239、300。[DFT §3.3.5](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/DensityFunctionalTheory.html#double-hybrid-functionals) · [MP2 §3.9](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/MP2.html)
- **双杂化激发能**。24 个参考泛函各可做 TD 或 TDA，包括表 3.8、3.9 下方的全部 14 种激发态专用参数化。导出显式 `nroots`、`tda` 和 `dcorr 1`，分配 AuxC。表内的 `SCS/SOS-B2PLYP21` 与 `SCS/SOS-WB2PLYP` 各表示一个拟合参数组，斜杠是关键词的一部分。四个分量的激发态系数由 ORCA 在 TD/TDA 时应用。当前预设采用闭壳层单重参考和固定几何。通用 TD-DFT/TDA-DFT 现在可另外选择 37 种原生参考泛函，历史默认仍为 B3LYP。参见 PDF 物理页 236–238、824–827。[DFT §3.3](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/DensityFunctionalTheory.html) · [激发态双激发修正 §5.6.9](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/tddft.html#double-hybrid-functionals-and-doubles-correction)
- **ωB97M(2)**。水分子 Compound 示例已在 macOS arm64 的 ORCA 6.1.1 上正常结束，归档输入与仓库示例逐字节一致。第一步收敛 ωB97M-V 轨道，得到 −76.429725928501 Eh（输出第 883 行）。第二步通过 `ReadMOs(1)` 读取第一步的轨道文件 `job_Compound_1.gbw`（第 1413 行），以 `NoIter CalcGuessEnergy` 和 RI-MP2 修正得到 ωB97M(2) 总能量 −76.468167713548 Eh（第 1706 行）。Compound 脚本从 `MP2_Total_Energy[2]` 读取并打印的数值与此一致（第 1810 行）。方法说明见 §3.3.5.2.1 与 §8.2，双杂化示例见 PDF 物理页 238–239。[水分子输入](../../examples/native_methods/water-wb97m2.inp) · [本机运行输出](../../artifacts/public/validation/ORCA-6.1.1-macOS-arm64/compound-wb97m2/job.out) · [Compound §8.2](https://orca-manual.mpi-muelheim.mpg.de/contents/workflowsautomatization/compound.html)
- **半经验**。表 3.22 与 3.23 分别列简单输入词和块内枚举。CNDO/INDO 的 1、2、S 版本导出 `%method Method CNDO_1` 等对应字段，ZINDO、ZNDDO 按表使用简单关键词。光谱用 S 参数组限制在固定几何；`ZINDO/S-CIS` 额外要求激发根数。界面禁用轨道基组和初始 GBW。ORCA 内置各元素参数的完整分布仍需以引擎核实。参见 PDF 物理页 257–262、807–809。[半经验方法 §3.5.1](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/semiempirical.html) · [CIS §5.6.2](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/tddft.html#semiempirical-methods)
- **MP2、MDCI 与 EOM**。MP2 表 3.34 的 RI、SCS/SOS、OO 和 F12 别名统一导出对应的规范关键词。两版都重复使用 `SCS-MP2` 和 `RI-SCS-MP2` 来描述相反自旋缩放。软件保留表内另有明列的 `RI-SOS-MP2` 及其别名，避免把 SCS 误译成 SOS。表 3.43 把 AO、AOX、MO、RI、RI34 定义为积分算法。常规 RI-CCSD 与 RI-CCSD(T) 的 KC_RI 不支持 UHF，导出时同时检查实际多重度和显式参考。§5.9 IP/EA 开壳层要求选取一个电离或附着自旋通道。MR-EOM 表的三个简单关键词见网页表 3.53、PDF 表 3.54，物理页 565。相关章节为物理页 300–301、347–350、881–896。[MP2 §3.9](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/MP2.html) · [MDCI §3.10](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mdci.html) · [EOM §5.9](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/eom.html)
- **活性空间**。21 个 CASDFT 关键词都生成 `TRAH` 和完整的 `%casscf`。CI-DFT、SA-CASSCF、SA-SC-NEVPT2、QD-SC-NEVPT2 都核对目标根数与给定电子数、轨道数及多重度下的自旋适配组态数。QD 采用手册建议的 Van Vleck 有效哈密顿量。DMRG-CASCI 使用 `CIStep DMRGCI` 与 `MaxIter 1`，依赖外部 DMRG 程序。参见 PDF 物理页 365–382、469–472、487–491、497–502。[CASSCF §3.13](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/CASSCF.html) · [DMRG §3.15](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/dmrg.html) · [NEVPT2 §3.16](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/NEVPT2.html) · [CASDFT §3.18](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/casdft.html)
- **RASSCF 与 ORMAS**。两个原生输入均采用完整水分子几何、4 电子 4 轨道、单重态和单根。RASSCF 示例中 RAS1 有 1 个轨道，最多留 1 个空穴，RAS2 有 2 个轨道，RAS3 有 1 个轨道且最多占据 1 个电子。ORMAS 示例将轨道分成 2、1、1 三组，分别允许 2–4、0–2、0–1 个电子，总数固定为 4。两版手册的具体示例都使用斜杠分隔 ORMAS 子空间。可在原生输入编辑器打开、修改并另存这些文件，再用 ORCA 运行。多组约束以单个构造表达式写在 `%casscf refs` 内，结构化标量面板尚未提供对应的分区编辑。分区还决定哪些轨道间允许电子跃迁，应用到其他体系时应检查轨道顺序。见 PDF 物理页 379–380。[RASSCF 水分子输入](../../examples/native_methods/water-rasscf.inp) · [ORMAS 水分子输入](../../examples/native_methods/water-ormas.inp) · [CASSCF §3.13.3](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/CASSCF.html#restricted-active-space-ras)
- **多组态响应**。MCRPA/MCTDA 先收敛单态根 CASSCF，再在独立的 `%mcrpa` 块指定响应根数及 TDA 开关。响应根数可以大于给定活性空间的单个自旋组态块维数，因为响应还包括轨道自由度。默认直接 Fock 构造配 AuxC，绕开当前不支持的 RIJK。参见 PDF 物理页 873–880。[MCRPA §5.8](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/mcrpa.html)

## 仍需分别验证的范围

上述逐表比对可以复核参数名是否出现在两版手册中，以及软件能否表达它。输入渲染与冻结测试能覆盖所有目录预设。实际 ORCA 可执行文件、对应操作系统上的外部库、元素参数、内存和数值收敛仍影响能否完成科学计算。

单多重度和等权根覆盖了本次活性空间模板。任意多重度块、非等权态平均、混合自旋块和外部 DMRG sweep 计划需要进一步的结构化编辑。基于用户自选占据的 CVS/IP、通用 MRCC 阶数、各个 LibXC 组件及其外部参数、依赖体系的 MM 力场和 QMMM 拓扑，同样应按具体输入工作流核查。117 项 LibXC 数字指表 3.12 的简单关键词。激发态能量模板名单也不覆盖每个激发态解析梯度、势能面跟踪及导数耦合作业。统计未包括光谱模拟、布居与波函数分析。

# ORCA 6.1.1 高级输入块交叉核对

核对对象为 OrcaView 在折叠输入块中提供的字段。按“完整嵌套路径＋关键字”去重后共 303 项，其中通用参数 128 项、求解器参数 147 项、溶剂和 IRC 专用参数 28 项。同名字段出现在不同层级时分别核对。选择作业、方法、积分近似、活性空间和目标根数时由模板写入的值另计。

PDF 封面标为 *ORCA Manual, Release 6.1.1*，日期为 2025-12-02，共 1601 页，SHA-256 为 `4df05dcc1126d7816b1770367e29388bb69d079b5ee7b907b939cc7c46830c92`。官网按钮的下载文件名仍含 6_1_0。下表使用 PDF 阅读器的物理页码，从封面第 1 页开始。每行链接打开相应 HTML 章节。 [官方 PDF](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf) · [网页版首页](https://orca-manual.mpi-muelheim.mpg.de/index.html)

## 字段对照

对实际方法和作业枚举 `catalog_options` 与 `solver_options`，展开参考类型、显式积分近似和色散的条件分支。逐字段在对应 HTML 正文和 PDF 同章页段匹配原生名称，再核对子块示例、表格和正文给出的算法条件。下表给出字段所在的来源，整数、实数、开关、枚举和字段间校验在两份目录中实现。未填写的值交由 ORCA 决定。

| 输入位置与用途 | 交叉核对的原生字段 | PDF 物理页及对应网页 |
|---|---|---|
| `%output` 输出详细程度 | `PrintLevel` | [56–59](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/output.html) |
| `%scf` 自动读取同名 GBW | `AutoStart` | [213–215](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/initialguess.html) |
| `%scf` 原生 xTB | `SmearTemp` `UseXTBMixer` | [257–267](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/semiempirical.html) |
| `%scf` 收敛与切换 | `AutoTRAH` `AutoTRAHIter` `AutoTRAHNInter` `AutoTRAHTol` `CNVDIIS` `CNVDamp` `CNVSOSCF` `CNVShift` `CNVZerner` `ConvCheckMode` `ConvForced` `Convergence` `DIISBFac` `DIISMaxEq` `DIISMaxIt` `DIISStart` `DampErr` `DampFac` `DampMax` `DampMin` `LShift` `MaxIter` `SOSCFMaxIt` `SOSCFStart` `ShiftErr` `TCut` `Thresh` `TolE` `TolErr` `TolG` `TolMaxP` `TolRMSP` `TolX` | [65–77](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/scf.html) |
| `%scf.trah` 轨道更新与预条件 | `AlphaMax` `AlphaMin` `InactiveMOs` `MaxNoise` `MaxRed` `MinTolMicro` `NStart` `OrbUpdate` `PreconMaxRed` `Precond` `PseudoRand` `QuadRegionStart` `Randomize` `TolFacMicro` `tradius` | [73–74](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/scf.html) |
| `%method` CP-SCF | `Z_COSX_Alg` `Z_GridX` `Z_GridXC` `Z_GridX_RHS` `Z_IntAccX` `Z_IntAccXC` `Z_MaxDIIS` `Z_MaxIter` `Z_Shift` `Z_Solver` `Z_Tol` | [215–217](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/cpscf.html)、[121–123](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/numericalintegration.html) |
| `%method` 色散系数 | `D3A1` `D3A2` `D3RS6` `D3S6` `D3S8` `D3alpha6` `D4A1` `D4A2` `D4S6` `D4S8` `D4S9` | [245–257](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/dispersioncorrections.html) |
| `%method` 解析 DFT | `ADFTLmaxAuxJ` `ADFTLmaxAuxX` `ADFTNRMaxIter` `ADFTNRTol` | [271–274](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/analyticDFT.html) |
| `%method` LibXC 阈值 | `LibXCDensityThreshold` `LibXCTauThreshold` `LibXCZetaThreshold` | [239–245](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/DensityFunctionalTheory.html) |
| `%method` 短程 CASDFT | `RangeSepMu` | [497–502](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/casdft.html) |
| `%method` 随机相位近似的能量积分 | `RPACNPoints` | [274–275](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/RPA.html) |
| `%method` 冻结芯轨道 | `CheckFrozenCore` `CorrectFrozenCore` | [214–216](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/frozencore.html) |
| `%method` COSX 交换积分及重叠拟合 | `COSX_IntSymmetry` `COSX_PartialContraction` `SFitInvertType` `SInvThresh` `UseQGradFit` `UseSFitting` | [114–119](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/RI.html) |
| `%method` 交换关联积分网格 | `AngularGrid` `BFCut` `GridPruning` `HGridReduced` `IntAcc` `NThetaMax` `WeightCut` | [119–123](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/numericalintegration.html) |
| `%geom` P-RFO 过渡态优化 | `HESS_MinEV` `HESS_Modification` | [630–631](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/optimizations_TS.html) |
| `%geom` 优化坐标与 Hessian | `AddExtraBonds` `AddExtraBonds_MaxDist` `AddExtraBonds_MaxLength` `Calc_Hess` `Convergence` `InHess` `MaxIter` `MaxStep` `NResetHess` `NStepsInResetHess` `NumHess` `ProjectTR` `Recalc_Hess` `Step` `TolE` `TolMaxD` `TolMaxG` `TolRMSD` `TolRMSG` `Trust` `Update` `coordsys` `freezeHydrogens` `optimizeHydrogens` | [601–620](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/optimizations.html) |
| `%freq` 解析或数值 Hessian | `CentralDiff` `Increment` `NumHessTransInvar` `ProjectTR` `TransInvar` | [653–658](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/frequencies.html) |
| `%casscf` 轨道优化 | `ActConstraints` `DIISThresh` `DThresh` `ETol` `GTol` `GradScaling` `MaxDIIS` `MaxIter` `MaxRot` `MinShift` `OrbStep` `ShiftDn` `ShiftUp` `SwitchConv` `SwitchIter` `SwitchStep` | [367–388](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/CASSCF.html) |
| `%casscf.CI` CI 与 ICE | `ETol` `ICEType` `MaxDim` `MaxIter` `NGuessMat` `RTol` `TGen` `TVar` | [376–386](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/CASSCF.html)、[451–469](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/iceci.html) |
| `%casscf.aughess` NR 增广 Hessian | `Compress` `DiagShift` `ExactDiagSwitch` `MaxDIIS` `MaxDim` `MaxIter` `NGuessMat` `SecShift` `Solver` `Tol` `UpdateShift` `UseDiagPrec` `UseSubMatrixGuess` | [370–373](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/CASSCF.html)、[384–387](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/CASSCF.html) |
| `%casscf.dmrg` DMRG 扫描 | `MaxIter` `SweepTol` `auto_ordering` `hf_occ` `maxM` `startM` `switch_rst` `warmup` | [469–476](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/dmrg.html) |
| `%casscf.PTSettings` 多参考微扰 | `CASPT2_IPEAshift` `CASPT2_ishift` `CASPT2_rshift` `D3TPre` `D4Step` `D4TPre` `MaxDIIS` `MaxIter` `NThresh` `TReg` `imaginary` | [481–493](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/NEVPT2.html)、[493–497](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/caspt2.html) |
| `%mrci` 未收缩多参考 CI | `Etol` `MaxIter` `Rtol` `TPre` `TSel` | [502–558](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mrci.html) |
| `%autoci` 自动生成的关联求解器 | `DIISStartIter` `LevelShift` `MaxDIIS` `MaxIter` `NThresh` `STol` | [350–364](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/autoci.html) |
| `%mrcc` 外部 MRCC | `ETol` | [364–365](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mrcc.html) |
| `%cim` 局域团簇构造 | `CIMTHRESH` | [324–329](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mdci.html) |
| `%mcrpa` 多组态响应求解器 | `MaxIter` `MaxRed` `PreConMaxRed` `PreCond` `TolR` | [878–881](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/mcrpa.html) |
| `%tddft` 响应求解器与 XC 网格 | `ETol` `GridXC` `IntAccXC` `MaxDim` `MaxIter` `NGuessMat` `RTol` | [805–850](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/tddft.html)、[122–123](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/numericalintegration.html) |
| `%rocis` 高自旋限制性 CI | `ETol` `MaxDim` `MaxIter` `NGuessMat` `RTol` | [850–873](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/rocis.html) |
| `%mdci` EOM 与相关 Davidson 控制 | `CheckEachRoot` `DTol` `DoRootwise` `FollowCIS` `NDav` `NInits` `OTol` `RootHoming` `UseCISUpdate` | [881–889](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/eom.html)、[741–761](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/excitedstates.html) |
| `%mdci` STEOM 活性空间 | `DoDbFilter` `DoNewActSch` `EASThrs` `IPSThrs` `NRootsCISNAT` `OThresh` `VThresh` | [889–896](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/steom.html) |
| `%mdci` 基态振幅、积分变换及局域阈值 | `KCOpt` `LShift` `MaxDIIS` `MaxIter` `PAOOverlapThresh` `STol` `TCutDO` `TCutDeloc` `TCutMKN` `TCutOSV` `TCutPNO` `TCutPairs` `TCutTNO` `TrafoType` `Triples` | [301–350](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mdci.html) |
| `%mp2` MP2 积分算法、正则化及局域阈值 | `DIISStart_PNO` `Damp1_PNO` `Damp2_PNO` `DoRegMP2` `FCut` `LocMet` `LocTol` `MP2Shift` `MP2Shift_PNO` `MaxCore` `MaxDIIS_PNO` `MaxLocIter` `MaxOrbIter` `MaxPNOIter` `PAOOverlapThresh` `Q1Opt` `RegMP2Kappa` `RegMP2Sigma` `RegMP2Type` `ScaleTCutC_MO` `TCutC` `TCutDO` `TCutDOPre` `TCutDOij` `TCutMKN` `TCutPNO` `TCutPre` `TolE` `TolR` | [275–301](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/MP2.html) |
| `%cpcm` C-PCM、耦合簇与 SMD | `epsilon` `refrac` `CPCMccm` `SMD18` `soln` `soln25` `sola` `solb` `solg` `solc` `solh` | [141–166](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/solvationmodels.html) |
| `%xtb` 自定义 ddCOSMO 介质 | `EPSILON` | [262–266](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/semiempirical.html) |
| `%irc` 初始位移、校正及收敛 | `MaxIter` `Direction` `InitHess` `hessMode` `Init_Displ_DE` `Scale_Init_Displ` `DE_Init_Displ` `Scale_Displ_SD` `Adapt_Scale_Displ` `SD_ParabolicFit` `Interpolate_only` `Do_SD_Corr` `Scale_Displ_SD_Corr` `SD_Corr_ParabolicFit` `TolRMSG` `TolMaxG` | [631–634](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/irc.html) |

## 容易生成无效或无效用输入的组合

- 静态阻尼 `CNVDamp` 和动态阻尼 `CNVZerner` 互斥。可以关闭前者并启用后者。TRAH 的 `PreconMaxRed` 只在完整 Hessian 预条件器下有效，关闭随机扰动后不接受扰动幅度。参见 PDF 70、73–74 页。 [SCF](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/scf.html)
- `%method Z_GridX_RHS` 从 SCF 已有的三个 COSX 网格中选取一个，用于 MP2 导数右端。`Z_GridX` 则选择响应方程左端的角向网格。显式 DEFGRID 预设、交换关联网格、COSX 网格、数值频率和解析 CP-SCF 分别按所选方法处理。参见 PDF 121–123、215–217 页。 [数值积分](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/numericalintegration.html) · [CP-SCF](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/cpscf.html)
- SP 和独立 FREQ 不提供 `%geom`。普通优化允许 qn、rfo，OptTS 使用 P-RFO 并开放其 Hessian 修正。冗余内坐标拒绝开启 `%geom ProjectTR`。BFGS Hessian 重建依赖更新算法，OptTS 默认 Bofill。频率中的同名 `%freq ProjectTR` 独立控制 Hessian 的转动平移投影。参见 PDF 618–620、630–631、653–657 页。 [几何优化](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/optimizations.html) · [过渡态](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/optimizations_TS.html) · [频率](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/frequencies.html)
- 表 3.43 与 §3.10.14 区分 SCF 的积分近似和 MDCI 的关联积分处理。`KCOpt` 指定含三、四个外部指标的处理，`TrafoType` 指定积分变换。完整四指标 MO、预存 AO、AO 直接、部分 RI、全 RI 可用这两项表达。`KC_MO` 与显式部分或 RI 变换冲突。三、四外部指标采用 RI 时需要关联辅助基组，`KC_RI`、`KC_RI2`、`KC_AO`、`KC_AOBLAS` 对参考波函数有限制。命名 DLPNO/F12/EOM 模板分别走自己的算法。参见 PDF 309–310、347–350 页。 [MDCI](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mdci.html)
- 正则化 MP2 只开放单点能量。常规 MP2 需要内存算法。RI-MP2 接受手册列出的三类处理，采用无歧义的输入拼写。DLPNO 的截断随 PNO 预设联动，三电子激发 TNO 截断只用于含相应激发的 DLPNO-CCSD 模板。参见 PDF 275–276、286–287、300、338–339 页。 [MP2](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/MP2.html) · [MDCI](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mdci.html)
- 定轨道 CASCI 固定宏迭代为 1。DMRG 的子块使用自己的迭代与扫描设置。NR 的 `aughess` 需要一个 NR 阶段，Davidson 维数、DIIS 向量数再按所选求解器检查。CASDFT 保留 TRAH，MCRPA 的 `PreConMaxRed` 依赖完整预条件器。CASPT2-K 的 `TReg` 和 FIC-NEVPT2 的 `imaginary` 分别绑定对应模型。参见 PDF 369–373、474–475、483、496–501、880–881 页。 [CASSCF](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/CASSCF.html) · [CASDFT](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/casdft.html) · [MCRPA](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/mcrpa.html)

## 两种载体的歧义与保留项

- HTML 和 PDF 表 2.44（PDF 第 118 页）均把 `RIJDX` 列在 RIJONX 和 RIJCOSX 两行。§3.9.18 又把 RIJDX 与 RIJCOSX 分列。输入使用规范的 `RIJONX`、`RIJCOSX`、`RI-JK`。 同表把关闭 Split-RI-J 一行的说明误写成启用，§2.8.2 正文明确给出关闭操作。 [RI](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/RI.html) · [MP2](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/MP2.html)
- 两版中 EOM 正文以布尔值示例说明 `NRootsPerBatch`，表 5.11、5.12 却列整数；正文还特别指出批次算法的 RHF 适用范围。该项保留为资料项，尚未加入表单。参见 PDF 887–889 页。 [EOM](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/eom.html)
- CASSCF 正文提到 `MaxRot` 默认 0.2，输入示例使用 0.05；ROCIS 的 `MaxDim` 示例与关键词表也给出不同数值。软件保留空值，用户可以主动覆盖。参见 PDF 370、851、872 页。 [CASSCF](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/CASSCF.html) · [ROCIS](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/rocis.html)
- ORCA 原生语法还包括按原子或轨道指定的数组、重复子块、索引和外部文件。`TS_Mode`、`Constraints`、`Hybrid_Hess`、`selectedRoots[block]`、RAS/ORMAS 划分、DMRG 自定义扫描计划或读取 Hessian 的 `InHessName` 都需要专门编辑器和体系/文件校验。上述字段尚未全部实现。只影响输出、布居、振动热化学、谱图等独立分析的设置未列入计算表单。 [几何优化](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/optimizations.html) · [CASPT2](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/caspt2.html) · [DMRG](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/dmrg.html)

## 复核方法

在仓库根目录执行以下命令。`manual-html` 是含官方 `contents/` 章节树的手册镜像。`pdftotext` 来自 Poppler，核对脚本只使用 Python 标准库和本工程。

```sh
pdftotext -layout orca.pdf manual-layout.txt
PYTHONPATH=src python3 tools/audit_orca_blocks.py manual-html manual-layout.txt
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*block_options.py'
```

本次脚本输出为 `Common 126, solver 147, solvent/path 28, distinct 301, matched in both sources 301`。加 `--show-fields` 可逐项输出匹配的 HTML 章节和该词在对应页段内的首个 PDF 物理页。脚本同时检查软件目录新增未登记字段、证据表中已经失效的字段，以及任一载体缺失的拼写。类型、嵌套关系和科学适用性仍需阅读该处上下文。21 项定向测试覆盖输入生成、模板归属、算法开关和互斥条件。其结果不能单独证明每个分子、方法和参数组合在 ORCA 中都能成功运行。 [核对脚本](../../tools/audit_orca_blocks.py)

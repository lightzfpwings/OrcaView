# ORCA 6.1.1 计算方法

按 ⌘K 可跨类别查找方法（例如 EOM）；也可用右侧的“方法类别”和“计算方法”逐级选择。窗口底部显示将导出的 ORCA 输入。0.1.0a5 的目录包含 **45 类、568 个命名预设和 417 个可选择的轨道基组**。命名预设包括不同实现、显式相关变体、色散参数化及 CBS 外推方案，计数只算目录条目。运行 `orcaview methods` 列出实际安装版本的全部条目，运行 `orcaview methods 'EOM-CCSD'` 查看该方法的适用设置。[ORCA 6.1.1 用户手册](https://orca-manual.mpi-muelheim.mpg.de/index.html)

| 方法类别 | 选择后生成的输入 |
|---|---|
| HF、LDA、GGA、meta-GGA、全局和范围分离杂化泛函 | 使用选定的轨道基组。SCAN 使用 ORCA 关键词 `SCANFUNC`，M06-2X 使用 `M062X`。两种 B3LYP 参数化分别保留 `B3LYP` 和 `B3LYP/G`。[DFT](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/DensityFunctionalTheory.html) |
| 双杂化和色散校正组合 | 双杂化配相应的关联拟合基组，如 `B2PLYP def2-TZVP def2-TZVP/C`。显式组合如 `B3LYP-D3(BJ)` 写为 `B3LYP D3BJ`。已有内置校正的 `WB97X-D3BJ` 保留独立关键词。[色散校正](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/dispersioncorrections.html) |
| 3c、NDDO 和原生 xTB | 采用各自规定的基组或参数。原生 xTB 保留 `Native-` 前缀。NDDO 模板开放 H、C、N、O、F、Si、P、S、Cl、Br、I 的组合。[复合方法](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/3cmethods.html) · [半经验方法](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/semiempirical.html) |
| MP2、MP3、耦合簇、CI 与电子对方法 | 可选择常规、RI 和目录中列出的 DLPNO 变体。RI-MP2 可做优化和数值频率，CCSD(T)、DLPNO-CCSD(T) 等在本版提供单点模板。[微扰理论](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/MP2.html) · [耦合簇与 CI](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mdci.html) |
| CASSCF、SC-NEVPT2 | 输入活性电子数和活性轨道数，生成指定多重度的单根 `%casscf`。程序检查活性电子、空穴和自旋是否相容，并考虑 def2 有效核势移除的电子。实际选入哪些轨道仍需检查初猜和计算输出。[CASSCF](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/CASSCF.html) · [NEVPT2](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/NEVPT2.html) |
| TD-DFT、TDA-DFT、CIS | 生成垂直激发能单点任务。在 TD-DFT / TDA-DFT 中可选参考泛函和激发根数。CIS 使用 HF 参考；TD-DFT 显式关闭 Tamm–Dancoff 近似。闭壳层沿用默认单重激发通道。[垂直激发态](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/tddft.html) |
| EOM、STEOM、ADC 与 ROCIS | 包括 EE、IP、EA、CCSD(2)、反变换 PNO、局域变体和高自旋 ROCIS/DFT。开壳层 IP/EA-EOM 的常规和反变换 PNO 版本须选电子通道。目标根数写入对应的 `%mdci` 或 `%rocis`。ROCIS/DFT 使用 B3LYP 与手册三参数。[EOM](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/eom.html) · [ROCIS](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/rocis.html) |
| 多参考关联 | 包括 CASCI、ICE、DMRG、CASPT2/K、NEVPT2、DCD-CAS(2)、内收缩及未收缩 MRCI、MRDDCI 与 MR-EOM。MR-EOM 模板将一个多重度的等权平均根数同时用于参考态和最终对角化。DMRG-CASSCF 的执行环境需提供手册指定的 Linux BLOCK 接口。[MR-EOM](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mreom.html) · [MRCI](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mrci.html) · [DMRG](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/dmrg.html) |
| 显式相关 F12 和局域关联 | 22 个 F12 预设涵盖 MP2、CC、QCI、CEPA 以及 RI、DLPNO、C/D 近似。F12 的 CABS 和 RI 的关联拟合基组分别指定。DLPNO-MP2-F12 的 C/D 两种模板均需要 RHF。局域关联还可设置 PNO 阈值，CIM 预设仅开放闭壳层，执行时还需留意手册所列 Windows 并行限制。[MP2](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/MP2.html) · [F12、CBS 与 CIM](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mdci.html) |
| 其他能量模型与实现 | 117 个表 3.12 所列 LibXC 简写、22 个单参考 AUTOCI 预设、实验性 ADFT、PBE 参考的直接 RPA 关联、FCI、外部 MRCC、外部 xTB/GFN-FF。界面为 LibXC 简写提供单点模板。MRCC 只接受闭壳层，外部 MRCC 和 xTB 需要在实际运行 ORCA 的机器上配置对应程序，外部 xTB 的接口文件名为 otool_xtb。[LibXC](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/DensityFunctionalTheory.html) · [AUTOCI](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/autoci.html) · [MRCC](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mrcc.html) |
| 完备基组极限 CBS | 可为 HF、MP2、CCSD 或 CCSD(T) 选择 2/3 或 3/4 两点外推，基组序列有 cc、aug-cc 和 def2。ORCA 按序列安排两次计算。6.1.1 手册已将这组内置外推关键词标为弃用。[基组外推](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mdci.html#automatic-extrapolation-to-the-basis-set-limit) |

## 近似和辅助基组

- **SCF 积分**。按方法可选 RI、Split-RI-J、NoSplit-RI-J、RIJONX、RIJCOSX、RI-JK 或 NoRI。RI-JK 在这里提供单点模板。SCF 的积分近似与后续 RI-MP2 等方法的关联拟合可同时设置。[RI 近似](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/RI.html)
- **辅助基组**。`AuxJ` 用于库仑拟合，`AuxJK` 用于库仑与交换拟合，`AuxC` 用于关联拟合，`CABS` 用于显式相关。界面按轨道基组显示适用槽位，`AutoAux` 写入指定槽。程序还按分子逐元素检查轨道与辅助基组覆盖范围。[基组及辅助槽](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/basisset.html)
- **参考态与精度**。适用方法可选 RHF/UHF/ROHF、RKS/UKS/ROKS，保留或取消冻结芯，设置 LoosePNO/NormalPNO/TightPNO，选择 DEFGRID1/2/3 及有对应参数的 D3BJ/D3ZERO/D4。参考波函数和分子多重度一并校验。[参考波函数](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/hftype.html) · [冻结芯](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/frozencore.html) · [数值积分](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/numericalintegration.html)
- **频率**。普通 HF/DFT、D3/D4 校正及目录中的六种 3c 方法默认生成 `Freq`。对支持解析 Hessian 的 HF/DFT，加上默认表面的 C-PCM 或 SMD 仍生成 `Freq`。MP2、双杂化、含 VV10 非局域项的泛函等使用 `NumFreq`。旧项目中显式设置的数值位移参数会继续生效。[振动频率](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/frequencies.html) · [MP2 梯度与 Hessian](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/MP2.html) · [非局域色散](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/dispersioncorrections.html) · [隐式溶剂](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/solvationmodels.html)
- **相对论**。专用轨道基组会带入 ZORA、DKH2 或 X2C，并匹配辅助基组。X2C 基组还可显式选择 DLU-X2C。DKH2 和 ZORA 在 ORCA 默认的单中心近似下支持解析 Hessian。[标量相对论](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/relativistic.html)

## 6.1.1 双版手册

“帮助 → ORCA 6.1.1 计算手册…”同时提供网页定位和 PDF 物理页。溶剂模型和溶剂名按选定方法筛选。标准 HF/DFT 的过渡态优化使用 OptTS，内禀反应坐标使用 IRC。带溶剂或这两种新作业的项目保存为 schema 6。详细的覆盖范围、手册歧义和原生工作流见[版本核对记录](research/ORCA611_AUDIT.md)。

## 命令行试用

```bash
orcaview manual 3.18
orcaview preview examples/water.xyz --method B3LYP --solvation SMD --solvent water --set cpcm.SMD18=true
orcaview preview examples/water.xyz --method r2SCAN-3c --job OPT
orcaview preview examples/water.xyz --method RI-MP2 --basis def2-TZVP --job OPT_FREQ
orcaview preview examples/water.xyz --method 'DLPNO-CCSD(T)' --basis def2-TZVPP
orcaview preview examples/water.xyz --method TD-DFT --reference-functional PBE0 --nroots 3
orcaview preview examples/water.xyz --method CASSCF --active-electrons 2 --active-orbitals 2
orcaview methods RI-MP2 --basis def2-TZVP --ri RIJCOSX
orcaview preview examples/water.xyz --method RI-MP2 --basis def2-TZVP --ri RIJCOSX --aux-j def2/J --aux-c def2-TZVP/C
orcaview preview examples/water.xyz --method 'DLPNO-CCSD(T)-F12' --basis cc-pVDZ-F12 --aux-c cc-pVTZ/C --cabs cc-pVDZ-F12-OptRI --pno-preset TightPNO
orcaview preview examples/water.xyz --method EOM-CCSD --nroots 3
orcaview preview examples/water.xyz --method MR-EOM --active-electrons 2 --active-orbitals 2 --nroots 2
```

上例用于试验输入生成。选择生产计算的活性空间需要检查实际轨道。高级设置会随项目保存，重新打开后可以继续调整并核对输入。

## 微调输入块

在“计算设置”底部展开“高级输入块”，再展开要调整的块。数字输入框留空、菜单选择“ORCA 默认”都会交由 ORCA 取值。布尔选项可以显式设为 `false`。每个块都有恢复默认按钮，折叠标题会显示已调整的项数。手动值随项目保存；折叠只影响显示。

ORCA 的 `%scf`、`%method` 和 `%geom` 是并列的顶层输入块。界面按当前计算显示适用项。选择几何优化、优化加频率或过渡态优化时会开放 `%geom`；改成单点后会从设置中移除几何优化参数，在日志中列出移除项，SCF 设置可以继续使用。`%freq` 用于频率任务，其中数值位移步长只在数值频率任务中开放。[输入块语法](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/input.html) · [SCF](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/scf.html) · [几何优化](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/optimizations.html) · [频率](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/frequencies.html)

| 要调整的计算 | 输入块中的示例 |
|---|---|
| 输出量与单点重启 | 在预览中添加一行 `! MiniPrint NoAutoStart`，或将 `%output → PrintLevel` 设为 `Mini`、`%scf → AutoStart` 设为关。`MiniPrint` 连写，单独的 `MINI` 是轨道基组名。`NoAutoStart` 关闭单点计算对同名 `.gbw` 的自动读取，几何优化会忽略这个开关。[输出设置](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/output.html#simple-input-keywords) · [初猜与重启](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/initialguess.html#autostart-feature) |
| SCF 与积分 | 在 `%scf` 调整 MaxIter、密度与能量收敛阈值、DIIS、阻尼或能级平移。TRAH 的微迭代参数位于其内层 trah 块。在适用的 DFT 方法中可通过 `%method` 调整积分网格。 |
| 优化与频率 | 在 `%geom` 设步数、梯度收敛阈值或 Hessian 更新方式。数值频率的 `%freq Increment` 以 bohr 为单位。 |
| CASSCF / CASPT2 | `%casscf MaxIter` 调整轨道宏迭代，`%casscf → CI → MaxIter` 调整内层 CI 迭代。CASPT2 的虚位移写入 `PTSettings` 子块。 |
| 激发态与关联求解器 | TD-DFT 用 `%tddft`，EOM-CCSD 用 `%mdci`，ROCIS 用 `%rocis`。同一个块中会同时保留主表单的根数和手动设置的求解器参数。 |
| 局域关联与资源 | 适用的 DLPNO 方法可微调 PNO 截断阈值；选择具名 PNO 精度后由该预设控制。MP2 的局部 MaxCore 会计入当前作业的资源估算。 |

命令行的 `methods --blocks` 可列出适用字段。每个 `--set` 设置一个值，内层路径使用点号。下列数值用于试验输入生成。

```bash
orcaview methods B3LYP --job OPT --blocks
orcaview preview examples/water.xyz --method HF --job SP --set output.PrintLevel=Mini --set scf.AutoStart=false
orcaview preview examples/water.xyz --method B3LYP --job OPT --set scf.MaxIter=250 --set geom.MaxIter=80
orcaview preview examples/water.xyz --method EOM-CCSD --nroots 3 --set mdci.NDav=8
orcaview preview examples/water.xyz --method CASPT2 --active-electrons 2 --active-orbitals 2 --set casscf.PTSettings.CASPT2_ishift=0.1
```

## 原生输入

“文件 → 编辑原生 ORCA 输入…”可从当前有效的预览开始，也可打开已有 UTF-8 `.inp`。可直接填写按原子指定混合基组、非等权态平均、多重度块、自定义 LibXC 参数或复合作业。用“另存为 .inp…”保存独立文件，项目表单只保存结构化设置。原生文本的语法与收敛性由执行端 ORCA 检查。

安装镜像的“示例/原生计算输入”提供 C-PCM、水溶剂 SMD、指定轨道占据的 ΔSCF、双步 ωB97M(2)、RAS/ORMAS、松弛扫描、NEB 和 AIMD 输入。在实际执行 ΔSCF 时，应检查所收敛轨道是否仍代表目标态。预览与导出可以离线完成，能量、梯度等科学结果需另行运行 ORCA。[隐式溶剂](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/solvationmodels.html) · [ΔSCF](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/deltascf.html)

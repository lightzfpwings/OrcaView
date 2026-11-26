# ORCA 6.1.1 手册与 OrcaView 0.1.0a5 核对记录

软件现有 45 类、568 个结构化计算预设和 301 个可调整的高级字段。已逐表核对的关键词、基组和字段见下表。完整 ORCA 输入还包含分区、数组、外部文件和多步依赖，部分工作流仍需使用原生输入编辑器。

## 使用的两版手册

网页版首页链接的 PDF 封面为 *ORCA Manual, Release 6.1.1*，出版日期 2025-12-02，共 1,601 页，SHA-256 为 `4df05dcc1126d7816b1770367e29388bb69d079b5ee7b907b939cc7c46830c92`。网页与 PDF 同源。本次下载了网页目录所链接的 136 个章节文件，按章节位置、标题、表头和内容对照。下文的 PDF 页码从封面算第 1 页。[网页版](https://orca-manual.mpi-muelheim.mpg.de/index.html) · [官方 PDF](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf)

| 核对对象 | 结果 |
|---|---|
| 计算章节 | 本地索引配对 81 个二级章节，含下级共 1,017 个标题，覆盖计算要素、模型化学、结构与反应、电子态计算、多尺度、分子动力学和 Compound。帮助菜单可按标题、章节号和示例词检索，分别打开 HTML 和 PDF。 |
| 电子结构关键词 | 对 11 张表的 269 个关键词条目逐一核对，包括 117 个 LibXC 简单关键词。方法预设另包含构造方法、别名、多参数组合和专用模板。见[电子结构记录](ORCA611_MODEL_AUDIT.md)。 |
| 轨道与辅助基组、ECP | 逐行核对 440 个轨道基组、84 个辅助基组及 78 行 ECP。界面可选择 417 个轨道基组，按元素、拟合用途和哈密顿量筛选。见[基组记录](ORCA611_BASIS_AUDIT.md)。 |
| 高级参数 | 对当前结构化目录中的 301 个唯一“块路径＋字段名”核实两版手册中的对应章节。正文和示例还用于确定字段类型、适用算法和互斥条件。见[逐字段对照](ORCA611_BLOCK_AUDIT.md)。 |
| 隐式溶剂 | 对照 §2.13 表 2.56 的 185 个源表行及 §3.5 表 3.24 的 98 行，逐列检查模型标记。两个溶剂表的 ALPB 名称集合一致。SMD 正文写 179 种；表内出现两行连续的 sulfolane 别名，合并后恰为 179 种。别名保留，共 245 个可输入的 SMD 拼写。 |

### 能复核的差异

0.1.0a60 补录 §2.4「输出控制」及两个子节，帮助索引现有 1,020 个标题。新增的 `%output PrintLevel` 与 `%scf AutoStart` 已用 ORCA 6.1.1 的水分子单点重算核对。[输出控制](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/output.html) · [AutoStart](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/initialguess.html#autostart-feature)

- 在 CAS-DFT 节，网页表 3.47–3.49 对应 PDF 表 3.48–3.50。网页和 PDF 的章节仍是 §3.18。比较程序按表题和关键词列匹配。[网页版 §3.18](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/casdft.html) · [PDF 第 498 页](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf#page=498)
- RI 总表在 RIJONX 和 RIJCOSX 两行重复列出 `RIJDX`。软件输出各算法的明确拼写。SCF 积分近似与 MDCI 的 `KCOpt`、`TrafoType` 分开选择。需要相关拟合时联动 AuxC，开壳层与仅限 RHF 的算法组合会被拒绝。[RI §2.8](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/RI.html) · [MDCI §3.10](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/mdci.html)
- 两版 EOM 章节对 `NRootsPerBatch` 的示例类型和表格说明存在分歧。它可在手册索引查询，结构化表单暂未收录。需要 ORCA 6.1.1 的实际解析行为才能进一步确认。[网页版 §5.9](https://orca-manual.mpi-muelheim.mpg.de/contents/spectroscopyproperties/eom.html) · [PDF 第 887 页](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf#page=887)
- 某些方法是多步计算。ωB97M(2) 的随包输入先收敛 ωB97M-V，再读入轨道计算第二步能量。[输入示例](../../examples/native_methods/water-wb97m2.inp) · [PDF 第 238 页](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf#page=238)

## 哪些计算可以直接设置

选定方法、允许的作业和基组后，GUI、CLI、项目读写和输入导出共用规则。计算子块默认折叠。CPCM、SMD、ALPB、DDCOSMO、CPCMX 按方法和作业筛选溶剂。0.1.0a52 起，HF/DFT 的 SMD 频率沿用气相方法的 Hessian 类型。外部 GFN2-xTB 的 CPCMX 限单点；ddCOSMO 可选具名溶剂或用 `%xtb EPSILON` 指定介电常数。[隐式溶剂](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/solvationmodels.html) · [ORCA xTB](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/semiempirical.html) · [xTB 溶剂支持](https://xtb-docs.readthedocs.io/en/latest/gbsa.html)

标准 HF 和具有对应导数的原生 DFT 预设增加 OptTS 与 IRC。单点不能带优化器 `%geom`。OptTS 可以设置 P-RFO 的 Hessian 参数。IRC 通过独立的 `%irc` 设置方向、初始位移和校正步。使用 down 方向时，后端会拦截依赖 Hessian 初始位移的设置。两项任务应从适当的过渡态猜测或已定位的过渡态构型开始。[过渡态搜索](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/optimizations_TS.html) · [IRC](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/irc.html)

| 输入层级 | 代表性工作流 |
|---|---|
| 主表单和折叠输入块 | RHF/UHF、DFT、RI-MP2、局域耦合簇、CAS-DFT、带相关拟合基组的双杂化 TD/TDA、EOM/STEOM、MCRPA/MCTDA；适用的溶剂、优化、频率、OptTS 和 IRC。 |
| 随包原生范例 | RAS/ORMAS 的复合占据约束、ωB97M(2) 的轨道传递、ΔSCF、松弛扫描、带两个端点文件的 NEB 和 AIMD。可打开原生编辑器修改，附件需与输入一起复制。[原生样例](../../examples/native_methods/) · [扫描、NEB、AIMD 使用说明](../../examples/native_methods/advanced_workflows/README.md) |
| 手册索引与手工输入 | 任意非等权、多重度混合的态平均，全套 LibXC 内部参数、依赖外部程序的 MRCC/DMRG 设置、完整 QM/MM 拓扑和多层区域、GOAT/SOLVATOR/DOCKER 以及各类手写多步任务。表单不能对这些自由输入的组合做全套冲突检查。 |

## 如何复跑

应用中选择“帮助 → ORCA 6.1.1 计算手册…”。在命令行运行 `orcaview manual 3.18` 或 `orcaview manual MaxIter` 可以得到 HTML 段落及对应 PDF 物理页。章节和搜索词可离线检索，官方内容需联网打开。章节索引表示该处存在对应的手册内容；可选参数请以 `orcaview methods 方法名 --blocks` 在具体方法与作业下给出的结果为准。

以下命令以同版本的 HTML 镜像、官方 PDF 和保留分页的布局文本为输入。开发用的来源对照程序使用 lxml 和 pypdfium2。运行 OrcaView 本身无需安装这两个库。

```sh
pdftotext -layout orca.pdf manual-layout.txt
PYTHONPATH=src python3 tools/audit_orca_models.py manual-html manual-layout.txt
PYTHONPATH=src python3 tools/audit_orca_basis.py manual-html manual-layout.txt
PYTHONPATH=src python3 tools/audit_orca_blocks.py manual-html manual-layout.txt
python3 tools/audit_orca_sections.py manual-html orca.pdf manual-layout.txt > /tmp/orca-sections.py
cmp /tmp/orca-sections.py src/orcaview/core/_manual_sections.py
python3 tools/audit_orca_solvents.py manual-html manual-layout.txt > /tmp/orca-solvents.py
cmp /tmp/orca-solvents.py src/orcaview/core/_solvents.py
PYTHONPATH=src python3 tools/audit_orca_catalog.py
```

目录遍历使用小分子、缺省轨道基组，以及方法所需的根数、活性空间或自旋设置。检查覆盖 568 个预设的 1,133 个方法／作业搭配，进一步展开可选参考态、显式 RI 和水溶剂模型后，共生成 25,967 份输入。它检查结构化字段重复、原生块重复和单点的优化块误入。其它基组、跨字段约束、故意非法的组合及项目往返另由回归用例检查。任意数值取值、所有分子及用户手写输入均超出这组枚举。

2026-11-19 在 Apple Silicon Mac 上使用真实 ORCA 6.1.1 完成五个水分子作业。随包脚本生成的串行 SMD、正则化 RI-MP2 和双根 EOM-CCSD 均正常结束。另用 Open MPI 4.1.1 以四进程重复 SMD，能量与单进程输出一致。气相 B3LYP 几何优化收敛，并得到三个正振动频率。真机计算覆盖这五组输入，25,967 份目录输入的核对范围仍是生成与静态检查。[公开验证样例](../../artifacts/public/validation/ORCA-6.1.1-macOS-arm64) · [串行检查脚本](../../tools/check_orca611.sh)

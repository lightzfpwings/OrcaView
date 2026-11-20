# ORCA 6.1.1 基组、拟合槽位和相对论核对

基准为 ORCA 6.1.1 官方 HTML 和 2025-12-02 发布的同版 PDF。表 2.12–2.37 的 524 行全部比对了关键词和元素范围，包括跨行的非连续区间。HTML 与 PDF 的这些字段一致。后文同时标注 PDF 文件页和纸面页，前者从封面起计。[HTML §2.7](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/basisset.html) · [PDF 第 79 页](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf#page=79)

| 范围 | 文件页（纸面页） | 核对结果 |
| --- | --- | --- |
| 表 2.12–2.25，常规及 F12 轨道 | 79–91（59–71） | 包括 Pople、Karlsruhe、Jensen、氢样、Sapporo、Partridge、CRENBL、LANL、相关一致、ANO 及专用基组 |
| 表 2.26–2.33，相对论轨道 | 91–95（71–75） | 按表登记各库名、元素和对应哈密顿量。可用的标量匹配包括 89 个 DKH2、ZORA 或 X2C 基组 |
| 表 2.34–2.37，拟合及互补辅助基组 | 95–97（75–77） | 5 个 AuxJ、12 个 AuxJK、47 个 AuxC、20 个 CABS。84 项均有可选组合 |
| 表 2.38，自动和旧式 ECP | 98–100（78–80） | 对照了 78 行核大小/元素组合。在自动 ECP 配对上按元素扣除芯电子，并检查多重度与活性空间 |
| 表 2.39 及 §2.8，RI 组合 | 107–108、110–119（87–88、90–99） | 分别核对交换/库仑拟合、相关拟合、F12 互补基，能量导数另行限制 |
| §2.12，相对论哈密顿量 | 131–141（111–121） | 核对标量 X2C、DLU-X2C、DKH 和 ZORA，及相应导数限制 |

## 可以在程序中选择的组合

440 个轨道基组库名中，有 417 个可按相应方法生成输入。通用输入的首选基组继续使用 `def2-SVP`。表 2.15 的 5 个二分量 dhf 基组、表 2.30 的 8 个 SO-X2C 基组和表 2.31–2.32 的 10 个 DKH3 基组纳入核对目录。§2.7 明确写明 ORCA 6.1.1 未实现所述二分量计算，§2.12 实现的一阶与二阶 DKH 也不能生成三阶哈密顿量。这 23 个库名均未放入可生成预设。表 2.32 将 `aug-cc-pwCVDZ-DK` 标为 DKH3，文件页 95 的表格给出了同样的标注。[基组章节](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/basisset.html) · [相对论章节](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/relativistic.html)

F12 可以选 9 个专用轨道基组，以及 Cu、Zn、Ag、Cd、Au、Hg 的 8 组增广 PP 轨道与 OptRI 搭配。表 2.37 对后者的说明带有 `-F12` 后缀，但表 2.22–2.23 没有这个轨道名称。基组作者维护的 ccRepo 明确说明这些 OptRI 搭配普通增广 PP 轨道。输入使用表 2.22 的实际轨道关键词，以 CABS 自身的元素范围限制生成。传统 `-CABS` 与 `-OptRI` 的覆盖也按各自行处理，例如 He 可以使用 `cc-pVDZ-F12-OptRI`。[PDF 文件页 97](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf#page=97) · [ccRepo 2016-09-23 记录](https://www.grant-hill.group.shef.ac.uk/ccrepo/changes.html)

RI-MP2 的相关拟合槽位与 SCF 部分的 `RIJONX`、`RIJCOSX` 或 `RI-JK` 可以分别设置。RI-JK 的手册实现限于能量。§2.8 的汇总表把 `RIJDX` 同时写在 RIJONX 和 RIJCOSX 两行，输入界面使用正文分别演示的两个明确关键词。CAS-DFT 默认保持全积分，显式 RIJCOSX 开放 AuxJ、AuxC。双杂化 TD/TDA 响应保留关联拟合，并允许调整 DFT 网格。[RI §2.8](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/RI.html) · [MP2 §3.9](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/MP2.html) · [CAS-DFT §3.18](https://orca-manual.mpi-muelheim.mpg.de/contents/modelchemistries/casdft.html)

## ECP 资料差异与输入边界

- 表 2.20 将 CRENBL-ECP 的元素列为 Li–Og，表 2.38 的芯电子数从 Al–Zn 直接跳到 Rb–Cd。两个版本相同。对照 Basis Set Exchange 收录的原始 CRENBL-ECP 数据，Ga–Kr 均替代 18 个电子。其余范围与表 2.38 一致。[PDF 文件页 99](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf#page=99) · [BSE CRENBL-ECP 数据](https://raw.githubusercontent.com/MolSSI-BSE/basis_set_exchange/master/basis_set_exchange/data/crenb/CRENBL-ECP.0.json)
- 表 2.13、2.25 对旧式 `def-ECP` 列出 Rb–Lr，表 2.38 只列出 Fr–Lr 的芯电子数。表 2.15 对 `dhf-ECP` 列出 Rb–Rn，而表 2.38 跳过 La–Lu。涉及这些缺口的组合会指出元素和待核实的 ECP。表 2.38 单列的旧式 `def-SD` 拥有自己的关键词。手动 ECP 替换会改变活性电子计数，当前生成器按全分子轨道基组自动选择的 ECP 计数。[HTML §2.7.5](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/basisset.html#effective-core-potentials)
- 基组元素范围和拟合元素范围分别校验。例如 `cc-pVDZ` 有 Ca，`cc-pVDZ/C` 缺少 Ca，RI-MP2 的该分子可选槽位内的 AutoAux。分元素或分原子混用轨道、外部基组文件及用户自定义收缩系数属于手册另外的输入途径，本次表格数字仅计入内置库名。[HTML §2.7](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/basisset.html)

本轮通过输入生成、各槽位可达性、元素边界、带电原子和 ECP 芯电子扣除回归测试。测试范围为 OrcaView 生成与校验，ORCA 的数值收敛和不同元素组合的实际运行需要外部 6.1.1 程序。

## 重现核对

准备官方 HTML 镜像以及用 Poppler 从同版 PDF 生成的布局文本。在装有 lxml 的 Python 环境中运行以下命令，文件路径按本机位置填写。

```sh
pdftotext -layout orca.pdf orca-layout.txt
PYTHONPATH=src python tools/audit_orca_basis.py manual-html orca-layout.txt
PYTHONPATH=src python -m unittest discover -s tests -p 'test_basis_manual_catalog.py'
```

复核器独立提取 PDF 表格中的名称和元素列，校验 HTML 中的名称集合、各元素区间与当前运行时代码，并核对 ECP 表的 78 行。PDF 表中的跨行范围及脚注按各自列处理。

# ORCA 6.1.1 扫描、NEB 和分子动力学示例

在本机装有 ORCA 6.1.1 后，将整个示例目录复制到可写位置。下面命令从本说明所在目录执行。把第一行换成本机 ORCA 可执行文件的绝对路径。每个算例在自己的目录写入日志和结果，重测时请使用示例的新副本。

```sh
ORCA_BIN='/absolute/path/to/orca'
(cd scan && "$ORCA_BIN" water-oh.inp > water-oh.out)
(cd neb && "$ORCA_BIN" ammonia-inversion.inp > ammonia-inversion.out)
(cd md && "$ORCA_BIN" water-md.inp > water-md.out)
```

这三个算例使用 PBE/def2-SVP、中性单重态和 Å 坐标。输入、单位和 NEB 附件已静态核对。本次交付未用真实 ORCA 执行这些算例，收敛情况及执行时间需在本机确认。

| 输入 | 计算内容 | 测试时查看 |
| --- | --- | --- |
| `scan/water-oh.inp` | 水的 O–H 松弛扫描。按 ORCA 从 0 起的原子序号固定 O(0)–H(1) 的键长，从 0.96 到 1.16 Å 均匀取 5 个点，其余自由度在每点优化 | 日志中的扫描点、约束键长及各点收敛能量。预期键长依次为 0.96、1.01、1.06、1.11 和 1.16 Å |
| `neb/ammonia-inversion.inp` | 氨的伞式反转。反应物和产物各有一个 N 和三个 H，原子顺序均为 N H H H。端点先优化，再在线性插值的 5 个内部图像上优化路径，两端点另计 | 保持 `reactant.xyz` 和 `product.xyz` 与输入同目录。观察两端的氮在同一氢平面的两侧，以及内部图像的能量、力和路径收敛结果 |
| `md/water-md.inp` | 单个水分子从 300 K 初始速度分布开始做短程无热浴动力学。步长 0.25 fs，共 20 步，对应 5 fs | 查看日志中的步数与能量，打开 `water-trajectory.xyz` 检查每步记录的坐标。300 K 指初始速度对应的温度，轨迹中的瞬时温度会波动 |

扫描设置依据 §4.2.2、§4.2.6，PDF 文件页 620–623（纸面 600–603）。[网页版](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/optimizations_scans.html) · [PDF](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf#page=620)

NEB 端点引用、预优化、图像数及插值依据 §4.5.7、§4.5.16，PDF 文件页 641–642、647–648（纸面 621–622、627–628）。[网页版](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/neb.html) · [PDF](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf#page=648)

动力学命令、时间和温度单位依据 §7.1.4、§7.1.6，PDF 文件页 1199–1200、1204 起（纸面 1179–1180、1184 起）。[网页版](https://orca-manual.mpi-muelheim.mpg.de/contents/moleculardynamics/moldyn.html) · [PDF](https://orca-manual.mpi-muelheim.mpg.de/_static/pdf/orca.pdf#page=1199)

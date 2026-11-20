# M6 单中心 Gaussian 参考样例

两个手工构造的 Molden 文件使用单中心、单个归一化 s 型 Gaussian，坐标为 Bohr。输入包含基组、轨道、占据和自旋。轨道能量字段为示例占位值。输入和解析参考值均为合成数据，可在没有 ORCA 的环境运行。格式依据 [Molden 官方规范](https://www.theochem.ru.nl/molden/molden_format.html)。

| 文件 | 核中心（Bohr） | 指数（Bohr⁻²） | 轨道占据 | 总电子数、自旋电子数差 |
|---|---|---:|---|---|
| `helium-closed.molden` | (0, 0, 0) | 0.75 | 闭壳层单个空间轨道，双占据 | 2、0 |
| `hydrogen-open.molden` | (0.4, −0.3, 0.2) | 1.125 | Alpha 轨道单占据，Beta 轨道空占据 | 1、1 |

## 解析参考与积分检查

在项目根目录运行下列命令。脚本核对两个输入的 SHA-256，输出同一组五个绝对坐标处的空间轨道、总密度与自旋密度的值、梯度、Hessian 和 Laplacian。点集包含两个核中心、非对称离轴点和远处点。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 examples/m6_reference/gaussian_reference.py \
  > /tmp/orcaview-m6-gaussian-reference.json
```

设位移向量为 `d = r − R`，归一化轨道为 `ψ = (2α/π)^(3/4) exp(−α |d|²)`。令 `n = nα + nβ`，总密度为 `ρ = n ψ²`，自旋密度为 `ρs = (nα − nβ) ψ²`。对形如 `F = A exp(−b |d|²)` 的函数，`∂i F = −2b di F`，`∂ij F = (4b² di dj − 2b δij) F`，Laplacian 是 Hessian 的迹。轨道值单位为 `Bohr^(-3/2)`，密度为 `e/Bohr³`，每阶空间导数再加一个 `Bohr^-1`。Hessian 以 `x,y,z` 为行列顺序。

脚本使用步长 `1e-4 Bohr` 的中心有限差分核对一、二阶导数，绝对阈值分别为 `1e-7` 与 `1e-6`。以核为中心，在半径 `10 Bohr` 内对径向体积元做 4096 段复合 Simpson 积分，检查轨道范数平方为 1，总密度积分为 2 或 1，自旋密度积分为 0 或 1。脚本检查积分绝对误差小于 `1e-12`。这些阈值用于解析参考的自检。

## 原版 Multiwfn 对照待运行

固定 Multiwfn `2026.11.12` 构建。每个输入使用独立目录并保存设置、stdout、stderr、版本、退出码和实际菜单输入。以下为 Linux 上单个样例的交互启动命令。将两个环境变量设置为已核对的绝对路径，在项目根目录运行。第二个样例以 `hydrogen-open.molden` 重复。

```bash
set -o pipefail
fixtures="$(pwd)/examples/m6_reference"
run_dir="$(mktemp -d)"
cp "$MULTIWFN_REFERENCE_SETTINGS" "$run_dir/settings.ini"
cp "$fixtures/helium-closed.molden" "$run_dir/input.molden"
(
  cd "$run_dir" || exit 1
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    timeout 120s "$MULTIWFN_REFERENCE_BINARY" input.molden -silent \
    2>reference.stderr | tee reference.stdout
)
```

1. 先核对原版打印的版本、原子坐标、波函数类型、轨道数、自旋和占据。再按该版本实际提示进入点值菜单，选择已占据空间轨道，按输出的 `position_bohr` 顺序输入坐标。保存轨道值、总密度、自旋密度和总密度的各梯度、Hessian 与 Laplacian 分量。原版若支持选择对应函数的梯度及 Hessian，再保存其余导数。[Multiwfn 官方快速入门](https://sobereva.com/multiwfn/misc/Multiwfn%20quick%20start.pdf)
2. 显式退出并保留退出码。要求每个预期点都返回完整字段，确认数据来自已载入波函数。原版未直接提供的分量记录为缺项，保留解析值和有限差分作为独立证据。
3. K1 有真实 worker 后，使用相同文件和点顺序，核对全部已支持量。原始双精度数组比较先用 `1e-10 + 1e-8 × |参考值|`，由绝对项保护近零值、相对项约束中大值。若原版通过文本输出，可加上最后一位的半个单位作为舍入边界，逐字段记录所用容差。若原版和 ABI 都保留文件相位，直接比较 MO 符号；若有已记录的重定相规则，单个 MO 跨全部点和导数只允许一个一致的相位因子。
4. 用批量点接口沿核中心径向采样，在相同积分区间核对电子数与轨道归一化。开放壳层要求 `ρs = ρ`，闭壳层要求 `ρs = 0`。保持点序，分别用批大小 `1 / 2 / 5` 比较，再在同一 worker 按 He→H→He 重复加载并核对第一次和第三次。两个点值样例以外，另测零长度、容量不足、非法轨道、缺轨道、损坏文件、周期输入、取消与崩溃后的恢复。

这里的紧凑样例验证一条明确的归一化、占据和导数路径。轨道角动量、收缩基组、ORCA 转换、真实开壳层多轨道、ECP/EDF、复杂积分需各自追加输入和基准。当前已运行解析参考脚本，原版和内嵌 worker 对照均待运行。

## 性能记录

以科学一致性通过为前提，同机固定输入、批大小、构建优化选项、BLAS/OpenMP 供应商与线程数。冷启动单列加载、进程/库初始化，热运行分别测原生批量计算和结果传输，另记父进程与 worker 峰值 RSS。原版菜单运行如包含文本格式化或文件 I/O，单独记端到端时间。性能用规模更大的固定分子和多个点数，保留原始时间、重复次数和统计量。

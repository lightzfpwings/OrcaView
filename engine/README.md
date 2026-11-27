# M6 K0 来源、构建与依赖审查

这里保存 2026 年 11 月对 Multiwfn 上游实现的研究与核验工具。OrcaView 0.1.0a76 的八种轨道成分分析均使用应用内置算法。[当前轨道分析](../docs/ORBITALS.md)

## 来源与本机验证

对照程序固定为 Multiwfn `2026.11.12`。2026-11-12 的项目审查从官方站点取得 `Multiwfn_2026.11.12_src_Linux.zip`，核对大小 `3,635,867` 字节、SHA-256 `f41897accb99d0a7bc1d156ef6a387075f6b2f21acdac0f775db3dccb8424503`、78 个目录条目、根目录 `Multiwfn_2026.11.12_src_Linux/`，以及源码中的版本标记。直接使用日期固定的文件，同名或 `latest` 下载均需通过哈希验证。本次只记录上游来源并使用本项目原有审查证据补充构建清单。 [官方下载页](http://sobereva.com/multiwfn/download.html) · [固定源码包](http://sobereva.com/multiwfn/misc/Multiwfn_2026.11.12_src_Linux.zip) · [2026-11-12 原审查](../docs/history/design/research/MULTIWFN_SOURCE_REVIEW.md)

2026-11-19 本机 `uname -sm` 为 `Darwin arm64`。项目、旧临时缓存和已检查的下载路径均未找到固定 ZIP；`ifort`、`ifx`、`gfortran`、`flang`、Docker 和 Podman 均未在 `PATH` 找到，`/opt/intel` 不存在。默认环境用 `curl` 请求固定 HTTPS/HTTP 路径均退出 `6`（DNS），允许网络后 HTTPS 退出 `35`（TLS 握手失败），HTTP 退出 `52`（服务器空响应）。网页检索也未取得固定 ZIP。本轮在这些条件下完成来源核对流程和静态审查；固定 ZIP 重新验哈希、原版 noGUI 构建、真实原版数值对照以及派生库链接均尚无本轮证据。

官方条款允许免费学术/商业使用和分发原版或修改后的代码，包括作为商业软件的免费组件。销售修改版须先取得原作者同意；论文或纳入代码须引用以下两篇论文。本轮 `engine/` 只包含 OrcaView 的核验脚本和审查记录，补丁清单为空，第三方源码、构建产物和运行库均未入库。将来保留上游声明并分别核对随同发布的依赖条款。 [下载页许可](http://sobereva.com/multiwfn/download.html) · [2012 年论文](https://doi.org/10.1002/jcc.22885) · [2024 年论文](https://doi.org/10.1063/5.0216272)

## 原版对照程序构建配方

在 Linux x86-64、GNU Make、Intel classic `ifort`、C 编译器以及已配置相容的 Intel oneMKL 和 OpenMP 环境中复现，先取得当地采集的官方固定 ZIP。上游 Makefile 采用 Intel 专用参数，编译器和数值库版本由构建日志登记。GNU Fortran、ifx、Linux ARM64 和 macOS 是独立移植验证。下面的配方来自固定版本历史源码审查及上游 `noGUI` 目标，当前本机未运行。可先在任意 Python 3.9+ 机器核验 ZIP，再将同一 ZIP 送到目标环境。

```bash
# Bash，在 OrcaView 仓库根目录运行。源码和证据都放入新的临时目录。
set -euo pipefail
ov_repo="$PWD"
ov_source_zip=/absolute/path/Multiwfn_2026.11.12_src_Linux.zip
ov_build_dir=$(mktemp -d "${TMPDIR:-/tmp}/orcaview-m6-k0.XXXXXX")
cp "$ov_source_zip" "$ov_build_dir/source.zip"
python3 "$ov_repo/engine/verify_upstream.py" "$ov_build_dir/source.zip" \
  | tee "$ov_build_dir/source.json"
unzip -q "$ov_build_dir/source.zip" -d "$ov_build_dir"
cd "$ov_build_dir/Multiwfn_2026.11.12_src_Linux"

test "$(uname -sm)" = 'Linux x86_64'
test -d "${MKLROOT:?load the pinned Intel oneMKL toolchain environment}"
for ov_tool in ifort cc make readelf ldd sha256sum; do
  command -v "$ov_tool"
done
grep -nE '^noGUI[[:space:]]*:' Makefile
{
  uname -a
  ifort --version
  cc --version
  make --version
  printf 'MKLROOT=%s\n' "$MKLROOT"
  grep -E '^#define[[:space:]]+__INTEL_MKL' "$MKLROOT/include/mkl_version.h"
  sha256sum Makefile COMPILATION_METHOD.txt settings.ini
} > "$ov_build_dir/toolchain.log" 2>&1

make -n -j1 noGUI 2>&1 | tee "$ov_build_dir/build-plan.log"
make -j1 noGUI 2>&1 | tee "$ov_build_dir/build.log"
test -x Multiwfn_noGUI
sha256sum Multiwfn_noGUI | tee "$ov_build_dir/binary.sha256"
readelf -h -d Multiwfn_noGUI > "$ov_build_dir/elf.log"
ldd Multiwfn_noGUI | tee "$ov_build_dir/runtime.log"
```

保留退出状态、工具版本与 MKL 头文件版本、实际命令、二进制哈希及 ELF/运行时报告。若系统库由静态方式链接，保留链接命令和相应静态库版本来补充 `ldd`。复现使用上游原样源码与 Makefile；数值结果或跨机构的位级可重现性需要另行测量。原版仍包含菜单主程序和多余编译单元，适合做同版对照。开启数值验证前先用带时限的命令核对发布版本和文件加载证据，再按固定菜单录制属性值，参考 [闭壳层/开壳层样例](../examples/m6_reference/README.md)。

## 计算闭包与第三方清单

以下是基于已登记源码的过渡依赖图，行号相对同一固定 ZIP 目录。这里列出保留、需拆分和暂缓的路径，最终闭包须以派生库编译、符号审查和入口故障测试验证。 [上游证据位置](../docs/history/design/MULTIWFN_ENGINE_DESIGN.md)

| 入口或依赖 | 采用范围与核对项 |
|---|---|
| 受控分子 Molden 读取 | `fileIO.f90:4121` `readmolden` → `define.f90:262–326` 体系/基组/MO/占据 → `sub.f90:1456–1510,3711` 归一化与基函数转换。先保留输入球谐/笛卡尔约定、MO 自旋和源到原子 ID 的有序映射。入口对晶胞、周期、ECP/EDF 未验证型、隐式外部转换明确拒绝。缺 `[GTO]`、不支持壳层等分支需从 `read(*)`/`stop` 改为返回结构化错误。 |
| K1 批量 MO、电子密度、梯度及 Hessian | `function.f90:422–491,2088–2108,2327–2338` → `defvar` 与相应的原生基函数和导数过程。保留占据、轨道顺序、自旋和方法参数。需按功能认定解析/数值导数与步长，禁止缺波函数时自动回落到叠加原子密度。先选出可达过程，把通用分派中的周期、插值和可选功能拆出。 |
| LIBRETA 及线性代数 | `function.f90:5–8` → `libreta.f90:4–7` → `ean.f90:1–5` → `hrr`、`blockhrr`、`eanvrr`、`boysfunc`。`util.f90:1489–1495,1588–1610` 使用 `DSYEV` 和 `DGEMM`。K0 原版依据上游 oneMKL/Intel OpenMP；K1 审查 `iso_c_binding` 运用、`-fPIC`、仅公开允许的符号、BLAS 整数接口和重复 OpenMP runtime。LIBRETA 与附带实现的版权文件列入分发记录。 |
| K2 规则网格、内部 ESP | `grid.f90:145–196` → 批量函数计算，显式保存原点、轴、尺寸与顺序。ESP 使用 `function.f90:4259–4270` 底层定义和 LIBRETA 路径，保留奇点掩码。去掉 `grid.f90:20–55,231–285` 的外部 cubegen、图形和交互输入。 |
| K2 Mayer / Hirshfeld | `bondorder.f90:285–346` 使用原生密度与重叠矩阵，记录总密度和 alpha/beta 的定义。`population.f90:5479–5528` 使用占据、内置原子径向参考、Lebedev (`Lebedev-Laikov.F`) 和径向积分 (`sub.f90:3093–3186`)。遵循各自原始算法和来源注记，方法参数和电子数积分随载荷。 |
| 其余随源码附带的算法与库 | SYVA (`sym.F:4–20`)、B-spline (`Bspline.f90:1–3`)、DFTxclib (`DFTxclib.F:57–62`)、EDF、其他原子就绪数据及原版对象清单中的 MINPACK 按实际闭包决定。保留文件首部来源和原作者声明，版本/分发条件未核清前不捆绑。FLINT/Arb 只依赖超几何函数的相关路径。禁用路径不得落入 `ext/no2F2.c` 的退出桩。 |
| 仅属原版或另行登记的入口 | 删除派生构建的主程序，排除可达的 DISLIN/X11/Motif/OpenGL、菜单与 PBC；`noGUI` 的 DISLIN 桩有不赋值的输出。通用 `.gbw` 自动转换、Gaussian/cubegen、DFT-D3 和 NBO/GENNBO 数值输入链按外部任务单列；仅保留显式来源和适用版本的数据连接。 |

## K1 ABI 和状态边界

- 首个共享库补丁按顺序处理受控读取、体系初始化及重置、无交互点值/导数、公开 C 符号和最小链接表。补丁附上游 SHA-256、可应用的变更与回归证据。原版主程序与原生库分开构建，GNU Make 原版对照配方保持零补丁。
- C ABI 以固定宽度整数和 `double` 表达，`iso_c_binding` 封装 Fortran 状态。点坐标内存布局为 `xyz[3 * i + axis]`，单位 Bohr。调用者持有缓冲区，越界、容量不足及请求失败返回状态。分配前校验尺寸和乘积，固定轨道、导数分量、单位和坐标顺序，成功前禁止发布部分数组。
- 加载、重复加载和清理均为显式动作；`sub.f90:2861–2945` 的模块清理、LIBRETA 积分表、原程序设置和文件 unit 进入检查范围。每个 worker 串行处理一套体系，记录 OpenMP/MKL 线程与内存限制，读取失败允许销毁 worker；无 stdio 等待、隐式外部程序或 `STOP`。逐入口核对符号与运行行为，包含缺字段、截断、未知功能、无轨道以及取消。K1 工具链版本、完整链接图和科学容差随实际构建/测量留证。

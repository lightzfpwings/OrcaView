# OrcaView 命令行与批处理

以下命令适用于 OrcaView 0.1.0a76。在仓库的虚拟环境中使用 `orcaview`，Linux 便携包使用解压目录中的 `./OrcaView`，macOS 应用使用 `/path/to/OrcaView.app/Contents/MacOS/OrcaView`，Windows 便携包使用 `OrcaView.exe`。运行 `orcaview --help` 查看入口，子命令均支持 `--help`。

## 新任务的核数和内存

桌面和命令行新建计算都默认使用 **16 核、每个 ORCA 进程 4096 MB**。生成的输入中对应 `nprocs 16` 和 `%maxcore 4096`。例如，`orcaview preview molecule.xyz --cores 8` 使用 8 核、每进程 4096 MB。也可以单独指定 `--maxcore`。打开已有项目时沿用保存的核数和内存，`--reset-calculation` 可恢复全部计算选项的默认值。

`orcaview resources` 以 JSON 输出当前节点的 CPU 上限和可用内存。`target` 对应新任务的固定默认值，`recommended` 显示按该节点资源算出的建议值。建议按可用内存的 75% 估算，在 Linux 上还会计入 CPU 亲和性、可读取的 cgroup 配额和 Slurm 的本节点分配。[ORCA 内存设置说明](https://www.faccts.de/docs/orca/6.1/manual/contents/quickstartguide/troubleshooting.html#out-of-memory-oom)

## 无桌面的行为

数据、项目、计算、设置和光谱数据导出可在终端运行。无桌面会话、图形后端不可用或显式设定 `ORCAVIEW_HEADLESS=1` 时，`gui` 跳过显示并以状态 0 退出。在 SSH、调度器或持续集成任务中可以显式设置这个环境变量。

`render`、`spectrum --format png` 和 `gui --screenshot` 在独立进程中使用软件离屏渲染，成功时安静退出。桌面包自带 Qt 离屏插件；源码安装可使用项目的 `gui` 依赖。生成图片需要可加载的离屏后端及系统运行库，缺少时命令返回非零并写入标准错误。渲染超时以秒为单位，由 `ORCAVIEW_RENDER_TIMEOUT` 指定，默认为 300。结果数据与设置可在完全没有 Qt 的安装中使用。读取 MOL/SDF、3D 优化等原本依赖 Open Babel 的操作仍需要对应的化学引擎。

## 从命令行查看轨道

运行 `orcaview gui job.uno`，确认转换后即可查看自然占据数和等值面。要直接生成图片，可运行 `orcaview gui job.uno --workspace orbitals --screenshot uno.png`。桌面包中附有 OH 的 UNO、UNSO 两个示例和水分子的 HOMO Cube 文件。[轨道文件及分解方法](ORBITALS.md)

## 常用入口

| 目标 | 命令 |
| --- | --- |
| 导入分子、ORCA 输出或旧项目，保存为项目 | `orcaview project water.xyz -o water.oview.json` |
| 创建空草图或获取桌面内置示例 | `project --new empty`、`project --new carbon`、`project --demo m1`、`project --demo m6`，配合 `-o PROJECT` |
| 保留历史和结果，另存项目或导出当前 XYZ | `project PROJECT -o COPY.oview.json`、`project PROJECT -o geometry.xyz` |
| 按原项目规则迁移 schema 1 | `migrate OLD.oview.json NEW.oview.json` |
| 更新计算设置、基组、电子态和 ORCA 输入块 | `project PROJECT --job OPT --cores 4 --set scf.MaxIter=250 -o opt.oview.json` |
| 预览或导出计算输入 | `preview opt.oview.json -o job.inp`，省略 `-o` 则写标准输出 |
| 应用编辑过的输入并规范化 | `preview water.xyz --edit-input edited.inp -o normalized.inp` |
| 将同一份编辑保存为项目 | `project water.xyz --edit-input edited.inp -o edited.oview.json` |
| 读写独立原生 ORCA 输入、通过管道编辑 | `native-input job.inp`、`native-input - -o edited.inp`，保留 UTF-8 BOM 与原始换行 |
| 结构设计、选区、键长、补氢、二维整理、三维优化、恢复历史 | `design INPUT --script steps.json -o edited.oview.json`，详见[设计命令](CLI_DESIGN.md) |
| 计算方法、可用计算参数和手册 | `methods`、`methods B3LYP --blocks`、`manual MaxIter` |
| 运行本地 POSIX 作业、查询执行记录 | `run opt.oview.json --orca /absolute/path/to/orca --workdir attempts`、`attempts attempts` |
| 浏览计算摘要、历史帧、原子数据、结果与出处 | `inspect job.out --job OPT`、`results job.out --all`，详见[结果和光谱命令](CLI_RESULTS.md) |
| 查看或导出光谱 | `spectrum job.out` 先列出谱表，再用 `--table 1 --format curve -o curve.csv` 或 `--format png -o plot.png` |
| 在桌面打开指定文件或静默截取工作区 | `gui water.xyz --workspace design`、`gui water.xyz --workspace input --screenshot window.png` |
| 更改元素配色、模型、原子尺寸、键粗细、成键距离 | `settings appearance` 与 `render`，见下文 |
| 语言、语言包目录 | `settings language --directory /path/to/language-packs --locale zh-Hans` |
| 检查更新、下载、安装或替换当前安装 | `update check`、`update download DIR`、`update install DIR`、`update replace-current`。便携版替换当前运行目录时返回后台安装状态及错误日志位置。 |

只有显式加上 `--finite` 才会将周期性输入作为有限结构导入。读取项目时沿用保存的计算设置，命令行传入的选项覆盖相应字段。可使用 `--reset-calculation` 从默认值开始，`--clear-blocks` 清除已保存的输入块覆盖项。运行计算按作业建立独立目录，可用 `--timeout` 限时或 Ctrl-C 取消。

`--edit-input` 接受一个含内嵌 `* xyz` 坐标段的单任务输入，传 `-` 可从标准输入读取。桌面预览和 `preview`、`project`、`run` 使用相同的解析器。程序先应用文本，再应用单独传入的参数，例如 `--cores 8`。未声明的核数和内存采用新任务默认值。格式化会统一空格、块缩进和坐标小数位，自定义注释集中在文件开头。无法映射到参数面板的指令会报告错误，独立原生输入编辑器可保存这类文本。

例如，`orcaview preview water.xyz --job OPT_FREQ --method B3LYP-D4 --solvation SMD --solvent water` 生成 `Opt Freq`。RI-MP2 气相任务的优化加频率生成 `Opt NumFreq`。两者与桌面预览共用频率规则。[ORCA 6.1.1 振动频率](https://orca-manual.mpi-muelheim.mpg.de/contents/structurereactivity/frequencies.html)

## 外观与静默出图

```sh
orcaview settings appearance --model ball-and-stick --atom-scale 1.2 --bond-scale 0.8 --bond-distance-factor 1.25
orcaview settings appearance --import-palette color-packs/contrast.json
orcaview render water.xyz water.png --model space-filling --rotate y:30 --width 800 --height 600 --scale 2
orcaview render water.oview.json sketch.pdf --view 2d --color-pack color-packs/contrast.json
orcaview settings appearance --reset
```

`settings` 的改动在下一次命令及桌面启动时生效。单次 `render` 传入的选项只作用于这次导出。结构图支持 PNG、JPEG、BMP、PDF，可控制尺寸、留白或裁切、分辨率、透明背景、相机和标签。用 `ORCAVIEW_CONFIG_DIR` 可以为一批任务指定独立的偏好与配色目录。

## 在 Linux 或 macOS 批量导出

```sh
set -e
export ORCAVIEW_HEADLESS=1
mkdir -p images
for input in ./*.xyz; do
    [ -f "$input" ] || continue
    name=${input##*/}
    orcaview render "$input" "images/${name%.xyz}.png" --model wireframe
done
```

数据命令向标准输出写 UTF-8 文本、JSON 或 CSV。批处理可根据退出状态判断本次命令是否完成；图片导出失败不会以成功状态返回。

## 后续开发约定

新增桌面操作或设置时，同时提供命令行入口，复用同一套数据、校验、默认值和绘图实现。回归测试应分别覆盖纯数据操作、无桌面时跳过交互显示，以及通过实际离屏后端生成文件。

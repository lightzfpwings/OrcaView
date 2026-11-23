# OrcaView 当前公开契约

软件版本为 `0.1.0a42`。写入时按计算设置、文档历史与日志报告选择能完整表示它们的最早项目格式。基本设置使用 schema 1/2，原有的五个参数化方法使用 schema 3，扩展目录、基组或近似设置使用 schema 4，手动输入块使用 schema 5，溶剂或反应路径设置使用 schema 6，日志报告自 schema 7 起保存，含显式连接标记的项目至少使用 schema 8，带特殊键型的几何至少使用 schema 9，含零原子草稿的修订历史使用 schema 10，带独立二维草图的修订使用 schema 11。[原始架构基线](DESIGN.md)

## 核心对象

导入路径为 `orcaview.core.models`。数据类均不可变；原子和键使用 tuple。

| 对象 | 字段 | 单位与规则 |
|---|---|---|
| `Atom` | `element, x, y, z` | 标准大小写元素符号；有限实数；长度为 Å |
| `Bond` | `a, b, order=1` | 原子索引从 0 开始；两个不同原子；键级 1–3 |
| `Molecule` | `name, atoms, bonds=(), charge=0, multiplicity=1, bonds_explicit=False` | 非空结构；总电荷为整数，多重度为正整数 |
| `CalculationSpec` | 基本方法、基组、作业类型、核数和每核内存，另有活性空间、目标根数、参考泛函和下列高级选项 | 核数和每核 MB 为正整数，方法决定适用字段。 |

`Molecule.validate_structure()` 检查结构；`Molecule.validate()` 另检查电子数与多重度的相容性。电子数为原子序数之和减去总电荷；检查不证明电子态在化学上合理，也不实现 ECP、ghost、broken-symmetry 或混合基组的完整语义。

schema 4 的计算记录在 schema 3 字段上增加 `integral_approximation, aux_j, aux_jk, aux_c, cabs, dispersion, integration_grid, pno_preset, relativity, electron_channel, wavefunction, frozen_core`。未指定的辅助槽和通道存为 JSON null，其余选择器默认 `Auto`。各方法的轨道基组、辅助拟合槽、积分近似和 ECP 覆盖范围由同一目录决定。固定基组或 CBS 外推方法只向 ORCA 传递预设所需的关键词。[计算方法](ORCA_METHODS.md)

schema 5 在计算记录中增加 `block_options` 数组，按 `{"block":"scf","key":"MaxIter","value":250}` 保存每个手动值。内层路径例如 `casscf.CI`，值使用 JSON 原生数值、布尔值或枚举字符串。仅允许目录中与当前方法、作业和近似匹配的字段。同一字段重复赋值、类型错误和已知冲突会拒绝加载或导出。恢复全部默认后，再次保存会选用能表示其余设置的最早格式。

现有任务为 `SP, OPT, FREQ, OPT_FREQ`。默认设置为 `B3LYP / def2-SVP / SP / 4 cores / 1000 MB per core`。各方法选用适用的任务子集。频率任务按方法写出 `Freq` 或 `NumFreq`。

## 文件和应用服务

| API | 输入 → 输出 | 失败语义 |
|---|---|---|
| `io.xyz.parse_xyz(text, name='Molecule')` | 严格单帧 XYZ → `Molecule` | 格式/元素/坐标错误抛 `ValueError` |
| `io.xyz.load_xyz(path)` | 路径 → `Molecule` | 文件错误为 `OSError`，内容错误为 `ValueError` |
| `io.xyz.write_xyz(molecule)` | 分子 → XYZ 字符串 | 结构错误为 `ValueError` |
| `core.geometry.infer_bonds(molecule)` | 几何 → `tuple[Bond, ...]` | 仅距离显示启发式，不识别键级 |
| `orca.input.render_input(molecule, spec)` | 结构化对象 → ORCA 输入字符串 | 完整基础校验未通过为 `ValueError`；不启动程序 |
| `orca.output.parse_output(text, job_type='SP')` | 单作业文本 → `OutputSummary` | 未知任务类型为 `ValueError`；缺证据不猜测成功 |
| `application.session.Session.open_xyz(path)` | 替换当前会话结构 | 先解析后提交；失败保留原分子 |
| `application.project.save_project(session, path)` | 按文档、设置和报告写 schema 1–11 | 校验后原子替换，失败保留旧文件 |
| `application.project.load_project(path)` | schema 1–11 JSON → `Session` | 拒绝未知版本、未知字段和失效的内部引用 |
| `application.project.migrate_project(source, destination)` | schema 1 → 新路径的 schema 2，并返回会话 | 目标已存在或写入失败时保留现场 |

XYZ 的空注释行可以保留，但第二行必须存在；每原子仅四列，额外列与多帧输入明确拒绝。XYZ 未提供电子态时保留默认电荷 0、多重度 1，不以启发式替用户选择自旋。因此奇电子几何可以查看，但必须修正电子态后才能导出计算输入。

schema 1 的 JSON 顶层字段为 `schema_version, software_version, molecule, calculation, source_path`。`source_path` 是来源提示。读取项目只读取项目文件本身。schema 1 的数据范围为一个分子及其计算设置。

## M1 几何、身份与来源

下表各类型的 `contract_version` 均为类常量 `1`。导入路径相对 `orcaview.core`。科学值保存在 frozen dataclass 和 tuple 中。

| 对象 | 主要字段 | 使用约定 |
|---|---|---|
| `snapshots.GeometryRef` | `document_id, revision, frame_id, snapshot_id` | 修订从 1 开始。空帧 ID 指该修订本身。每次发布都分配独立的快照 ID。同一项目的两个副本各自产生修订 2 或同名帧时，仍可区分其内容。 |
| `snapshots.GeometrySnapshot` | `ref, parent, molecule, atom_ids, provenance, source_unit, content_hash` | `atom_ids[i]` 与 `molecule.atoms[i]` 对应。`id_at(i)` 和 `index_of(id)` 检查边界。电子态与键保存在本快照的分子中。 |
| `snapshots.SelectionContext` | `geometry, atom_ids, mode` | 保留点选顺序。`atom_set` 支持集合运算。`indices(snapshot)` 校验所属帧并返回从 0 开始的行号。 |
| `provenance.ArtifactRef` | `artifact_id, format, path_hint, sha256` | 文件身份与位置分别记录。已有字节使用 `from_bytes`，磁盘文件可用 `from_file` 流式取摘要。仅有旧路径时哈希为 `None`。 |
| `provenance.Provenance` | `kind, producer, producer_version, parents, parameters` | `parents` 为输入文件引用，`parameters` 为不可变的字符串键值对。父几何另见 `snapshot.parent`。 |

`application.document.MoleculeDocument` 管理一个文档。`Session.document` 在首次访问时为传统会话分配身份。`Session.open_xyz` 直接建立带真实文件哈希的文档。GUI、CLI 和已有 `Session(molecule, calculation, source_path)` 构造入口都使用同一分子类型。

| 同步服务 | 行为 |
|---|---|
| `doc.publish_revision(expected, molecule, atom_ids, provenance=None, *, source_unit="angstrom")` | 在当前修订上提交。传入按新行顺序排列的旧 ID，新增位置填 `None`。删除的 ID 保留在历史快照中。基准已变抛 `StaleRevisionError`。 |
| `doc.restore_revision(expected, target)` | `history-restore/1`：把本文件已存在的历史修订完整复制为新修订，恢复原 ID、顺序、坐标、键、电子态及源单位。期望当前 head；不能恢复实际帧或当前修订自身。 |
| `doc.add_frame(base, frame_id, molecule, atom_ids, provenance, source_unit="angstrom")` | 将实际帧挂到指定修订，允许数组重排。须提供完整的 ID 与元素映射，电荷和多重度与该修订一致。编辑头继续指向原修订。 |
| `doc.resolve(ref)` | 精确解析文档、修订及帧。未找到抛 `GeometryLookupError`。 |
| `doc.add_dataset(data)`、`doc.dataset(id)` | 登记时检查实际几何和原子轴。同一数据集的相同递送可重试，冲突内容抛 `ValueError`。 |
| `doc.artifact(id)`、`doc.records()` | 按 ID 查询已登记的文件来源，或取同一时刻的不可变快照序列与数据集序列。 |

会话由调用端管理。后台生产者可持有文档并以明确的修订或实际帧发布数据。文档内的发布与一致性读取由同一把锁保护。直接赋值 `session.molecule` 兼容原型调用。已跟踪文档中，原子行完全相同的设置修改沿用 ID。整体替换坐标而未提供映射时，分配全新 ID。编辑器通过 `publish_revision` 提供实际映射。

设计页的碳环模板以一条编辑命令提交原子和键。用已有起始碳建环时保留其原子 ID。调整非环键键长时，去掉该键后，移动端所在的连通分量沿键轴整体平移。两类操作均可整步撤销或重做。

一次 `AddHydrogen` 编辑接受一个原子 ID，立即追加一个 H 及其与所选原子间的单键，保留已有坐标、原子 ID 和选区。单击「+H」启用连续加氢工具，点选目标原子后发布编辑。双击工具按钮则为当前结构补齐可确定的缺氢位点，合并为一次可撤销的编辑。自动补氢使用中性单重态模型，对只有坐标的多原子结构先感知键级。设计页显示键级总和异常及电子态诊断，允许继续修改草图。

两个按钮都在发起时保存几何快照，完成时由编辑器校验当前修订，再提交一个可撤销的操作。二维整理按分子拓扑绘制结构式。普通有机单键直链采用 120° 锯齿，环和复杂拓扑交给 Open Babel 的 `gen2D` 排版，绘图以 1.5 为参考键长。生成的结构式在草图平面内对齐到原有中心和朝向，按原子 ID 对应保存 XY。三维预优化在独立进程中使用 Open Babel 的 MMFF94 或 UFF，保存新的笛卡尔坐标及必要的感知键级，并保留当前二维草图。三维力场计算中临时使用的氢不会写入项目。ORCA 输入始终取实际分子的三维坐标。

从结果页选择「用此结构设计」时，编辑器解析所显示快照的完整 `GeometryRef`，将其几何发布为可撤销的编辑。仍在当前修订的原子沿用其 ID。采纳坐标不会移动或重新绑定原始计算数据集。

### 编辑历史恢复协议 `history-restore/1`

M1 提供恢复机制，M2 管理编辑命令和撤销/重做栈。命令记录提交前后的完整 `GeometryRef`；撤销调用 `doc.restore_revision(expected_head, before_ref)`，重做调用 `doc.restore_revision(expected_head, after_ref)`。每次成功都返回新的修订，下一次提交使用其完整引用作为期望值。历史修订和结果帧不删除、不改写，恢复后几何内容相同也不复用旧快照 ID。该入口只恢复完整修订；从实际结果帧派生编辑仍是后续独立协议。

`expected` 与当前 head 不同（包括同号但不同快照的分支）抛 `StaleRevisionError`；目标不在当前文档历史中抛 `GeometryLookupError`；目标不是完整引用、指向当前修订或实际帧时抛 `ValueError`。失败不发布修订。两个生产者对同一 head 提交，仅一个成功。普通 `publish_revision` 仍仅允许当前活跃 ID，新原子使用 `None`，不能借恢复协议任意混入历史 ID。

恢复来源使用现有 `Provenance` 字段，保留以下完整表示；参数按表中顺序保存，不能由普通编辑或文件导入伪装成恢复记录：

| 字段 | 固定语义 |
|---|---|
| `kind` | `history-restore`，仅文档恢复入口产生；初始快照和实际帧禁用 |
| `producer / producer_version` | `orcaview.document / 1`，版本指恢复协议 |
| `parents` | 空 tuple；目标几何通过下列引用追溯，原始来源保留在目标快照 |
| `parameters` | 依次为 `("target_document_id", target.document_id)`、`("target_revision", str(target.revision))`、`("target_snapshot_id", target.snapshot_id)`；目标的 `frame_id` 固定为 `None` |

项目回读与 `Session` 分支复制按发布顺序重放。恢复目标必须已在历史中，完整引用必须匹配；新修订的分子全部字段、有序原子 ID 和 `source_unit` 必须与目标一致，不能仅凭几何哈希认定恢复有效。缺失、额外或未知版本的恢复证据明确拒绝。这是内部一致性校验，不是项目文件真实性签名。

公共对象字段和项目 JSON 线格式不变，继续使用对象版本 1、schema 1/2。包含恢复历史的文件应由支持 `history-restore/1` 的读取器打开；旧读取器遇到重新启用已删除 ID 的修订会明确拒绝。没有重新启用已删除 ID 的恢复，旧读取器可保留来源后读取，但不会执行新增的恢复证据核验。升级后可直接读取旧项目，无需重新分配身份。撤销栈本身不在项目中保存，M2 可在重开后建立新栈，或日后另行定义持久化。

几何哈希的输入为版本前缀、有序元素原子序数和 Å 坐标的 IEEE 754 binary64 大端表示。正负零统一。名称、相机、显示设置、键、电荷及自旋在该哈希之外。即使两个几何哈希相同，结果仍须引用指定文档、修订及帧。

### 单位边界

科学坐标一律为 Å。单帧 XYZ 缺省按 Å 解读，也可在注释中明确写 `units=bohr` 或 `units=angstrom`。`io.xyz.parse_xyz_record` 返回分子、源单位及单位依据。导入来源的 `unit_source` 记录 `xyz-default` 或 `xyz-comment`。声明了晶胞、k 点、周期边界或未知长度单位的输入会报错。

`snapshot.coordinates("bohr")` 向数值调用方提供新的坐标 tuple。原坐标继续以 Å 保存。`core.units.convert_length` 双向使用同一换算因子，拒绝非有限值和浮点溢出。采用 2022 CODATA 的 `1 bohr = 0.529177210544 Å`。[NIST 常数表](https://www.physics.nist.gov/cuu/pdf/wallet_2022.pdf)

## M1 公共结果、事件与资源

| 对象 | 字段与约束 |
|---|---|
| `results.ResultDataset` | `dataset_id, kind, data_version, geometry, provenance, dtype, shape, unit, axes` 描述载荷。`method, density, spin, state_id, quality` 保存方法、密度、态与质量证据。`None` 表示相应元数据未知。 |
| `results.DatasetAxis` | `kind, ids`。每一维对应一条轴。原子、轨道、模态、态、自旋轴要求有序且唯一的身份，其数量等于轴长。规则网格轴允许只声明种类与长度。 |
| `tasks.TaskEvent` | `task_id, attempt_id, sequence, timestamp, kind, stage, progress, log, error`。时间带时区。未知进度为 `None`，已知进度为 0 到 1。`check_after` 校验同次尝试的序号严格递增。 |
| `tasks.ErrorInfo` | `code, reason, retryable, evidence`。重试性可以未知。证据使用文件引用。M4、M6 分别解释自己的领域状态。 |
| `tasks.ResourceBudget` | `processes, threads_per_process, total_memory_mb` 均为正整数。线程总数取乘积。内存预算以十进制 MB 计，覆盖整次任务。`CalculationSpec.maxcore_mb` 继续表示 ORCA 的每进程设定。 |

载荷支持 `float64` 和 `int64`。内联数值按 C 顺序展平，标量写作 `shape=(), values=(value,)`。部分缺失在原位置填 `None` 并给出 `missing_reason`，`valid_mask` 逐项反映有效性。整项缺失保留已知的形状、单位及原因，`values` 和 `array_ref` 都为空。

外部数组使用 `array_ref` 引用格式为 `raw-le` 的文件，按小端序连续存储，必须有 SHA-256。项目保存引用、形状和单位，文件字节由来源方保管。消费者显式传入选定路径并使用 `with data.open_array(path) as view`。服务分块校验大小、哈希与浮点有效性，再返回私有临时副本的只读映射。源文件之后的改动不影响已打开的映射。借用的缓冲区须在上下文结束前释放。丢失文件抛 `OSError`，数据失配抛 `ValueError`。重新定位相同内容后可再打开。分块校验与私有映射需要约一份载荷大小的临时磁盘空间。

## 项目 schema 2 与迁移

| 内容 | schema 1 | schema 2 |
|---|---|---|
| 公共字段 | `schema_version, software_version, calculation, source_path` | 同左，另有 `contract_version=1` |
| 结构 | 顶层 `molecule` | `document.coordinate_unit="angstrom"`，`document.snapshots` 按发布顺序保存所有修订与帧 |
| 结果 | 无对应字段 | `document.datasets` 保存内联结果或外部数组描述，恢复时校验几何引用与原子轴 |
| 旧数据 | 原字段可原样读写 | 迁移时新分配稳定 ID，保留原项目哈希和未经核实的旧来源路径 |

旧会话在使用身份接口前仍按 schema 1 保存。访问 `session.document`、导入 XYZ 或打开 schema 2 后，保存自动采用 schema 2。升级旧项目时另选新路径。`migrate_project(source, destination)` 以独占创建方式写入，目标文件已存在时抛 `FileExistsError`。两个版本均拒绝未知字段与重复 JSON 键。普通保存采用同目录临时文件、同步写盘和原子替换。外部数组按需验证，缺失的外部文件不妨碍项目内几何和元数据的恢复。

schema 2 此版保存一个分子文档的完整修订、实际帧和已登记的数据集。作业、尝试、分析请求以及视图状态的持久化由后续契约扩展。`TaskEvent` 与 `ResourceBudget` 已可在内存中使用。

## 输出摘要证据

schema 7 在顶层保存 `log_report`。其中 `source` 引用文档已登记的原始日志，`properties` 存名称、数值、单位、计算上下文和源行，`spectra` 存谱名、含单位的表头、逐行数值和表头源行，`status` 记录日志的终止信息。源行从 1 计数。文件级观察值可跨多个优化步，逐原子布居数据仍须绑定到对应快照的原子轴。重开项目仅从项目内数据还原这些记录。

schema 8 在各几何快照的分子对象中保存布尔字段 `bonds_explicit`。当它为真时，空键表表示用户明确指定这些原子之间没有键。旧格式中的空键表沿用按距离推断显示连线的行为。任一历史快照需要显式标记时，当前项目至少使用 schema 8，保留整段历史和所有原子 ID。该格式允许 `log_report` 取 null。

schema 9 保存键的绘图样式和有向端点。配位键以起点为供体，终点为受体。芳香键和部分三键分别表示 1.5 和 2.5 级。键型菜单参考 ChemDraw 对显示样式与分数键级的定义。[键级](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Bond_Order.htm) · [显示样式](https://iupac.github.io/IUPAC-FAIRSpec/cdx_sdk/properties/Bond_Display.htm)

仅包含常规键的旧项目仍可按原格式读写。

schema 10 允许在设计修订中保存零原子草稿。清空草图是一条可撤销的删除操作，已有修订、计算帧和结果数据集继续保存。当前草稿为空时，输入和结果页暂停结构相关操作。

schema 11 在可编辑的快照上记录可选的 `sketch_xy`。每个坐标对与同一行的稳定原子 ID 对应。几何哈希仍只包含元素和三维坐标。旧项目打开时从 XY 投影显示草图，首次二维整理或三维优化时保存独立图形。

`OutputSummary` 字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `normal_termination` | bool | 文本中是否观测到正常结束标记；不是总体成功结论 |
| `optimization_converged` | bool 或 None | 最后可识别的明确几何收敛证据；无证据为 None |
| `scf_converged` | bool 或 None | 最后可识别的明确 SCF 收敛证据；无证据为 None |
| `final_energy_hartree` | float 或 None | 最后可识别的有限 `FINAL SINGLE POINT ENERGY`；Hartree |
| `status` | str | 见下表 |
| `warnings` | tuple[str, ...] | 缺失、未验证或冲突证据 |

| 状态 | 解释 |
|---|---|
| `failed` | 出现可识别的明确异常终止证据，优先于旧正常结束标记 |
| `incomplete` | 缺少正常结束证据，可能截断、仍运行或失败 |
| `unconverged` | 有明确 SCF 或所需优化未收敛证据 |
| `needs_review` | 必需证据缺失、频率尚未验证或检测到多任务 |
| `completed` | 该单作业摘要的必要文本证据齐全，不证明科学结论正确 |

这是有限的文本证据提取器，不是完整 ORCA 语法解析器。多个 banner、`$new_job` 等常见多任务迹象会阻止 `completed`，但任意拼接、嵌套 compound 和所有版本的日志变体尚未覆盖。显示最后能量时不能默认它与当前 GUI 分子对应；GUI 明确将导入摘要作为独立来源。

频率任务即使正常结束，也只能进入 `needs_review`，不能进入 `completed`；明确失败和未完成仍优先显示各自状态。后续结果层需要验证真实模态、几何和完整性。缺失信息以 None 表示；不能用零值或 true 填补。

## 扩展接口原则

渲染后端、运行器与解析器可通过 G0 提案核对样例。完整视图状态、冻结计算输入、任务记录与内部数值服务仍由相应模块实现。M1 的数据往返可运行[独立示例](../examples/m1_roundtrip.py)。


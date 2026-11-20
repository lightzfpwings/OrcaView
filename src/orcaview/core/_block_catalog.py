"""Structured settings from the ORCA 6.1.1 manual.

See §§2.6 (SCF), 2.9 (integration), 2.21–22 (core and response),
3.3–5 (DFT, dispersion, xTB), 3.7 (ADFT), 4.1 (geometry) and 4.6
(frequencies). An omitted value is always delegated to ORCA.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from ._advanced_methods import CBS_PROTOCOLS
from ._dft_methods import DFT_METHOD_GROUPS, DLPNO_DOUBLE_HYBRIDS, EXTRA_DFT_GROUPS
from ._state_catalog import CASDFT_METHODS, DOUBLE_HYBRID_RESPONSE
from .methods import DISPERSION_RECIPES, METHODS, frozen_core_options
from .solvation import uses_numerical_frequencies


@dataclass(frozen=True)
class BlockOption:
    block: str
    key: str
    label: str
    kind: str
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: Tuple[str, ...] = ()
    hint: str = ""
    minimum_exclusive: bool = False
    maximum_exclusive: bool = False


def _positive(block, key, label, hint=""):
    return BlockOption(block, key, label, "float", minimum=0, minimum_exclusive=True, hint=hint)


def _iterations(block, key, label):
    return BlockOption(block, key, label, "int", minimum=1)


def _choice(block, key, label, choices):
    return BlockOption(block, key, label, "choice", choices=choices)


def _damping(key, label):
    return BlockOption("scf", key, label, "float", minimum=0, maximum=1, maximum_exclusive=True)


_SCF_ITER = _iterations("scf", "MaxIter", "SCF 最大迭代次数")
_SCF = (
    _SCF_ITER,
    _choice("scf", "Convergence", "SCF 收敛级别", ("Sloppy", "Loose", "Medium", "Strong", "Tight", "VeryTight", "Extreme")),
    _positive("scf", "TolE", "能量变化阈值（Eh）"),
    _positive("scf", "TolRMSP", "密度矩阵均方根变化阈值"),
    _positive("scf", "TolMaxP", "密度矩阵最大变化阈值"),
    _positive("scf", "TolErr", "DIIS 误差阈值"),
    _positive("scf", "TolG", "轨道梯度阈值"),
    _positive("scf", "TolX", "轨道旋转角阈值"),
    BlockOption("scf", "ConvCheckMode", "收敛判据组合", "int", 0, 2,
                hint="0 检查全部判据，1 任一判据通过即可，2 检查总能量和单电子能量变化。"),
    BlockOption("scf", "ConvForced", "后续步骤强制要求 SCF 收敛", "int", 0, 1),
    _positive("scf", "Thresh", "积分预筛选阈值"),
    _positive("scf", "TCut", "原始高斯积分预筛选阈值"),
    BlockOption("scf", "CNVDIIS", "启用 DIIS", "bool"),
    BlockOption("scf", "DIISStart", "启动 DIIS 的误差阈值", "float", minimum=0),
    _iterations("scf", "DIISMaxIt", "启动 DIIS 前的最大迭代数"),
    BlockOption("scf", "DIISMaxEq", "保留的 DIIS Fock 矩阵数", "int", minimum=1),
    _positive("scf", "DIISBFac", "DIIS 低能量偏置因子"),
    BlockOption("scf", "CNVDamp", "启用密度阻尼", "bool"),
    BlockOption("scf", "CNVZerner", "启用 Zerner 动态阻尼", "bool"),
    _damping("DampFac", "密度阻尼因子"),
    BlockOption("scf", "DampErr", "停用阻尼的误差阈值", "float", minimum=0),
    _damping("DampMin", "动态阻尼下限"),
    _damping("DampMax", "动态阻尼上限"),
    BlockOption("scf", "CNVShift", "启用虚轨道能级平移", "bool"),
    BlockOption("scf", "LShift", "虚轨道能级平移（Eh）", "float", minimum=0),
    BlockOption("scf", "ShiftErr", "停用能级平移的误差阈值", "float", minimum=0),
)
_SOSCF = (
    BlockOption("scf", "CNVSOSCF", "启用近似二阶 SCF", "bool"),
    _positive("scf", "SOSCFStart", "启动 SOSCF 的轨道梯度阈值"),
    _iterations("scf", "SOSCFMaxIt", "启动 SOSCF 前的最大迭代数"),
)
_TRAH = (
    BlockOption("scf", "AutoTRAH", "收敛缓慢时切换到 TRAH", "bool"),
    _positive("scf", "AutoTRAHTol", "自动切换所用收敛速率阈值"),
    _iterations("scf", "AutoTRAHIter", "最早切换到 TRAH 的迭代步"),
    BlockOption("scf", "AutoTRAHNInter", "估计收敛速率的迭代步数", "int", minimum=2),
    _iterations("scf.trah", "MaxRed", "Davidson 最大微迭代数"),
    BlockOption("scf.trah", "NStart", "Davidson 初始向量数", "int", minimum=2),
    _positive("scf.trah", "TolFacMicro", "微迭代阈值缩放因子"),
    _positive("scf.trah", "MinTolMicro", "微迭代精度下限"),
    _positive("scf.trah", "QuadRegionStart", "转入牛顿步的梯度阈值"),
    _positive("scf.trah", "tradius", "初始信赖半径"),
    _positive("scf.trah", "AlphaMin", "梯度缩放因子下限"),
    _positive("scf.trah", "AlphaMax", "梯度缩放因子上限"),
    BlockOption("scf.trah", "Randomize", "给 Davidson 起始向量添加随机扰动", "bool"),
    BlockOption("scf.trah", "PseudoRand", "使用可复现的伪随机扰动", "bool"),
    BlockOption("scf.trah", "MaxNoise", "随机扰动幅度上限", "float", minimum=0),
    _choice("scf.trah", "OrbUpdate", "轨道更新算法", ("Taylor", "Cayley")),
    _choice("scf.trah", "InactiveMOs", "非活性轨道处理", ("Canonical", "NotSet")),
    _choice("scf.trah", "Precond", "Hessian 预条件器", ("Diag", "Full", "None")),
    _iterations("scf.trah", "PreconMaxRed", "完整 Hessian 预条件空间上限"),
)
_NATIVE_XTB_SCF = (
    BlockOption("scf", "UseXTBMixer", "使用 xTB 专用 SCF 混合器", "bool"),
    BlockOption("scf", "SmearTemp", "电子温度（K）", "float", minimum=0),
    _SCF_ITER,
)
_DFT_METHODS = frozenset(name for _, entries in DFT_METHOD_GROUPS + EXTRA_DFT_GROUPS
                         for name, _ in entries if name != "HF") | DLPNO_DOUBLE_HYBRIDS.keys()
_DFT_GRID = (
    BlockOption("method", "AngularGrid", "交换关联角向积分网格", "int", 0, 7,
                hint="0 为 SimpleGrid，1–7 为不同阶数的 Lebedev 网格。"),
    _positive("method", "IntAcc", "交换关联径向积分精度"),
    _positive("method", "NThetaMax", "SimpleGrid 角向点数乘数"),
    _choice("method", "GridPruning", "积分网格裁剪", ("Adaptive", "OldPruning", "Unpruned")),
    BlockOption("method", "HGridReduced", "降低 H、He 的网格密度", "bool"),
    _positive("method", "BFCut", "数值积分基函数截断阈值"),
    _positive("method", "WeightCut", "积分权重截断阈值"),
)
_LIBXC = (
    _positive("method", "LibXCDensityThreshold", "LibXC 密度阈值"),
    _positive("method", "LibXCZetaThreshold", "LibXC 自旋极化阈值"),
    _positive("method", "LibXCTauThreshold", "LibXC 动能密度阈值"),
)
_ADFT = (
    _positive("method", "ADFTNRTol", "ADFT 牛顿迭代收敛阈值"),
    _iterations("method", "ADFTNRMaxIter", "ADFT 牛顿迭代最大次数"),
    BlockOption("method", "ADFTLmaxAuxJ", "库仑拟合的最大角动量", "int", minimum=0),
    BlockOption("method", "ADFTLmaxAuxX", "交换拟合的最大角动量", "int", minimum=0),
)
_DISPERSION_COEFFICIENTS = {
    "D3BJ": ("D3S6", "D3S8", "D3A1", "D3A2"),
    "D3ZERO": ("D3S6", "D3S8", "D3RS6", "D3alpha6"),
    "D4": ("D4S6", "D4S8", "D4A1", "D4A2", "D4S9"),
}
_DISPERSION_TUNING = {
    name: tuple(BlockOption("method", key, f"{name} 色散参数 {key}", "float",
                            hint="覆盖所选泛函的色散参数化。") for key in keys)
    for name, keys in _DISPERSION_COEFFICIENTS.items()
}
_FROZEN_CORE = (
    BlockOption("method", "CheckFrozenCore", "检查芯轨道排序", "bool"),
    BlockOption("method", "CorrectFrozenCore", "纠正错排的芯轨道", "bool"),
)
_CP_SCF = (
    _choice("method", "Z_Solver", "CP-SCF 线性方程求解器", ("Pople", "DIIS", "CG")),
    _positive("method", "Z_Tol", "CP-SCF 残差收敛阈值"),
    _iterations("method", "Z_MaxIter", "CP-SCF 最大迭代次数"),
    _iterations("method", "Z_MaxDIIS", "CP-SCF 保留的 DIIS 向量数"),
    BlockOption("method", "Z_Shift", "CP-SCF DIIS 能级平移", "float", minimum=0),
)
_COSX = (
    BlockOption("method", "UseSFitting", "COSX 重叠矩阵拟合", "bool"),
    _choice("method", "SFitInvertType", "重叠拟合矩阵求逆", ("Cholesky", "Cholesky_Q", "Diag", "Diag_Q")),
    _positive("method", "SInvThresh", "对角化求逆的本征值阈值"),
    BlockOption("method", "COSX_PartialContraction", "为广义收缩壳层使用中间基组", "bool"),
    _choice("method", "COSX_IntSymmetry", "COSX 积分置换对称性", ("Standard", "Full")),
)
_GEOM = (
    _iterations("geom", "MaxIter", "最大几何优化步数"),
    _choice("geom", "coordsys", "优化坐标系", ("redundant", "cartesian")),
    _choice("geom", "Convergence", "几何优化收敛级别", ("loose", "normal", "tight")),
    _positive("geom", "TolE", "能量变化阈值（Eh）"),
    _positive("geom", "TolRMSG", "均方根梯度阈值（原子单位）"),
    _positive("geom", "TolMaxG", "最大梯度阈值（原子单位）"),
    _positive("geom", "TolRMSD", "均方根位移阈值（原子单位）"),
    _positive("geom", "TolMaxD", "最大位移阈值（原子单位）"),
    _choice("geom", "Step", "优化步算法", ("qn", "rfo")),
    _positive("geom", "MaxStep", "内坐标最大步长（原子单位）"),
    BlockOption("geom", "Trust", "信赖半径（原子单位）", "float", hint="负值表示固定半径，正值表示可调整半径。"),
    _choice("geom", "InHess", "初始 Hessian 模型", ("unit", "Almloef", "Lindh", "Swart", "Schlegel")),
    _choice("geom", "Update", "Hessian 更新方法", ("BFGS", "Powell", "Bofill")),
    BlockOption("geom", "Calc_Hess", "开始优化时计算 Hessian", "bool"),
    _iterations("geom", "Recalc_Hess", "重新计算 Hessian 的步数间隔"),
    BlockOption("geom", "NumHess", "用数值微分计算优化中的 Hessian", "bool"),
    _iterations("geom", "NResetHess", "BFGS 模型 Hessian 重建间隔"),
    _iterations("geom", "NStepsInResetHess", "重建模型 Hessian 采用的历史步数"),
    BlockOption("geom", "ProjectTR", "投影笛卡尔优化的平移与转动", "bool"),
    BlockOption("geom", "AddExtraBonds", "为相邻原子添加额外的冗余内坐标键", "bool"),
    _iterations("geom", "AddExtraBonds_MaxLength", "额外成键原子间的拓扑距离上限（键数）"),
    _positive("geom", "AddExtraBonds_MaxDist", "额外成键原子间的空间距离上限（Å）"),
    BlockOption("geom", "optimizeHydrogens", "仅优化含氢坐标", "bool"),
    BlockOption("geom", "freezeHydrogens", "固定氢相对重原子的位置", "bool"),
)
_GEOM_TS = tuple(o for o in _GEOM if o.key != "Step") + (
    _choice("geom", "HESS_Modification", "P-RFO Hessian 修正方式", ("Shift_Diag", "EV_Reverse")),
    _positive("geom", "HESS_MinEV", "P-RFO Hessian 本征值绝对值下限"),
)
_FREQ = (
    BlockOption("freq", "TransInvar", "计算后施加 Hessian 平移不变性", "bool"),
    BlockOption("freq", "ProjectTR", "投影平移与转动自由度", "bool"),
)
_NUMFREQ = (
    BlockOption("freq", "CentralDiff", "使用中心差分", "bool", hint="关闭时使用单边差分。"),
    _positive("freq", "Increment", "数值位移步长（bohr）"),
    BlockOption("freq", "NumHessTransInvar", "计算位移梯度时利用平移不变性", "bool"),
)


def catalog_options(spec):
    preset = METHODS[spec.method]
    has_derivatives = spec.job_type != "SP"
    has_frequency = spec.job_type in ("FREQ", "OPT_FREQ")
    numerical = uses_numerical_frequencies(spec)
    options = []
    if spec.method.startswith("Native-"):
        options.extend(_NATIVE_XTB_SCF)
    elif spec.method in CBS_PROTOCOLS:
        # The extrapolation protocol sets TightSCF itself.
        options.append(_SCF_ITER)
    elif spec.method in CASDFT_METHODS:
        # !TRAH is part of the CASDFT recipe. Conventional SCF convergers
        # and switches that turn automatic TRAH on/off do not belong here.
        options.extend(o for o in _SCF if o.key in ("MaxIter", "Convergence", "TolE", "TolG", "TolX", "Thresh", "TCut"))
        options.extend(o for o in _TRAH if o.block == "scf.trah")
    elif preset.basis_mode != "semiempirical":
        options.extend(_SCF)
        if (spec.wavefunction not in ("ROHF", "ROKS") and
                spec.method not in ("ROCIS", "RI-ROCIS") and not spec.method.startswith("ADFT(")):
            options.extend(_SOSCF)
            # Section 2.6.7 lists PWPB95 as missing the required native kernel.
            if DLPNO_DOUBLE_HYBRIDS.get(spec.method, spec.method) != "PWPB95":
                options.extend(_TRAH)

    is_grid_dft = (spec.method in _DFT_METHODS or spec.method in DOUBLE_HYBRID_RESPONSE or spec.method.startswith("LibXC(") or
                   spec.method in DISPERSION_RECIPES or spec.method in
                   ("TDA-DFT", "TD-DFT", "ROCIS/DFT", "RI-ROCIS/DFT", "SF-TDA-BHANDHLYP", "RPAC(PBE)"))
    if is_grid_dft and spec.integration_grid == "Auto":
        options.extend(_DFT_GRID)
    if spec.method.startswith("LibXC("):
        options.extend(_LIBXC)
    if spec.method.startswith("ADFT("):
        options.extend(_ADFT)
    if spec.method == "RPAC(PBE)":
        options.append(_iterations("method", "RPACNPoints", "RPA 频率积分的求积点数"))
    if spec.integral_approximation == "RIJCOSX":
        options.extend(_COSX)
        if has_derivatives:
            options.append(BlockOption("method", "UseQGradFit", "梯度使用 SCF 重叠拟合矩阵", "bool"))
    options.extend(_DISPERSION_TUNING.get(spec.dispersion, ()))
    if spec.frozen_core != "NoFrozenCore" and "FrozenCore" in frozen_core_options(spec.method):
        options.extend(_FROZEN_CORE)
    mp2_response = has_derivatives and spec.method in ("MP2", "RI-MP2", "RI-SCS-MP2", "RI-SOS-MP2", "SCS-MP2")
    if (has_frequency and not numerical) or mp2_response:
        options.extend(_CP_SCF)
        if is_grid_dft and spec.integration_grid == "Auto":
            options.extend((BlockOption("method", "Z_GridXC", "CP-SCF 交换关联角向网格", "int", 0, 7),
                            _positive("method", "Z_IntAccXC", "CP-SCF 交换关联径向精度")))
        if spec.integral_approximation == "RIJCOSX":
            options.append(BlockOption("method", "Z_COSX_Alg", "CP-SCF COSX 算法", "int", 0, 2))
            if spec.integration_grid == "Auto":
                options.extend((BlockOption("method", "Z_GridX", "CP-SCF COSX 角向网格", "int", 0, 7),
                                _positive("method", "Z_IntAccX", "CP-SCF COSX 径向精度")))
                if mp2_response:
                    options.append(BlockOption("method", "Z_GridX_RHS", "MP2 Z 向量右端使用的 SCF 网格", "int", 1, 3))

    if spec.job_type in ("OPT", "OPT_FREQ"):
        options.extend(_GEOM)
    elif spec.job_type == "OPT_TS":
        options.extend(_GEOM_TS)
    if has_frequency:
        options.extend(_FREQ)
        if numerical:
            options.extend(_NUMFREQ)
    return tuple(options)


def validate_common_combinations(spec, values):
    """Check explicit switches against the controls that depend on them."""
    def fields(block):
        return {key: value for (path, key), value in values.items() if path == block}

    scf = fields("scf")
    geom = fields("geom")
    method = fields("method")
    trah = fields("scf.trah")
    for switch, keys in (
        ("CNVDIIS", ("DIISStart", "DIISMaxIt", "DIISMaxEq", "DIISBFac")),
        ("CNVShift", ("LShift", "ShiftErr")),
        ("CNVSOSCF", ("SOSCFStart", "SOSCFMaxIt")),
        ("AutoTRAH", ("AutoTRAHTol", "AutoTRAHIter", "AutoTRAHNInter")),
    ):
        if scf.get(switch) is False and any(key in scf for key in keys):
            raise ValueError(f"%scf {switch} 已关闭，不能同时设置其子参数")
    if spec.method.startswith("Native-") and "MaxIter" in scf and scf.get("UseXTBMixer") is not False:
        raise ValueError("原生 xTB 手动设置 SCF MaxIter 需要 UseXTBMixer false")
    if scf.get("CNVDamp") and scf.get("CNVZerner"):
        raise ValueError("CNVDamp 静态阻尼和 CNVZerner 动态阻尼互斥")
    if scf.get("CNVDamp") is False and not scf.get("CNVZerner") and any(
            k in scf for k in ("DampFac", "DampErr", "DampMin", "DampMax")):
        raise ValueError("已关闭静态与动态阻尼，不能设置阻尼参数")
    if trah and scf.get("AutoTRAH") is False:
        raise ValueError("%scf AutoTRAH 已关闭，不能设置 trah 子块")
    if scf.get("DampMin", 0.0) > scf.get("DampMax", 0.98):
        raise ValueError("动态阻尼下限 DampMin 不能大于 DampMax")
    if trah.get("AlphaMin", 0.1) > trah.get("AlphaMax", 1000.0):
        raise ValueError("TRAH 梯度缩放的 AlphaMin 不能大于 AlphaMax")
    if trah.get("Randomize") is False and any(k in trah for k in ("PseudoRand", "MaxNoise")):
        raise ValueError("TRAH 随机扰动参数需要启用 Randomize")
    if "PreconMaxRed" in trah and trah.get("Precond") != "Full":
        raise ValueError("PreconMaxRed 需要选择完整 Hessian 预条件器 Precond Full")
    if any(key in method for key in ("Z_MaxDIIS", "Z_Shift")) and method.get("Z_Solver") != "DIIS":
        raise ValueError("CP-SCF 的 DIIS 向量数和能级平移需要选择 Z_Solver DIIS")
    if "NThetaMax" in method and method.get("AngularGrid") != 0:
        raise ValueError("NThetaMax 只适用于 AngularGrid 0（SimpleGrid）")
    if method.get("UseSFitting") is False and (any(k in method for k in ("SFitInvertType", "SInvThresh"))
                                                or method.get("UseQGradFit") is True):
        raise ValueError("关闭 COSX 重叠拟合后不能设置其求逆算法或复用其矩阵计算梯度")
    if "SInvThresh" in method and method.get("SFitInvertType") not in ("Diag", "Diag_Q"):
        raise ValueError("SInvThresh 需要选择 Diag 或 Diag_Q 重叠拟合矩阵求逆")
    if method.get("CheckFrozenCore") is False and method.get("CorrectFrozenCore") is True:
        raise ValueError("关闭芯轨道排序检查后不能请求纠正排序")
    if geom.get("Trust") == 0.0:
        raise ValueError("%geom Trust 需要非零信赖半径")
    if geom.get("ProjectTR") and geom.get("coordsys") != "cartesian":
        raise ValueError("几何优化 ProjectTR true 需要选择笛卡尔坐标")
    bond_limits = ("AddExtraBonds_MaxLength", "AddExtraBonds_MaxDist")
    if geom.get("coordsys") == "cartesian" and any(k in geom for k in ("AddExtraBonds", *bond_limits)):
        raise ValueError("额外冗余内坐标键需要选择冗余内坐标")
    if geom.get("AddExtraBonds") is False and any(k in geom for k in bond_limits):
        raise ValueError("关闭 AddExtraBonds 后不能指定额外键的距离阈值")
    default_update = "Bofill" if spec.job_type == "OPT_TS" else "BFGS"
    if geom.get("Update", default_update) != "BFGS" and any(k in geom for k in ("NResetHess", "NStepsInResetHess")):
        raise ValueError("模型 Hessian 重建间隔和历史步数仅用于 BFGS 更新")
    if geom.get("optimizeHydrogens") and geom.get("freezeHydrogens"):
        raise ValueError("仅优化含氢坐标与固定氢相对位置不能同时启用")
    if geom.get("coordsys") == "cartesian" and geom.get("InHess") == "Lindh":
        raise ValueError("Lindh 初始 Hessian 需要冗余内坐标")
    if "InHess" in geom and (geom.get("Calc_Hess") or "Recalc_Hess" in geom):
        raise ValueError("起始步计算 Hessian 时不能同时指定初始模型 InHess")
    if geom.get("Calc_Hess") is False and "Recalc_Hess" in geom:
        raise ValueError("Recalc_Hess 会在起始步计算 Hessian，与 Calc_Hess false 冲突")
    if "NumHess" in geom and not (geom.get("Calc_Hess") or "Recalc_Hess" in geom):
        raise ValueError("NumHess 需要同时请求 Calc_Hess 或 Recalc_Hess")
    if (geom.get("Calc_Hess") or "Recalc_Hess" in geom) and geom.get("NumHess") is not True:
        if uses_numerical_frequencies(spec):
            raise ValueError("当前方法的优化 Hessian 需要设置 %geom NumHess true")

"""ORCA 6.1.1 electronic-structure solver controls.

Native keyword references: CASSCF §3.13, ICE §3.14, NEVPT2 §3.16,
CASPT2 §3.17, MRCI §3.19, MP2 §3.9, MDCI/CIM §3.10, AUTOCI §3.11,
MRCC §3.12, and ADC/TD-DFT/ROCIS/EOM/STEOM §§5.4–5.10.
https://orca-manual.mpi-muelheim.mpg.de/index.html
"""

from ._block_catalog import BlockOption, _positive
from ._dft_methods import DLPNO_DOUBLE_HYBRIDS
from ._state_catalog import (
    ACTIVE_SPACE_METHODS, CASDFT_METHODS, DOUBLE_HYBRID_RESPONSE, MCRPA_METHODS, MDCI_METHODS,
    MREOM_METHODS, RESPONSE_METHODS, ROCIS_METHODS, _CAS_AUTOCI, _UNCONTRACTED,
)
from ._wavefunction_methods import OTHER_METHOD_GROUPS


def _count(block, key, label, minimum=1, hint=""):
    return BlockOption(block, key, label, "int", minimum=minimum, hint=hint)


def _davidson(block):
    return (
        _count(block, "MaxIter", "最大迭代次数"),
        _count(block, "MaxDim", "Davidson 空间倍数", hint="展开空间大小为该倍数乘以目标根数。"),
        _count(block, "NGuessMat", "初猜矩阵阶数"),
        _positive(block, "ETol", "能量收敛阈值（Eh）"),
        _positive(block, "RTol", "残差收敛阈值"),
    )


_TWO_STEP = ("SuperCI_PT", "SuperCI", "DIIS", "KDIIS", "SOSCF", "NR")
_CASSCF = (
    _count("casscf", "MaxIter", "轨道优化最大宏迭代数", 2, "一次宏迭代将转为固定轨道 CASCI。"),
    _positive("casscf", "GTol", "轨道梯度收敛阈值"),
    _positive("casscf", "ETol", "宏迭代能量收敛阈值（Eh）"),
    BlockOption("casscf", "OrbStep", "初始轨道优化算法", "choice", choices=_TWO_STEP),
    BlockOption("casscf", "SwitchStep", "后期轨道优化算法", "choice", choices=_TWO_STEP),
    _positive("casscf", "SwitchConv", "切换轨道优化算法的梯度范数"),
    _count("casscf", "SwitchIter", "切换轨道优化算法的宏迭代步"),
    BlockOption("casscf", "ShiftUp", "虚轨道向上位移（Eh）", "float", minimum=0),
    BlockOption("casscf", "ShiftDn", "非活性轨道向下位移（Eh）", "float", minimum=0),
    BlockOption("casscf", "MinShift", "子空间最小能量间隔（Eh）", "float", minimum=0),
    BlockOption("casscf", "ActConstraints", "活性轨道约束方式", "int", minimum=0, maximum=4,
                hint="0 关闭，1 最大重叠，2 自然轨道，3 正则轨道，4 局域轨道。"),
    _positive("casscf", "MaxRot", "SuperCI_PT 的轨道旋转步长上限"),
    BlockOption("casscf", "DThresh", "SuperCI_PT 的临界占据阈值", "float", minimum=0),
    _count("casscf", "MaxDIIS", "轨道优化保留的 DIIS 向量数"),
    _positive("casscf", "DIISThresh", "轨道优化 DIIS 线性相关阈值"),
    _positive("casscf", "GradScaling", "轨道优化梯度缩放"),
)
_AH = "casscf.aughess"
_AUGHESS = (
    BlockOption(_AH, "Solver", "增广 Hessian 求解器", "int", minimum=0, maximum=2,
                hint="0 为 Davidson，1 为 Pople，2 为 DIIS。需要选择 NR 轨道优化。"),
    _count(_AH, "MaxIter", "增广 Hessian 最大迭代数"),
    _count(_AH, "MaxDim", "Davidson 展开空间维数"),
    _count(_AH, "MaxDIIS", "增广 Hessian 的 DIIS 向量数"),
    BlockOption(_AH, "UseSubMatrixGuess", "对角化子矩阵生成初猜", "bool"),
    _count(_AH, "NGuessMat", "生成初猜的子矩阵维数"),
    _count(_AH, "ExactDiagSwitch", "直接对角化的维数上限"),
    _positive(_AH, "Tol", "增广 Hessian 收敛阈值"),
    BlockOption(_AH, "Compress", "使用压缩存储", "bool"),
    BlockOption(_AH, "DiagShift", "Hessian 对角线位移", "float"),
    BlockOption(_AH, "UseDiagPrec", "使用对角预条件", "bool"),
    BlockOption(_AH, "SecShift", "Davidson 高根位移", "float"),
    BlockOption(_AH, "UpdateShift", "更新系数的分母位移", "float"),
)
_DMRG = "casscf.dmrg"
_DMRG_OPTIONS = (
    _count(_DMRG, "startM", "起始重整化态数"),
    _count(_DMRG, "maxM", "最大重整化态数"),
    _count(_DMRG, "MaxIter", "最大扫描次数"),
    _positive(_DMRG, "SweepTol", "扫描能量收敛阈值"),
    BlockOption(_DMRG, "auto_ordering", "活性轨道排序", "choice", choices=("NOREORDER", "FIEDLER", "GAOPT")),
    BlockOption(_DMRG, "hf_occ", "初始轨道占据", "int", minimum=1, maximum=2,
                hint="1 按单电子积分，2 按正则轨道能量排序。"),
    _positive(_DMRG, "switch_rst", "切换至单点 DMRG 更新的轨道梯度阈值"),
    BlockOption(_DMRG, "warmup", "预热算法", "int", minimum=1, maximum=4),
)
_CI = _davidson("casscf.CI")
_ICE = (
    _positive("casscf.CI", "TGen", "ICE 生成阈值"),
    BlockOption("casscf.CI", "TVar", "ICE 变分选择阈值", "float",
                hint="正数为绝对阈值。负数的绝对值乘以 TGen，得到实际阈值。"),
    BlockOption("casscf.CI", "ICEType", "ICE 组态表示", "choice", choices=("CFGs", "CSFs", "DETs")),
)
_PT = "casscf.PTSettings"
_PT_SCREENING = (
    BlockOption(_PT, "D3TPre", "三阶密度矩阵预筛阈值", "float", minimum=0),
    BlockOption(_PT, "D4TPre", "四阶密度矩阵预筛阈值", "float", minimum=0),
)
_CASPT2 = (
    _count(_PT, "MaxIter", "微扰方程最大迭代数"),
    _count(_PT, "MaxDIIS", "DIIS 向量数"),
    _positive(_PT, "NThresh", "内收缩组态线性相关阈值"),
    BlockOption(_PT, "CASPT2_ishift", "虚能级位移（Eh）", "float", minimum=0),
    BlockOption(_PT, "CASPT2_rshift", "实能级位移（Eh）", "float"),
    BlockOption(_PT, "CASPT2_IPEAshift", "IPEA 位移（Eh）", "float"),
)
_MRCI = (
    _count("mrci", "MaxIter", "CI 求解器最大迭代数"),
    _positive("mrci", "Etol", "CI 能量收敛阈值（Eh）"),
    _positive("mrci", "Rtol", "CI 残差收敛阈值"),
)
_MRCI_SELECTION = (
    BlockOption("mrci", "TSel", "激发组态选择阈值", "float", minimum=0),
    BlockOption("mrci", "TPre", "参考组态预筛阈值", "float", minimum=0),
)
_MREOM_AMPLITUDES = (
    _count("mdci", "MaxIter", "多参考振幅最大迭代数"),
    _positive("mdci", "STol", "多参考振幅残差收敛阈值"),
)
_AUTOCI = (
    _count("autoci", "MaxIter", "最大迭代次数"),
    _count("autoci", "MaxDIIS", "DIIS 向量数"),
    _count("autoci", "DIISStartIter", "DIIS 起始迭代", 0, "迭代编号从 0 开始。"),
    _positive("autoci", "STol", "振幅残差收敛阈值"),
    BlockOption("autoci", "LevelShift", "DIIS 能级位移（Eh）", "float"),
)
_MDCI_GROUND = (
    _count("mdci", "MaxIter", "基态振幅最大迭代数"),
    _count("mdci", "MaxDIIS", "基态 DIIS 向量数"),
    _positive("mdci", "STol", "基态振幅残差收敛阈值"),
    BlockOption("mdci", "LShift", "振幅更新能级位移（Eh）", "float"),
)
_EOM_DAVIDSON = (
    _count("mdci", "NDav", "Davidson 空间倍数", hint="展开空间大小为该倍数乘以目标根数。"),
    BlockOption("mdci", "DoRootwise", "逐根求解", "bool"),
)
_EOM = (
    _positive("mdci", "DTol", "Davidson 残差收敛阈值"),
    _positive("mdci", "OTol", "正交化阈值"),
)
_CANONICAL_EOM = (
    _count("mdci", "NInits", "CIS 初猜根数倍数", 0, "0 由 ORCA 根据根数和 NDav 选择。"),
    BlockOption("mdci", "FollowCIS", "跟踪初始 CIS 根", "bool"),
    BlockOption("mdci", "UseCISUpdate", "用 CIS 对角元更新试探向量", "bool"),
)
_STEOM = (
    BlockOption("mdci", "OThresh", "IP 活性占据轨道选择阈值", "float", minimum=0),
    BlockOption("mdci", "VThresh", "EA 活性虚轨道选择阈值", "float", minimum=0),
)
_CANONICAL_STEOM = (
    BlockOption("mdci", "DoDbFilter", "过滤以双激发为主的态", "bool"),
    BlockOption("mdci", "DoNewActSch", "使用新的活性空间选择算法", "bool"),
    BlockOption("mdci", "IPSThrs", "IP 根的单激发百分比阈值", "int", 0, 100),
    BlockOption("mdci", "EASThrs", "EA 根的单激发百分比阈值", "int", 0, 100),
    _count("mdci", "NRootsCISNAT", "活性空间选择的 CIS 初始根数"),
)
_ROOT_TRACKING = (
    BlockOption("mdci", "CheckEachRoot", "逐根检查收敛", "bool"),
    BlockOption("mdci", "RootHoming", "按重叠跟踪目标根", "bool"),
)
_PNO = {
    block: (
        BlockOption(block, "TCutPNO", "对自然轨道占据截断", "float", minimum=0),
        BlockOption(block, "TCutDO", "局域轨道域截断", "float", minimum=0),
        BlockOption(block, "TCutMKN", "局域辅助拟合域截断", "float", minimum=0),
    ) for block in ("mp2", "mdci")
}
_MP2_MEMORY = _count("mp2", "MaxCore", "MP2 每核内存上限（MB）",
                     hint="覆盖 MP2 阶段的每核内存预算。")
_MP2_Q1 = BlockOption("mp2", "Q1Opt", "常规 MP2 积分算法", "int", minimum=-1, maximum=2,
                      hint="−1 为磁盘算法，1、2 分别为双精度和单精度缓冲的内存算法。梯度计算要求内存算法。")
_REGULARIZED_MP2 = (
    BlockOption("mp2", "DoRegMP2", "启用正则化 MP2", "bool"),
    BlockOption("mp2", "RegMP2Type", "正则化类型", "int", minimum=0, maximum=2,
                hint="启用正则化后，0 为 κ，1 为 σ，2 为 σ²。"),
    _positive("mp2", "RegMP2Kappa", "κ 正则化参数"),
    _positive("mp2", "RegMP2Sigma", "σ 正则化参数"),
)
_LOCAL_MP2 = (
    _count("mp2", "MaxPNOIter", "局域振幅最大迭代数"),
    _count("mp2", "MaxLocIter", "轨道局域化最大迭代数"),
    _positive("mp2", "TolE", "局域 MP2 能量收敛阈值（Eh）"),
    _positive("mp2", "TolR", "局域振幅残差阈值"),
    _positive("mp2", "LocTol", "轨道局域化收敛阈值"),
    BlockOption("mp2", "LocMet", "局域化方法", "choice", choices=("AHFB", "FB", "PM", "IAOIBO", "IAOBOYS", "NEWBOYS")),
    _count("mp2", "DIISStart_PNO", "PNO 振幅 DIIS 起始步", minimum=0),
    _count("mp2", "MaxDIIS_PNO", "PNO 振幅 DIIS 向量数"),
    BlockOption("mp2", "Damp1_PNO", "启动 DIIS 之前的阻尼", "float", 0, 1, maximum_exclusive=True),
    BlockOption("mp2", "Damp2_PNO", "DIIS 期间的阻尼", "float", 0, 1, maximum_exclusive=True),
    BlockOption("mp2", "MP2Shift_PNO", "局域振幅更新的能级位移（Eh）", "float"),
)
_MP2_SCREENING = tuple(BlockOption("mp2", key, label, "float", minimum=0) for key, label in (
    ("FCut", "占据轨道 Fock 矩阵元截断"), ("TCutPre", "偶极预筛的能量阈值"),
    ("TCutDOij", "轨道对差分重叠预筛阈值"), ("TCutDOPre", "预筛时选取投影原子轨道的阈值"),
    ("TCutC", "投影原子轨道系数截断"), ("ScaleTCutC_MO", "分子轨道截断相对 TCutC 的倍数"),
    ("PAOOverlapThresh", "投影原子轨道线性相关阈值"),
))
_MDCI_SCREENING = (
    BlockOption("mdci", "TCutPairs", "电子对的估算关联能截断", "float", minimum=0),
    BlockOption("mdci", "TCutDeloc", "扩展局域域的离域阈值", "float", minimum=0),
    BlockOption("mdci", "TCutOSV", "预筛中轨道特定虚轨道的阈值", "float", minimum=0),
    BlockOption("mdci", "PAOOverlapThresh", "投影原子轨道线性相关阈值", "float", minimum=0),
)
_MCRPA = (
    _positive("mcrpa", "TolR", "响应方程残差范数阈值"),
    _count("mcrpa", "MaxIter", "响应方程 Davidson 最大迭代数"),
    _count("mcrpa", "MaxRed", "所有响应向量共用的展开空间维数"),
    BlockOption("mcrpa", "PreCond", "响应方程预条件器", "choice", choices=("full", "diag")),
    _count("mcrpa", "PreConMaxRed", "预条件中精确 Hessian 子空间的维数"),
)
_ORBITAL_MP2 = (
    _count("mp2", "MaxOrbIter", "最大轨道迭代数"),
    BlockOption("mp2", "MP2Shift", "轨道优化能级位移（Eh）", "float"),
)

_CASCI_NAMES = ("CASCI", "ICE-CASCI", "DMRG-CASCI", "FCI")
_CASPT2_NAMES = ("CASPT2", "CASPT2K", "RI-CASPT2", "RI-CASPT2K")
_NEVPT2_NAMES = ("SC-NEVPT2", "SA-SC-NEVPT2", "QD-SC-NEVPT2", "RI-NEVPT2", "FIC-NEVPT2", "DLPNO-NEVPT2")
_FIC_AUTOCI = {name for name, _ in _CAS_AUTOCI}
_UNCONTRACTED_NAMES = {name for name, _ in _UNCONTRACTED}
_STANDARD_MP2 = ("MP2", "SCS-MP2", "RI-MP2", "RI-SCS-MP2", "RI-SOS-MP2")
_OO_MP2 = ("OO-RI-MP2", "OO-RI-SCS-MP2", "OO-RI-SOS-MP2")
_DLPNO_MP2 = ("DLPNO-MP2", "DLPNO-SCS-MP2", "DLPNO-SOS-MP2", "F12-DLPNO-MP2", "F12/D-DLPNO-MP2")
_GROUND_MDCI_NAMES = {name for family, entries in OTHER_METHOD_GROUPS if family in
                      ("耦合簇", "组态相互作用与电子对方法") for name, _ in entries}
_CANONICAL_MDCI = {name for name in _GROUND_MDCI_NAMES if not name.startswith(("DLPNO-", "pCCSD/"))}
MDCI_RHF_ONLY_KC = ("KC_AO", "KC_AOBLAS", "KC_RI", "KC_RI2")
_ADC_NAMES = ("ADC2", "IP-ADC2", "EA-ADC2")


def _mdci_integral_options(spec):
    # §3.10.2 and §3.10.14 distinguish transformation of the lower-rank
    # integrals from formation of terms with 3–4 external indices.
    kc = ("KC_MO", "KC_AOX")
    if spec.wavefunction in ("Auto", "RHF"):
        kc += MDCI_RHF_ONLY_KC
    return (BlockOption("mdci", "KCOpt", "含三、四个外部指标的 MDCI 积分算法", "choice", choices=kc,
                        hint="MO 全变换，AOX 用预存 AO 积分。AO 直接和 RI 外部积分算法需要闭壳层参考。"),
            BlockOption("mdci", "TrafoType", "MDCI 积分变换", "choice",
                        choices=("trafo_jk", "trafo_ri", "trafo_full"),
                        hint="jk 为 J/K 部分变换，ri 用关联拟合基组，full 为完整四指标变换。"))


def _cas_options(method):
    if method in CASDFT_METHODS:
        result = tuple(o for o in _CASSCF if o.key in ("MaxIter", "ETol", "GTol"))
        if method.removeprefix("CI-").startswith("sr"):
            result += (_positive("method", "RangeSepMu", "短程泛函的范围分离参数（bohr⁻¹）"),)
        return result
    result = () if method in _CASCI_NAMES else _CASSCF + _AUGHESS
    if method in ("DMRG-CASSCF", "DMRG-CASCI"):
        return result + tuple(o for o in _DMRG_OPTIONS if method == "DMRG-CASSCF" or o.key != "switch_rst")
    result += _CI
    if method in MCRPA_METHODS:
        result += _MCRPA
    if method.startswith("ICE-"):
        result += _ICE
    if method in _CASPT2_NAMES or method in _NEVPT2_NAMES:
        result += _PT_SCREENING
    if method in _CASPT2_NAMES:
        result += _CASPT2
        if method.endswith("CASPT2K"):
            result += (_positive(_PT, "TReg", "CASPT2-K 的 Tikhonov 正则化参数"),)
    if method in ("FIC-NEVPT2", "SC-NEVPT2", "RI-NEVPT2", "SA-SC-NEVPT2"):
        result += (BlockOption(_PT, "D4Step", "高阶约化密度矩阵算法", "choice",
                               choices=("efficient", "fly", "Cu4", "Cu34")),)
    if method == "FIC-NEVPT2":
        result += (BlockOption(_PT, "imaginary", "虚能级位移（Eh）", "float", minimum=0),
                   _positive(_PT, "NThresh", "内收缩组态线性相关阈值"))
    if method in _UNCONTRACTED_NAMES or method in MREOM_METHODS:
        result += _MRCI
    if method in _UNCONTRACTED_NAMES:
        result += _MRCI_SELECTION
    if method in MREOM_METHODS:
        result += _MREOM_AMPLITUDES
    if method in _FIC_AUTOCI:
        result += (_positive("autoci", "NThresh", "内收缩组态线性相关阈值"),)
        if method in ("FIC-MRCI", "FIC-CEPA(0)", "FIC-ACPF", "FIC-AQCC", "FIC-DDCI3", "FIC-MRCC"):
            result += _AUTOCI
    return result


def _mp2_options(spec):
    name = spec.method
    result = (_MP2_MEMORY,)
    if name in ("MP2", "SCS-MP2"):
        result += (_MP2_Q1,)
    if spec.job_type == "SP" and (name == "MP2" or (
            name == "RI-MP2" and spec.integral_approximation in ("RIJONX", "RIJCOSX", "RI-JK"))):
        result += _REGULARIZED_MP2
    if name in _OO_MP2:
        result += _ORBITAL_MP2
    if name in _DLPNO_MP2 or name in DLPNO_DOUBLE_HYBRIDS:
        result += _LOCAL_MP2
        if spec.pno_preset == "Auto":
            result += _PNO["mp2"] + _MP2_SCREENING
    return result


def solver_options(spec):
    method = spec.method
    if method in ACTIVE_SPACE_METHODS or method == "FCI":
        return _cas_options(method)
    if method in RESPONSE_METHODS:
        result = _davidson("tddft")
        if (method in ("TD-DFT", "TDA-DFT", "SF-TDA-BHANDHLYP") or method in DOUBLE_HYBRID_RESPONSE) and spec.integration_grid == "Auto":
            result += (BlockOption("tddft", "GridXC", "激发态交换关联角向网格", "int", 0, 7),
                       _positive("tddft", "IntAccXC", "激发态交换关联径向精度"))
        return result
    if method in ROCIS_METHODS:
        return _davidson("rocis")
    if method in _ADC_NAMES:
        return _EOM_DAVIDSON + _ROOT_TRACKING
    if method in MDCI_METHODS:
        # The order-two approximation skips the normal ground-state CCSD solve.
        result = () if method.endswith("(2)") else _MDCI_GROUND
        if method != "IH-FSMR-CCSD":
            result += _EOM_DAVIDSON + _EOM
        if "STEOM" in method:
            result += _STEOM
            if method in ("STEOM-CCSD", "STEOM-CCSD(2)"):
                result += _CANONICAL_STEOM
        elif "EOM" in method:
            result += _ROOT_TRACKING
        if method in ("EOM-CCSD", "EOM-CCSD(2)", "IP-EOM-CCSD", "EA-EOM-CCSD"):
            result += _CANONICAL_EOM
        return result
    if method in _STANDARD_MP2 + _OO_MP2 + _DLPNO_MP2 or method in DLPNO_DOUBLE_HYBRIDS:
        return _mp2_options(spec)
    if method in _GROUND_MDCI_NAMES or ("F12" in method and "MP2" not in method):
        result = _MDCI_GROUND
        if method in _CANONICAL_MDCI:
            result += _mdci_integral_options(spec)
        if method in ("CCSD(T)", "RI-CCSD(T)", "QCISD(T)") and spec.wavefunction == "RHF":
            result += (BlockOption("mdci", "Triples", "微扰三激发算法", "int", 1, 2,
                                   hint="1 使用高内存算法，2 使用较低内存的闭壳层算法。"),)
        if method.startswith("DLPNO-CCSD") and spec.pno_preset == "Auto":
            result += _PNO["mdci"] + _MDCI_SCREENING
            if "(T" in method:
                result += (BlockOption("mdci", "TCutTNO", "三电子激发自然轨道截断（0 为自动）", "float", minimum=0),)
        return result
    if method.startswith("AUTOCI-") and not method.startswith("AUTOCI-MP"):
        return _AUTOCI
    if method.startswith("CIM-"):
        return (_positive("cim", "CIMTHRESH", "团簇构建重叠阈值"),)
    if method.startswith("MRCC-"):
        return (_count("mrcc", "ETol", "能量收敛精度指数", hint="此接口使用整数精度指数，如 9。"),)
    return ()


def validate_solver_combinations(spec, values):
    casscf = {key: value for (block, key), value in values.items() if block == "casscf"}
    stages = {casscf.get("OrbStep", "SuperCI_PT"), casscf.get("SwitchStep", "SuperCI_PT")}
    if "SuperCI_PT" not in stages and any(k in casscf for k in ("MaxRot", "DThresh")):
        raise ValueError("MaxRot 和 DThresh 需要在一个轨道优化阶段使用 SuperCI_PT")
    if stages.isdisjoint(("SuperCI_PT", "DIIS", "KDIIS")) and any(k in casscf for k in ("MaxDIIS", "DIISThresh")):
        raise ValueError("轨道优化 DIIS 设置需要 SuperCI_PT、DIIS 或 KDIIS 阶段")
    aughess = {key: value for (block, key), value in values.items() if block == _AH}
    if aughess:
        if "NR" not in stages:
            raise ValueError("aughess 设置需要在一个轨道优化阶段选择 NR")
        solver = aughess.get("Solver", 0)
        if solver != 0 and any(k in aughess for k in ("MaxDim", "SecShift")):
            raise ValueError("增广 Hessian 的 MaxDim 和 SecShift 需要 Davidson 求解器")
        if solver != 2 and "MaxDIIS" in aughess:
            raise ValueError("增广 Hessian 的 MaxDIIS 需要 DIIS 求解器")
        if aughess.get("UseSubMatrixGuess") is False and "NGuessMat" in aughess:
            raise ValueError("关闭增广 Hessian 子矩阵初猜后不能设置 NGuessMat")
    if (_DMRG, "startM") in values and (_DMRG, "maxM") in values and values[_DMRG, "startM"] > values[_DMRG, "maxM"]:
        raise ValueError("DMRG 的起始重整化态数 startM 不能超过 maxM")
    if ("mdci", "NRootsCISNAT") in values and values["mdci", "NRootsCISNAT"] < spec.nroots:
        raise ValueError("用于 STEOM 活性空间的 CIS 根数不能小于目标根数")
    if ("mcrpa", "PreConMaxRed") in values and values.get(("mcrpa", "PreCond")) == "diag":
        raise ValueError("MCRPA 的完整 Hessian 预条件空间需要 PreCond full")
    kc = values.get(("mdci", "KCOpt"))
    trafo = values.get(("mdci", "TrafoType"))
    if kc == "KC_MO" and trafo in ("trafo_jk", "trafo_ri"):
        raise ValueError("KC_MO 使用完整四指标变换，不能同时指定部分或 RI 积分变换")
    if spec.method in ("RI-CCSD", "RI-CCSD(T)") and (kc == "KC_MO" or
            (kc in ("KC_AO", "KC_AOBLAS", "KC_AOX") and trafo in ("trafo_jk", "trafo_full"))):
        raise ValueError("选定的 RI-MDCI 方法需要关联积分变换或外部积分至少一处使用 RI")
    q1 = values.get(("mp2", "Q1Opt"))
    if q1 == 0 or (q1 == -1 and spec.job_type != "SP"):
        raise ValueError("mp2.Q1Opt 接受 −1 或正整数，梯度与频率任务需要正整数")
    regularized = values.get(("mp2", "DoRegMP2"), False)
    if any(("mp2", key) in values for key in ("RegMP2Type", "RegMP2Kappa", "RegMP2Sigma")) and not regularized:
        raise ValueError("请先开启 mp2.DoRegMP2，再指定正则化参数")
    if regularized:
        if spec.method == "MP2" and (q1 is None or q1 < 1):
            raise ValueError("常规 MP2 的正则化需要显式选择内存算法 mp2.Q1Opt > 0")
        reg_type = values.get(("mp2", "RegMP2Type"), 0)
        if (reg_type == 0 and ("mp2", "RegMP2Sigma") in values
                or reg_type in (1, 2) and ("mp2", "RegMP2Kappa") in values):
            raise ValueError("mp2.RegMP2Type 与所填 κ 或 σ 参数不匹配")

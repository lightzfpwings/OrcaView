"""Intrinsic reaction coordinate settings, ORCA 6.1.1 §4.4."""

from ._block_catalog import BlockOption
from .solvation import uses_numerical_frequencies


def options(spec):
    if spec.job_type != "IRC":
        return ()
    algorithms = ("calc_numfreq",) if uses_numerical_frequencies(spec) else ("calc_anfreq", "calc_numfreq")
    return (
        BlockOption("irc", "MaxIter", "IRC 最大步数", "int", 1),
        BlockOption("irc", "Direction", "路径方向", "choice", choices=("both", "forward", "backward", "down")),
        BlockOption("irc", "InitHess", "初始 Hessian 算法", "choice", choices=algorithms),
        BlockOption("irc", "hessMode", "初始位移的 Hessian 模式（从 0 起）", "int", 0),
        BlockOption("irc", "Init_Displ_DE", "初始位移定义", "choice", choices=("DE", "length")),
        BlockOption("irc", "Scale_Init_Displ", "初始位移长度（原子单位）", "float", 0, minimum_exclusive=True),
        BlockOption("irc", "DE_Init_Displ", "初始位移能量差（mEh）", "float", 0, minimum_exclusive=True),
        BlockOption("irc", "Scale_Displ_SD", "最速下降步长系数", "float", 0, minimum_exclusive=True),
        BlockOption("irc", "Adapt_Scale_Displ", "随路径调整步长", "bool"),
        BlockOption("irc", "SD_ParabolicFit", "最速下降步使用抛物线拟合", "bool"),
        BlockOption("irc", "Interpolate_only", "抛物线拟合仅允许插值", "bool"),
        BlockOption("irc", "Do_SD_Corr", "校正最速下降步", "bool"),
        BlockOption("irc", "Scale_Displ_SD_Corr", "校正步的长度系数", "float", 0, minimum_exclusive=True),
        BlockOption("irc", "SD_Corr_ParabolicFit", "校正步使用抛物线拟合", "bool"),
        BlockOption("irc", "TolRMSG", "均方根梯度阈值（原子单位）", "float", 0, minimum_exclusive=True),
        BlockOption("irc", "TolMaxG", "最大梯度阈值（原子单位）", "float", 0, minimum_exclusive=True),
    )


def validate(values):
    fields = {key: v for (block, key), v in values.items() if block == "irc"}
    if fields.get("Direction") == "down" and fields.keys() & {
            "InitHess", "hessMode", "Init_Displ_DE", "Scale_Init_Displ", "DE_Init_Displ"}:
        raise ValueError("IRC 的 down 方向沿梯度下降，不能同时设置 Hessian 初始位移")
    length = fields.get("Init_Displ_DE", "DE") == "length"
    if (length and "DE_Init_Displ" in fields) or (not length and "Scale_Init_Displ" in fields):
        raise ValueError("IRC 初始位移参数与选定的 DE / length 模式不匹配")
    if fields.get("Do_SD_Corr") is False and fields.keys() & {"Scale_Displ_SD_Corr", "SD_Corr_ParabolicFit"}:
        raise ValueError("关闭 IRC 校正步后不能指定校正步参数")
    initial_fit = fields.get("SD_ParabolicFit", True)
    correction_fit = fields.get("Do_SD_Corr", True) and fields.get("SD_Corr_ParabolicFit", True)
    if "Interpolate_only" in fields and not (initial_fit or correction_fit):
        raise ValueError("Interpolate_only 需要在最速下降步或校正步中启用抛物线拟合")


def generated_options(spec, values):
    if spec.job_type != "IRC" or not uses_numerical_frequencies(spec):
        return values
    if values.get(("irc", "Direction")) == "down" or ("irc", "InitHess") in values:
        return values
    return {**values, ("irc", "InitHess"): "calc_numfreq"}

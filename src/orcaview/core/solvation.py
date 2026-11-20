"""ORCA 6.1.1 §§2.13 and 3.5. Model availability and named solvent input."""

from ._solvents import SOLVENT_ROWS
from ._advanced_methods import LIBXC_PURE, LIBXC_HYBRID
from ._dft_methods import DFT_METHOD_GROUPS
from .methods import DISPERSION_RECIPES, METHODS

MODELS = ("CPCM", "SMD", "ALPB", "DDCOSMO", "CPCMX")
_flags = {name: set(flags.split()) for name, flags in (row.split("|") for row in SOLVENT_ROWS)}
SOLVENTS = {model: tuple(name for name in ("water", *sorted(_flags.keys() - {"water"}))
                         if model in _flags[name]) for model in MODELS}
_SCF = {name for _, group in DFT_METHOD_GROUPS for name, profile in group
        if profile in ("standard", "numeric-freq")}
_SCF.update(f"LibXC({name})" for name in (LIBXC_PURE + " " + LIBXC_HYBRID).split())
_SCF.update(name for name, recipe in DISPERSION_RECIPES.items() if recipe.split()[0] in _SCF)
_CC = ("CCSD", "DLPNO-CCSD")


def solvation_options(method, job):
    if method in _SCF or method in ("CASSCF", "SA-CASSCF"):
        return ("Gas", "CPCM", "SMD")
    if method in ("TD-DFT", "TDA-DFT", "CIS", "TD-HF", *_CC, "MP2", "RI-MP2") and job == "SP":
        return ("Gas", "CPCM")
    if method.startswith("Native-") and "GFN" in method:
        return ("Gas", "ALPB", "CPCM", "SMD")
    if method in ("GFN1-xTB", "GFN2-xTB"):
        if method == "GFN2-xTB" and job == "SP":
            return ("Gas", "ALPB", "DDCOSMO", "CPCMX")
        return ("Gas", "ALPB", "DDCOSMO")
    if method == "GFN-FF":
        return ("Gas", "ALPB")
    return ("Gas",)


def validate_solvation(spec):
    if spec.solvation_model not in solvation_options(spec.method, spec.job_type):
        raise ValueError(f"{spec.method} / {spec.job_type} 不支持溶剂模型 {spec.solvation_model!r}")
    if spec.solvation_model == "DDCOSMO" and spec.solvent is None:
        from .block_options import BlockOverride
        if not isinstance(spec.block_options, tuple) or not any(
                isinstance(option, BlockOverride) and (option.block, option.key) == ("xtb", "EPSILON")
                for option in spec.block_options):
            raise ValueError("自定义 ddCOSMO 介质需要指定 %xtb EPSILON")
        return
    if spec.solvation_model == "Gas":
        if spec.solvent is not None:
            raise ValueError("气相计算不能指定溶剂")
    elif not isinstance(spec.solvent, str) or spec.solvent.lower() not in SOLVENTS[spec.solvation_model]:
        raise ValueError(f"{spec.solvation_model} 需要从该模型的溶剂列表选择溶剂，收到 {spec.solvent!r}")


def solvation_input(spec):
    validate_solvation(spec)
    model = spec.solvation_model
    if model == "Gas":
        return (), ()
    if model == "DDCOSMO" and spec.solvent is None:
        return (), ("%xtb", "  DODDCOSMO true", "end")
    solvent = spec.solvent.lower()
    if " " not in solvent and "(" not in solvent:
        return (f"{model}({solvent})",), ()
    # Keep multi-word names and embedded parentheses out of the ! tokenizer.
    if model == "CPCM":
        return ("CPCM",), ("%cpcm", f'  solvent "{solvent}"', "end")
    if model == "SMD":
        return ("CPCM",), ("%cpcm", "  smd true", f'  SMDsolvent "{solvent}"', "end")
    if model == "ALPB" and solvent == "octanol(wet)":
        return ("ALPB(woctanol)",), ()
    if model == "ALPB" and spec.method.startswith("Native-"):
        # Table 2.56 gives a single-token alias for every native ALPB solvent.
        alias = {"carbon disulfide": "cs2", "diethyl ether": "diethylether", "ethyl acetate": "ethylacetate"}[solvent]
        return (f"ALPB({alias})",), ()
    return (), ("%xtb", f"  DO{model} true", f'  {model}SOLVENT "{solvent}"', "end")


def uses_numerical_frequencies(spec):
    from .integrals import uses_numerical_scalar_frequencies
    return (METHODS[spec.method].uses_numerical_frequencies or uses_numerical_scalar_frequencies(spec)
            or spec.solvation_model == "SMD")


def solvation_block_options(spec):
    from ._block_catalog import BlockOption
    if spec.solvation_model == "DDCOSMO" and spec.solvent is None:
        return (BlockOption("xtb", "EPSILON", "介电常数", "float", minimum=1),)
    if spec.solvation_model not in ("CPCM", "SMD"):
        return ()
    if spec.solvation_model == "CPCM":
        options = [
            BlockOption("cpcm", "epsilon", "静态介电常数", "float", minimum=1),
            BlockOption("cpcm", "refrac", "折射率", "float", minimum=0, minimum_exclusive=True),
        ]
        if spec.method in _CC:
            options.append(BlockOption("cpcm", "CPCMccm", "耦合簇溶剂方案（0、1 或 2）", "int", 0, 2))
        return tuple(options)
    return (
        BlockOption("cpcm", "SMD18", "使用 SMD18 的溴、碘半径", "bool"),
        BlockOption("cpcm", "soln", "293 K 光学折射率", "float", minimum=0, minimum_exclusive=True),
        BlockOption("cpcm", "soln25", "298 K 光学折射率", "float", minimum=0, minimum_exclusive=True),
        BlockOption("cpcm", "sola", "氢键酸度", "float"),
        BlockOption("cpcm", "solb", "氢键碱度", "float"),
        BlockOption("cpcm", "solg", "相对宏观表面张力", "float"),
        BlockOption("cpcm", "solc", "芳香非氢原子比例", "float", 0, 1),
        BlockOption("cpcm", "solh", "F、Cl、Br 占非氢原子的比例", "float", 0, 1),
    )

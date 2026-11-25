"""ORCA 6.1.1 §§2.13 and 3.5. Model availability and named solvent input."""

from ._solvents import SOLVENT_ROWS
from ._advanced_methods import LIBXC_PURE, LIBXC_HYBRID
from ._block_catalog import uses_numerical_frequencies
from ._dft_methods import DFT_METHOD_GROUPS
from .methods import DISPERSION_RECIPES

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
        raise ValueError(f"{spec.method} / {spec.job_type} does not support solvent model {spec.solvation_model!r}")
    if spec.solvation_model == "DDCOSMO" and spec.solvent is None:
        from .block_options import BlockOverride
        if not isinstance(spec.block_options, tuple) or not any(
                isinstance(option, BlockOverride) and (option.block, option.key) == ("xtb", "EPSILON")
                for option in spec.block_options):
            raise ValueError("Custom ddCOSMO media require %xtb EPSILON")
        return
    if spec.solvation_model == "Gas":
        if spec.solvent is not None:
            raise ValueError("Gas-phase calculations cannot specify a solvent")
    elif not isinstance(spec.solvent, str) or spec.solvent.lower() not in SOLVENTS[spec.solvation_model]:
        raise ValueError(f"{spec.solvation_model} requires a solvent from its own list; received {spec.solvent!r}")


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


def solvation_block_options(spec):
    from ._block_catalog import BlockOption
    if spec.solvation_model == "DDCOSMO" and spec.solvent is None:
        return (BlockOption("xtb", "EPSILON", "Dielectric constant", "float", minimum=1),)
    if spec.solvation_model not in ("CPCM", "SMD"):
        return ()
    if spec.solvation_model == "CPCM":
        options = [
            BlockOption("cpcm", "epsilon", "Static dielectric constant", "float", minimum=1),
            BlockOption("cpcm", "refrac", "Refractive index", "float", minimum=0, minimum_exclusive=True),
        ]
        if spec.method in _CC:
            options.append(BlockOption("cpcm", "CPCMccm", "Coupled-cluster solvation scheme (0, 1 or 2)", "int", 0, 2))
        return tuple(options)
    return (
        BlockOption("cpcm", "SMD18", "Use SMD18 radii for bromine and iodine", "bool"),
        BlockOption("cpcm", "soln", "Optical refractive index at 293 K", "float", minimum=0, minimum_exclusive=True),
        BlockOption("cpcm", "soln25", "Optical refractive index at 298 K", "float", minimum=0, minimum_exclusive=True),
        BlockOption("cpcm", "sola", "Hydrogen bond acidity", "float"),
        BlockOption("cpcm", "solb", "Hydrogen bond basicity", "float"),
        BlockOption("cpcm", "solg", "Relative macroscopic surface tension", "float"),
        BlockOption("cpcm", "solc", "Fraction of aromatic nonhydrogen atoms", "float", 0, 1),
        BlockOption("cpcm", "solh", "Fraction of F, Cl and Br among nonhydrogen atoms", "float", 0, 1),
    )

"""ORCA 6.1.1 method presets shared by project validation, the GUI and input writers."""

from dataclasses import dataclass
from typing import Tuple

from ._advanced_methods import ADVANCED_ALIASES, ADVANCED_GROUPS, check_extrapolation_basis, dispersion_options
from ._dft_methods import DFT_METHOD_ALIASES, DFT_METHOD_GROUPS, DLPNO_DFT_GROUP, DLPNO_DOUBLE_HYBRIDS, EXTRA_DFT_GROUPS
from ._state_catalog import DOUBLE_HYBRID_RESPONSE
from ._state_methods import (ACTIVE_SPACE_METHODS, ELECTRON_CHANNEL_METHODS, EXCITED_STATE_METHODS,
                            REFERENCE_FUNCTIONAL_METHODS, RESPONSE_FUNCTIONALS,
                            STATE_METHOD_ALIASES, STATE_METHOD_GROUPS)
from ._wavefunction_methods import (
    CANONICAL_MDCI, EXTRA_NDO_GROUPS, METHOD_ELEMENTS, METHOD_MAX_Z, OTHER_METHOD_GROUPS, RI_CANONICAL_CC,
)
from .elements import ATOMIC_NUMBERS


ORDINARY_JOBS = ("SP", "OPT", "FREQ", "OPT_FREQ")
PATH_JOBS = ("OPT_TS", "IRC")
ALL_JOBS = ORDINARY_JOBS + PATH_JOBS


@dataclass(frozen=True)
class MethodPreset:
    name: str
    family: str
    basis_mode: str
    job_types: Tuple[str, ...]
    uses_numerical_frequencies: bool

    @property
    def uses_orbital_basis(self) -> bool:
        return self.basis_mode in ("orbital", "correlation")

    @property
    def allows_initial_gbw(self) -> bool:
        return self.basis_mode != "semiempirical"

    def validate_system(self, molecule) -> None:
        check_extrapolation_basis(self.name, molecule)
        if self.name in RI_CANONICAL_CC and molecule.multiplicity != 1:
            raise ValueError(f"{self.name} 的 MDCI RI 积分算法要求闭壳层单重参考态")
        upper_bound = METHOD_MAX_Z.get(self.name)
        elements = METHOD_ELEMENTS.get(self.name)
        for symbol in dict.fromkeys(atom.element for atom in molecule.atoms):
            if ((upper_bound is not None and ATOMIC_NUMBERS[symbol] > upper_bound)
                    or (elements is not None and symbol not in elements)):
                raise ValueError(f"{self.name} 的当前基组或参数不覆盖元素 {symbol}")

    def keywords(self, basis_keywords, job: str, method_keywords: str, *, numerical_frequency=False) -> str:
        words = [method_keywords] if method_keywords else []
        words.extend(basis_keywords)
        if job == "SP":
            words.append("SP")
        if job == "OPT_TS":
            words.append("OptTS")
        if job == "IRC":
            words.append("IRC")
        if job in ("OPT", "OPT_FREQ"):
            words.append("Opt")
        if job in ("FREQ", "OPT_FREQ"):
            words.append("NumFreq" if self.uses_numerical_frequencies or numerical_frequency else "Freq")
        return " ".join(words)


# basis assignment, supported jobs and frequency differentiation
_PROFILES = {
    "standard": ("orbital", ALL_JOBS, False),
    "numeric-freq": ("orbital", ORDINARY_JOBS, True),
    "double-hybrid": ("correlation", ORDINARY_JOBS, True),
    "mp2-aux": ("correlation", ORDINARY_JOBS, True),
    "sp": ("orbital", ("SP",), False),
    "sp-aux": ("correlation", ("SP",), False),
    "fixed": ("fixed", ORDINARY_JOBS, True),
    "fixed-sp": ("fixed", ("SP",), False),
    "semiempirical": ("semiempirical", ORDINARY_JOBS, True),
    "semiempirical-sp": ("semiempirical", ("SP",), False),
}

METHODS = {}
METHOD_GROUPS = {}
# These labels expand to two ORCA keywords. Functionals with built-in dispersion
# (e.g. WB97X-D3BJ) retain the single keyword in the DFT tables.
DISPERSION_RECIPES = {
    "B3LYP-D3(BJ)": "B3LYP D3BJ", "PBE0-D3(BJ)": "PBE0 D3BJ",
    "PBE-D3(BJ)": "PBE D3BJ", "TPSS-D3(BJ)": "TPSS D3BJ",
    "B3LYP-D4": "B3LYP D4", "PBE0-D4": "PBE0 D4", "PBE-D4": "PBE D4",
    "r2SCAN-D4": "R2SCAN D4", "B2PLYP-D4": "B2PLYP D4",
}
_DISPERSION_GROUP = (("DFT 色散校正组合", tuple(
    (name, "double-hybrid" if name == "B2PLYP-D4" else "numeric-freq")
    for name in DISPERSION_RECIPES
)),)
_ALL_GROUPS = (DFT_METHOD_GROUPS + EXTRA_DFT_GROUPS + DLPNO_DFT_GROUP + _DISPERSION_GROUP
               + OTHER_METHOD_GROUPS + EXTRA_NDO_GROUPS + STATE_METHOD_GROUPS + ADVANCED_GROUPS)
for family, entries in _ALL_GROUPS:
    METHOD_GROUPS[family] = tuple(name for name, _ in entries)
    for name, profile in entries:
        METHODS[name] = MethodPreset(name, family, *_PROFILES[profile])

# Schema 1–3 readers know this subset of the catalog and the original three bases.
EARLIER_METHODS = frozenset(name for _, entries in DFT_METHOD_GROUPS + _DISPERSION_GROUP + OTHER_METHOD_GROUPS
                            for name, _ in entries) | {"CIS", "TD-DFT", "TDA-DFT", "CASSCF", "SC-NEVPT2"}

_CLI_NAMES = {name.casefold(): name for name in METHODS}
for aliases in (DFT_METHOD_ALIASES, STATE_METHOD_ALIASES, ADVANCED_ALIASES):
    _CLI_NAMES.update({alias.casefold(): keyword for alias, keyword in aliases.items()})
_CLI_NAMES["tddft"] = "TD-DFT"


def pno_options(name):
    if name in DLPNO_DOUBLE_HYBRIDS or ("DLPNO" in name and any(tag in name for tag in ("MP2", "CCSD"))):
        return ("Auto", "LoosePNO", "NormalPNO", "TightPNO")
    return ("Auto",)


def reference_options(name, job=None):
    choices = _reference_methods(name)
    if job not in (None, "SP"):
        return tuple(choice for choice in choices if choice not in ("ROHF", "ROKS"))
    return choices


def _reference_methods(name):
    if name in DOUBLE_HYBRID_RESPONSE:
        return ("Auto", "RKS")
    if name == "HF":
        return ("Auto", "RHF", "UHF", "ROHF")
    if name in ("F12-DLPNO-MP2", "F12/D-DLPNO-MP2"):
        return ("Auto", "RHF")
    if name in RI_CANONICAL_CC:
        return ("Auto", "RHF")
    if "F12" in name or name in CANONICAL_MDCI or name in ("MP2", "RI-MP2"):
        return ("Auto", "RHF", "UHF")
    family = METHODS[name].family
    if name in DISPERSION_RECIPES:
        family = METHODS[DISPERSION_RECIPES[name].split()[0]].family
    if "双杂化" in family:
        return ("Auto", "RKS", "UKS")
    if family.startswith(("局域密度", "广义梯度", "动能密度", "LibXC")) or "杂化" in family:
        return ("Auto", "RKS", "UKS", "ROKS")
    return ("Auto",)


def frozen_core_options(name):
    family = METHODS[name].family
    if (family in ("微扰理论", "耦合簇", "组态相互作用与电子对方法", "显式相关 F12", "自动生成单参考关联 AUTOCI")
            or "双杂化" in family or name == "B2PLYP-D4"):
        return ("Auto", "FrozenCore", "NoFrozenCore")
    return ("Auto",)


def canonical_method(name: str) -> str:
    try:
        return _CLI_NAMES[name.casefold()]
    except KeyError:
        raise ValueError(f"未收录计算方法 {name!r}，使用 orcaview methods 查看可选项") from None

"""Orbital and fitting basis slots for the molecular ORCA 6.1.1 input writer.

Sections 2.7 and 2.8 specify basis coverage, fitting slots and SCF RI methods.
https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/basisset.html
https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/RI.html
"""

from ._basis_library import (
    BASIS_HAMILTONIANS, BASIS_POTENTIALS, FITTING_COVERAGE, ORBITAL_COVERAGE, atomic_numbers,
)
from ._state_catalog import CASDFT_METHODS, DOUBLE_HYBRID_RESPONSE
from .block_options import BlockOverride
from .elements import ATOMIC_NUMBERS
from .relativistic import SCALAR_BASES


_DEF2 = ("def2-SVP", "def2-TZVP", "def2-TZVPP", "def2-SV(P)", "def2-TZVP(-f)",
         "def2-QZVP", "def2-QZVPP", "def2-SVPD", "def2-TZVPD", "def2-TZVPPD",
         "def2-QZVPD", "def2-QZVPPD")
_MA_DEF2 = tuple("ma-def2-" + quality for quality in
                 ("SVP", "SV(P)", "mSVP", "TZVP", "TZVP(-f)", "TZVPP", "QZVPP"))
_F12_VALENCE = tuple(f"cc-pV{q}Z-F12" for q in "DTQ")
_F12_CORE = tuple(f"cc-pCV{q}Z-F12" for q in "DTQ")
_F12_PP = tuple(f"cc-pV{q}Z-PP-F12" for q in "DTQ")
_F12 = _F12_VALENCE + _F12_CORE + _F12_PP
# The OptRI sets for groups 11/12 were optimized with ordinary augmented PP
# orbital sets (Grant Hill ccRepo 2016-09-23; ORCA Table 2.37).
_F12_AUGMENTED_PP = tuple(b for b in ORBITAL_COVERAGE if b.startswith("aug-") and b + "-OptRI" in FITTING_COVERAGE)

# Keep existing defaults first even though the manual starts with Pople bases.
# DKH3 and two-component entries are library definitions without a matching
# molecular Hamiltonian in this release (manual §§2.7.2.4, 2.7.3.5, 2.12).
_UNMATCHED_BASES = (BASIS_HAMILTONIANS.keys() - SCALAR_BASES.keys()) | {
    name for name, potential in BASIS_POTENTIALS.items() if potential == "dhf-ECP-2c"
}
BASES = _DEF2 + tuple(name for name in ORBITAL_COVERAGE if name not in _DEF2 and name not in _UNMATCHED_BASES)
_ORDINARY_BASES = tuple(name for name in BASES if name not in _F12 and name not in SCALAR_BASES)

# Table 2.36 lists neither def2-QZVP/C nor a separate fit for def2-SV(P).
_DEF2_C = {
    "def2-SVP": "def2-SVP/C", "def2-SV(P)": "def2-SVP/C",
    "def2-TZVP": "def2-TZVP/C", "def2-TZVP(-f)": "def2-TZVP/C",
    "def2-TZVPP": "def2-TZVPP/C", "def2-QZVP": "def2-QZVPP/C", "def2-QZVPP": "def2-QZVPP/C",
    "def2-SVPD": "def2-SVPD/C", "def2-TZVPD": "def2-TZVPD/C", "def2-TZVPPD": "def2-TZVPPD/C",
    "def2-QZVPD": "def2-QZVPPD/C", "def2-QZVPPD": "def2-QZVPPD/C",
}
_CORRELATION_FITS = {
    **_DEF2_C,
    **{s: s + "/C" for s in _ORDINARY_BASES if s + "/C" in FITTING_COVERAGE},
    **{s: s + "-MP2Fit" for s in _F12},
}
# A larger fit in the same family can be selected explicitly.
_CORRELATION_SERIES = (
    ("def2-SVP/C", "def2-TZVP/C", "def2-TZVPP/C", "def2-QZVPP/C"),
    ("def2-SVPD/C", "def2-TZVPD/C", "def2-TZVPPD/C", "def2-QZVPPD/C"),
    ("cc-pVDZ/C", "cc-pVTZ/C", "cc-pVQZ/C", "cc-pV5Z/C", "cc-pV6Z/C"),
    ("aug-cc-pVDZ/C", "aug-cc-pVTZ/C", "aug-cc-pVQZ/C", "aug-cc-pV5Z/C", "aug-cc-pV6Z/C"),
)


def _preset(method):
    # The method registry also serves the model layer that imports BASES.
    from .methods import METHODS
    if not isinstance(method, str) or method not in METHODS:
        raise ValueError(f"未收录计算方法 {method!r}")
    return METHODS[method]


def basis_options(method_name):
    if not _preset(method_name).uses_orbital_basis:
        return ()
    if "F12" in method_name:
        return _F12 + _F12_AUGMENTED_PP
    if _scf_kind(method_name) in ("hf", "pure", "hybrid", "double-hybrid", "casscf", "correlated-hf") or (
            method_name in ("MP2", "SCS-MP2", "CCSD", "CCSD(T)")):
        return _ORDINARY_BASES + tuple(SCALAR_BASES)
    return _ORDINARY_BASES


def scalar_options(method_name, basis):
    if basis not in SCALAR_BASES or basis not in basis_options(method_name):
        return ("Auto",)
    model, _ = SCALAR_BASES[basis]
    return ("Auto", "X2C", "DLU-X2C") if model == "X2C" else ("Auto", model)


def uses_numerical_scalar_frequencies(spec):
    return (_preset(spec.method).uses_orbital_basis and spec.basis in SCALAR_BASES
            and SCALAR_BASES[spec.basis][0] in ("DKH2", "ZORA"))


def _scf_kind(method):
    from .methods import DISPERSION_RECIPES
    base = DISPERSION_RECIPES[method].split()[0] if method in DISPERSION_RECIPES else method
    family = _preset(base).family
    if method == "HF":
        return "hf"
    if method in DOUBLE_HYBRID_RESPONSE:
        return "double-hybrid-response"
    if method in CASDFT_METHODS:
        return "casdft"
    if method in ("TD-DFT", "TDA-DFT"):
        return "response"
    if method in ("CASSCF", "SC-NEVPT2"):
        return "casscf"
    if "双杂化" in family:
        return "double-hybrid"
    if "杂化" in family:
        return "hybrid"
    if family.startswith(("局域密度", "广义梯度", "动能密度", "LibXC")):
        return "pure"
    if method == "RPAC(PBE)" or method.startswith("ADFT("):
        return "density-fit"
    if method in ("RI-MP2", "RI-SCS-MP2", "RI-SOS-MP2", "DLPNO-MP2", "DLPNO-SCS-MP2",
                  "DLPNO-SOS-MP2", "DLPNO-CCSD", "DLPNO-CCSD(T)", "DLPNO-CCSD(T1)"):
        return "correlated-hf"
    return "other"


def integral_options(method_name, job=None):
    kind = _scf_kind(method_name)
    if kind in ("hf", "hybrid"):
        options = ("Auto", "NoRI", "RIJONX", "RIJCOSX", "RI-JK")
    elif kind == "pure":
        options = ("Auto", "NoRI", "RI", "Split-RI-J", "NoSplit-RI-J")
    elif method_name == "RI-MP2":
        options = ("Auto", "RIJONX", "RIJCOSX", "RI-JK")
    elif kind == "casdft":
        options = ("Auto", "RIJCOSX")
    elif kind in ("correlated-hf", "double-hybrid", "casscf"):
        options = ("Auto", "RIJCOSX", "RI-JK")
    elif kind == "response":
        options = ("Auto", "NoRI")
    elif "CCSD" in method_name and "F12" in method_name and "/RI" in method_name:
        options = ("Auto", "RI-JK")
    else:
        options = ("Auto",)
    # ORCA 6.1.1 section 2.8.5 provides only energies for RI-JK.
    return tuple(s for s in options if s != "RI-JK" or job in (None, "SP"))


def grid_options(method, approximation="Auto"):
    if approximation not in integral_options(method):
        raise ValueError(f"{method} 不支持积分设置 {approximation!r}")
    kind = _scf_kind(method)
    if (kind in ("pure", "hybrid", "double-hybrid", "double-hybrid-response", "casdft", "response") or method == "RPAC(PBE)"
            or approximation == "RIJCOSX"):
        return ("Auto", "DEFGRID1", "DEFGRID2", "DEFGRID3")
    return ("Auto",)


def _needs_c(method, approximation):
    if "F12" in method:
        return any(tag in method for tag in ("DLPNO", "/RI", "RI-"))
    if (method in ("CASSCF", "SC-NEVPT2") or method in CASDFT_METHODS) and approximation == "RIJCOSX":
        return True
    return method in DOUBLE_HYBRID_RESPONSE or _preset(method).basis_mode == "correlation"


def _correlation_options(basis):
    if basis in _F12_VALENCE:
        # Section 3.10.7 also recommends an ordinary fit one zeta level up.
        larger = {"cc-pVDZ-F12": "cc-pVTZ/C", "cc-pVTZ-F12": "cc-pVQZ/C", "cc-pVQZ-F12": "cc-pV5Z/C"}
        return (basis + "-MP2Fit", larger[basis], "AutoAux")
    if basis in _F12:
        return (basis + "-MP2Fit", "AutoAux")
    if basis.endswith("-DK"):
        fit = basis[:-3] + "/C"
        return ("AutoAux", fit) if fit in FITTING_COVERAGE else ("AutoAux",)
    matched = _CORRELATION_FITS.get(basis)
    if matched is None:
        return ("AutoAux",)
    for series in _CORRELATION_SERIES:
        if matched in series:
            return (*series[series.index(matched):], "AutoAux")
    return (matched, "AutoAux")


def _jk_fits(basis):
    if basis in _DEF2 or basis in _MA_DEF2:
        return ("def2/JK", "def2/JKsmall")
    if basis + "/JK" in FITTING_COVERAGE:
        return (basis + "/JK",)
    return ()


def auxiliary_options(method_name, basis, approximation, block_options=()):
    """Return active slots and their explicit choices, with the default choice first."""
    if approximation not in integral_options(method_name):
        raise ValueError(f"{method_name} 不支持积分设置 {approximation!r}")
    orbitals = basis_options(method_name)
    if not isinstance(basis, str) or basis not in (orbitals or BASES):
        raise ValueError(f"{method_name} 不支持轨道基组 {basis!r}")
    if not orbitals:
        return {}
    kind = _scf_kind(method_name)
    scf_fits_j = approximation in ("RI", "Split-RI-J", "NoSplit-RI-J", "RIJONX", "RIJCOSX") or (
        approximation == "Auto" and kind in ("pure", "hybrid", "double-hybrid", "response", "double-hybrid-response", "density-fit"))
    slots = {}
    if scf_fits_j:
        if basis in SCALAR_BASES:
            fit = "x2c/J" if SCALAR_BASES[basis][0] == "X2C" else "SARC/J"
            slots["aux_j"] = (fit, "AutoAux")
        elif basis in ("def2-mTZVP", "def2-mTZVPP"):
            slots["aux_j"] = (basis + "/J", "def2/J", "AutoAux")
        else:
            slots["aux_j"] = ("def2/J", "AutoAux") if basis in _DEF2 or basis in _MA_DEF2 else ("AutoAux", "def2/J")
        # Sec. 2.7.4.2 explicitly permits a JK fit in the J slot via %basis.
        slots["aux_j"] += _jk_fits(basis)
    if approximation == "RI-JK":
        slots["aux_jk"] = (*_jk_fits(basis), "AutoAux")
    if _needs_c(method_name, approximation) or _mdci_uses_correlation_fit(block_options):
        slots["aux_c"] = _correlation_options(basis)
    if "F12" in method_name:
        slots["cabs"] = (basis + "-OptRI", basis + "-CABS") if basis in _F12_VALENCE else (basis + "-OptRI",)
    return slots


def _mdci_uses_correlation_fit(overrides):
    # Typed overrides are validated by the block catalog; ignore malformed
    # records here so the validator can report them at their own field.
    return isinstance(overrides, tuple) and any(
        isinstance(item, BlockOverride) and item.block == "mdci" and (
            (item.key == "KCOpt" and item.value in ("KC_RI", "KC_RI2"))
            or (item.key == "TrafoType" and item.value == "trafo_ri")
        ) for item in overrides
    )


def _check_elements(molecule, name, supported):
    for atom in molecule.atoms:
        if ATOMIC_NUMBERS[atom.element] not in supported:
            raise ValueError(f"基组 {name} 不覆盖元素 {atom.element}")


def _core_sizes(*groups):
    return {z: n for n, elements in groups for z in atomic_numbers(elements)}


# Table 2.38. Explicit zeroes distinguish all-electron atoms from missing
# core-size entries. Do not silently count missing ECP data as all-electron.
_DEF2_CORES = _core_sizes((0, "H-Kr"), (28, "Rb-Xe Ce-Lu"), (46, "Cs-La"), (60, "Hf-Rn"))
_DEF_HEAVY = _core_sizes((78, "Fr-Ra"), (60, "Ac-Lr"))
_ECP_CORES = {
    "def2-ECP": _DEF2_CORES,
    "def-ECP": {**dict.fromkeys(atomic_numbers("H-Kr"), 0), **_DEF_HEAVY},
    "def2-ECP+def-ECP": {**_DEF2_CORES, **_DEF_HEAVY},
    "dhf-ECP": _core_sizes((0, "H-Kr"), (28, "Rb-Xe"), (46, "Cs-Ba"), (60, "Hf-Rn U")),
    "SK-MCDHF-RSC": _core_sizes((10, "Ca Cu-Kr"), (28, "Sr-Xe"), (46, "Ba"), (60, "Hf-Rn U"), (78, "Ra")),
    "HayWadt": _core_sizes((0, "H-Ne"), (10, "Na-Cu"), (18, "Zn"), (28, "Ga-Ag"), (36, "Cd"),
                           (46, "In-La"), (60, "Hf-Au"), (68, "Hg-Tl"), (78, "Pb-Bi U-Pu")),
    "vDZP-ECP": _core_sizes((0, "H-Be"), (2, "B-Mg"), (10, "Al-Zn"), (28, "Ga-Cd"), (46, "In-Lu"),
                            (60, "Hf-Hg"), (78, "Tl-Rn")),
    # Ga–Kr are missing from Table 2.38. BSE CRENBL-ECP revision 0 supplies 18.
    "CRENBL-ECP": _core_sizes((0, "H"), (2, "Li-Mg"), (10, "Al-Zn"), (18, "Ga-Kr"), (28, "Rb-Cd"),
                              (36, "In-Xe"), (46, "Cs-La"), (54, "Ce-Lu"), (60, "Hf-Hg"),
                              (68, "Tl-Rn"), (78, "Fr-Ts"), (92, "Og")),
}


def effective_electron_count(basis, molecule):
    if not isinstance(basis, str) or basis not in BASES:
        raise ValueError(f"未知轨道基组 {basis!r}")
    _check_elements(molecule, basis, ORBITAL_COVERAGE[basis])
    potential = BASIS_POTENTIALS.get(basis)
    if potential is None:
        return molecule.electron_count
    cores = _ECP_CORES[potential]
    for atom in molecule.atoms:
        if ATOMIC_NUMBERS[atom.element] not in cores:
            raise ValueError(f"{basis} 的 {potential} 对 {atom.element} 的芯电子数未经核实")
    return molecule.electron_count - sum(cores[ATOMIC_NUMBERS[atom.element]] for atom in molecule.atoms)


def validate_basis_system(basis, molecule):
    if effective_electron_count(basis, molecule) < molecule.multiplicity - 1:
        raise ValueError("轨道基组和有效核势保留的显式电子数不足以构成所选多重度")


_SLOT_KEYWORDS = {"aux_j": "AuxJ", "aux_jk": "AuxJK", "aux_c": "AuxC", "cabs": "CABS"}


def orbital_and_aux_input(spec, molecule=None):
    """Return the simple input keywords and the companion %basis block."""
    method, basis, approximation = spec.method, spec.basis, spec.integral_approximation
    if approximation not in integral_options(method, spec.job_type):
        raise ValueError(f"{method} 的 {spec.job_type} 任务不支持 {approximation!r} 积分设置")
    options = auxiliary_options(method, basis, approximation, spec.block_options)
    words = [basis] if _preset(method).uses_orbital_basis else []
    if words and molecule is not None:
        validate_basis_system(basis, molecule)
        if molecule.multiplicity != 1 and spec.block_options:
            from ._solver_block_catalog import MDCI_RHF_ONLY_KC
            if any(isinstance(item, BlockOverride) and item.block == "mdci" and item.key == "KCOpt"
                   and item.value in MDCI_RHF_ONLY_KC for item in spec.block_options):
                raise ValueError("所选 MDCI 积分算法需要闭壳层 RHF 参考波函数")
    if spec.relativity not in scalar_options(method, basis):
        raise ValueError(f"{method} / {basis} 不支持相对论设置 {spec.relativity!r}")
    if words and basis in SCALAR_BASES:
        model = SCALAR_BASES[basis][0] if spec.relativity == "Auto" else spec.relativity
        words.append(model)
    if approximation in ("Split-RI-J", "NoSplit-RI-J"):
        words.extend(("RI", approximation))
    elif approximation != "Auto":
        words.append(approximation)
    if spec.integration_grid not in grid_options(method, approximation):
        raise ValueError(f"{method} / {approximation} 不支持积分网格 {spec.integration_grid!r}")
    if spec.integration_grid != "Auto":
        words.append(spec.integration_grid)
    assignments = []
    for slot, keyword in _SLOT_KEYWORDS.items():
        chosen = getattr(spec, slot)
        choices = options.get(slot, ())
        if chosen is not None and chosen not in choices:
            raise ValueError(f"{method} / {basis} / {approximation} 不支持 {keyword}={chosen!r}")
        if not choices:
            continue
        fit = choices[0] if chosen is None else chosen
        # ORCA supplies def2/J by default for SCF fitting. Keep original Auto input bytes.
        if chosen is None and approximation == "Auto" and slot == "aux_j" and basis in _DEF2:
            if _scf_kind(method) != "density-fit":
                continue
        if molecule is not None and fit != "AutoAux":
            coverage = FITTING_COVERAGE[fit]
            if fit == "def2/J" and BASIS_POTENTIALS.get(basis) not in ("def2-ECP", "def2-ECP+def-ECP"):
                coverage = coverage & atomic_numbers("H-Kr")  # def2/J assumes an appropriate ECP beyond Kr.
            _check_elements(molecule, fit, coverage)
        if fit == "AutoAux" or (slot == "aux_j" and "/JK" in fit):
            # Simple-input AutoAux assigns three slots, and a /JK keyword always assigns AuxJK.
            assignments.append(f'  {keyword} "{fit}"')
        else:
            words.append(fit)
    block = ("%basis", *assignments, "end") if assignments else ()
    return tuple(words), block


def orbital_and_aux_keywords(spec, molecule=None):
    return orbital_and_aux_input(spec, molecule)[0]


def auxiliary_basis_block(spec):
    return orbital_and_aux_input(spec)[1]

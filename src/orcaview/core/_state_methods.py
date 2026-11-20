"""ORCA 6.1.1 state inputs, from chapters 3.11, 3.13–3.20 and 5.4–5.13."""

from ._dft_methods import DFT_METHOD_GROUPS
from ._state_catalog import (
    ACTIVE_SPACE_METHODS, CLOSED_SHELL_METHODS, ELECTRON_CHANNEL_METHODS, EXCITED_STATE_METHODS,
    MDCI_METHODS, MREOM_METHODS, REFERENCE_FUNCTIONAL_METHODS, RESPONSE_METHODS, ROCIS_METHODS,
    CASDFT_METHODS, DOUBLE_HYBRID_RESPONSE, MCRPA_METHODS, MULTIROOT_CAS_METHODS, SPIN_FLIP_METHODS,
    STATE_METHOD_ALIASES, STATE_METHOD_GROUPS,
)
from ._validation import integer
from .integrals import effective_electron_count


EARLIER_RESPONSE_FUNCTIONALS = ("B3LYP", "PBE0", "CAM-B3LYP", "PBE", "BP86")
# §5.6.4 supports pure and hybrid DFT. Restrict this selector to native
# LDA/GGA kernels and global or long-range hybrid GGAs. Double hybrids
# use their dedicated RI doubles-correction presets.
_NATIVE_RESPONSE_GGAS = tuple(name for family, entries in DFT_METHOD_GROUPS
                              if family.startswith(("局域密度", "广义梯度", "全局杂化 GGA"))
                              for name, _ in entries)
RESPONSE_FUNCTIONALS = tuple(dict.fromkeys((
    *EARLIER_RESPONSE_FUNCTIONALS, *_NATIVE_RESPONSE_GGAS, "LC-BLYP", "LC-PBE", "WB97", "WB97X",
)))


def _positive_input_integer(value, label):
    integer(value, label, 1)
    if value > 2**31 - 1:
        raise ValueError(f"{label} 超出 32 位整数范围")


def _validate_active_space(active_electrons, active_orbitals):
    _positive_input_integer(active_electrons, "活性电子数")
    _positive_input_integer(active_orbitals, "活性轨道数")
    if active_electrons > 2 * active_orbitals:
        raise ValueError("活性电子数不能超过活性轨道数的两倍")


def _validate_active_spin(active_electrons, active_orbitals, multiplicity):
    integer(multiplicity, "自旋多重度", 1)
    unpaired = multiplicity - 1
    holes = 2 * active_orbitals - active_electrons
    if unpaired > min(active_electrons, holes) or (active_electrons - unpaired) % 2:
        raise ValueError("活性空间的电子数和空穴数与所选自旋多重度不相容")


def validate_parameters(method, active_electrons, active_orbitals, nroots, reference_functional,
                        electron_channel=None):
    """Check method-specific fields, including unused fields in saved projects."""
    if method in ACTIVE_SPACE_METHODS:
        _validate_active_space(active_electrons, active_orbitals)
    elif active_electrons is not None or active_orbitals is not None:
        raise ValueError(f"{method} 不使用活性电子数或活性轨道数")

    if method in EXCITED_STATE_METHODS:
        _positive_input_integer(nroots, "目标根数")
    elif nroots is not None:
        raise ValueError("激发态数仅适用于垂直激发能计算；活性空间模板固定为单根")

    if method in REFERENCE_FUNCTIONAL_METHODS:
        if reference_functional not in RESPONSE_FUNCTIONALS:
            raise ValueError(f"{method} 需要指定参考泛函，可选 " + "、".join(RESPONSE_FUNCTIONALS))
    elif reference_functional is not None:
        raise ValueError(f"{method} 不使用可选参考泛函")
    if electron_channel is not None:
        if method not in ELECTRON_CHANNEL_METHODS:
            raise ValueError(f"{method} 不使用电离或附着自旋通道")
        if electron_channel not in ("alpha", "beta"):
            raise ValueError("电子自旋通道必须为 alpha 或 beta")


def _validate_reference(method, multiplicity, electron_channel):
    if method in CLOSED_SHELL_METHODS and multiplicity != 1:
        raise ValueError(f"{method} 模板需要闭壳层单重参考态")
    if method in SPIN_FLIP_METHODS and multiplicity < 3:
        raise ValueError(f"{method} 的自旋翻转参考态多重度至少为 3")
    if method in ROCIS_METHODS and multiplicity < 2:
        raise ValueError(f"{method} 模板需要高自旋开壳层参考态")
    if method in ELECTRON_CHANNEL_METHODS:
        if multiplicity > 1 and electron_channel not in ("alpha", "beta"):
            raise ValueError(f"{method} 开壳层参考态须指定 alpha 或 beta 自旋通道")
        if multiplicity == 1 and electron_channel is not None:
            raise ValueError(f"{method} 的闭壳层模板不使用自旋通道")


def validate_state_system(method, molecule, active_electrons, active_orbitals,
                          electron_channel=None, basis="def2-SVP"):
    """Check the electrons retained by the selected orbital basis and ECP."""
    if method not in ACTIVE_SPACE_METHODS and method not in EXCITED_STATE_METHODS:
        return
    electrons = molecule.electron_count if method == "ZINDO/S-CIS" else effective_electron_count(basis, molecule)
    if electrons < 1 or electrons < molecule.multiplicity - 1:
        raise ValueError("显式电子数不足以构成所选电子态，请检查电荷、多重度和 ECP")
    _validate_reference(method, molecule.multiplicity, electron_channel)
    if (method in ELECTRON_CHANNEL_METHODS and "IP-" in method and electron_channel == "beta"
            and electrons == molecule.multiplicity - 1):
        raise ValueError("参考态中没有可移除的 beta 电子")
    if method in ACTIVE_SPACE_METHODS:
        _validate_active_space(active_electrons, active_orbitals)
        inactive = electrons - active_electrons
        if inactive < 0 or inactive % 2:
            raise ValueError("活性电子数必须使剩余显式电子能成对占据非活性轨道")
        _validate_active_spin(active_electrons, active_orbitals, molecule.multiplicity)


def _active_space_input(method, electrons, orbitals, multiplicity, nroots):
    _validate_active_spin(electrons, orbitals, multiplicity)
    if method in MULTIROOT_CAS_METHODS:
        _validate_cas_roots(electrons, orbitals, multiplicity, nroots)
    reference_roots = nroots if method in MULTIROOT_CAS_METHODS else 1
    lines = ["%casscf", f"  nel {electrons}", f"  norb {orbitals}", f"  mult {multiplicity}",
             f"  nroots {reference_roots}"]
    if method in MCRPA_METHODS:
        tda = "true" if method == "MCTDA" else "false"
        return "", (*lines, "end", "%mcrpa", f"  NRoots {nroots}", f"  TDA {tda}", "end")
    if method in CASDFT_METHODS:
        return "TRAH " + method, (*lines, "end")
    # An active-space solver is requested in the block. Post-CAS methods
    # normally add a simple keyword to the same CASSCF reference.
    block_methods = {
        "CASSCF": (), "CASCI": ("maxiter 1",), "ICE-CASSCF": ("cistep ICE",),
        "ICE-CASCI": ("cistep ICE", "maxiter 1"), "DMRG-CASSCF": ("cistep DMRGCI",),
        "DMRG-CASCI": ("cistep DMRGCI", "maxiter 1"), "SA-CASSCF": (),
        "SA-SC-NEVPT2": ("PTMethod SC_NEVPT2",),
        "QD-SC-NEVPT2": ("PTMethod SC_NEVPT2", "PTSettings", "  QDType QD_VanVleck", "end"),
        "FIC-NEVPT2": ("PTMethod FIC_NEVPT2",),
    }
    keyword = method
    if method in block_methods:
        keyword = ""
        lines.extend("  " + line for line in block_methods[method])
    return keyword, (*lines, "end")


def _response_input(method, nroots, reference_functional):
    if method == "ZINDO/S-CIS":
        return "ZINDO/S", ("%tddft", f"  nroots {nroots}", "  tda true", "end")
    if method in DOUBLE_HYBRID_RESPONSE:
        tda = "true" if method.startswith("TDA-") else "false"
        return DOUBLE_HYBRID_RESPONSE[method], ("%tddft", f"  nroots {nroots}",
                                                f"  tda {tda}", "  dcorr 1", "end")
    keyword = reference_functional if method in REFERENCE_FUNCTIONAL_METHODS else "HF"
    tda = "false" if method in ("TD-DFT", "TD-HF") else "true"
    lines = ["%tddft", f"  nroots {nroots}", f"  tda {tda}"]
    if method in SPIN_FLIP_METHODS:
        lines.append("  sf true")
        if method == "SF-TDA-BHANDHLYP":
            keyword = "BHANDHLYP"
    if method in ("CIS(D)", "SCS-CIS(D)"):
        lines.append("  dcorr 1")
        if method == "SCS-CIS(D)":
            lines.extend(("  doscs true", "  scspar 0.333, 1.2, 0.43, 1.24"))
    return keyword, (*lines, "end")


def _mdci_input(method, nroots, electron_channel):
    lines = ["%mdci", f"  nroots {nroots}"]
    if method in ("EOM-CCSD(2)", "STEOM-CCSD(2)"):
        method = method.removesuffix("(2)")
        lines.append("  CCSD2 true")
    if electron_channel is not None:
        lines.append("  DoAlpha true" if electron_channel == "alpha" else "  DoBeta true")
    return method, (*lines, "end")


def _binomial_up_to(n, k, cap):
    """A bounded binomial avoids huge integers for unnecessarily large CAS inputs."""
    result = 1
    for i in range(1, min(k, n - k) + 1):
        result = result * (n - i + 1) // i
        if result >= cap:
            return cap
    return result


def _validate_cas_roots(electrons, orbitals, multiplicity, nroots):
    alpha = (electrons + multiplicity - 1) // 2
    beta = electrons - alpha
    # The number of spin-adapted CAS references of spin S is
    # C(m,alpha)*C(m+1,beta)*(2S+1)/(alpha+1). Only the comparison matters.
    minimum_product = (nroots * (alpha + 1) + multiplicity - 1) // multiplicity
    product = _binomial_up_to(orbitals, alpha, minimum_product)
    product *= _binomial_up_to(orbitals + 1, beta, minimum_product)
    if product < minimum_product:
        raise ValueError("目标根数超过该多重度下活性空间的自旋适配组态数")


def _mr_eom_input(method, electrons, orbitals, multiplicity, nroots):
    _validate_active_spin(electrons, orbitals, multiplicity)
    _validate_cas_roots(electrons, orbitals, multiplicity, nroots)
    # One multiplicity and equal weights. The template uses the same number
    # of roots in the reference average and the final diagonalization.
    lines = ["%casscf", f"  nel {electrons}", f"  norb {orbitals}", f"  mult {multiplicity}",
             f"  nroots {nroots}", "end"]
    if method == "MR-EOM-MRPT":
        method = "MR-EOM"
        lines.extend(("%mdci", "  DoMREOM_MRPT true", "end"))
    lines.extend(("%mrci", f"  newblock {multiplicity} *", f"    nroots {nroots}",
                  f"    refs cas({electrons},{orbitals}) end", "  end", "end"))
    return method, tuple(lines)


def _rocis_input(method, multiplicity, nroots):
    dft = method.endswith("/DFT")
    lines = []
    if not dft:
        lines.extend(("%scf", "  HFTyp ROHF", "  ROHF_Case HighSpin",
                      f"  ROHF_Nel[1] = {multiplicity - 1}", "end"))
    # Explicitly select the original high-spin implementation. The DFT
    # recipe uses the B3LYP orbitals and coefficients from §5.7.1.3.
    ri = "true" if method.startswith("RI-") else "false"
    lines.extend(("%rocis", "  DoGenROCIS false", f"  NRoots {nroots}", f"  DoRI {ri}"))
    if dft:
        lines.extend(("  DoDFTCIS true", "  DFTCIS_c = 0.18, 0.20, 0.40"))
    return ("B3LYP" if dft else "HF"), (*lines, "end")


def state_keywords_and_block(method, active_electrons, active_orbitals, nroots,
                             reference_functional, multiplicity, electron_channel=None):
    """Return the simple line's method and individual ORCA block lines."""
    validate_parameters(method, active_electrons, active_orbitals, nroots, reference_functional, electron_channel)
    _validate_reference(method, multiplicity, electron_channel)
    if method in MREOM_METHODS:
        return _mr_eom_input(method, active_electrons, active_orbitals, multiplicity, nroots)
    if method in ROCIS_METHODS:
        return _rocis_input(method, multiplicity, nroots)
    if method in ACTIVE_SPACE_METHODS:
        return _active_space_input(method, active_electrons, active_orbitals, multiplicity, nroots)
    if method in RESPONSE_METHODS:
        return _response_input(method, nroots, reference_functional)
    if method in MDCI_METHODS:
        return _mdci_input(method, nroots, electron_channel)
    return method, ()

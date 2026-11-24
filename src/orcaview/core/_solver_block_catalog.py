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
        _count(block, "MaxIter", "Maximum iterations"),
        _count(block, "MaxDim", "Davidson space multiplier", hint="The expansion space equals this factor times the number of target roots."),
        _count(block, "NGuessMat", "Guess matrix order"),
        _positive(block, "ETol", "Energy convergence threshold (Eh)"),
        _positive(block, "RTol", "Residual convergence threshold"),
    )


_TWO_STEP = ("SuperCI_PT", "SuperCI", "DIIS", "KDIIS", "SOSCF", "NR")
_CASSCF = (
    _count("casscf", "MaxIter", "Maximum orbital optimization macroiterations", 2, "One macroiteration gives CASCI with fixed orbitals."),
    _positive("casscf", "GTol", "Orbital gradient convergence threshold"),
    _positive("casscf", "ETol", "Macroiteration energy convergence threshold (Eh)"),
    BlockOption("casscf", "OrbStep", "Initial orbital optimization algorithm", "choice", choices=_TWO_STEP),
    BlockOption("casscf", "SwitchStep", "Late-stage orbital optimization algorithm", "choice", choices=_TWO_STEP),
    _positive("casscf", "SwitchConv", "Gradient norm for switching orbital optimization algorithms"),
    _count("casscf", "SwitchIter", "Macroiteration for switching orbital optimization algorithms"),
    BlockOption("casscf", "ShiftUp", "Virtual orbital upward shift (Eh)", "float", minimum=0),
    BlockOption("casscf", "ShiftDn", "Inactive orbital downward shift (Eh)", "float", minimum=0),
    BlockOption("casscf", "MinShift", "Minimum subspace energy gap (Eh)", "float", minimum=0),
    BlockOption("casscf", "ActConstraints", "Active orbital constraints", "int", minimum=0, maximum=4,
                hint="0: off, 1: maximum overlap, 2: natural, 3: canonical, 4: localized orbitals."),
    _positive("casscf", "MaxRot", "Maximum SuperCI_PT orbital rotation step"),
    BlockOption("casscf", "DThresh", "SuperCI_PT critical occupation threshold", "float", minimum=0),
    _count("casscf", "MaxDIIS", "Retained orbital optimization DIIS vectors"),
    _positive("casscf", "DIISThresh", "Orbital optimization DIIS linear dependence threshold"),
    _positive("casscf", "GradScaling", "Orbital optimization gradient scaling"),
)
_AH = "casscf.aughess"
_AUGHESS = (
    BlockOption(_AH, "Solver", "Augmented Hessian solver", "int", minimum=0, maximum=2,
                hint="0: Davidson, 1: Pople, 2: DIIS. Requires NR orbital optimization."),
    _count(_AH, "MaxIter", "Maximum augmented Hessian iterations"),
    _count(_AH, "MaxDim", "Davidson expansion space dimension"),
    _count(_AH, "MaxDIIS", "Augmented Hessian DIIS vectors"),
    BlockOption(_AH, "UseSubMatrixGuess", "Diagonalize a submatrix for the initial guess", "bool"),
    _count(_AH, "NGuessMat", "Submatrix dimension for the initial guess"),
    _count(_AH, "ExactDiagSwitch", "Maximum dimension for direct diagonalization"),
    _positive(_AH, "Tol", "Augmented Hessian convergence threshold"),
    BlockOption(_AH, "Compress", "Use compressed storage", "bool"),
    BlockOption(_AH, "DiagShift", "Hessian diagonal shift", "float"),
    BlockOption(_AH, "UseDiagPrec", "Use diagonal preconditioning", "bool"),
    BlockOption(_AH, "SecShift", "Davidson shift for higher roots", "float"),
    BlockOption(_AH, "UpdateShift", "Denominator shift for coefficient updates", "float"),
)
_DMRG = "casscf.dmrg"
_DMRG_OPTIONS = (
    _count(_DMRG, "startM", "Initial renormalized states"),
    _count(_DMRG, "maxM", "Maximum renormalized states"),
    _count(_DMRG, "MaxIter", "Maximum sweeps"),
    _positive(_DMRG, "SweepTol", "Sweep energy convergence threshold"),
    BlockOption(_DMRG, "auto_ordering", "Active orbital ordering", "choice", choices=("NOREORDER", "FIEDLER", "GAOPT")),
    BlockOption(_DMRG, "hf_occ", "Initial orbital occupations", "int", minimum=1, maximum=2,
                hint="1 sorts by one-electron integrals, 2 by canonical orbital energies."),
    _positive(_DMRG, "switch_rst", "Orbital gradient threshold for single-site DMRG updates"),
    BlockOption(_DMRG, "warmup", "Warm-up algorithm", "int", minimum=1, maximum=4),
)
_CI = _davidson("casscf.CI")
_ICE = (
    _positive("casscf.CI", "TGen", "ICE generation threshold"),
    BlockOption("casscf.CI", "TVar", "ICE variational selection threshold", "float",
                hint="A positive value is an absolute threshold. A negative value uses its magnitude times TGen."),
    BlockOption("casscf.CI", "ICEType", "ICE configuration representation", "choice", choices=("CFGs", "CSFs", "DETs")),
)
_PT = "casscf.PTSettings"
_PT_SCREENING = (
    BlockOption(_PT, "D3TPre", "Three-body density matrix prescreening threshold", "float", minimum=0),
    BlockOption(_PT, "D4TPre", "Four-body density matrix prescreening threshold", "float", minimum=0),
)
_CASPT2 = (
    _count(_PT, "MaxIter", "Maximum perturbation equation iterations"),
    _count(_PT, "MaxDIIS", "Number of DIIS vectors"),
    _positive(_PT, "NThresh", "Internally contracted configuration linear dependence threshold"),
    BlockOption(_PT, "CASPT2_ishift", "Imaginary level shift (Eh)", "float", minimum=0),
    BlockOption(_PT, "CASPT2_rshift", "Real level shift (Eh)", "float"),
    BlockOption(_PT, "CASPT2_IPEAshift", "IPEA shift (Eh)", "float"),
)
_MRCI = (
    _count("mrci", "MaxIter", "Maximum CI solver iterations"),
    _positive("mrci", "Etol", "CI energy convergence threshold (Eh)"),
    _positive("mrci", "Rtol", "CI residual convergence threshold"),
)
_MRCI_SELECTION = (
    BlockOption("mrci", "TSel", "Excited configuration selection threshold", "float", minimum=0),
    BlockOption("mrci", "TPre", "Reference configuration prescreening threshold", "float", minimum=0),
)
_MREOM_AMPLITUDES = (
    _count("mdci", "MaxIter", "Maximum multireference amplitude iterations"),
    _positive("mdci", "STol", "Multireference amplitude residual threshold"),
)
_AUTOCI = (
    _count("autoci", "MaxIter", "Maximum iterations"),
    _count("autoci", "MaxDIIS", "Number of DIIS vectors"),
    _count("autoci", "DIISStartIter", "DIIS starting iteration", 0, "Iteration numbering starts at 0."),
    _positive("autoci", "STol", "Amplitude residual convergence threshold"),
    BlockOption("autoci", "LevelShift", "DIIS level shift (Eh)", "float"),
)
_MDCI_GROUND = (
    _count("mdci", "MaxIter", "Maximum ground-state amplitude iterations"),
    _count("mdci", "MaxDIIS", "Ground-state DIIS vectors"),
    _positive("mdci", "STol", "Ground-state amplitude residual threshold"),
    BlockOption("mdci", "LShift", "Amplitude update level shift (Eh)", "float"),
)
_EOM_DAVIDSON = (
    _count("mdci", "NDav", "Davidson space multiplier", hint="The expansion space equals this factor times the number of target roots."),
    BlockOption("mdci", "DoRootwise", "Solve one root at a time", "bool"),
)
_EOM = (
    _positive("mdci", "DTol", "Davidson residual convergence threshold"),
    _positive("mdci", "OTol", "Orthogonalization threshold"),
)
_CANONICAL_EOM = (
    _count("mdci", "NInits", "CIS initial guess root multiplier", 0, "With 0, ORCA selects a value from the number of roots and NDav."),
    BlockOption("mdci", "FollowCIS", "Track initial CIS roots", "bool"),
    BlockOption("mdci", "UseCISUpdate", "Update trial vectors with CIS diagonal elements", "bool"),
)
_STEOM = (
    BlockOption("mdci", "OThresh", "IP active occupied orbital selection threshold", "float", minimum=0),
    BlockOption("mdci", "VThresh", "EA active virtual orbital selection threshold", "float", minimum=0),
)
_CANONICAL_STEOM = (
    BlockOption("mdci", "DoDbFilter", "Filter predominantly doubly excited states", "bool"),
    BlockOption("mdci", "DoNewActSch", "Use the new active space selection algorithm", "bool"),
    BlockOption("mdci", "IPSThrs", "IP root singles percentage threshold", "int", 0, 100),
    BlockOption("mdci", "EASThrs", "EA root singles percentage threshold", "int", 0, 100),
    _count("mdci", "NRootsCISNAT", "Initial CIS roots for active space selection"),
)
_ROOT_TRACKING = (
    BlockOption("mdci", "CheckEachRoot", "Check convergence separately for each root", "bool"),
    BlockOption("mdci", "RootHoming", "Track target roots by overlap", "bool"),
)
_PNO = {
    block: (
        BlockOption(block, "TCutPNO", "Pair natural orbital occupation cutoff", "float", minimum=0),
        BlockOption(block, "TCutDO", "Local orbital domain cutoff", "float", minimum=0),
        BlockOption(block, "TCutMKN", "Local auxiliary fitting domain cutoff", "float", minimum=0),
    ) for block in ("mp2", "mdci")
}
_MP2_MEMORY = _count("mp2", "MaxCore", "MP2 memory limit per core (MB)",
                     hint="Overrides the per-core memory budget for the MP2 stage.")
_MP2_Q1 = BlockOption("mp2", "Q1Opt", "Conventional MP2 integral algorithm", "int", minimum=-1, maximum=2,
                      hint="−1: disk; 1 and 2: in-memory double- and single-precision buffers. Gradients require an in-memory algorithm.")
_REGULARIZED_MP2 = (
    BlockOption("mp2", "DoRegMP2", "Enable regularized MP2", "bool"),
    BlockOption("mp2", "RegMP2Type", "Regularization type", "int", minimum=0, maximum=2,
                hint="When regularization is enabled: 0 selects κ, 1 selects σ, 2 selects σ²."),
    _positive("mp2", "RegMP2Kappa", "κ regularization parameter"),
    _positive("mp2", "RegMP2Sigma", "σ regularization parameter"),
)
_LOCAL_MP2 = (
    _count("mp2", "MaxPNOIter", "Maximum local amplitude iterations"),
    _count("mp2", "MaxLocIter", "Maximum orbital localization iterations"),
    _positive("mp2", "TolE", "Local MP2 energy convergence threshold (Eh)"),
    _positive("mp2", "TolR", "Local amplitude residual threshold"),
    _positive("mp2", "LocTol", "Orbital localization convergence threshold"),
    BlockOption("mp2", "LocMet", "Localization method", "choice", choices=("AHFB", "FB", "PM", "IAOIBO", "IAOBOYS", "NEWBOYS")),
    _count("mp2", "DIISStart_PNO", "DIIS start for PNO amplitudes", minimum=0),
    _count("mp2", "MaxDIIS_PNO", "DIIS vectors for PNO amplitudes"),
    BlockOption("mp2", "Damp1_PNO", "Damping before DIIS", "float", 0, 1, maximum_exclusive=True),
    BlockOption("mp2", "Damp2_PNO", "Damping during DIIS", "float", 0, 1, maximum_exclusive=True),
    BlockOption("mp2", "MP2Shift_PNO", "Local amplitude update level shift (Eh)", "float"),
)
_MP2_SCREENING = tuple(BlockOption("mp2", key, label, "float", minimum=0) for key, label in (
    ("FCut", "Occupied Fock matrix element cutoff"), ("TCutPre", "Dipole prescreening energy threshold"),
    ("TCutDOij", "Orbital pair differential overlap prescreening threshold"), ("TCutDOPre", "Projected atomic orbital selection threshold for prescreening"),
    ("TCutC", "Projected atomic orbital coefficient cutoff"), ("ScaleTCutC_MO", "MO cutoff as a multiple of TCutC"),
    ("PAOOverlapThresh", "Projected atomic orbital linear dependence threshold"),
))
_MDCI_SCREENING = (
    BlockOption("mdci", "TCutPairs", "Estimated pair correlation energy cutoff", "float", minimum=0),
    BlockOption("mdci", "TCutDeloc", "Delocalization threshold for extending local domains", "float", minimum=0),
    BlockOption("mdci", "TCutOSV", "Orbital-specific virtual orbital prescreening threshold", "float", minimum=0),
    BlockOption("mdci", "PAOOverlapThresh", "Projected atomic orbital linear dependence threshold", "float", minimum=0),
)
_MCRPA = (
    _positive("mcrpa", "TolR", "Response equation residual norm threshold"),
    _count("mcrpa", "MaxIter", "Maximum Davidson iterations for response equations"),
    _count("mcrpa", "MaxRed", "Expansion space shared by all response vectors"),
    BlockOption("mcrpa", "PreCond", "Response equation preconditioner", "choice", choices=("full", "diag")),
    _count("mcrpa", "PreConMaxRed", "Exact Hessian subspace dimension for preconditioning"),
)
_ORBITAL_MP2 = (
    _count("mp2", "MaxOrbIter", "Maximum orbital iterations"),
    BlockOption("mp2", "MP2Shift", "Orbital optimization level shift (Eh)", "float"),
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
                      ("Coupled cluster", "Configuration interaction and electron-pair methods") for name, _ in entries}
_CANONICAL_MDCI = {name for name in _GROUND_MDCI_NAMES if not name.startswith(("DLPNO-", "pCCSD/"))}
MDCI_RHF_ONLY_KC = ("KC_AO", "KC_AOBLAS", "KC_RI", "KC_RI2")
_ADC_NAMES = ("ADC2", "IP-ADC2", "EA-ADC2")


def _mdci_integral_options(spec):
    # §3.10.2 and §3.10.14 distinguish transformation of the lower-rank
    # integrals from formation of terms with 3–4 external indices.
    kc = ("KC_MO", "KC_AOX")
    if spec.wavefunction in ("Auto", "RHF"):
        kc += MDCI_RHF_ONLY_KC
    return (BlockOption("mdci", "KCOpt", "MDCI algorithm for integrals with three or four external indices", "choice", choices=kc,
                        hint="MO uses a full transformation; AOX uses stored AO integrals. Direct AO and external RI require closed shells."),
            BlockOption("mdci", "TrafoType", "MDCI integral transformation", "choice",
                        choices=("trafo_jk", "trafo_ri", "trafo_full"),
                        hint="jk: partial J/K transformation; ri: correlation fitting basis; full: full four-index transformation."))


def _cas_options(method):
    if method in CASDFT_METHODS:
        result = tuple(o for o in _CASSCF if o.key in ("MaxIter", "ETol", "GTol"))
        if method.removeprefix("CI-").startswith("sr"):
            result += (_positive("method", "RangeSepMu", "Short-range functional range separation (bohr⁻¹)"),)
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
            result += (_positive(_PT, "TReg", "CASPT2-K Tikhonov regularization parameter"),)
    if method in ("FIC-NEVPT2", "SC-NEVPT2", "RI-NEVPT2", "SA-SC-NEVPT2"):
        result += (BlockOption(_PT, "D4Step", "Higher-order reduced density matrix algorithm", "choice",
                               choices=("efficient", "fly", "Cu4", "Cu34")),)
    if method == "FIC-NEVPT2":
        result += (BlockOption(_PT, "imaginary", "Imaginary level shift (Eh)", "float", minimum=0),
                   _positive(_PT, "NThresh", "Internally contracted configuration linear dependence threshold"))
    if method in _UNCONTRACTED_NAMES or method in MREOM_METHODS:
        result += _MRCI
    if method in _UNCONTRACTED_NAMES:
        result += _MRCI_SELECTION
    if method in MREOM_METHODS:
        result += _MREOM_AMPLITUDES
    if method in _FIC_AUTOCI:
        result += (_positive("autoci", "NThresh", "Internally contracted configuration linear dependence threshold"),)
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
            result += (BlockOption("tddft", "GridXC", "Excited-state exchange–correlation angular grid", "int", 0, 7),
                       _positive("tddft", "IntAccXC", "Excited-state exchange–correlation radial accuracy"))
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
            result += (BlockOption("mdci", "Triples", "Perturbative triples algorithm", "int", 1, 2,
                                   hint="1: high-memory algorithm; 2: lower-memory closed-shell algorithm."),)
        if method.startswith("DLPNO-CCSD") and spec.pno_preset == "Auto":
            result += _PNO["mdci"] + _MDCI_SCREENING
            if "(T" in method:
                result += (BlockOption("mdci", "TCutTNO", "Triples natural orbital cutoff (0: automatic)", "float", minimum=0),)
        return result
    if method.startswith("AUTOCI-") and not method.startswith("AUTOCI-MP"):
        return _AUTOCI
    if method.startswith("CIM-"):
        return (_positive("cim", "CIMTHRESH", "Cluster construction overlap threshold"),)
    if method.startswith("MRCC-"):
        return (_count("mrcc", "ETol", "Energy convergence accuracy exponent", hint="Use an integer accuracy exponent, e.g. 9."),)
    return ()


def validate_solver_combinations(spec, values):
    casscf = {key: value for (block, key), value in values.items() if block == "casscf"}
    stages = {casscf.get("OrbStep", "SuperCI_PT"), casscf.get("SwitchStep", "SuperCI_PT")}
    if "SuperCI_PT" not in stages and any(k in casscf for k in ("MaxRot", "DThresh")):
        raise ValueError("MaxRot and DThresh require a SuperCI_PT orbital optimization stage")
    if stages.isdisjoint(("SuperCI_PT", "DIIS", "KDIIS")) and any(k in casscf for k in ("MaxDIIS", "DIISThresh")):
        raise ValueError("Orbital optimization DIIS requires a SuperCI_PT, DIIS or KDIIS stage")
    aughess = {key: value for (block, key), value in values.items() if block == _AH}
    if aughess:
        if "NR" not in stages:
            raise ValueError("aughess options require NR in an orbital optimization stage")
        solver = aughess.get("Solver", 0)
        if solver != 0 and any(k in aughess for k in ("MaxDim", "SecShift")):
            raise ValueError("Augmented Hessian MaxDim and SecShift require the Davidson solver")
        if solver != 2 and "MaxDIIS" in aughess:
            raise ValueError("Augmented Hessian MaxDIIS requires the DIIS solver")
        if aughess.get("UseSubMatrixGuess") is False and "NGuessMat" in aughess:
            raise ValueError("NGuessMat requires an augmented Hessian submatrix guess")
    if (_DMRG, "startM") in values and (_DMRG, "maxM") in values and values[_DMRG, "startM"] > values[_DMRG, "maxM"]:
        raise ValueError("DMRG startM cannot exceed maxM")
    if ("mdci", "NRootsCISNAT") in values and values["mdci", "NRootsCISNAT"] < spec.nroots:
        raise ValueError("STEOM active space selection needs at least as many CIS roots as target roots")
    if ("mcrpa", "PreConMaxRed") in values and values.get(("mcrpa", "PreCond")) == "diag":
        raise ValueError("Full-Hessian MCRPA preconditioning requires PreCond full")
    kc = values.get(("mdci", "KCOpt"))
    trafo = values.get(("mdci", "TrafoType"))
    if kc == "KC_MO" and trafo in ("trafo_jk", "trafo_ri"):
        raise ValueError("KC_MO uses a full four-index transformation and cannot use partial or RI transformations")
    if spec.method in ("RI-CCSD", "RI-CCSD(T)") and (kc == "KC_MO" or
            (kc in ("KC_AO", "KC_AOBLAS", "KC_AOX") and trafo in ("trafo_jk", "trafo_full"))):
        raise ValueError("The selected RI-MDCI method requires RI in the correlation integral transformation or external integrals")
    q1 = values.get(("mp2", "Q1Opt"))
    if q1 == 0 or (q1 == -1 and spec.job_type != "SP"):
        raise ValueError("mp2.Q1Opt accepts −1 or a positive integer. Gradients and frequencies require a positive integer.")
    regularized = values.get(("mp2", "DoRegMP2"), False)
    if any(("mp2", key) in values for key in ("RegMP2Type", "RegMP2Kappa", "RegMP2Sigma")) and not regularized:
        raise ValueError("Enable mp2.DoRegMP2 before setting regularization parameters")
    if regularized:
        if spec.method == "MP2" and (q1 is None or q1 < 1):
            raise ValueError("Regularized conventional MP2 requires an explicit in-memory algorithm (mp2.Q1Opt > 0)")
        reg_type = values.get(("mp2", "RegMP2Type"), 0)
        if (reg_type == 0 and ("mp2", "RegMP2Sigma") in values
                or reg_type in (1, 2) and ("mp2", "RegMP2Kappa") in values):
            raise ValueError("mp2.RegMP2Type does not match the specified κ or σ parameter")

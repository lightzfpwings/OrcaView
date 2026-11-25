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
from .block_options import BlockOverride
from .methods import DISPERSION_RECIPES, METHODS, frozen_core_options


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


_SCF_ITER = _iterations("scf", "MaxIter", "Maximum SCF iterations")
_SCF = (
    _SCF_ITER,
    _choice("scf", "Convergence", "SCF convergence level", ("Sloppy", "Loose", "Medium", "Strong", "Tight", "VeryTight", "Extreme")),
    _positive("scf", "TolE", "Energy change threshold (Eh)"),
    _positive("scf", "TolRMSP", "RMS density matrix change threshold"),
    _positive("scf", "TolMaxP", "Maximum density matrix change threshold"),
    _positive("scf", "TolErr", "DIIS error threshold"),
    _positive("scf", "TolG", "Orbital gradient threshold"),
    _positive("scf", "TolX", "Orbital rotation angle threshold"),
    BlockOption("scf", "ConvCheckMode", "Convergence criteria combination", "int", 0, 2,
                hint="0 checks every criterion, 1 accepts any one criterion, 2 checks changes in total and one-electron energies."),
    BlockOption("scf", "ConvForced", "Require SCF convergence in subsequent steps", "int", 0, 1),
    _positive("scf", "Thresh", "Integral prescreening threshold"),
    _positive("scf", "TCut", "Primitive Gaussian integral prescreening threshold"),
    BlockOption("scf", "CNVDIIS", "Enable DIIS", "bool"),
    BlockOption("scf", "DIISStart", "Error threshold to start DIIS", "float", minimum=0),
    _iterations("scf", "DIISMaxIt", "Maximum iterations before starting DIIS"),
    BlockOption("scf", "DIISMaxEq", "Retained DIIS Fock matrices", "int", minimum=1),
    _positive("scf", "DIISBFac", "DIIS low-energy bias factor"),
    BlockOption("scf", "CNVDamp", "Enable density damping", "bool"),
    BlockOption("scf", "CNVZerner", "Enable dynamic Zerner damping", "bool"),
    _damping("DampFac", "Density damping factor"),
    BlockOption("scf", "DampErr", "Error threshold to disable damping", "float", minimum=0),
    _damping("DampMin", "Minimum dynamic damping"),
    _damping("DampMax", "Maximum dynamic damping"),
    BlockOption("scf", "CNVShift", "Enable virtual orbital level shift", "bool"),
    BlockOption("scf", "LShift", "Virtual orbital level shift (Eh)", "float", minimum=0),
    BlockOption("scf", "ShiftErr", "Error threshold to disable level shifting", "float", minimum=0),
)
_SOSCF = (
    BlockOption("scf", "CNVSOSCF", "Enable approximate second-order SCF", "bool"),
    _positive("scf", "SOSCFStart", "Orbital gradient threshold to start SOSCF"),
    _iterations("scf", "SOSCFMaxIt", "Maximum iterations before starting SOSCF"),
)
_TRAH = (
    BlockOption("scf", "AutoTRAH", "Switch to TRAH on slow convergence", "bool"),
    _positive("scf", "AutoTRAHTol", "Convergence rate threshold for automatic switching"),
    _iterations("scf", "AutoTRAHIter", "Earliest iteration to switch to TRAH"),
    BlockOption("scf", "AutoTRAHNInter", "Iterations used to estimate the convergence rate", "int", minimum=2),
    _iterations("scf.trah", "MaxRed", "Maximum Davidson microiterations"),
    BlockOption("scf.trah", "NStart", "Initial Davidson vectors", "int", minimum=2),
    _positive("scf.trah", "TolFacMicro", "Microiteration threshold scaling factor"),
    _positive("scf.trah", "MinTolMicro", "Minimum microiteration accuracy"),
    _positive("scf.trah", "QuadRegionStart", "Gradient threshold for switching to Newton steps"),
    _positive("scf.trah", "tradius", "Initial trust radius"),
    _positive("scf.trah", "AlphaMin", "Minimum gradient scaling factor"),
    _positive("scf.trah", "AlphaMax", "Maximum gradient scaling factor"),
    BlockOption("scf.trah", "Randomize", "Perturb starting Davidson vectors randomly", "bool"),
    BlockOption("scf.trah", "PseudoRand", "Use reproducible pseudorandom perturbations", "bool"),
    BlockOption("scf.trah", "MaxNoise", "Maximum random perturbation amplitude", "float", minimum=0),
    _choice("scf.trah", "OrbUpdate", "Orbital update algorithm", ("Taylor", "Cayley")),
    _choice("scf.trah", "InactiveMOs", "Inactive orbital treatment", ("Canonical", "NotSet")),
    _choice("scf.trah", "Precond", "Hessian preconditioner", ("Diag", "Full", "None")),
    _iterations("scf.trah", "PreconMaxRed", "Maximum full-Hessian preconditioning space"),
)
_NATIVE_XTB_SCF = (
    BlockOption("scf", "UseXTBMixer", "Use the xTB SCF mixer", "bool"),
    BlockOption("scf", "SmearTemp", "Electronic temperature (K)", "float", minimum=0),
    _SCF_ITER,
)
_DFT_METHODS = frozenset(name for _, entries in DFT_METHOD_GROUPS + EXTRA_DFT_GROUPS
                         for name, _ in entries if name != "HF") | DLPNO_DOUBLE_HYBRIDS.keys()
_DFT_GRID = (
    BlockOption("method", "AngularGrid", "Exchange–correlation angular grid", "int", 0, 7,
                hint="0 selects SimpleGrid; 1–7 select Lebedev grids of increasing order."),
    _positive("method", "IntAcc", "Exchange–correlation radial integration accuracy"),
    _positive("method", "NThetaMax", "SimpleGrid angular point multiplier"),
    _choice("method", "GridPruning", "Integration grid pruning", ("Adaptive", "OldPruning", "Unpruned")),
    BlockOption("method", "HGridReduced", "Reduce grid density for H and He", "bool"),
    _positive("method", "BFCut", "Integration basis function cutoff"),
    _positive("method", "WeightCut", "Integration weight cutoff"),
)
_LIBXC = (
    _positive("method", "LibXCDensityThreshold", "LibXC density threshold"),
    _positive("method", "LibXCZetaThreshold", "LibXC spin polarization threshold"),
    _positive("method", "LibXCTauThreshold", "LibXC kinetic energy density threshold"),
)
_ADFT = (
    _positive("method", "ADFTNRTol", "ADFT Newton convergence threshold"),
    _iterations("method", "ADFTNRMaxIter", "Maximum ADFT Newton iterations"),
    BlockOption("method", "ADFTLmaxAuxJ", "Maximum angular momentum for Coulomb fitting", "int", minimum=0),
    BlockOption("method", "ADFTLmaxAuxX", "Maximum angular momentum for exchange fitting", "int", minimum=0),
)
_DISPERSION_COEFFICIENTS = {
    "D3BJ": ("D3S6", "D3S8", "D3A1", "D3A2"),
    "D3ZERO": ("D3S6", "D3S8", "D3RS6", "D3alpha6"),
    "D4": ("D4S6", "D4S8", "D4A1", "D4A2", "D4S9"),
}
_DISPERSION_TUNING = {
    name: tuple(BlockOption("method", key, f"{name} dispersion parameter {key}", "float",
                            hint="Override the dispersion parameterization of the selected functional.") for key in keys)
    for name, keys in _DISPERSION_COEFFICIENTS.items()
}
_FROZEN_CORE = (
    BlockOption("method", "CheckFrozenCore", "Check core orbital ordering", "bool"),
    BlockOption("method", "CorrectFrozenCore", "Correct misordered core orbitals", "bool"),
)
_CP_SCF = (
    _choice("method", "Z_Solver", "CP-SCF linear solver", ("Pople", "DIIS", "CG")),
    _positive("method", "Z_Tol", "CP-SCF residual convergence threshold"),
    _iterations("method", "Z_MaxIter", "Maximum CP-SCF iterations"),
    _iterations("method", "Z_MaxDIIS", "Retained CP-SCF DIIS vectors"),
    BlockOption("method", "Z_Shift", "CP-SCF DIIS level shift", "float", minimum=0),
)
_COSX = (
    BlockOption("method", "UseSFitting", "COSX overlap matrix fitting", "bool"),
    _choice("method", "SFitInvertType", "Overlap fitting matrix inversion", ("Cholesky", "Cholesky_Q", "Diag", "Diag_Q")),
    _positive("method", "SInvThresh", "Eigenvalue threshold for inversion by diagonalization"),
    BlockOption("method", "COSX_PartialContraction", "Use an intermediate basis for generally contracted shells", "bool"),
    _choice("method", "COSX_IntSymmetry", "COSX integral permutation symmetry", ("Standard", "Full")),
)
_GEOM = (
    _iterations("geom", "MaxIter", "Maximum geometry optimization steps"),
    _choice("geom", "coordsys", "Optimization coordinates", ("redundant", "cartesian")),
    _choice("geom", "Convergence", "Geometry convergence level", ("loose", "normal", "tight")),
    _positive("geom", "TolE", "Energy change threshold (Eh)"),
    _positive("geom", "TolRMSG", "RMS gradient threshold (a.u.)"),
    _positive("geom", "TolMaxG", "Maximum gradient threshold (a.u.)"),
    _positive("geom", "TolRMSD", "RMS displacement threshold (a.u.)"),
    _positive("geom", "TolMaxD", "Maximum displacement threshold (a.u.)"),
    _choice("geom", "Step", "Optimization step algorithm", ("qn", "rfo")),
    _positive("geom", "MaxStep", "Maximum internal coordinate step (a.u.)"),
    BlockOption("geom", "Trust", "Trust radius (a.u.)", "float", hint="Negative values fix the radius; positive values allow adjustment."),
    _choice("geom", "InHess", "Initial Hessian model", ("unit", "Almloef", "Lindh", "Swart", "Schlegel")),
    _choice("geom", "Update", "Hessian update method", ("BFGS", "Powell", "Bofill")),
    BlockOption("geom", "Calc_Hess", "Compute Hessian at the start of optimization", "bool"),
    _iterations("geom", "Recalc_Hess", "Hessian recalculation interval"),
    BlockOption("geom", "NumHess", "Use numerical differentiation for the optimization Hessian", "bool"),
    _iterations("geom", "NResetHess", "BFGS model Hessian rebuild interval"),
    _iterations("geom", "NStepsInResetHess", "History length for rebuilding the model Hessian"),
    BlockOption("geom", "ProjectTR", "Project translations and rotations out of Cartesian optimization", "bool"),
    BlockOption("geom", "AddExtraBonds", "Add redundant internal bonds between neighboring atoms", "bool"),
    _iterations("geom", "AddExtraBonds_MaxLength", "Maximum topological distance for extra bonds (bonds)"),
    _positive("geom", "AddExtraBonds_MaxDist", "Maximum spatial distance for extra bonds (Å)"),
    BlockOption("geom", "optimizeHydrogens", "Optimize only hydrogen coordinates", "bool"),
    BlockOption("geom", "freezeHydrogens", "Fix hydrogens relative to heavy atoms", "bool"),
)
_GEOM_TS = tuple(o for o in _GEOM if o.key != "Step") + (
    _choice("geom", "HESS_Modification", "P-RFO Hessian modification", ("Shift_Diag", "EV_Reverse")),
    _positive("geom", "HESS_MinEV", "Minimum absolute P-RFO Hessian eigenvalue"),
)
_FREQ = (
    BlockOption("freq", "TransInvar", "Enforce Hessian translation invariance after calculation", "bool"),
    BlockOption("freq", "ProjectTR", "Project out translations and rotations", "bool"),
)
NUMERICAL_FREQUENCY_OPTIONS = (
    BlockOption("freq", "CentralDiff", "Use central differences", "bool", hint="When off, use one-sided differences."),
    _positive("freq", "Increment", "Numerical displacement (bohr)"),
    BlockOption("freq", "NumHessTransInvar", "Use translation invariance for displaced gradients", "bool"),
)
_NUMFREQ_KEYS = tuple(option.key for option in NUMERICAL_FREQUENCY_OPTIONS)


def uses_numerical_frequencies(spec):
    if METHODS[spec.method].uses_numerical_frequencies:
        return True
    # A project that explicitly configures displaced gradients requests NumFreq.
    # Common %freq settings such as ProjectTR apply to either Hessian.
    return spec.job_type in ("FREQ", "OPT_FREQ") and any(
        isinstance(item, BlockOverride) and item.block == "freq" and item.key in _NUMFREQ_KEYS
        for item in spec.block_options
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
        options.append(_iterations("method", "RPACNPoints", "RPA frequency quadrature points"))
    if spec.integral_approximation == "RIJCOSX":
        options.extend(_COSX)
        if has_derivatives:
            options.append(BlockOption("method", "UseQGradFit", "Use the SCF overlap fitting matrix for gradients", "bool"))
    options.extend(_DISPERSION_TUNING.get(spec.dispersion, ()))
    if spec.frozen_core != "NoFrozenCore" and "FrozenCore" in frozen_core_options(spec.method):
        options.extend(_FROZEN_CORE)
    mp2_response = has_derivatives and spec.method in ("MP2", "RI-MP2", "RI-SCS-MP2", "RI-SOS-MP2", "SCS-MP2")
    if (has_frequency and not numerical) or mp2_response:
        options.extend(_CP_SCF)
        if is_grid_dft and spec.integration_grid == "Auto":
            options.extend((BlockOption("method", "Z_GridXC", "CP-SCF exchange–correlation angular grid", "int", 0, 7),
                            _positive("method", "Z_IntAccXC", "CP-SCF exchange–correlation radial accuracy")))
        if spec.integral_approximation == "RIJCOSX":
            options.append(BlockOption("method", "Z_COSX_Alg", "CP-SCF COSX algorithm", "int", 0, 2))
            if spec.integration_grid == "Auto":
                options.extend((BlockOption("method", "Z_GridX", "CP-SCF COSX angular grid", "int", 0, 7),
                                _positive("method", "Z_IntAccX", "CP-SCF COSX radial accuracy")))
                if mp2_response:
                    options.append(BlockOption("method", "Z_GridX_RHS", "SCF grid for the MP2 Z-vector right-hand side", "int", 1, 3))

    if spec.job_type in ("OPT", "OPT_FREQ"):
        options.extend(_GEOM)
    elif spec.job_type == "OPT_TS":
        options.extend(_GEOM_TS)
    if has_frequency:
        options.extend(_FREQ)
        if numerical:
            options.extend(NUMERICAL_FREQUENCY_OPTIONS)
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
            raise ValueError(f"Subparameters cannot be set when %scf {switch} is off")
    if spec.method.startswith("Native-") and "MaxIter" in scf and scf.get("UseXTBMixer") is not False:
        raise ValueError("Setting SCF MaxIter for native xTB requires UseXTBMixer false")
    if scf.get("CNVDamp") and scf.get("CNVZerner"):
        raise ValueError("Static CNVDamp and dynamic CNVZerner damping are mutually exclusive")
    if scf.get("CNVDamp") is False and not scf.get("CNVZerner") and any(
            k in scf for k in ("DampFac", "DampErr", "DampMin", "DampMax")):
        raise ValueError("Damping parameters require static or dynamic damping")
    if trah and scf.get("AutoTRAH") is False:
        raise ValueError("The trah subblock requires %scf AutoTRAH")
    if scf.get("DampMin", 0.0) > scf.get("DampMax", 0.98):
        raise ValueError("DampMin cannot exceed DampMax")
    if trah.get("AlphaMin", 0.1) > trah.get("AlphaMax", 1000.0):
        raise ValueError("TRAH AlphaMin cannot exceed AlphaMax")
    if trah.get("Randomize") is False and any(k in trah for k in ("PseudoRand", "MaxNoise")):
        raise ValueError("TRAH perturbation parameters require Randomize")
    if "PreconMaxRed" in trah and trah.get("Precond") != "Full":
        raise ValueError("PreconMaxRed requires the full Hessian preconditioner (Precond Full)")
    if any(key in method for key in ("Z_MaxDIIS", "Z_Shift")) and method.get("Z_Solver") != "DIIS":
        raise ValueError("CP-SCF DIIS vector count and level shift require Z_Solver DIIS")
    if "NThetaMax" in method and method.get("AngularGrid") != 0:
        raise ValueError("NThetaMax is only available with AngularGrid 0 (SimpleGrid)")
    if method.get("UseSFitting") is False and (any(k in method for k in ("SFitInvertType", "SInvThresh"))
                                                or method.get("UseQGradFit") is True):
        raise ValueError("COSX inversion settings and matrix reuse for gradients require overlap fitting")
    if "SInvThresh" in method and method.get("SFitInvertType") not in ("Diag", "Diag_Q"):
        raise ValueError("SInvThresh requires Diag or Diag_Q overlap fitting matrix inversion")
    if method.get("CheckFrozenCore") is False and method.get("CorrectFrozenCore") is True:
        raise ValueError("Core orbital ordering must be checked before it can be corrected")
    if geom.get("Trust") == 0.0:
        raise ValueError("%geom Trust requires a nonzero trust radius")
    if geom.get("ProjectTR") and geom.get("coordsys") != "cartesian":
        raise ValueError("ProjectTR true requires Cartesian geometry optimization")
    bond_limits = ("AddExtraBonds_MaxLength", "AddExtraBonds_MaxDist")
    if geom.get("coordsys") == "cartesian" and any(k in geom for k in ("AddExtraBonds", *bond_limits)):
        raise ValueError("Extra redundant internal bonds require redundant internal coordinates")
    if geom.get("AddExtraBonds") is False and any(k in geom for k in bond_limits):
        raise ValueError("The extra bond distance threshold requires AddExtraBonds")
    default_update = "Bofill" if spec.job_type == "OPT_TS" else "BFGS"
    if geom.get("Update", default_update) != "BFGS" and any(k in geom for k in ("NResetHess", "NStepsInResetHess")):
        raise ValueError("Model Hessian rebuild interval and history length apply only to BFGS updates")
    if geom.get("optimizeHydrogens") and geom.get("freezeHydrogens"):
        raise ValueError("Optimizing only hydrogen coordinates conflicts with fixing hydrogens relative to heavy atoms")
    if geom.get("coordsys") == "cartesian" and geom.get("InHess") == "Lindh":
        raise ValueError("The Lindh initial Hessian requires redundant internal coordinates")
    if "InHess" in geom and (geom.get("Calc_Hess") or "Recalc_Hess" in geom):
        raise ValueError("An initial Hessian calculation conflicts with an InHess starting model")
    if geom.get("Calc_Hess") is False and "Recalc_Hess" in geom:
        raise ValueError("Recalc_Hess computes the initial Hessian and conflicts with Calc_Hess false")
    if "NumHess" in geom and not (geom.get("Calc_Hess") or "Recalc_Hess" in geom):
        raise ValueError("NumHess requires Calc_Hess or Recalc_Hess")
    if (geom.get("Calc_Hess") or "Recalc_Hess" in geom) and geom.get("NumHess") is not True:
        if uses_numerical_frequencies(spec):
            raise ValueError("For this method, the optimization Hessian requires %geom NumHess true")

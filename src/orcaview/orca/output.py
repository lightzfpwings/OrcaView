"""Extract normal termination, SCF convergence and geometry convergence independently."""

from dataclasses import dataclass
import math
import re
from typing import Optional, Tuple


# ORCA also mentions "Compound Job" in the author credits of single jobs.
# Match a job heading or an input directive, optionally in a numbered input echo.
_MULTI_JOB_MARKER = re.compile(
    r"^[ \t]*(?:(?:\*+[ \t]*)?COMPOUND[ \t]+JOB\b|"
    r"(?:\|[ \t]*\d+>[ \t]*)?(?:\$[ \t]*NEW_JOB\b|%COMPOUND\b))",
    re.MULTILINE,
)


@dataclass(frozen=True)
class OutputSummary:
    normal_termination: bool
    optimization_converged: Optional[bool]
    scf_converged: Optional[bool]
    final_energy_hartree: Optional[float]
    status: str
    warnings: Tuple[str, ...]


def parse_output(text: str, job_type: str = "SP") -> OutputSummary:
    """Summarize single-job output without parsing a compound or new_job task tree."""
    from ..core.methods import ALL_JOBS, PATH_JOBS
    if job_type not in ALL_JOBS:
        raise ValueError("Unknown job type")
    upper = text.upper()
    normal = "ORCA TERMINATED NORMALLY" in upper
    warnings = []
    # Use the last explicit evidence so a successful retry supersedes earlier failures.
    scf_events = []
    for pattern, value in ((r"SCF\s+CONVERGED\s+AFTER", True), (r"SCF\s+NOT\s+CONVERGED|SCF\s+DID\s+NOT\s+CONVERGE", False)):
        scf_events.extend((match.start(), value) for match in re.finditer(pattern, upper))
    scf = max(scf_events)[1] if scf_events else None
    optimization_events = []
    for pattern, value in ((r"THE OPTIMIZATION HAS CONVERGED", True), (r"THE OPTIMIZATION HAS NOT CONVERGED|OPTIMIZATION DID NOT CONVERGE|MAXIMUM NUMBER OF OPTIMIZATION CYCLES REACHED", False)):
        optimization_events.extend((match.start(), value) for match in re.finditer(pattern, upper))
    optimization = max(optimization_events)[1] if optimization_events else None
    energies = re.findall(r"FINAL SINGLE POINT ENERGY\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DEde][+-]?\d+)?)", text)
    energy = float(energies[-1].replace("D", "E").replace("d", "e")) if energies else None
    if energy is not None and not math.isfinite(energy):
        energy = None
        warnings.append("The final energy is nonfinite and cannot be used as a calculation result.")
    explicit_error = bool(re.search(
        r"ORCA\s+FINISHED\s+BY\s+ERROR\s+TERMINATION|ORCA\s+TERMINATED\s+ABNORMALLY|ERROR\s+TERMINATION",
        upper,
    ))
    banner_count = len(re.findall(r"(?m)^\s*\*\s*O\s+R\s+C\s+A\s*\*\s*$", upper))
    version_count = len(re.findall(r"\bPROGRAM\s+VERSION\s+\d", upper))
    last_normal = upper.rfind("ORCA TERMINATED NORMALLY")
    # Calculation evidence after termination may belong to an incomplete appended job.
    trailing_calculation = normal and bool(re.search(
        r"SCF\s+(?:ITERATIONS|CONVERGED\s+AFTER|NOT\s+CONVERGED|DID\s+NOT\s+CONVERGE)|FINAL SINGLE POINT ENERGY|PROGRAM\s+VERSION\s+\d",
        upper[last_normal + len("ORCA TERMINATED NORMALLY"):],
    ))
    multiple_jobs = (
        upper.count("ORCA TERMINATED NORMALLY") > 1
        or banner_count > 1
        or version_count > 1
        or _MULTI_JOB_MARKER.search(upper) is not None
        or trailing_calculation
    )
    if multiple_jobs:
        warnings.append("Multiple jobs or subsequent calculations were detected. Their dependencies have not been verified.")
    if explicit_error:
        warnings.append("An abnormal termination was found after an earlier normal termination.")
    needs_optimization = job_type in ("OPT", "OPT_FREQ", "OPT_TS")
    if not normal:
        warnings.append("No ORCA normal termination marker was found. The file may be incomplete or the calculation may have failed.")
    if scf is False:
        warnings.append("The final explicit SCF status indicates nonconvergence.")
    if needs_optimization and optimization is not True:
        warnings.append("Geometry convergence was not confirmed.")
    if job_type in PATH_JOBS:
        warnings.append("Check the transition-state imaginary frequency or the IRC endpoints for reaction path jobs.")
    if job_type in ("FREQ", "OPT_FREQ"):
        warnings.append("Frequency completeness and imaginary modes have not been verified for this frequency job.")
    if explicit_error:
        status = "failed"
    elif not normal:
        status = "incomplete"
    elif multiple_jobs:
        status = "needs_review"
    elif scf is False or (needs_optimization and optimization is False):
        status = "unconverged"
    elif needs_optimization and optimization is None:
        status = "needs_review"
    elif job_type in ("FREQ", "OPT_FREQ", *PATH_JOBS) or scf is None or energy is None:
        status = "needs_review"
    else:
        status = "completed"
    return OutputSummary(normal, optimization, scf, energy, status, tuple(warnings))

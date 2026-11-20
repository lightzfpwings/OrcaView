"""保守提取文本证据：正常结束、SCF 收敛和几何收敛分别记录。"""

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
    """提取单任务文本的摘要，不解析 compound/new_job 的任务树。"""
    from ..core.methods import ALL_JOBS, PATH_JOBS
    if job_type not in ALL_JOBS:
        raise ValueError("未知任务类型")
    upper = text.upper()
    normal = "ORCA TERMINATED NORMALLY" in upper
    warnings = []
    # 采用最后一次明确证据；优化中早期失败不能覆盖后续重试的收敛证据。
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
        warnings.append("最终能量不是有限数值，不能作为计算结果。")
    explicit_error = bool(re.search(
        r"ORCA\s+FINISHED\s+BY\s+ERROR\s+TERMINATION|ORCA\s+TERMINATED\s+ABNORMALLY|ERROR\s+TERMINATION",
        upper,
    ))
    banner_count = len(re.findall(r"(?m)^\s*\*\s*O\s+R\s+C\s+A\s*\*\s*$", upper))
    version_count = len(re.findall(r"\bPROGRAM\s+VERSION\s+\d", upper))
    last_normal = upper.rfind("ORCA TERMINATED NORMALLY")
    # 结束标记之后又有计算证据，说明文本可能拼接了尚未完成的后续任务。
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
        warnings.append("检测到多任务或后续计算证据；此解析器不验证多任务输出的完整依赖关系。")
    if explicit_error:
        warnings.append("检测到明确的异常终止证据；不能由先前正常结束标记判定整体成功。")
    needs_optimization = job_type in ("OPT", "OPT_FREQ", "OPT_TS")
    if not normal:
        warnings.append("未发现 ORCA 正常结束标记；文件可能仍在写入或计算已失败。")
    if scf is False:
        warnings.append("最后一条明确 SCF 证据表明未收敛。")
    if needs_optimization and optimization is not True:
        warnings.append("未确认几何优化收敛；正常结束不能替代优化收敛证据。")
    if job_type in PATH_JOBS:
        warnings.append("反应路径任务还需核对过渡态虚频或 IRC 路径终点。")
    if job_type in ("FREQ", "OPT_FREQ"):
        warnings.append("当前解析器未验证频率完整性或虚频；频率任务不能据此判定科学成功。")
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

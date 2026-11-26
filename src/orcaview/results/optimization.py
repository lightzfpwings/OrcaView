"""Geometry-optimization histories from line-addressable ORCA energy observations."""

from dataclasses import dataclass
import re
from typing import Optional, Tuple


@dataclass(frozen=True)
class OptimizationPoint:
    step: Optional[int]  # None is the separate stationary-point evaluation.
    energy: float  # Eh
    line: int
    scf_warning: bool


@dataclass(frozen=True)
class OptimizationRun:
    job: str  # Printed subjob context, or empty for an ordinary output file.
    points: Tuple[OptimizationPoint, ...]


def optimization_runs(report) -> Tuple[OptimizationRun, ...]:
    """Recover source order from the ranked properties in new and saved reports."""
    if report is None:
        return ()
    observations = sorted((p for p in report.properties
                           if p.label == "Final single-point energy" and p.unit == "Eh"),
                          key=lambda p: p.line)
    runs = []
    points = []
    current_job = ""
    for prop in observations:
        parts = prop.context.split(" · ")
        job = next((s for s in parts if re.fullmatch(r"Job \d+", s)), "")
        cycle = next((s for s in parts if re.fullmatch(r"Optimization step \d{1,18}", s)), "")
        if cycle:
            step = int(cycle.split()[-1])
            if points and (job != current_job or points[-1].step is None or step < points[-1].step):
                runs.append(OptimizationRun(current_job, tuple(points)))
                points = []
            elif points and step == points[-1].step:
                # Earlier saved reports can label subsequent single-point results
                # with the last printed cycle. Only its first energy belongs here.
                continue
            current_job = job
        elif "Final optimization energy evaluation" in parts and points and job == current_job:
            # Older reports can carry the final-stage label into a subsequent
            # frequency calculation. Use only the first printed endpoint.
            if points[-1].step is None:
                continue
            step = None
        else:
            continue
        points.append(OptimizationPoint(step, prop.value, prop.line,
                                        "Wavefunction not fully converged" in parts))
    if points:
        runs.append(OptimizationRun(current_job, tuple(points)))
    return tuple(runs)

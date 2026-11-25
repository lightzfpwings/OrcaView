"""Local hardware recommendations for ORCA jobs (memory in MB per process)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from .models import CalculationSpec

TARGET_CORES = CalculationSpec.cores
TARGET_MAXCORE_MB = CalculationSpec.maxcore_mb
_MB = 1024 ** 2


@dataclass(frozen=True)
class ResourceAssessment:
    """Visible logical CPUs and currently available or allocated memory on one node."""

    cpu_limit: Optional[int]
    memory_mb: Optional[int]

    def recommend(self, *, cores: Optional[int] = None,
                  maxcore_mb: Optional[int] = None) -> tuple[int, int]:
        for value in (cores, maxcore_mb):
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError("Resource overrides must be positive integers")
        cpu_target = min(TARGET_CORES, self.cpu_limit or 4)
        memory_target = 1000 if self.memory_mb is None else TARGET_MAXCORE_MB
        budget = None if self.memory_mb is None else self.memory_mb * 3 // 4
        if cores is None:
            cores = cpu_target
            if budget is not None:
                cores = max(1, min(cores, budget // (maxcore_mb or memory_target)))
        if maxcore_mb is None:
            maxcore_mb = memory_target
            if budget is not None:
                maxcore_mb = max(1, min(maxcore_mb, budget // cores))
        return cores, maxcore_mb


def _minimum(*values: Optional[int]) -> Optional[int]:
    return min((value for value in values if value is not None), default=None)


def _number(value: Optional[str], minimum: int = 1) -> Optional[int]:
    try:
        number = int(value) if value else None
    except ValueError:
        return None
    return number if number is not None and number >= minimum else None


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except (OSError, UnicodeError):
        return ""


def _quota_cpus(quota: str, period: str) -> Optional[int]:
    limit, interval = _number(quota), _number(period)
    return max(1, limit // interval) if limit and interval else None


def _cgroup_limits(proc: Path) -> tuple[Optional[int], Optional[int]]:
    groups = {}
    for line in _read(proc / "self/cgroup").splitlines():
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[2].startswith("/"):
            for controller in fields[1].split(","):
                groups[controller] = Path(fields[2])

    cpu = memory = None
    for line in _read(proc / "self/mountinfo").splitlines():
        mount, _, fs = line.partition(" - ")
        fields, info = mount.split(), fs.split()
        if len(fields) < 5 or len(info) < 3 or info[0] not in ("cgroup2", "cgroup"):
            continue
        unified = info[0] == "cgroup2"
        controllers = [""] if unified else info[2].split(",")
        for controller in controllers:
            if controller not in ("", "cpu", "memory") or controller not in groups:
                continue
            # mountinfo escapes spaces, tabs, newlines and backslashes with octal.
            root, mountpoint = (Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), f))
                                for f in fields[3:5])
            group = groups[controller]
            if ".." in group.parts:
                # An unreachable parent in a container still leaves mount limits visible.
                relative = Path(".")
            else:
                try:
                    relative = group.relative_to(root)
                except ValueError:
                    # A private cgroup namespace reports paths relative to its own root.
                    relative = group.relative_to("/")
            current = mountpoint / relative
            while True:
                if unified:
                    pair = _read(current / "cpu.max").split()
                    if len(pair) == 2:
                        cpu = _minimum(cpu, _quota_cpus(*pair))
                elif controller == "cpu":
                    cpu = _minimum(cpu, _quota_cpus(_read(current / "cpu.cfs_quota_us"),
                                                   _read(current / "cpu.cfs_period_us")))
                if unified or controller == "memory":
                    limit_file = "memory.max" if unified else "memory.limit_in_bytes"
                    limit = _number(_read(current / limit_file), minimum=0)
                    # v1 represents an unlimited budget by a page-rounded LONG_MAX.
                    if limit is not None and (unified or limit < 2 ** 60):
                        usage_file = "memory.current" if unified else "memory.usage_in_bytes"
                        usage = _number(_read(current / usage_file), minimum=0)
                        remaining = max(0, limit - (usage or 0)) // _MB
                        memory = _minimum(memory, remaining)
                if current == mountpoint:
                    break
                current = current.parent
    return cpu, memory


def _linux_memory(proc: Path) -> Optional[int]:
    info = _read(proc / "meminfo")
    for name in ("MemAvailable", "MemFree"):
        match = re.search(rf"^{name}:\s+(\d+)\s+kB$", info, re.MULTILINE)
        if match:
            return int(match[1]) // 1024
    return None


def _mac_memory() -> Optional[int]:
    try:
        result = subprocess.run(("/usr/bin/vm_stat",), capture_output=True, text=True,
                                timeout=0.4, check=True, env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    size = re.search(r"page size of (\d+) bytes", result.stdout)
    free = re.search(r"^Pages free:\s+(\d+)", result.stdout, re.MULTILINE)
    inactive = re.search(r"^Pages inactive:\s+(\d+)", result.stdout, re.MULTILINE)
    if size and free:
        return (int(free[1]) + (int(inactive[1]) if inactive else 0)) * int(size[1]) // _MB
    return None


def _windows_limits() -> tuple[Optional[int], Optional[int]]:
    import ctypes
    from ctypes import wintypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD),
                    ("total_phys", ctypes.c_uint64), ("avail_phys", ctypes.c_uint64),
                    ("total_page", ctypes.c_uint64), ("avail_page", ctypes.c_uint64),
                    ("total_virtual", ctypes.c_uint64), ("avail_virtual", ctypes.c_uint64),
                    ("avail_extended", ctypes.c_uint64)]

    cpu = memory = None
    try:
        kernel = ctypes.windll.kernel32
        process_mask, system_mask = ctypes.c_size_t(), ctypes.c_size_t()
        if kernel.GetProcessAffinityMask(wintypes.HANDLE(-1), ctypes.byref(process_mask),
                                         ctypes.byref(system_mask)) and process_mask.value:
            cpu = bin(process_mask.value).count("1")
        status = MemoryStatus(length=ctypes.sizeof(MemoryStatus))
        if kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
            memory = status.avail_phys // _MB
    except (AttributeError, OSError):
        pass
    return cpu, memory


def _per_node(value: str, index: Optional[int]) -> Optional[int]:
    """Read Slurm's count[(xnodes)],... without expanding repetitions."""
    counts = []
    for field in value.split(","):
        match = re.fullmatch(r"(\d+)(?:\(x(\d+)\))?", field.strip())
        if not match:
            return None
        count, repeat = int(match[1]), int(match[2] or 1)
        if index is not None:
            if index < repeat:
                return count or None
            index -= repeat
        counts.append(count)
    return min(counts) or None


def _slurm_limits(env: Mapping[str, str]) -> tuple[Optional[int], Optional[int]]:
    index = _number(env.get("SLURM_NODEID"), minimum=0)
    allocated = _number(env.get("SLURM_CPUS_ON_NODE"))
    if allocated is None:
        allocated = _per_node(env.get("SLURM_JOB_CPUS_PER_NODE", ""), index)
    node_tasks = _per_node(env.get("SLURM_TASKS_PER_NODE", ""), index)
    if node_tasks is None:
        node_tasks = _number(env.get("SLURM_NTASKS_PER_NODE"))
    nodes = _number(env.get("SLURM_JOB_NUM_NODES") or env.get("SLURM_NNODES"))
    if node_tasks is None and (nodes == 1 or env.get("SLURM_NTASKS") == "1"):
        node_tasks = _number(env.get("SLURM_NTASKS"))
    per_task = _number(env.get("SLURM_CPUS_PER_TASK"))
    if node_tasks is not None:
        allocated = _minimum(allocated, node_tasks * (per_task or 1))
    elif allocated is None:
        allocated = per_task
    memory = _number(env.get("SLURM_MEM_PER_NODE"))
    per_cpu = _number(env.get("SLURM_MEM_PER_CPU"))
    if per_cpu:
        memory = _minimum(memory, per_cpu * (allocated or 1))
    return allocated, memory


def detect_resources() -> ResourceAssessment:
    """Read a snapshot of local limits without starting ORCA or a benchmark."""
    try:
        cpu = os.cpu_count()
    except (OSError, NotImplementedError):
        cpu = None
    try:
        cpu = _minimum(cpu, len(os.sched_getaffinity(0)) or None)
    except (AttributeError, OSError, NotImplementedError):
        pass
    memory = None
    if sys.platform.startswith("linux"):
        proc = Path("/proc")
        cg_cpu, cg_memory = _cgroup_limits(proc)
        cpu = _minimum(cpu, cg_cpu)
        memory = _minimum(_linux_memory(proc), cg_memory)
    elif sys.platform == "darwin":
        memory = _mac_memory()
    elif sys.platform == "win32":
        win_cpu, memory = _windows_limits()
        cpu = _minimum(cpu, win_cpu)
    job_cpu, job_memory = _slurm_limits(os.environ)
    return ResourceAssessment(_minimum(cpu, job_cpu), _minimum(memory, job_memory))

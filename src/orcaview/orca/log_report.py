"""File-level ORCA observations, kept separate from frame-bound datasets."""

from dataclasses import dataclass, replace
import re
from typing import Tuple

from orcaview.core._validation import finite_number, integer, nonempty
from orcaview.core.provenance import ArtifactRef
from .log_properties import LogProperty, parse_log_properties, ranked_properties
from .log_spectra import SpectrumTable, parse_log_spectra


@dataclass(frozen=True)
class LogReport:
    source: ArtifactRef
    properties: Tuple[LogProperty, ...]
    spectra: Tuple[SpectrumTable, ...]
    status: str

    def __post_init__(self):
        if not isinstance(self.source, ArtifactRef) or self.source.format != "orca-out" or not self.source.sha256:
            raise ValueError("日志报告需要有摘要的 ORCA 来源文件")
        nonempty(self.status, "日志状态")
        for prop in self.properties:
            for label in (prop.group, prop.label):
                nonempty(label, "计算结果标签")
            finite_number(prop.value, "计算结果")
            integer(prop.line, "来源行号", 1)
            if not isinstance(prop.context, str) or not isinstance(prop.unit, str):
                raise ValueError("计算结果上下文和单位应为文字")
        for table in self.spectra:
            integer(table.source_line, "光谱来源行号", 1)
            for label in (table.kind, table.title, *table.columns):
                nonempty(label, "光谱标签")
            if not table.columns or not table.rows:
                raise ValueError("光谱需要列标题与数据")
            for row in table.rows:
                if len(row) != len(table.columns):
                    raise ValueError("光谱行与表头列数不一致")
                for cell in row:
                    if cell is not None and not isinstance(cell, str):
                        finite_number(cell, "光谱数据")


_SUBJOB = re.compile(r"\s*\**\s*(?:COMPOUND JOB|JOB (?:NUMBER|NO\.))\s*[:#]?\s*(\d+)\s*\**\s*", re.I)


def job_sections(lines):
    """Partition printed subjobs without treating ORCA's lists of contributors as headers."""
    starts = [0]
    seen_version = False
    seen_banner = False
    for index, line in enumerate(lines):
        if _SUBJOB.fullmatch(line):
            starts.append(index)
        elif re.fullmatch(r"\s*\*\s*O\s+R\s+C\s+A\s*\*\s*", line, re.I):
            if seen_banner or seen_version:
                starts.append(index)
                seen_version = False
            seen_banner = True
        elif re.match(r"\s*Program Version\s+\d", line, re.I):
            if seen_version:
                starts.append(index)
            seen_version = True
    return tuple((start, end) for start, end in zip(starts, [*starts[1:], len(lines)]) if start < end)


def parse_log_report(lines, artifact):
    # Preserve source row numbers while dropping echoed input and its comments.
    if isinstance(lines, str):
        lines = lines.splitlines()
    lines = ["" if re.match(r"\s*\|\s*\d+>", line) else line for line in lines]
    sections = job_sections(lines)
    properties, tables = [], []
    for n, (start, end) in enumerate(sections, 1):
        section = lines[start:end]
        props = parse_log_properties(section)
        spectra = parse_log_spectra(section)
        printed = _SUBJOB.fullmatch(lines[start])
        step = f"作业 {printed[1] if printed else n}" if len(sections) > 1 else ""
        properties.extend(replace(p, line=p.line + start, context=" · ".join(filter(None, (step, p.context))))
                          for p in props)
        tables.extend(replace(t, source_line=t.source_line + start, title=" · ".join(filter(None, (step, t.title))))
                      for t in spectra)
    normal = re.compile(r"\s*\**\s*ORCA TERMINATED NORMALLY\s*\**\s*", re.I)
    failure = re.compile(r"\s*\**\s*ORCA (?:finished by error termination|terminated abnormally)\b", re.I)
    final_start = sections[-1][0] if sections else 0
    normal_lines = [i for i in range(final_start, len(lines)) if normal.fullmatch(lines[i])]
    last_data_line = max([p.line for p in properties] + [t.source_line for t in tables], default=0)
    if any(failure.match(line) for line in lines):
        status = "记录了异常终止"
    elif normal_lines and normal_lines[-1] + 1 >= last_data_line:
        status = "正常终止"
    else:
        status = "未记录正常终止"
    if len(sections) > 1:
        status += " · 多作业日志"
    return LogReport(artifact, ranked_properties(properties), tuple(tables), status)

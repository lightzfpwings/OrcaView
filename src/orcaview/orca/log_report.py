"""File-level ORCA observations, kept separate from frame-bound datasets."""

from dataclasses import dataclass, replace
import re
from typing import Tuple

from orcaview.core._validation import finite_number, integer, nonempty
from orcaview.core.provenance import ArtifactRef
from .log_properties import LogProperty, parse_log_properties, ranked_properties
from .log_spectra import SpectrumTable, parse_log_spectra
from .normal_modes import NormalModeGroup, parse_normal_modes


@dataclass(frozen=True)
class LogReport:
    source: ArtifactRef
    properties: Tuple[LogProperty, ...]
    spectra: Tuple[SpectrumTable, ...]
    status: str
    normal_modes: Tuple[NormalModeGroup, ...] = ()

    def __post_init__(self):
        if not isinstance(self.source, ArtifactRef) or self.source.format != "orca-out" or not self.source.sha256:
            raise ValueError("A log report requires an ORCA source file with a digest")
        nonempty(self.status, "Log status")
        if any(not isinstance(group, NormalModeGroup) for group in self.normal_modes):
            raise ValueError("Invalid normal mode group in log report")
        for prop in self.properties:
            for label in (prop.group, prop.label):
                nonempty(label, "Result label")
            finite_number(prop.value, "Calculation results")
            integer(prop.line, "Source line number", 1)
            if not isinstance(prop.context, str) or not isinstance(prop.unit, str):
                raise ValueError("Result context and unit must be text")
        for table in self.spectra:
            integer(table.source_line, "Spectrum source line", 1)
            for label in (table.kind, table.title, *table.columns):
                nonempty(label, "Spectrum label")
            if not table.columns or not table.rows:
                raise ValueError("A spectrum requires column headings and data")
            for row in table.rows:
                if len(row) != len(table.columns):
                    raise ValueError("Spectrum row does not match the header column count")
                for cell in row:
                    if cell is not None and not isinstance(cell, str):
                        finite_number(cell, "Spectral data")


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
    properties, tables, normal_modes = [], [], []
    for n, (start, end) in enumerate(sections, 1):
        section = lines[start:end]
        props = parse_log_properties(section)
        spectra = parse_log_spectra(section)
        printed = _SUBJOB.fullmatch(lines[start])
        step = f"Job {(printed[1] if printed else n)}" if len(sections) > 1 else ""
        normal_modes.extend(parse_normal_modes(section, start, step))
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
        status = "Abnormal termination recorded"
    elif normal_lines and normal_lines[-1] + 1 >= last_data_line:
        status = "Normal termination"
    else:
        status = "Normal termination not recorded"
    if len(sections) > 1:
        status += " · multiple-job log"
    return LogReport(artifact, ranked_properties(properties), tuple(tables), status, tuple(normal_modes))

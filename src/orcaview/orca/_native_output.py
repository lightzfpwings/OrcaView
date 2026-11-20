"""Collect line-level evidence for the narrow ORCA 6.1 single-point import."""

from dataclasses import dataclass
from math import fsum, isclose, isfinite
import re
from typing import Optional, Tuple

from ..core._validation import Versioned
from ..core.elements import ATOMIC_NUMBERS
from ..core.models import Atom, Molecule
from ..core.units import BOHR_IN_ANGSTROM


_NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[EeDd][+-]?[0-9]+)?"
_INT = r"[+-]?[0-9]{1,18}"
_ELEMENT = r"[A-Z][a-z]?"
_DASHES = re.compile(r"-{3,}")
_XYZ_ROW = re.compile(rf"({_ELEMENT})\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})")
_AU_ROW = re.compile(
    rf"([0-9]{{1,18}})\s+({_ELEMENT})\s+({_NUMBER})\s+[0-9]+\s+{_NUMBER}"
    rf"\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})"
)
_MULLIKEN_ROW = re.compile(rf"([0-9]{{1,18}})\s+({_ELEMENT})\s*:\s*({_NUMBER})")
_MULLIKEN_SUM = re.compile(rf"SUM OF ATOMIC CHARGES\s*:\s*({_NUMBER})", re.I)
_ECHO = r"\|\s*[0-9]+>\s*(.*)"
_ECHO_STATE = re.compile(rf"\*\s*XYZ(FILE)?\s+({_INT})\s+({_INT})(?:\s+(.+))?", re.I)
_ECHO_RUN_TYPE = re.compile(r"(?:%METHOD\s+)?RUNTYP(?:\s*=\s*|\s+)([A-Z][A-Z0-9_-]*)\b", re.I)
_ECHO_TASK_BLOCK = re.compile(r"%(?:COMPOUND|MD|NEB)\b", re.I)
_TOTAL_RUN_TIME = re.compile(
    r"TOTAL RUN TIME:\s+[0-9]+ days?\s+[0-9]+ hours?\s+[0-9]+ minutes?\s+[0-9]+ seconds?\s+[0-9]+ msec",
    re.I,
)
_OTHER_TASK_KEYS = frozenset(
    "OPT NORMALOPT TIGHTOPT LOOSEOPT VERYTIGHTOPT COPT L-OPT OPTTS SCAN IRC NEB NEB-TS NEB-CI MD DOCKER "
    "FREQ ANFREQ NUMFREQ ENGRAD NUMGRAD NUMNACME NUM-NACME".split()
)


@dataclass(frozen=True)
class OutputIssue(Versioned):
    code: str
    message: str
    line: Optional[int] = None


@dataclass(frozen=True)
class NativeOutputEvidence(Versioned):
    program_version: Optional[str]
    atoms: Tuple[Atom, ...]
    charge: Optional[int]
    multiplicity: Optional[int]
    energy_hartree: Optional[float]
    normal_termination: Optional[bool]
    scf_converged: Optional[bool]
    optimization_converged: Optional[bool]
    issues: Tuple[OutputIssue, ...]
    version_line: Optional[int]
    geometry_line: Optional[int]
    charge_line: Optional[int]
    multiplicity_line: Optional[int]
    energy_line: Optional[int]
    termination_line: Optional[int]
    scf_line: Optional[int]
    optimization_line: Optional[int]
    mulliken_charges: Optional[Tuple[float, ...]]
    mulliken_line: Optional[int]
    mulliken_missing_reason: Optional[str]
    mulliken_issue: Optional[OutputIssue]

    @property
    def importable(self) -> bool:
        return not self.issues


def _matches(lines, pattern):
    expression = re.compile(pattern, re.I)
    for line_number, line in enumerate(lines, start=1):
        match = expression.fullmatch(line)
        if match:
            yield line_number, match


def _line_numbers(lines, pattern):
    return [line_number for line_number, _ in _matches(lines, pattern)]


def _finite(token):
    value = float(token.replace("D", "E").replace("d", "e"))
    if not isfinite(value):
        raise ValueError("数值超出有限浮点范围")
    return value


def _table(lines, heading):
    """Read a dashed ORCA table as indexed, contiguous source rows."""
    if heading >= len(lines) or not _DASHES.fullmatch(lines[heading]):
        raise ValueError("数据表缺少标题分隔线")
    for index in range(heading + 1, len(lines)):
        line = lines[index]
        if not line or _DASHES.fullmatch(line):
            break
        yield index + 1, line


def _geometry(lines, angstrom, bohr, atom_counts, scf_line):
    if len(angstrom) != 1:
        if angstrom:
            return (), angstrom[0], OutputIssue("ambiguous_geometry", "存在多个 Å 坐标表。", angstrom[1])
        return (), None, OutputIssue("missing_geometry", "未找到实际 Å 笛卡尔坐标表。")
    heading = angstrom[0]
    atoms = []
    row_number = heading
    try:
        for row_number, row in _table(lines, heading):
            match = _XYZ_ROW.fullmatch(row)
            if not match or match[1] not in ATOMIC_NUMBERS:
                raise ValueError("Å 坐标表含有未知元素或不符合格式的坐标行")
            atoms.append(Atom(match[1], *(_finite(value) for value in match.groups()[1:])))
        if not atoms:
            raise ValueError("Å 坐标表为空")
    except ValueError as error:
        return (), heading, OutputIssue("invalid_geometry", str(error), row_number)
    if any(count != len(atoms) for _, count in atom_counts):
        count_line = next(line for line, count in atom_counts if count != len(atoms))
        return (), heading, OutputIssue("conflicting_geometry", "实际坐标与输出中的原子总数不一致。", count_line)
    if bohr:
        conflict = _crosscheck_bohr(lines, heading, bohr, atoms, scf_line)
        if conflict is not None:
            return (), heading, conflict
    elif not any(heading < line and (scf_line is None or line < scf_line) for line, _ in atom_counts):
        return tuple(atoms), heading, OutputIssue(
            "missing_atom_count", "缺少可核对 Å 坐标表完整性的 Bohr 坐标或计算前原子总数。", heading,
        )
    return tuple(atoms), heading, None


def _crosscheck_bohr(lines, heading, bohr, atoms, scf_line):
    row_number = bohr[0]
    try:
        if len(bohr) != 1 or row_number <= heading or (scf_line is not None and row_number >= scf_line):
            raise ValueError
        rows = iter(_table(lines, row_number))
        _, columns = next(rows, (0, ""))
        if columns.upper().split() != ["NO", "LB", "ZA", "FRAG", "MASS", "X", "Y", "Z"]:
            raise ValueError
        atom_count = 0
        for index, (row_number, row) in enumerate(rows):
            match = _AU_ROW.fullmatch(row)
            if not match or index >= len(atoms):
                raise ValueError
            atom = atoms[index]
            if int(match[1]) != index or match[2] != atom.element or _finite(match[3]) != ATOMIC_NUMBERS[atom.element]:
                raise ValueError
            converted = (_finite(value) * BOHR_IN_ANGSTROM for value in match.groups()[3:])
            # ORCA's two coordinate tables each round independently to six decimal places.
            if not all(isclose(ang, au, rel_tol=0.0, abs_tol=1e-6)
                       for ang, au in zip((atom.x, atom.y, atom.z), converted)):
                raise ValueError
            atom_count += 1
        if atom_count != len(atoms):
            raise ValueError
    except ValueError:
        return OutputIssue(
            "conflicting_geometry", "Bohr 坐标表格式、原子身份或单位换算与 Å 坐标表不一致。", row_number,
        )
    return None


def _electronic_state(lines, echoed_lines, geometry_line, scf_line, atoms):
    charges = [(line, match[1]) for line, match in _matches(lines, r"TOTAL CHARGE\s+CHARGE\s*\.{3,}\s*(.*)")]
    multiplicities = [(line, match[1]) for line, match in _matches(lines, r"MULTIPLICITY\s+MULT\s*\.{3,}\s*(.*)")]
    echo_states = []
    for line, echoed in echoed_lines:
        match = _ECHO_STATE.fullmatch(echoed)
        if match and (bool(match[1]) == bool(match[4])):
            echo_states.append(line)
            charges.append((line, match[2]))
            multiplicities.append((line, match[3]))
    charge_line = charges[0][0] if charges else None
    multiplicity_line = multiplicities[0][0] if multiplicities else None
    charge = multiplicity = None
    try:
        if len(echo_states) > 1 or (geometry_line is not None and any(line >= geometry_line for line in echo_states)):
            raise ValueError("回显包含多个几何输入或位于实际几何表之后。")
        for entries in (charges, multiplicities):
            if any(not re.fullmatch(_INT, value) for _, value in entries):
                raise ValueError("总电荷和多重度必须为明确的整数。")
            if len({int(value) for _, value in entries}) > 1:
                raise ValueError("输出与回显输入的总电荷或多重度证据不一致。")
            if scf_line is not None and any(line >= scf_line for line, _ in entries):
                raise ValueError("电子态证据出现在 SCF 证据之后。")
        if charge_line is not None:
            charge = int(charges[0][1])
        if multiplicity_line is not None:
            multiplicity = int(multiplicities[0][1])
        if charge is None or multiplicity is None:
            return charge, multiplicity, charge_line, multiplicity_line, OutputIssue(
                "missing_electronic_state", "缺少有明确证据的总电荷或自旋多重度。", geometry_line,
            )
        if multiplicity < 1:
            raise ValueError("自旋多重度必须为正整数。")
        if atoms:
            Molecule("ORCA output", atoms, charge=charge, multiplicity=multiplicity).validate()
    except ValueError as error:
        return None, None, charge_line, multiplicity_line, OutputIssue(
            "conflicting_electronic_state", str(error), charge_line or multiplicity_line,
        )
    return charge, multiplicity, charge_line, multiplicity_line, None


def _energy(lines):
    entries = list(_matches(lines, r"FINAL\s+SINGLE\s+POINT\s+ENERGY\b\s*(.*)"))
    if not entries:
        return None, None, OutputIssue("missing_energy", "未找到最终单点能。")
    heading, match = entries[0]
    if len(entries) > 1:
        return None, heading, OutputIssue("ambiguous_energy", "存在多个最终单点能条目。", entries[1][0])
    value = re.fullmatch(rf"({_NUMBER})(?:\s+(?:EH|HARTREE))?", match[1], re.I)
    try:
        if value is None:
            raise ValueError
        return _finite(value[1]), heading, None
    except ValueError:
        return None, heading, OutputIssue("invalid_energy", "最终单点能不是有限的 Hartree 数值。", heading)


def _mulliken(lines, atoms, charge, scf_line, normal_line):
    headings = list(_matches(lines, r"MULLIKEN ATOMIC CHARGES\b(.*)"))
    if not headings:
        return None, None, "输出中没有 Mulliken 原子电荷表。", None
    heading, match = headings[0]
    row_number = heading
    try:
        if len(headings) > 1 or match[1]:
            raise ValueError("Mulliken 表不唯一或标题超出当前支持的电荷表格式。")
        if not (scf_line is not None and normal_line is not None and scf_line < heading < normal_line):
            raise ValueError("Mulliken 电荷表不在已核对的计算区间内。")
        values = []
        printed_total = None
        for row_number, row in _table(lines, heading):
            total = _MULLIKEN_SUM.fullmatch(row)
            if total and row_number < normal_line:
                printed_total = _finite(total[1])
                break
            entry = _MULLIKEN_ROW.fullmatch(row)
            index = len(values)
            if (
                not entry or index >= len(atoms) or int(entry[1]) != index
                or entry[2] != atoms[index].element or row_number >= normal_line
            ):
                raise ValueError("Mulliken 电荷表的单位、行格式或有序原子身份不匹配。")
            values.append(_finite(entry[3]))
        if not values or len(values) != len(atoms):
            raise ValueError("Mulliken 电荷表的原子数量不匹配。")
        # Printed per-atom values have six decimal places, and the printed total has seven.
        if printed_total is not None:
            if charge is not None and not isclose(printed_total, charge, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError("Mulliken 表中的总电荷与计算电子态不一致。")
            if not isclose(fsum(values), printed_total, rel_tol=0.0, abs_tol=len(values) * 0.5e-6 + 1e-7):
                raise ValueError("Mulliken 表逐原子数值之和与输出的总电荷不一致。")
    except (ValueError, OverflowError) as error:
        reason = str(error)
        return None, heading, reason, OutputIssue("invalid_mulliken", reason, row_number)
    return tuple(values), heading, None, None


def _echo_has_other_task(echo):
    run_type = _ECHO_RUN_TYPE.match(echo)
    if run_type:
        return run_type[1].upper() not in ("ENERGY", "SP")
    if echo.startswith("!"):
        return bool(_OTHER_TASK_KEYS.intersection(echo[1:].upper().split()))
    return bool(_ECHO_TASK_BLOCK.match(echo))


def parse_native_output(text: str) -> NativeOutputEvidence:
    """Identify an unambiguous, converged single-job ORCA 6.1.x energy and frame."""
    lines = tuple(line.strip() for line in text.split("\n"))
    banners = _line_numbers(lines, r"\*\s*O\s+R\s+C\s+A\s*\*")
    versions = list(_matches(lines, r"PROGRAM\s+VERSION\s+(\S+)(?:\s+.*)?"))
    normal_lines = _line_numbers(lines, r"\**\s*ORCA\s+TERMINATED\s+NORMALLY\s*\**")
    abnormal_lines = _line_numbers(
        lines, r"\**\s*ORCA\s+(?:FINISHED\s+BY\s+ERROR\s+TERMINATION|TERMINATED\s+ABNORMALLY)(?:\s+.*|\**)",
    )
    single_point = _line_numbers(lines, r"\**\s*SINGLE\s+POINT\s+CALCULATION\s*\**")
    angstrom = _line_numbers(lines, r"CARTESIAN COORDINATES\s+\(ANGSTROEM\)")
    bohr = _line_numbers(lines, r"CARTESIAN COORDINATES\s+\(A\.U\.\)")
    length_headers = _line_numbers(lines, r"CARTESIAN COORDINATES\s+\(.*\)")
    unsupported_units = sorted(set(length_headers) - set(angstrom) - set(bohr))
    atom_counts = [(line, int(match[1])) for line, match in _matches(
        lines, r"NUMBER OF ATOMS\s*\.{3,}\s*([0-9]{1,18})",
    )]
    echoes = [(line, match[1].split("#", 1)[0].strip()) for line, match in _matches(lines, _ECHO)]
    echoed_other_tasks = [line for line, echo in echoes if _echo_has_other_task(echo)]
    job_directives = _line_numbers(lines, r"\**\s*(?:COMPOUND JOB\b.*|\$\s*NEW_JOB\b.*)")
    job_directives += [line for line, echo in echoes if re.match(r"\$\s*NEW_JOB\b|%COMPOUND\b", echo, re.I)]
    other_tasks = _line_numbers(
        lines, r"\**\s*(?:GEOMETRY OPTIMIZATION\b.*|VIBRATIONAL FREQUENCIES\b.*|"
        r"(?:ANALYTICAL|NUMERICAL) FREQUENCY\b.*|RELAXED SURFACE SCAN\b.*|"
        r"MOLECULAR DYNAMICS\b.*|IRC CALCULATION\b.*|NEB CALCULATION\b.*)",
    ) + echoed_other_tasks
    scf_events = sorted(
        [(line, True) for line in _line_numbers(lines, r"\**\s*SCF CONVERGED AFTER\s+[0-9]+\s+CYCLES?\s*\**")]
        + [(line, False) for line in _line_numbers(
            lines, r"\**\s*SCF (?:NOT CONVERGED|DID NOT CONVERGE)(?:\s+AFTER\s+[0-9]+\s+CYCLES?)?[.!]?\s*\**",
        )],
    )
    optimization_events = sorted(
        [(line, True) for line in _line_numbers(lines, r"\**\s*THE OPTIMIZATION HAS CONVERGED[.!]?\s*\**")]
        + [(line, False) for line in _line_numbers(
            lines, r"\**\s*(?:THE OPTIMIZATION HAS NOT CONVERGED|(?:THE )?OPTIMIZATION DID NOT CONVERGE"
            r"(?: BUT REACHED THE MAXIMUM NUMBER OF)?|MAXIMUM NUMBER OF OPTIMIZATION CYCLES REACHED)[.!]?\s*\**",
        )],
    )

    version_line, program_version = (versions[0][0], versions[0][1][1]) if versions else (None, None)
    scf_line, scf = scf_events[-1] if scf_events else (None, None)
    optimization_line, optimization = optimization_events[-1] if optimization_events else (None, None)
    normal_line = next(iter(normal_lines), None)
    normal = False if abnormal_lines else True if normal_line is not None else None
    termination_line = abnormal_lines[0] if abnormal_lines else normal_line
    atoms, geometry_line, geometry_issue = _geometry(lines, angstrom, bohr, atom_counts, scf_line)
    charge, multiplicity, charge_line, mult_line, state_issue = _electronic_state(
        lines, echoes, geometry_line, scf_line, atoms,
    )
    energy, energy_line, energy_issue = _energy(lines)
    mulliken, mulliken_line, mulliken_reason, mulliken_issue = _mulliken(lines, atoms, charge, scf_line, normal_line)

    issues = [issue for issue in (geometry_issue, state_issue, energy_issue) if issue is not None]
    if program_version is None:
        issues.append(OutputIssue("missing_version", "缺少 ORCA 版本横幅。"))
    elif not re.fullmatch(r"6\.1(?:\.[0-9]+)?", program_version):
        issues.append(OutputIssue("unsupported_version", "当前适配仅支持 ORCA 6.1 系列。", version_line))
    repeated = [group[1] for group in (banners, [line for line, _ in versions], normal_lines, single_point)
                if len(group) > 1]
    if repeated or job_directives or (normal_lines and abnormal_lines):
        repeated.extend(job_directives)
        repeated.extend(abnormal_lines if normal_lines else ())
        issues.append(OutputIssue("multiple_jobs", "存在多个任务或拼接输出的证据。", min(repeated)))
    if optimization_line is not None:
        other_tasks.append(optimization_line)
    if not single_point or other_tasks:
        issues.append(OutputIssue("unsupported_task", "未能确认这是唯一的单点任务。", min(other_tasks, default=None)))
    if unsupported_units or (bohr and not angstrom):
        issues.append(OutputIssue("unsupported_geometry_unit", "几何发布需要明确的 Å 坐标及一致的单位证据。",
                                  (unsupported_units or bohr)[0]))
    if scf is None:
        issues.append(OutputIssue("missing_scf_convergence", "未找到明确的 SCF 收敛证据。"))
    elif scf is False:
        issues.append(OutputIssue("scf_unconverged", "SCF 明确未收敛。", scf_line))
    if len(scf_events) > 1:
        issues.append(OutputIssue("ambiguous_scf", "检测到多个 SCF 完成标记。", scf_events[1][0]))
    if normal is None:
        issues.append(OutputIssue("incomplete_output", "未找到 ORCA 正常结束标记。"))
    elif normal is False:
        issues.append(OutputIssue("abnormal_termination", "输出包含异常结束标记。", termination_line))
    expected_order = (
        version_line, next(iter(single_point), None), geometry_line, scf_line, energy_line, termination_line,
    )
    observed = [line for line in expected_order if line is not None]
    if observed != sorted(set(observed)):
        issues.append(OutputIssue("inconsistent_evidence", "单点任务的版本、几何、SCF、能量或结束证据顺序冲突。"))
    if normal is True and len(normal_lines) == 1:
        trailing = [(number, line) for number, line in enumerate(lines[termination_line:], termination_line + 1) if line]
        if trailing and (len(trailing) != 1 or not _TOTAL_RUN_TIME.fullmatch(trailing[0][1])):
            extra_line = next((number for number, line in trailing if not _TOTAL_RUN_TIME.fullmatch(line)), trailing[0][0])
            issues.append(OutputIssue("multiple_jobs", "正常结束标记之后有无法归入本次计算的文本。", extra_line))

    return NativeOutputEvidence(
        program_version=program_version, atoms=atoms, charge=charge, multiplicity=multiplicity,
        energy_hartree=energy, normal_termination=normal, scf_converged=scf,
        optimization_converged=optimization, issues=tuple(issues), version_line=version_line,
        geometry_line=geometry_line, charge_line=charge_line, multiplicity_line=mult_line,
        energy_line=energy_line, termination_line=termination_line, scf_line=scf_line,
        optimization_line=optimization_line, mulliken_charges=mulliken, mulliken_line=mulliken_line,
        mulliken_missing_reason=mulliken_reason, mulliken_issue=mulliken_issue,
    )


def reported_geometry(text):
    """Read one explicit structure for a report, including a converged optimisation's final evaluation."""
    lines = tuple(line.strip() for line in text.splitlines())
    headings = _line_numbers(lines, r"CARTESIAN COORDINATES\s+\(ANGSTROEM\)")
    stationary = _line_numbers(lines, r"\*+\s*FINAL ENERGY EVALUATION AT THE STATIONARY POINT\s*\*+")
    if len(headings) == 1:
        heading = headings[0]
    elif stationary:
        heading = next((line for line in headings if line > stationary[-1]), None)
    else:
        return None
    if heading is None:
        return None
    end = next((line for line in headings if line > heading), len(lines) + 1)
    bohr = [n for n in _line_numbers(lines, r"CARTESIAN COORDINATES\s+\(A\.U\.\)") if heading < n < end]
    counts = [(n, int(m[1])) for n, m in _matches(lines, r"NUMBER OF ATOMS\s*\.{3,}\s*([0-9]{1,18})")]
    atoms, _, issue = _geometry(lines, [heading], bohr, counts, None)
    if issue:
        return None
    echoes = [(n, m[1].split("#", 1)[0].strip()) for n, m in _matches(lines, _ECHO)]
    charge, mult, _, _, issue = _electronic_state(lines, echoes, None, None, atoms)
    return None if issue else (atoms, charge, mult, heading)


def _hirshfeld_table(lines, start, end, atoms):
    """Read the atom charges and spins printed by ORCA's grid integration."""
    i = start + 1
    while i < end and (not lines[i] or _DASHES.fullmatch(lines[i])
                       or re.fullmatch(r"Total integrated (?:alpha|beta) density\s*=\s*" + _NUMBER, lines[i], re.I)):
        i += 1
    if i == end or lines[i].upper().split() != ["ATOM", "CHARGE", "SPIN"]:
        return None
    charges, spins = [], []
    for index, atom in enumerate(atoms):
        i += 1
        fields = lines[i].split() if i < end else ()
        if len(fields) != 4 or fields[:2] != [str(index), atom.element]:
            return None
        charges.append(_finite(fields[2]))
        spins.append(_finite(fields[3]))
    i += 1
    while i < end and not lines[i]:
        i += 1
    fields = lines[i].split() if i < end else ()
    if len(fields) != 3 or fields[0].upper() != "TOTAL":
        return None
    # Compare to the printed totals: integration residuals need not vanish.
    tolerance = (len(atoms) + 1) * 0.5e-6 + 1e-9
    if not all(isclose(fsum(values), _finite(total), abs_tol=tolerance, rel_tol=0)
               for values, total in zip((charges, spins), fields[1:])):
        return None
    return tuple(charges), tuple(spins)


def population_tables(lines, geometry_line, molecule):
    """Read ordered, charge-balanced population tables printed for this coordinate block."""
    lines = tuple(line.strip() for line in lines)
    end = next((i for i in range(geometry_line, len(lines))
                if lines[i].upper() == "CARTESIAN COORDINATES (ANGSTROEM)"), len(lines))
    population_row = re.compile(rf"([0-9]+)\s+({_ELEMENT})\s*:\s*({_NUMBER})(?:\s+({_NUMBER}))?")
    for i in range(geometry_line, end):
        if lines[i].upper() == "HIRSHFELD ANALYSIS":
            try:
                result = _hirshfeld_table(lines, i, end, molecule.atoms)
            except (ValueError, OverflowError):
                result = None
            if result is not None:
                yield "Hirshfeld", i + 1, *result
            continue
        title = re.fullmatch(r"(MULLIKEN|LOEWDIN) ATOMIC CHARGES( AND SPIN POPULATIONS)?", lines[i], re.I)
        if not title:
            continue
        values, spins = [], []
        try:
            for _, row in _table(lines, i + 1):
                if _MULLIKEN_SUM.fullmatch(row) or row.lower().startswith("sum of atomic charges"):
                    break
                m = population_row.fullmatch(row)
                idx = len(values)
                if (not m or idx >= len(molecule.atoms) or int(m[1]) != idx
                        or m[2] != molecule.atoms[idx].element or bool(m[4]) != bool(title[2])):
                    raise ValueError("布居表中的原子身份或行格式不匹配")
                values.append(_finite(m[3]))
                if m[4]:
                    spins.append(_finite(m[4]))
            else:
                row = ""
            total = _MULLIKEN_SUM.fullmatch(row)
            if total and not isclose(_finite(total[1]), molecule.charge, rel_tol=0, abs_tol=1e-6):
                continue
            if (len(values) != len(molecule.atoms) or
                    not isclose(fsum(values), molecule.charge, rel_tol=0, abs_tol=len(values)*0.5e-6 + 1e-6)):
                continue
        except (ValueError, OverflowError):
            continue
        method = "Mulliken" if title[1].upper() == "MULLIKEN" else "Löwdin"
        yield method, i + 1, tuple(values), tuple(spins)

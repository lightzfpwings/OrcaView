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
_COORDINATE_HEADING = re.compile(
    r"CARTESIAN COORDINATES\s+\((?:(?P<angstrom>ANGSTROEM)|(?P<bohr>A\.U\.)|(?P<unsupported>.*))\)", re.I,
)
_XYZ_ROW = re.compile(rf"({_ELEMENT})\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})")
_AU_ROW = re.compile(
    rf"([0-9]{{1,18}})\s+({_ELEMENT})\s+({_NUMBER})(\*?)\s+[0-9]+\s+{_NUMBER}"
    rf"\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})"
)
_POPULATION_ROW = re.compile(rf"([0-9]{{1,18}})\s+({_ELEMENT})\s*:\s*({_NUMBER})(?:\s+({_NUMBER}))?")
_MULLIKEN_SUM = re.compile(rf"SUM OF ATOMIC CHARGES\s*:\s*({_NUMBER})", re.I)
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


def _coordinate_headings(lines):
    by_unit = {"angstrom": [], "bohr": [], "unsupported": []}
    for number, line in enumerate(lines, 1):
        match = _COORDINATE_HEADING.fullmatch(line)
        if match:
            by_unit[match.lastgroup].append(number)
    return by_unit["angstrom"], by_unit["bohr"], by_unit["unsupported"]


def _input_echo(lines):
    return [(line, match[1].partition("#")[0].strip())
            for line, match in _matches(lines, r"\|\s*[0-9]+>\s*(.*)")]


def _finite(token):
    value = float(token.replace("D", "E").replace("d", "e"))
    if not isfinite(value):
        raise ValueError("The number is outside the finite floating-point range")
    return value


def _table(lines, heading):
    """Read a dashed ORCA table as indexed, contiguous source rows."""
    if heading >= len(lines) or not _DASHES.fullmatch(lines[heading]):
        raise ValueError("The table is missing its header separator")
    for index in range(heading + 1, len(lines)):
        line = lines[index]
        if not line or _DASHES.fullmatch(line):
            break
        yield index + 1, line


def _geometry(lines, angstrom, bohr, scf_line):
    if len(angstrom) != 1:
        if angstrom:
            return (), angstrom[0], OutputIssue("ambiguous_geometry", "Multiple coordinate tables in angstroms were found.", angstrom[1])
        return (), None, OutputIssue("missing_geometry", "No actual Cartesian coordinate table in angstroms was found.")
    heading = angstrom[0]
    atoms = []
    row_number = heading
    try:
        for row_number, row in _table(lines, heading):
            match = _XYZ_ROW.fullmatch(row)
            if not match or match[1] not in ATOMIC_NUMBERS:
                raise ValueError("The coordinate table in angstroms has an unknown element or malformed row")
            atoms.append(Atom(match[1], *(_finite(value) for value in match.groups()[1:])))
        if not atoms:
            raise ValueError("The coordinate table in angstroms is empty")
    except ValueError as error:
        return (), heading, OutputIssue("invalid_geometry", str(error), row_number)
    count_before_scf = False
    for line, match in _matches(lines, r"NUMBER OF ATOMS\s*\.{3,}\s*([0-9]{1,18})"):
        if int(match[1]) != len(atoms):
            return (), heading, OutputIssue("conflicting_geometry", "The actual coordinates do not match the reported atom count.", line)
        if heading < line and (scf_line is None or line < scf_line):
            count_before_scf = True
    if bohr:
        conflict = _crosscheck_bohr(lines, heading, bohr, atoms, scf_line)
        if conflict is not None:
            return (), heading, conflict
    elif not count_before_scf:
        return tuple(atoms), heading, OutputIssue(
            "missing_atom_count", "Missing Bohr coordinates or precalculation atom count to verify the coordinate table in angstroms.", heading,
        )
    return tuple(atoms), heading, None


def bohr_nuclear_charges(lines, heading, atoms):
    """Read ZA only from a Bohr table that corroborates the selected geometry."""
    rows = iter(_table(lines, heading))
    _, columns = next(rows, (0, ""))
    if columns.upper().split() != ["NO", "LB", "ZA", "FRAG", "MASS", "X", "Y", "Z"]:
        raise ValueError
    charges = []
    has_ecp = False
    for index, atom in enumerate(atoms):
        match = _AU_ROW.fullmatch(next(rows, (0, ""))[1])
        if not match or int(match[1]) != index or match[2] != atom.element:
            raise ValueError
        charge, atomic_number = _finite(match[3]), ATOMIC_NUMBERS[atom.element]
        if match[4]:
            if not charge.is_integer() or not 0 < charge < atomic_number:
                raise ValueError
            has_ecp = True
        elif charge != atomic_number:
            raise ValueError
        converted = (_finite(value) * BOHR_IN_ANGSTROM for value in match.groups()[4:])
        if not all(isclose(ang, au, rel_tol=0.0, abs_tol=1e-6)
                   for ang, au in zip((atom.x, atom.y, atom.z), converted)):
            raise ValueError
        charges.append(charge)
    if has_ecp and next(rows, (0, ""))[1].casefold() != "* core charge reduced due to ecp":
        raise ValueError
    if next(rows, None) is not None:
        raise ValueError
    return tuple(charges)


def _crosscheck_bohr(lines, heading, bohr, atoms, scf_line):
    row_number = bohr[0]
    try:
        if len(bohr) != 1 or row_number <= heading or (scf_line is not None and row_number >= scf_line):
            raise ValueError
        bohr_nuclear_charges(lines, row_number, atoms)
    except ValueError:
        return OutputIssue(
            "conflicting_geometry", "The Bohr table format, atom identities or unit conversion disagree with the table in angstroms.", row_number,
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
            raise ValueError("The input echo contains multiple geometries or follows the actual geometry table.")
        for entries in (charges, multiplicities):
            if any(not re.fullmatch(_INT, value) for _, value in entries):
                raise ValueError("Total charge and multiplicity must be explicit integers.")
            if len({int(value) for _, value in entries}) > 1:
                raise ValueError("Charge or multiplicity in the output and input echo disagree.")
            if scf_line is not None and any(line >= scf_line for line, _ in entries):
                raise ValueError("Electronic state information appears after the SCF evidence.")
        if charge_line is not None:
            charge = int(charges[0][1])
        if multiplicity_line is not None:
            multiplicity = int(multiplicities[0][1])
        if charge is None or multiplicity is None:
            return charge, multiplicity, charge_line, multiplicity_line, OutputIssue(
                "missing_electronic_state", "No unambiguous total charge or spin multiplicity was found.", geometry_line,
            )
        if multiplicity < 1:
            raise ValueError("Spin multiplicity must be a positive integer.")
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
        return None, None, OutputIssue("missing_energy", "No final single-point energy was found.")
    heading, match = entries[0]
    if len(entries) > 1:
        return None, heading, OutputIssue("ambiguous_energy", "Multiple final single-point energies were found.", entries[1][0])
    value = re.fullmatch(rf"({_NUMBER})(?:\s+(?:EH|HARTREE))?", match[1], re.I)
    try:
        if value is None:
            raise ValueError
        return _finite(value[1]), heading, None
    except ValueError:
        return None, heading, OutputIssue("invalid_energy", "The final single-point energy is not a finite Hartree value.", heading)


def _matches_printed_charge_sum(values, printed_total):
    # Per-atom charges have six decimal places and the printed total has seven.
    return isclose(fsum(values), printed_total, rel_tol=0, abs_tol=len(values) * 0.5e-6 + 1e-7)


def _mulliken(lines, atoms, charge, scf_line, normal_line):
    headings = list(_matches(lines, r"MULLIKEN ATOMIC CHARGES\b(.*)"))
    if not headings:
        return None, None, "The output has no Mulliken atomic charge table.", None
    heading, match = headings[0]
    row_number = heading
    try:
        with_spin = match[1].strip().upper() == "AND SPIN POPULATIONS"
        if len(headings) > 1 or (match[1] and not with_spin):
            raise ValueError("The Mulliken table is ambiguous or uses an unsupported header.")
        if not (scf_line is not None and normal_line is not None and scf_line < heading < normal_line):
            raise ValueError("The Mulliken charge table lies outside the verified calculation interval.")
        values = []
        printed_total = None
        for row_number, row in _table(lines, heading):
            total = _MULLIKEN_SUM.fullmatch(row)
            if total and row_number < normal_line:
                printed_total = _finite(total[1])
                break
            entry = _POPULATION_ROW.fullmatch(row)
            index = len(values)
            if (
                not entry or index >= len(atoms) or int(entry[1]) != index
                or entry[2] != atoms[index].element or bool(entry[4]) != with_spin or row_number >= normal_line
            ):
                raise ValueError("Mulliken table units, row format or ordered atom identities do not match.")
            values.append(_finite(entry[3]))
            if with_spin:
                _finite(entry[4])
        if not values or len(values) != len(atoms):
            raise ValueError("The Mulliken charge table has the wrong atom count.")
        if printed_total is not None:
            if charge is not None and not isclose(printed_total, charge, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError("The total Mulliken charge is inconsistent with the electronic state.")
            if not _matches_printed_charge_sum(values, printed_total):
                raise ValueError("The sum of the atomic Mulliken charges differs from the reported total.")
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
    angstrom, bohr, unsupported_units = _coordinate_headings(lines)
    echoes = _input_echo(lines)
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
    atoms, geometry_line, geometry_issue = _geometry(lines, angstrom, bohr, scf_line)
    charge, multiplicity, charge_line, mult_line, state_issue = _electronic_state(
        lines, echoes, geometry_line, scf_line, atoms,
    )
    energy, energy_line, energy_issue = _energy(lines)
    mulliken, mulliken_line, mulliken_reason, mulliken_issue = _mulliken(lines, atoms, charge, scf_line, normal_line)

    issues = [issue for issue in (geometry_issue, state_issue, energy_issue) if issue is not None]
    if program_version is None:
        issues.append(OutputIssue("missing_version", "The ORCA version banner is missing."))
    elif not re.fullmatch(r"6\.1(?:\.[0-9]+)?", program_version):
        issues.append(OutputIssue("unsupported_version", "Only ORCA 6.1 output is supported by this adapter.", version_line))
    repeated = [group[1] for group in (banners, [line for line, _ in versions], normal_lines, single_point)
                if len(group) > 1]
    if repeated or job_directives or (normal_lines and abnormal_lines):
        repeated.extend(job_directives)
        repeated.extend(abnormal_lines if normal_lines else ())
        issues.append(OutputIssue("multiple_jobs", "The output contains multiple jobs or concatenated calculations.", min(repeated)))
    if optimization_line is not None:
        other_tasks.append(optimization_line)
    if not single_point or other_tasks:
        issues.append(OutputIssue("unsupported_task", "Could not confirm a single, unique single-point job.", min(other_tasks, default=None)))
    if unsupported_units or (bohr and not angstrom):
        issues.append(OutputIssue("unsupported_geometry_unit", "Publishing the geometry requires explicit angstrom coordinates and consistent unit information.",
                                  (unsupported_units or bohr)[0]))
    if scf is None:
        issues.append(OutputIssue("missing_scf_convergence", "Explicit SCF convergence evidence is missing."))
    elif scf is False:
        issues.append(OutputIssue("scf_unconverged", "SCF did not converge.", scf_line))
    if len(scf_events) > 1:
        issues.append(OutputIssue("ambiguous_scf", "Multiple SCF completion markers were found.", scf_events[1][0]))
    if normal is None:
        issues.append(OutputIssue("incomplete_output", "The normal ORCA termination marker is missing."))
    elif normal is False:
        issues.append(OutputIssue("abnormal_termination", "The output contains an abnormal termination marker.", termination_line))
    expected_order = (
        version_line, next(iter(single_point), None), geometry_line, scf_line, energy_line, termination_line,
    )
    observed = [line for line in expected_order if line is not None]
    if observed != sorted(set(observed)):
        issues.append(OutputIssue("inconsistent_evidence", "Version, geometry, SCF, energy or termination evidence is out of order for a single-point job."))
    if normal is True and len(normal_lines) == 1:
        trailing = [(number, line) for number, line in enumerate(lines[termination_line:], termination_line + 1) if line]
        if trailing and (len(trailing) != 1 or not _TOTAL_RUN_TIME.fullmatch(trailing[0][1])):
            extra_line = next((number for number, line in trailing if not _TOTAL_RUN_TIME.fullmatch(line)), trailing[0][0])
            issues.append(OutputIssue("multiple_jobs", "Text after the normal termination marker cannot be attributed to this calculation.", extra_line))

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
    headings, bohr_headings, _ = _coordinate_headings(lines)
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
    bohr = [n for n in bohr_headings if heading < n < end]
    atoms, _, issue = _geometry(lines, [heading], bohr, None)
    if issue:
        return None
    charge, mult, _, _, issue = _electronic_state(lines, _input_echo(lines), None, None, atoms)
    return None if issue else (atoms, charge, mult, heading)


def _hirshfeld_table(lines, start, atoms):
    """Read the atom charges and spins printed by ORCA's grid integration."""
    end = len(lines)
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
    for i in range(geometry_line, len(lines)):
        heading = _COORDINATE_HEADING.fullmatch(lines[i])
        if heading and heading.lastgroup == "angstrom":
            break
        if lines[i].upper() == "HIRSHFELD ANALYSIS":
            try:
                result = _hirshfeld_table(lines, i, molecule.atoms)
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
            for line_number, row in _table(lines, i + 1):
                total = _MULLIKEN_SUM.fullmatch(row)
                if total:
                    following = lines[line_number] if line_number < len(lines) else ""
                    if spins and following.upper().startswith("SUM OF ATOMIC SPIN POPULATIONS"):
                        spin_total = re.fullmatch(rf"SUM OF ATOMIC SPIN POPULATIONS\s*:\s*({_NUMBER})", following, re.I)
                        if not spin_total or not _matches_printed_charge_sum(spins, _finite(spin_total[1])):
                            spins.clear()
                    break
                m = _POPULATION_ROW.fullmatch(row)
                idx = len(values)
                if (not m or idx >= len(molecule.atoms) or int(m[1]) != idx
                        or m[2] != molecule.atoms[idx].element or bool(m[4]) != bool(title[2])):
                    raise ValueError("Population table atom identities or row format do not match")
                values.append(_finite(m[3]))
                if m[4]:
                    spins.append(_finite(m[4]))
            else:
                total = None
            if total:
                printed_total = _finite(total[1])
                if (not isclose(printed_total, molecule.charge, rel_tol=0, abs_tol=1e-6)
                        or not _matches_printed_charge_sum(values, printed_total)):
                    continue
            if (len(values) != len(molecule.atoms) or
                    not isclose(fsum(values), molecule.charge, rel_tol=0, abs_tol=len(values)*0.5e-6 + 1e-6)):
                continue
        except (ValueError, OverflowError):
            continue
        method = "Mulliken" if title[1].upper() == "MULLIKEN" else "Löwdin"
        yield method, i + 1, tuple(values), tuple(spins)

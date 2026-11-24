"""Line-addressable properties from an ORCA output job, in the printed coordinate frame."""

import math
import re
from dataclasses import dataclass
from typing import Iterable, Sequence, Tuple, Union

from ._native_output import _NUMBER, _finite


@dataclass(frozen=True)
class LogProperty:
    group: str
    label: str
    value: float
    unit: str
    line: int  # one-based source line; a gap points to its LUMO row
    context: str = ""


_CYCLE = re.compile(r"\**\s*GEOMETRY OPTIMIZATION CYCLE\s+(\d+)\s*\**", re.I)
_CYCLE_CONTEXT = re.compile("Optimization step \\d+|Final optimization energy evaluation")
_JOIN = " · "
_FINAL = re.compile(rf"FINAL SINGLE POINT ENERGY\s+({_NUMBER})(?:\s+Eh)?"
                    r"(?:\s+\((Wavefunction not fully converged)!?\))?", re.I)
_SCF = re.compile(rf"Total Energy\s*:\s*({_NUMBER})\s+Eh(?:\s+{_NUMBER}\s+eV)?", re.I)
_MP2 = re.compile(rf"((?:RI-|DLPNO-|SCS-)?MP2) CORRELATION ENERGY\s*:\s*({_NUMBER})\s+Eh", re.I)
_SOLVENT = re.compile(rf"(CPCM Dielectric|SMD CDS \(Gcds\))\s*:\s*({_NUMBER})\s+Eh(?:\s+{_NUMBER}\s+eV)?", re.I)
_SPIN = re.compile(rf"Expectation value of <S(?:\*\*|\^)2>\s*:\s*({_NUMBER})", re.I)
_DISP = re.compile(rf"Edisp/kcal,au\s*:\s*{_NUMBER}\s+({_NUMBER})", re.I)
_BODY_TITLES = {"TOTAL SCF ENERGY", "COUPLED CLUSTER ENERGY", "DIPOLE MOMENT", "ORBITAL ENERGIES",
                "SCF CONVERGENCE", "ROTATIONAL SPECTRUM", "IR SPECTRUM", "STATIC POLARIZABILITY TENSOR (DIPOLE/DIPOLE)"}
_CC = re.compile(rf"(E\(CORR\)(?:\(corrected\))?|E\(TOT\)|T1 diagnostic)\s+\.{{3}}\s+({_NUMBER})(?:\s+Eh)?", re.I)
_DIPOLE = re.compile(rf"Total Dipole Moment\s*:\s*({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})", re.I)
_DEBYE = re.compile(rf"Magnitude \(Debye\)\s*:\s*({_NUMBER})", re.I)
_TRIPLE = re.compile(rf"({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})")
_ISOTROPIC = re.compile(rf"Isotropic polarizability\s*:\s*({_NUMBER})", re.I)
_ROTATION = re.compile(rf"Rotational constants in (cm-1|MHz)\s*:\s*({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})", re.I)
_ORB_HEAD = re.compile(r"NO\s+OCC\s+E\(Eh\)\s+E\(eV\)(\s+Irrep)?", re.I)
_ORB_ROW = re.compile(rf"(\d{{1,18}})\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})(?:\s+(\S+))?")
_THERMO = re.compile(rf"THERMOCHEMISTRY(?: AT\s+({_NUMBER})\s*K)?", re.I)
_CONDITION = re.compile(rf"(Temperature|Pressure)\s+\.{{3}}\s+({_NUMBER})\s+(K|atm|bar|Pa)", re.I)
_THERMAL_ROW = re.compile(rf"(.+?)\s+(?:\.{{3}}\s+)?({_NUMBER})\s+Eh(?:\s+{_NUMBER}\s+kcal/mol)?", re.I)
_THERMAL_LABELS = {
    ("INNER ENERGY", "zero point energy"): "Zero-point vibrational energy ZPE",
    ("INNER ENERGY", "total thermal energy"): "Internal energy U",
    ("ENTHALPY", "total enthalpy"): "Enthalpy H",
    ("ENTROPY", "final entropy term"): "Entropy term T·S",
    ("GIBBS FREE ENERGY", "final gibbs free energy"): "Gibbs free energy G",
    ("GIBBS FREE ENERGY", "g-e(el)"): "Gibbs energy correction G−E(el)",
}
_PRIORITY = {label: i for i, label in enumerate((
    "Final single-point energy", "Gibbs free energy G", "Enthalpy H", "Zero-point vibrational energy ZPE", "Dipole magnitude", "Isotropic static polarizability", "HOMO–LUMO gap",
    "HOMO", "LUMO", "Total SCF energy", "Total coupled-cluster energy", "Internal energy U", "Entropy term T·S",
    "Gibbs energy correction G−E(el)", "⟨S²⟩", "Dipole moment X", "Dipole moment Y", "Dipole moment Z",
))}


def property_series_key(prop: LogProperty):
    """Group optimization history while keeping different jobs, densities, spins and baths distinct."""
    context = _JOIN.join(c for c in prop.context.split(_JOIN) if not _CYCLE_CONTEXT.fullmatch(c))
    if prop.group == "Rotational constants":
        # ORCA prints MHz and wavenumbers side by side in the rotational spectrum.
        context = _context(context, prop.unit)
    return prop.group, prop.label, context


def ranked_properties(items: Iterable[LogProperty]) -> Tuple[LogProperty, ...]:
    """Put the newest sourced value of each job/series ahead of its earlier history."""
    items = tuple(items)
    latest = {}
    for prop in items:
        key = property_series_key(prop)
        latest[key] = max(latest.get(key, 0), prop.line)
    return tuple(sorted(items, key=lambda p: (p.line != latest[property_series_key(p)],
                                               _PRIORITY.get(p.label, 100), p.group, p.label, -p.line)))


def _context(*parts):
    return _JOIN.join(p for p in parts if p)


def _is_rule(line):
    return bool(line) and line.startswith("-") and not line.strip("- ")


def _section_title(lines, i):
    return (0 < i < len(lines)-1 and _is_rule(lines[i-1]) and _is_rule(lines[i+1])
            and re.fullmatch(r"[A-Za-z][A-Za-z ()/–-]*", lines[i]) is not None)


def _body(lines, start):
    """Read one property block and stop before another banner or unnumbered input."""
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.upper() in _BODY_TITLES or line.startswith(("|", "#", "*", "Program Version", "FINAL SINGLE POINT ENERGY")):
            break
        if i > start + 2 and _section_title(lines, i):
            break
        yield i, line


def _property(group, label, token, unit, index, context):
    try:
        return LogProperty(group, label, _finite(token), unit, index + 1, context)
    except ValueError:
        return None


def _density_attribute(line):
    key, sep, value = line.partition(":")
    prefix = {"Method": "", "Type of density": "", "Level": "", "Multiplicity": "Multiplicity ",
              "Irrep": "Irreducible representation ", "Root": "Root ", "State": "State "}
    if sep and value.strip() and key.strip() in prefix:
        return prefix[key.strip()] + value.strip()
    return ""


def _dipole(lines, start, stage):
    attributes = []
    for i, line in _body(lines, start):
        if attribute := _density_attribute(line):
            attributes.append(attribute)
        vector = _DIPOLE.fullmatch(line)
        if vector:
            try:
                xyz = tuple(_finite(token) for token in vector.groups())
            except ValueError:
                continue
            for label, component in zip("XYZ", xyz):
                yield LogProperty("Dipole moment", f"Dipole moment {label}", component, "a.u.", i+1, _context(stage, *attributes))
        magnitude = _DEBYE.fullmatch(line)
        if magnitude:
            yield _property("Dipole moment", "Dipole magnitude", magnitude[1], "Debye", i, _context(stage, *attributes))
            break


def _polarizability(lines, start, stage):
    attributes = []
    atomic_units = False
    for i, line in _body(lines, start):
        if attribute := _density_attribute(line):
            attributes.append(attribute)
        if line.lower() == "the raw cartesian tensor (atomic units):":
            atomic_units = True
            rows = [_TRIPLE.fullmatch(row) for row in lines[i+1:i+4]]
            if len(rows) == 3 and all(rows):
                try:
                    matrix = [tuple(_finite(v) for v in row.groups()) for row in rows]
                except ValueError:
                    continue
                for offset, (axis, row) in enumerate(zip("XYZ", matrix), 1):
                    for other, value in zip("XYZ", row):
                        yield LogProperty("Static polarizability", f"Static polarizability α{axis}{other}", value, "a.u.",
                                          i+offset+1, _context(stage, *attributes))
        elif atomic_units and (m := _ISOTROPIC.fullmatch(line)):
            yield _property("Static polarizability", "Isotropic static polarizability", m[1], "a.u.", i, _context(stage, *attributes))
            break


def _rotational_constants(match, index, context):
    unit = "cm⁻¹" if match[1].lower() == "cm-1" else "MHz"
    try:
        values = tuple(_finite(token) for token in match.groups()[1:])
    except ValueError:
        return
    for axis, value in zip("ABC", values):
        yield LogProperty("Rotational constants", f"Rotational constant {axis}", value, unit, index+1, context)


def _orbital_frontier(lines, header, spin, stage, irrep):
    frontier = []
    last_no, last_ev, lumo = None, -math.inf, None
    homo = None
    for i in range(header + 1, len(lines)):
        line = lines[i]
        if not line or not line[0].isdigit():
            break
        row = _ORB_ROW.fullmatch(line)
        if not row or bool(row[5]) != irrep:
            return ()
        try:
            no, occ, _, ev = int(row[1]), _finite(row[2]), _finite(row[3]), _finite(row[4])
        except ValueError:
            return ()
        if (last_no is not None and no != last_no + 1) or ev < last_ev:
            return ()
        last_no, last_ev = no, ev
        # Fractional occupations and non-Aufbau occupation patterns have no conventional
        # occupied/virtual boundary. Never manufacture a frontier by applying a threshold.
        if occ not in (0, 1, 2) or (spin and occ > 1) or (occ and lumo is not None):
            return ()
        if occ:
            homo = ev, i + 1
        elif lumo is None:
            lumo = ev, i + 1
    if homo is not None and lumo is not None:
        context = _context(stage, spin)
        for label, value, lineno in (("HOMO", *homo), ("LUMO", *lumo),
                                     ("HOMO–LUMO gap", lumo[0]-homo[0], lumo[1])):
            if math.isfinite(value):
                frontier.append(LogProperty("Frontier orbitals", label, value, "eV", lineno, context))
    return frontier


def _orbitals(lines, start, stage):
    i, spin = start + 1, ""
    while i < len(lines):
        line = lines[i]
        if line in ("SPIN UP ORBITALS", "SPIN DOWN ORBITALS"):
            spin = "α spin" if "UP" in line else "β spin"
        elif head := _ORB_HEAD.fullmatch(line):
            yield from _orbital_frontier(lines, i, spin, stage, bool(head[1]))
            # Skip this table including print limits, and look for its other spin block.
            i += 1
            while i < len(lines) and lines[i] and lines[i][0].isdigit():
                i += 1
            continue
        elif line and not (_is_rule(line) or line.startswith("*Only the first ")):
            break
        i += 1


def _thermochemistry(lines, start, temperature, stage):
    # Enthalpy and Gibbs sections reprint the preceding sums. Extract each quantity
    # from its own summary, preserving T*S (energy) rather than relabelling it as S.
    conditions = {"Temperature": "", "Pressure": ""}
    if temperature:
        try:
            conditions["Temperature"] = f"{_finite(temperature):g} K"
        except ValueError:
            pass
    subsection = ""
    for i in range(start+1, len(lines)):
        line = lines[i]
        if _THERMO.fullmatch(line) or line.startswith(("#", "Program Version", "FINAL SINGLE POINT ENERGY")):
            break
        if line in ("INNER ENERGY", "ENTHALPY", "ENTROPY", "GIBBS FREE ENERGY"):
            subsection = line
        elif i > start+2 and _section_title(lines, i):
            break
        if m := _ROTATION.fullmatch(line):
            yield from _rotational_constants(m, i, _context(stage, "Thermochemistry", *conditions.values()))
        elif cond := _CONDITION.fullmatch(line):
            key = cond[1].capitalize()
            unit = cond[3]
            if (key == "Temperature") == (unit.upper() == "K"):
                try:
                    conditions[key] = f"{_finite(cond[2]):g} {unit}"
                except ValueError:
                    pass
        elif "eh" in line.lower() and (match := _THERMAL_ROW.fullmatch(line)):
            label = _THERMAL_LABELS.get((subsection, match[1].casefold()))
            if label:
                yield _property("Thermochemistry", label, match[2], "Eh", i, _context(stage, *conditions.values()))
                if match[1].casefold() == "g-e(el)":
                    break


def parse_log_properties(lines: Union[str, Sequence[str]]) -> Tuple[LogProperty, ...]:
    """Collect reported values for one job; the newest value of each series is ranked first."""
    if isinstance(lines, str):
        lines = lines.splitlines()
    lines = [line.strip() for line in lines]
    items = []
    stage = ""
    for i, line in enumerate(lines):
        if not line or line[0] in "|#-0123456789":
            continue
        if line == "TOTAL SCF ENERGY":
            for j, body in _body(lines, i):
                if m := _SCF.fullmatch(body):
                    items.append(_property("Electronic energy", "Total SCF energy", m[1], "Eh", j, stage))
                    break
        elif line == "COUPLED CLUSTER ENERGY":
            for j, body in _body(lines, i):
                if m := _CC.fullmatch(body):
                    key = m[1].upper()
                    label = ("T1 diagnostic" if key == "T1 DIAGNOSTIC" else
                             "Total coupled-cluster energy" if key == "E(TOT)" else "Coupled-cluster correlation energy")
                    items.append(_property("Electronic energy", label, m[2], "" if key == "T1 DIAGNOSTIC" else "Eh", j, stage))
        elif line == "DIPOLE MOMENT":
            items.extend(_dipole(lines, i, stage))
        elif line == "STATIC POLARIZABILITY TENSOR (Dipole/Dipole)":
            items.extend(_polarizability(lines, i, stage))
        elif line.casefold() == "rotational spectrum":
            for j, body in _body(lines, i):
                if m := _ROTATION.fullmatch(body):
                    items.extend(_rotational_constants(m, j, _context(stage, "Rotational spectrum")))
        elif line == "ORBITAL ENERGIES":
            items.extend(_orbitals(lines, i, stage))
        elif m := _THERMO.fullmatch(line):
            items.extend(_thermochemistry(lines, i, m[1], stage))
        elif m := _FINAL.fullmatch(line):
            context = _context(stage, "Wavefunction not fully converged" if m[2] else "")
            items.append(_property("Electronic energy", "Final single-point energy", m[1], "Eh", i, context))
        elif m := _MP2.fullmatch(line):
            items.append(_property("Electronic energy", f"{m[1].upper()} correlation energy", m[2], "Eh", i, stage))
        elif m := _SOLVENT.fullmatch(line):
            label = "CPCM dielectric energy" if m[1].upper().startswith("CPCM") else "SMD nonelectrostatic CDS term"
            items.append(_property("Solvation", label, m[2], "Eh", i, stage))
        elif m := _SPIN.fullmatch(line):
            items.append(_property("Spin", "⟨S²⟩", m[1], "ℏ²", i, stage))
        elif m := _DISP.fullmatch(line):
            items.append(_property("Electronic energy", "Dispersion model", m[1], "Eh", i, stage))
        elif m := _CYCLE.fullmatch(line):
            stage = f"Optimization step {m[1]}"
        elif line.strip("* ").upper() == "FINAL ENERGY EVALUATION AT THE STATIONARY POINT":
            stage = "Final optimization energy evaluation"

    return ranked_properties(item for item in items if item is not None)

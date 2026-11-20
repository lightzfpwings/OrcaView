"""Read calculated spectral properties from ORCA's printed tables."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Sequence, Union

from ._native_output import _NUMBER, _finite


Cell = Optional[Union[str, int, float]]


@dataclass(frozen=True)
class SpectrumTable:
    """A native result table with display units and its one-based source heading."""

    kind: str
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]
    source_line: int


_IR = "IR SPECTRUM"
_RAMAN = "RAMAN SPECTRUM"
_FREQUENCIES = "VIBRATIONAL FREQUENCIES"
_SHIELD = "CHEMICAL SHIELDING SUMMARY (PPM)"
_COUPLING = "SUMMARY OF ISOTROPIC COUPLING CONSTANTS J (HZ)"
_LENGTH = "ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS"
_VELOCITY = "ABSORPTION SPECTRUM VIA TRANSITION VELOCITY DIPOLE MOMENTS"
_CD_LENGTH = "CD SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS"
_CD_VELOCITY = "CD SPECTRUM VIA TRANSITION VELOCITY DIPOLE MOMENTS"
_SECTIONS = {_IR, _RAMAN, _FREQUENCIES, _SHIELD, _COUPLING, _LENGTH, _VELOCITY, _CD_LENGTH, _CD_VELOCITY}
_TRANSITION_MOMENTS = {
    "SPECTRUM FOR RIGHT TRANSITION MOMENTS": "右跃迁矩",
    "SPECTRUM FOR LEFT TRANSITION MOMENTS": "左跃迁矩",
    "SPECTRUM FOR LEFT-RIGHT TRANSITION MOMENTS": "左–右跃迁矩",
}
_NUMBER_RE = re.compile(_NUMBER)
_RULE = re.compile(r"[-=\s]+")
_INDEX = re.compile(r"[0-9]{1,12}")
_NUCLEUS = re.compile(r"[A-Z][a-z]?")
_MODE_FREQUENCY = re.compile(
    rf"\s*([0-9]{{1,12}}):\s*({_NUMBER})\s+cm(?:\*\*|\^)?-1(?:\s+\**\s*imaginary mode\s*\**)?\s*", re.I
)
_WAVENUMBER = "波数（cm⁻¹）"
_INTENSITY = "红外强度（km/mol）"
_MODE = ("振动模式", _WAVENUMBER)
_UV_LEGACY = ("激发态", _WAVENUMBER, "波长（nm）", "振子强度")
_UV_MODERN = ("跃迁", "能量（eV）", _WAVENUMBER, "波长（nm）", "振子强度")


def _next_content(lines, index):
    while index < len(lines) and (not lines[index].strip() or _RULE.fullmatch(lines[index])):
        index += 1
    return index


def _numbers(tokens, expected):
    if len(tokens) != expected:
        return None
    values = []
    for token in tokens:
        if _NUMBER_RE.fullmatch(token):
            try:
                values.append(_finite(token))
            except ValueError:  # A printed number can overflow floating point.
                values.append(None)
        elif token.upper().lstrip("+-") in {"N/A", "NA", "NAN", "INF", "INFINITY"} or re.fullmatch(r"\*+|-{2,}", token):
            values.append(None)
        else:
            return None
    return tuple(values)


def _mode_row(line, count):
    fields = line.replace("(", " ").replace(")", " ").split()
    if fields and re.fullmatch(r"[0-9]{1,12}:", fields[0]):
        values = _numbers(fields[1:], count - 1)
        if values is not None and values[0] is not None:
            return (int(fields[0][:-1]), *values)


def _shield_row(line, count):
    fields = line.split()
    if len(fields) == count and _INDEX.fullmatch(fields[0]) and _NUCLEUS.fullmatch(fields[1]):
        values = _numbers(fields[2:], count - 2)
        if values is not None:
            # Isotropic shielding identifies this result; anisotropy is optional.
            return (int(fields[0]), fields[1], *values) if values[0] is not None else ()


def _transition_row(line, count):
    # Symmetry labels can contain spaces, e.g. "0-1 Ag -> 1-1 B3g".
    fields = line.strip().rsplit(None, count - 1)
    if len(fields) == count and re.fullmatch(r"\d[^>]*?\s*->\s*\d[^>]*", fields[0]):
        values = _numbers(fields[1:], count - 1)
        if values is not None and any(value is not None for value in values[:3]):
            return (" ".join(fields[0].split()), *values)


def _state_row(line, count):
    fields = line.split()
    if len(fields) < 3 or not _INDEX.fullmatch(fields[0]):
        return None
    # Older ORCA writes a text annotation in place of all five transition properties.
    forbidden = re.fullmatch(r"spin forbidden(?:\s+\(mult\s*=\s*\d+\))?", " ".join(fields[3:]), re.I)
    if forbidden:
        values = _numbers(fields[1:3], 2)
        if values is not None:
            return (int(fields[0]), *values, *(None,) * 5, forbidden.group())
    values = _numbers(fields[1:], count - 2)
    if values is not None and any(value is not None for value in values[:2]):
        return (int(fields[0]), *values, None)


def _read_rows(lines, start, columns, read_row):
    start = _next_content(lines, start)
    if start < len(lines) and lines[start].strip().lower().startswith(("cm**-1", "(cm-1)", "(ev)")):
        start = _next_content(lines, start + 1)
    rows = []
    for index in range(start, len(lines)):
        row = read_row(lines[index], len(columns))
        if row is None:
            break
        if row:  # An identified source row can lack its required measurement.
            rows.append(row)
    return tuple(rows)


def _couplings(lines, heading, start):
    # ORCA prints a symmetric matrix in blocks of up to six columns.
    # Each distinct pair appears twice, often in different blocks.
    pairs = {}
    column_nuclei = ()
    for index in range(start, len(lines)):
        tokens = lines[index].split()
        if not tokens:
            # Some versions separate column blocks by a blank line.
            continue
        if (len(tokens) % 2 == 0 and
                all(_INDEX.fullmatch(n) and _NUCLEUS.fullmatch(e) for n, e in zip(tokens[::2], tokens[1::2]))):
            column_nuclei = tuple((int(n), e) for n, e in zip(tokens[::2], tokens[1::2]))
            continue
        if not column_nuclei or len(tokens) < 3 or not _INDEX.fullmatch(tokens[0]) or not _NUCLEUS.fullmatch(tokens[1]):
            break
        values = _numbers(tokens[2:], len(column_nuclei))
        if values is None:
            break
        nucleus = (int(tokens[0]), tokens[1])
        for other, value in zip(column_nuclei, values):
            if other != nucleus:
                pair = tuple(sorted((nucleus, other)))
                if pairs.get(pair) is None:
                    pairs[pair] = value
    if any(value is not None for value in pairs.values()):
        rows = tuple((f"{i} {a}", f"{j} {b}", value) for ((i, a), (j, b)), value in pairs.items())
        return SpectrumTable("nmr", "NMR 自旋–自旋耦合", ("原子核 1", "原子核 2", "各向同性 J（Hz）"), rows, heading + 1)


def _moment_columns(symbol):
    return (f"{symbol}²（a.u.²）", *(f"{symbol}{axis}（a.u.）" for axis in "xyz"))


def _optical_title(lines, heading, title, length_gauge):
    gauge = "长度表象" if length_gauge else "速度表象"
    for index in range(heading - 1, max(-1, heading - 9), -1):
        line = lines[index].strip().upper()
        if line and not _RULE.fullmatch(line):
            context = _TRANSITION_MOMENTS.get(line)
            if context:
                gauge += f"，{context}"
            break
    return f"{title}（{gauge}）"


def _frequencies(lines, heading, start):
    if lines[start].strip().lower().startswith("scaling factor for frequencies"):
        start = _next_content(lines, start + 1)
    rows = []
    for index in range(start, len(lines)):
        match = _MODE_FREQUENCY.fullmatch(lines[index])
        if not match:
            break
        try:
            frequency = _finite(match[2])
        except ValueError:
            continue
        rows.append((int(match[1]), frequency))
    if rows:
        return SpectrumTable("vibrations", "振动频率（仅波数）", _MODE, tuple(rows), heading + 1)


def _layout(lines, heading, section, header):
    if section == _IR:
        if header == "mode freq eps int t**2 tx ty tz":
            columns = _MODE + ("摩尔吸光系数（L·mol⁻¹·cm⁻¹）", _INTENSITY, "T²（a.u.）", "Tx（a.u.）", "Ty（a.u.）", "Tz（a.u.）")
        elif header == "mode freq (cm**-1) t**2 tx ty tz":
            # ORCA <= 4.2.1 used a different T**2 convention; keep its native columns.
            columns = _MODE + ("T²（km/mol）", "Tx", "Ty", "Tz")
        else:
            return None
        return "ir", "红外光谱", columns, _mode_row

    if section == _RAMAN and header == "mode freq (cm**-1) activity depolarization":
        return "raman", "拉曼光谱", _MODE + ("拉曼活性（Å⁴/amu）", "退偏比"), _mode_row

    if section == _SHIELD and header == "nucleus element isotropic anisotropy":
        columns = ("原子核序号", "元素", "各向同性屏蔽（ppm）", "屏蔽各向异性（ppm）")
        return "nmr", "NMR 化学屏蔽", columns, _shield_row

    if section in {_LENGTH, _VELOCITY}:
        length_gauge = section == _LENGTH
        symbol = "D" if length_gauge else "P"
        title = _optical_title(lines, heading, "紫外–可见吸收", length_gauge)
        if header == f"transition energy energy wavelength fosc({symbol}2) {symbol}2 {symbol}x {symbol}y {symbol}z".lower():
            return "uvvis", title, _UV_MODERN + _moment_columns(symbol), _transition_row
        symbol = "T" if length_gauge else "P"
        if header == f"state energy wavelength fosc {symbol}2 {symbol}x {symbol}y {symbol}z".lower():
            columns = _UV_LEGACY + _moment_columns(symbol) + ("备注",)
            return "uvvis", title, columns, _state_row
    if section in {_CD_LENGTH, _CD_VELOCITY} and header == "transition energy energy wavelength r mx my mz":
        title = _optical_title(lines, heading, "电子圆二色谱 CD", section == _CD_LENGTH)
        columns = _UV_MODERN[:4] + ("旋光强度（10⁻⁴⁰ cgs）", "Mx（a.u.）", "My（a.u.）", "Mz（a.u.）")
        return "cd", title, columns, _transition_row
    return None


def parse_log_spectra(text: Union[str, Sequence[str]]) -> tuple[SpectrumTable, ...]:
    """Return nonempty printed result tables in source order with one-based heading lines."""
    lines = text.splitlines() if isinstance(text, str) else text
    tables = []
    frequency_index = None
    for index, line in enumerate(lines):
        section = line.strip().upper()
        if section not in _SECTIONS:
            if frequency_index is not None and re.match(r"\**\s*(?:ORCA TERMINATED|COMPOUND JOB|PROGRAM VERSION)\b", section):
                frequency_index = None
            continue
        start = _next_content(lines, index + 1)
        if start >= len(lines):
            continue
        if section == _FREQUENCIES:
            table = _frequencies(lines, index, start)
            frequency_index = len(tables) if table else None
            if table:
                tables.append(table)
            continue
        if section == _COUPLING:
            table = _couplings(lines, index, start)
            if table:
                tables.append(table)
            continue
        header = " ".join(lines[start].lower().split())
        layout = _layout(lines, index, section, header)
        if layout:
            kind, title, columns, read_row = layout
            rows = _read_rows(lines, start + 1, columns, read_row)
            if rows:
                if kind in {"ir", "raman"} and frequency_index is not None:
                    tables.pop(frequency_index)
                    frequency_index = None
                tables.append(SpectrumTable(kind, title, columns, rows, index + 1))
    return tuple(tables)

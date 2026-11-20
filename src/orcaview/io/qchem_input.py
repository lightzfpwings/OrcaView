"""Read the explicit Cartesian molecule in a Q-Chem input file."""

import re

from ._quantum_geometry import atom, check_periodic, geometry


def read_qchem_input(path, raw, *, remove_periodicity=False):
    text = raw.decode("utf-8-sig")
    # Q-Chem accepts commas as coordinate separators and '=' in $rem.
    lines = [line.partition("!")[0].strip() for line in text.splitlines()]
    sections = {}
    section = None
    for line in lines:
        tag = line.lower()
        if tag == "@@@":
            raise ValueError("Q-Chem 输入包含多个作业，请选择单作业文件。")
        if tag == "$end":
            section = None
        elif tag.startswith("$"):
            if section is not None or tag in sections:
                raise ValueError("Q-Chem 输入含未闭合或重复的输入段。")
            sections[tag] = section = []
        elif section is not None and line:
            section.append(line)
    if section is not None or not sections.get("$molecule"):
        raise ValueError("未找到完整的 Q-Chem $molecule 坐标段。")
    unit = "angstrom"
    periodic = any(line.lower().split()[0] in ("ewald", "box_length")
                   for line in sections.get("$forceman", ()))
    for line in sections.get("$rem", ()):
        tokens = line.lower().replace("=", " ").split()
        if tokens and tokens[0] == "ewald_on" and tokens[1:] in (["true"], ["1"]):
            periodic = True
        if tokens and tokens[0] == "input_bohr":
            if len(tokens) != 2 or tokens[1] not in ("true", "false", "1", "0"):
                raise ValueError("无法识别 Q-Chem INPUT_BOHR 的单位设置。")
            unit = "bohr" if tokens[1] in ("true", "1") else "angstrom"
    check_periodic(periodic, remove_periodicity)
    rows = iter(sections["$molecule"])
    state = next(rows)
    if not re.fullmatch(r"[+-]?\d+[\s,]+\d+", state):
        raise ValueError("Q-Chem 文件需要显式的电荷、多重度和笛卡尔坐标。")
    charge, mult = map(int, state.replace(",", " ").split())
    atoms = []
    for line in rows:
        if line.startswith("--"):
            fragment = next(rows, "")
            if not re.fullmatch(r"[+-]?\d+[\s,]+\d+", fragment):
                raise ValueError("Q-Chem 分片缺少电荷或多重度。")
            continue
        fields = line.replace(",", " ").split()
        if len(fields) < 4 or any(not re.fullmatch(r"[+-]?\d+", field) for field in fields[4:]):
            raise ValueError("Q-Chem 导入需要显式的元素和三个笛卡尔坐标。")
        atoms.append(atom(fields[0], fields[1:4], unit))
    return geometry(path.stem, atoms, unit, charge, mult, periodic=periodic)

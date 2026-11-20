"""严格读取单帧 XYZ；不从注释行猜测电荷与自旋。"""

import json
from pathlib import Path
import re
from typing import NamedTuple, Tuple, Union

from ..core.models import Atom, Molecule
from ..core.units import convert_length


_METADATA = re.compile(
    r"""(?:^|\s)(?:([\w-]+)\s*=\s*|(?=["']))("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\S*)"""
)
_UNITS = {"angstrom": "angstrom", "angstroms": "angstrom", "å": "angstrom",
          "bohr": "bohr", "a0": "bohr"}


class XYZRecord(NamedTuple):
    molecule: Molecule
    source_unit: str
    unit_source: str


def _source_unit(comment: str) -> Tuple[str, str]:
    unit = None
    for key, raw in _METADATA.findall(comment):
        key, value = key.lower(), raw.strip("'\"").lower()
        if key == "pbc":
            flags = value.split()
            if len(flags) not in (1, 3) or any(flag not in ("f", "false", "0") for flag in flags):
                raise ValueError("XYZ 含周期边界或无法识别的 PBC 声明")
        elif key in ("unit", "units"):
            declared = _UNITS.get(value)
            if declared is None or (unit is not None and unit != declared):
                raise ValueError("XYZ 声明了未知或冲突的长度单位")
            unit = declared
        elif key == "lattice" or re.fullmatch(r"k[-_]?points?", key):
            raise ValueError("分子 XYZ 不支持晶胞或 k 点元数据")
    return (unit, "xyz-comment") if unit is not None else ("angstrom", "xyz-default")


def parse_xyz(text: str, name: str = "Molecule") -> Molecule:
    return parse_xyz_record(text, name).molecule


def parse_xyz_record(text: str, name: str = "Molecule") -> XYZRecord:
    """Keep whether the length unit was declared or supplied by the XYZ default."""
    lines = text.splitlines()
    if len(lines) < 2:
        raise ValueError("XYZ 必须包含原子数和注释行")
    try:
        count = int(lines[0].strip())
    except ValueError as exc:
        raise ValueError("XYZ 第一行必须是正整数原子数") from exc
    if count <= 0:
        raise ValueError("XYZ 原子数必须大于零")
    if len(lines) < count + 2:
        raise ValueError(f"XYZ 声明 {count} 个原子，但坐标行不足")
    if any(line.strip() for line in lines[count + 2:]):
        raise ValueError("当前原型只支持单帧 XYZ；检测到额外内容或多帧轨迹")
    unit, unit_source = _source_unit(lines[1])
    atoms = []
    for index, line in enumerate(lines[2:count + 2], start=3):
        fields = line.split()
        if len(fields) != 4:
            raise ValueError(f"XYZ 第 {index} 行必须是元素和三个坐标")
        try:
            atom = Atom(fields[0], *(convert_length(float(value), unit, "angstrom") for value in fields[1:]))
            atom.validate()
        except ValueError as exc:
            raise ValueError(f"XYZ 第 {index} 行无效：{exc}") from exc
        atoms.append(atom)
    molecule = Molecule(name=name, atoms=tuple(atoms))
    molecule.validate_structure()
    return XYZRecord(molecule, unit, unit_source)


def load_xyz(path: Union[str, Path]) -> Molecule:
    source = Path(path)
    return parse_xyz(source.read_text(encoding="utf-8"), name=source.stem)


def write_xyz(molecule: Molecule) -> str:
    molecule.validate_structure()
    # 注释中的换行不能改变 XYZ 帧结构。
    comment = " ".join(molecule.name.splitlines())
    if _METADATA.search(comment):
        comment = "name=" + json.dumps(comment, ensure_ascii=False)
    coordinates = [f"{a.element:<2} {a.x: .10f} {a.y: .10f} {a.z: .10f}" for a in molecule.atoms]
    return "\n".join([str(len(molecule.atoms)), comment, *coordinates]) + "\n"

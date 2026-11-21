"""Single-structure import; keep native Open Babel readers out of the GUI process."""

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.io.structure_record import PeriodicStructureError, StructureRecord
from orcaview.io.xyz import _METADATA, parse_xyz_record


BABEL_FORMATS = {
    ".xyz": "xyz", ".extxyz": "xyz", ".sdf": "sdf", ".sd": "sdf", ".mol": "mol",
    ".mol2": "mol2", ".pdb": "pdb", ".ent": "pdb", ".smi": "smi", ".smiles": "smi",
    ".can": "smi", ".inchi": "inchi", ".cdxml": "cdxml", ".cml": "cml",
    ".cif": "cif", ".vasp": "poscar",
    ".poscar": "poscar", ".contcar": "poscar", "poscar": "poscar", "contcar": "poscar",
}


def _xyz_columns(properties):
    fields = properties.split(":")
    if len(fields) % 3:
        raise ValueError("扩展 XYZ 的 Properties 声明不完整")
    width = 0
    columns = {}
    for key, kind, count in zip(fields[::3], fields[1::3], fields[2::3]):
        size = int(count)
        if size < 1 or key in columns:
            raise ValueError("扩展 XYZ 的 Properties 列数或字段名无效")
        columns[key] = (width, size, kind)
        width += size
    element = columns.get("species") or columns.get("Z")
    position = columns.get("pos")
    if not element or element[1] != 1 or not position or position[1] != 3:
        raise ValueError("扩展 XYZ 需要 species 或 Z，以及三个笛卡尔 pos 坐标")
    return width, element, position[0]


def read_xyz_structure(raw, name, *, remove_periodicity=False, default_unit="angstrom"):
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    if len(lines) < 2:
        raise ValueError("XYZ 需要原子数和注释行")
    comment = lines[1]
    metadata = {key.lower(): value.strip("'\"") for key, value in _METADATA.findall(comment) if key}
    pbc = metadata.get("pbc")
    periodic = "lattice" in metadata or any(re.fullmatch(r"k[-_]?points?", k) for k in metadata)
    if pbc is not None:
        flags = pbc.lower().split()
        if len(flags) not in (1, 3) or any(f not in ("t", "true", "1", "f", "false", "0") for f in flags):
            raise ValueError("XYZ 的 pbc 声明无效")
        periodic = any(f in ("t", "true", "1") for f in flags)
    if periodic and not remove_periodicity:
        raise PeriodicStructureError("XYZ 声明了周期性边界。")
    # Preserve unrelated metadata and coordinate units, but hand the finite
    # Cartesian record to the existing strict single-frame XYZ reader.
    if periodic or "lattice" in metadata or pbc is not None:
        lines[1] = _METADATA.sub(
            lambda m: "" if re.fullmatch(r"pbc|lattice|k[-_]?points?", m.group(1) or "", re.I)
            else m.group(0), comment)
    if default_unit != "angstrom" and not ("unit" in metadata or "units" in metadata):
        lines[1] += f" units={default_unit}"
    if "properties" in metadata:
        width, element, pos = _xyz_columns(metadata["properties"])
        symbols = {number: symbol for symbol, number in ATOMIC_NUMBERS.items()}
        for i in range(2, min(len(lines), 2 + int(lines[0]))):
            row = lines[i].split()
            if len(row) != width:
                raise ValueError(f"扩展 XYZ 第 {i + 1} 行与 Properties 列数不符")
            symbol = row[element[0]]
            if element[2].upper() == "I":
                symbol = symbols.get(int(symbol))
                if symbol is None:
                    raise ValueError("扩展 XYZ 原子序数无效")
            lines[i] = " ".join((symbol, *row[pos:pos + 3]))
    record = parse_xyz_record("\n".join(lines), name)
    return StructureRecord(record.molecule, record.source_unit, record.unit_source, removed_periodicity=periodic)


def _read_poscar(raw, name, remove_periodicity):
    lines = raw.decode("utf-8-sig").splitlines()
    if len(lines) < 8:
        raise ValueError("POSCAR 晶胞、元素或坐标记录不完整")
    if not remove_periodicity:
        raise PeriodicStructureError("POSCAR 包含周期性晶胞。")
    scales = [float(v) for v in lines[1].split("!")[0].split()]
    vectors = [tuple(map(float, line.split()[:3])) for line in lines[2:5]]
    if any(len(v) != 3 for v in vectors) or len(scales) not in (1, 3):
        raise ValueError("POSCAR 晶格矢量或缩放因子无效")
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = vectors
    volume = abs(ax * (by * cz - bz * cy) + ay * (bz * cx - bx * cz) + az * (bx * cy - by * cx))
    if not math.isfinite(volume) or volume == 0 or any(not math.isfinite(v) or v == 0 for v in scales):
        raise ValueError("POSCAR 的晶胞体积或缩放因子无效")
    if len(scales) == 1:
        scale = scales[0] if scales[0] > 0 else (-scales[0] / volume) ** (1 / 3)
        scales = [scale] * 3
    elif min(scales) <= 0:
        raise ValueError("POSCAR 的三个轴缩放因子必须为正")
    elements = lines[5].split("!")[0].split()
    if not elements or any(s not in ATOMIC_NUMBERS for s in elements):
        raise ValueError("需要显式给出元素名称的 VASP 5/6 POSCAR")
    counts = list(map(int, lines[6].split("!")[0].split()))
    if len(elements) != len(counts) or min(counts) < 0:
        raise ValueError("POSCAR 元素与原子数不匹配")
    start = 8 if lines[7].strip().lower().startswith("s") else 7
    if start >= len(lines) or len(lines) - start - 1 < sum(counts):
        raise ValueError("POSCAR 坐标记录不足")
    mode = lines[start].strip().lower()[:1]
    if mode not in ("d", "c", "k"):
        raise ValueError("POSCAR 需要 Direct 或 Cartesian 坐标模式")
    rows = iter(lines[start + 1:])
    atoms = []
    for symbol, count in zip(elements, counts):
        for _ in range(count):
            point = list(map(float, next(rows).split()[:3]))
            if len(point) != 3:
                raise ValueError("POSCAR 的原子位置需要三个坐标")
            if mode == "d":
                point = [sum(point[j] * vectors[j][i] for j in range(3)) for i in range(3)]
            atoms.append(Atom(symbol, *(p * s for p, s in zip(point, scales))))
    molecule = Molecule(name, tuple(atoms))
    molecule.validate_structure()
    return StructureRecord(molecule, removed_periodicity=True)


def run_babel_worker(raw, *arguments):
    """Run one isolated native operation and decode its JSON response."""
    frozen = getattr(sys, "frozen", False)
    args = [sys.executable, "--babel-worker"] if frozen else [sys.executable, "-m", "orcaview.io.babel_worker"]
    args.extend(arguments)
    env = os.environ.copy()
    if not frozen:
        # Also support a source checkout imported by adding src to sys.path.
        env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(Path(__file__).resolve().parents[2]),
                                                           env.get("PYTHONPATH"))))
    try:
        result = subprocess.run(args, input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=90, env=env)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Open Babel 操作超时") from exc
    try:
        payload = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Open Babel 未能完成结构处理") from exc
    if not isinstance(payload, dict):
        raise ValueError("Open Babel 未能完成结构处理")
    if result.returncode or "error" in payload:
        raise ValueError(payload.get("error", "Open Babel 未能完成结构处理"))
    return payload


def read_babel_structure(raw, name, format_id, *, remove_periodicity=False):
    if format_id == "xyz":
        return read_xyz_structure(raw, name, remove_periodicity=remove_periodicity)
    if format_id == "poscar":
        return _read_poscar(raw, name, remove_periodicity)
    if format_id not in BABEL_FORMATS.values():
        raise ValueError(f"不支持的分子文件类型：{format_id}")
    if format_id == "cif" and not remove_periodicity and re.search(
            rb"(?im)^\s*_(?:cell_length_[abc]|atom_site_fract_[xyz])(?:\s|$)", raw):
        raise PeriodicStructureError("CIF 声明了周期性晶胞。")
    arguments = (format_id, "--finite") if remove_periodicity else (format_id,)
    payload = run_babel_worker(raw, *arguments)
    if payload.get("periodic"):
        raise PeriodicStructureError("该结构包含周期性晶胞。")
    molecule = Molecule(name, tuple(Atom(*row) for row in payload["atoms"]),
                        tuple(Bond(*row) for row in payload["bonds"]),
                        payload["charge"], payload["multiplicity"])
    molecule.validate_structure()
    return StructureRecord(molecule, generated_3d=payload["generated"], removed_periodicity=payload["finite"])

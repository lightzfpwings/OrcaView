"""Import nuclear geometries without executing quantum-chemistry inputs."""

from dataclasses import replace
from pathlib import Path
import re

from ..core.provenance import ArtifactRef
from ._quantum_geometry import atom, check_periodic, geometry
from .structure_record import PeriodicStructureError


QUANTUM_FORMATS = {
    ".gjf": "gaussian-input", ".com": "gaussian-input", ".gau": "gaussian-input",
    ".g09": "gaussian-input", ".g16": "gaussian-input", ".inp": "orca-input", ".orca": "orca-input",
    ".molden": "molden", ".molden.input": "molden", ".mold": "molden",
    ".fchk": "gaussian-fchk", ".fch": "gaussian-fchk",
    ".wfx": "wfx", ".wfn": "wfn", ".mwfn": "mwfn",
}


def _gaussian_units(route):
    unit, degrees = "angstrom", True
    match = re.search(r"(?i)\bunits\s*(?:=\s*)?(?:\(([^)]*)\)|([A-Za-z]+))", route)
    if match:
        for keyword in re.split(r"[,\s]+", (match[1] or match[2]).strip().lower()):
            if keyword in ("bohr", "bohrs", "au"):
                unit = "bohr"
            elif keyword in ("ang", "angs", "angstrom", "angstroms"):
                unit = "angstrom"
            elif keyword in ("deg", "degree", "degrees"):
                degrees = True
            elif keyword in ("rad", "radian", "radians"):
                degrees = False
            else:
                raise ValueError(f"未知 Gaussian 坐标单位：{keyword}")
    return unit, degrees


def _gaussian(path, text, remove_periodicity):
    # Route, title and molecule specification are separate blank-terminated
    # sections. A pair of integers in a title or basis set is not a geometry.
    if re.search(r"(?im)^[ \t]*--link1--[ \t]*$", text):
        raise ValueError("Gaussian 多作业输入请先拆分为单个作业")
    start = re.search(r"(?m)^[ \t]*#", text)
    if start is None:
        raise ValueError("找不到 Gaussian 路由行（#）")
    sections = re.split(r"\n[ \t]*\n(?:[ \t]*\n)*", text[start.start():].strip(), maxsplit=3)
    if len(sections) < 3:
        raise ValueError("Gaussian 输入缺少显式分子坐标；检查点坐标需另开 FCHK")
    route, _, molecule = sections[:3]
    if re.search(r"(?i)\bqst[23]\b", route):
        raise ValueError("Gaussian QST 输入包含多套结构，请先拆分")
    unit, degrees = _gaussian_units(route)
    # Some writers put Variables:/Constants: immediately after the atoms,
    # others start a separate blank-delimited variables section.
    definitions = sections[3] if len(sections) > 3 else ""
    marker = re.search(r"(?im)^\s*(?:variables|constants)\s*:\s*$", molecule)
    if marker:
        definitions = molecule[marker.start():] + "\n" + definitions
        molecule = molecule[:marker.start()]
    rows = [row.split("!", 1)[0].strip().replace(",", " ").split()
            for row in molecule.splitlines() if row.split("!", 1)[0].strip()]
    if not rows or not re.fullmatch(r"(?:[-+]?\d+ [-+]?\d+)(?: [-+]?\d+ [-+]?\d+)*", " ".join(rows[0])):
        raise ValueError("Gaussian 坐标段缺少电荷和自旋多重度")
    charge, mult = map(int, rows[0][:2])
    periodic = any(row[0].lower() == "tv" for row in rows[1:])
    check_periodic(periodic, remove_periodicity)
    if len(rows) > 1 and len(rows[1]) == 1:
        from ._gaussian_zmatrix import z_matrix_atoms

        nuclear_rows = rows[1:]
        if periodic:
            first_tv = next(i for i, row in enumerate(nuclear_rows) if row[0].lower() == "tv")
            if any(row[0].lower() != "tv" for row in nuclear_rows[first_tv:]):
                raise ValueError("带周期矢量的 Gaussian Z 矩阵需将 Tv 放在原子表末尾")
            nuclear_rows = nuclear_rows[:first_tv]
        return geometry(path.stem, z_matrix_atoms(nuclear_rows, definitions, unit, degrees),
                        unit, charge, mult, periodic)
    atoms = []
    for row in rows[1:]:
        if row[0].lower() == "tv":
            continue
        label = re.fullmatch(r"([A-Za-z]{1,2})\d*(?:\([^)]*\))?|(\d+)", row[0])
        if not label or not (len(row) == 4 or (len(row) == 5 and row[1] in ("-1", "0", "1"))):
            raise ValueError("Gaussian 分子输入需要显式笛卡尔坐标或常规 Z 矩阵；无法识别此混合或分层格式")
        atoms.append(atom(label[1] or label[2], row[-3:], unit))
    return geometry(path.stem, atoms, unit, charge, mult, periodic)


def _external_xyz(path, filename, unit, charge, mult, remove_periodicity):
    from .babel_structure import read_xyz_structure

    quoted = filename[:1] in ("'", '"')
    if quoted and filename[-1:] != filename[0]:
        raise ValueError("ORCA 外部坐标文件名引号不匹配")
    name = filename[1:-1] if quoted else filename
    source = (path.parent / name).resolve()
    if source.suffix.lower() not in (".xyz", ".extxyz") or not source.is_file():
        raise ValueError(f"找不到本地 XYZ 坐标文件：{source}")
    raw = source.read_bytes()
    ref = ArtifactRef.from_bytes(raw, "xyz", str(source))
    try:
        record = read_xyz_structure(raw, source.stem, remove_periodicity=remove_periodicity, default_unit=unit)
    except PeriodicStructureError as exc:
        exc.source = ref
        raise
    molecule = replace(record.molecule, name=path.stem, charge=charge, multiplicity=mult)
    if mult < 1:
        raise ValueError("ORCA 自旋多重度必须大于零")
    return replace(record, molecule=molecule, auxiliary_sources=(ref,))


def _orca(path, text, remove_periodicity):
    lines = [line.split("#", 1)[0].strip() for line in text.splitlines()]
    text = "\n".join(lines)
    units = []
    for line in lines:
        if line.startswith("!"):
            units.extend(re.findall(r"(?i)\b(bohrs?|angs)\b", line))
    blocks = list(re.finditer(r"(?im)^%coords\b", text))
    stars = list(re.finditer(r"(?im)^\*[ \t]*(xyzfile|xyz|int(?:ernal)?|gzmt|pdbfile)\b([^\n]*)", text))
    if len(stars) > 1 or len(blocks) > 1:
        raise ValueError("ORCA 输入含多个几何定义，请拆分为单个结构")
    block = ""
    if blocks:
        after = text[blocks[0].end():]
        # The atom rows occupy the nested 'coords ... end'; coordinate
        # settings precede that block or the outer 'end' in a units-only block.
        block = re.split(r"(?im)^\s*end\b", after, maxsplit=1)[0]
        units.extend(re.findall(r"(?i)\bunits?\s+(bohrs?|angs)\b", block))
    if len({u.lower().startswith("bohr") for u in units}) > 1:
        raise ValueError("ORCA 输入声明了相互冲突的长度单位")
    unit = "bohr" if units and units[-1].lower().startswith("bohr") else "angstrom"
    nested = re.search(r"(?im)^[ \t]*coords[ \t]*$", block)
    if stars:
        if nested:
            raise ValueError("ORCA 输入同时包含两套坐标")
        header = stars[0]
        form = header[1].lower()
        state = header[2].split(maxsplit=2)
        if len(state) != (3 if form == "xyzfile" else 2):
            raise ValueError("ORCA 坐标头需要电荷、自旋多重度以及 xyzfile 的文件名")
        charge, mult = map(int, state[:2])
        if form == "xyzfile":
            return _external_xyz(path, state[2], unit, charge, mult, remove_periodicity)
        if form != "xyz":
            raise ValueError("此 ORCA 输入需要先转换为笛卡尔坐标（xyz 或 xyzfile）")
        body, end, _ = text[header.end():].partition("\n*")
        if not end:
            raise ValueError("ORCA 坐标段缺少结束符 *")
    elif nested:
        form = re.search(r"(?i)\bctyp(?:e)?\s+(\w+)", block[:nested.start()])
        if form and form[1].lower() != "xyz":
            raise ValueError("ORCA %coords 需要 CTyp xyz")
        charge_field = re.search(r"(?i)\bcharge\s+([-+]?\d+)\b", block[:nested.start()])
        mult_field = re.search(r"(?i)\bmult\s+(\d+)\b", block[:nested.start()])
        charge = int(charge_field[1]) if charge_field else 0
        mult = int(mult_field[1]) if mult_field else 1
        body = block[nested.end():]
    else:
        raise ValueError("找不到 ORCA 的 * xyz、* xyzfile 或 %coords 笛卡尔坐标段")
    atoms = []
    for row in body.splitlines():
        if not row:
            continue
        fields = row.split()
        if len(fields) != 4:
            raise ValueError(f"ORCA 坐标行需要一个实原子和三个坐标：{row}")
        label = re.sub(r"\(\d+\)$", "", fields[0])  # fragment identifier
        atoms.append(atom(label, fields[1:], unit))
    return geometry(path.stem, atoms, unit, charge, mult)


def read_quantum_structure(path, raw, *, remove_periodicity=False, format_id=None):
    """Read a single explicit molecular geometry. All returned positions are Å."""
    from ._wavefunction_geometry import read_wavefunction

    path = Path(path)
    suffix = ".molden.input" if path.name.lower().endswith(".molden.input") else path.suffix.lower()
    fmt = format_id or QUANTUM_FORMATS.get(suffix)
    if fmt is None:
        raise ValueError(f"无法识别的量化输入或波函数类型：{path.name}")
    if b"\x00" in raw:
        raise ValueError("需要文本波函数或量化输入；检测到二进制数据")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if fmt == "gaussian-input":
        return _gaussian(path, text, remove_periodicity)
    if fmt == "orca-input":
        return _orca(path, text, remove_periodicity)
    name = path.name[:-len(suffix)] if suffix == ".molden.input" else path.stem
    return read_wavefunction(fmt, name, text, remove_periodicity)

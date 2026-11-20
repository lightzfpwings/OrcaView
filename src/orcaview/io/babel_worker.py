"""Private, single-file Open Babel subprocess. The stdout protocol is UTF-8 JSON."""

import json
import math
import re
import sys
from xml.etree import ElementTree


def _single_record(text, fmt):
    if fmt in ("sdf", "mol"):
        records = re.split(r"(?m)^\$\$\$\$[ \t]*\r?$", text)
        multiple = sum(bool(r.strip()) for r in records) > 1
    elif fmt in ("smi", "inchi"):
        multiple = sum(bool(line.strip()) and not line.startswith("#") for line in text.splitlines()) > 1
    else:
        marker = {"mol2": r"^@<TRIPOS>MOLECULE\s*$", "cif": r"^data_\S*", "pdb": r"^MODEL\s+"}[fmt]
        multiple = len(re.findall(marker, text, re.M | re.I)) > 1
    if multiple:
        raise ValueError("文件含多个分子、模型或数据块，请选择单个结构记录")


def _single_xml(text, fmt):
    if "<!ENTITY" in text:
        raise ValueError("结构 XML 不能引用自定义实体")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValueError("化学结构 XML 不完整") from exc
    nodes = list(root.iter())
    tag = "fragment" if fmt == "cdxml" else "molecule"
    if sum(node.tag.rsplit("}", 1)[-1] == tag for node in nodes) != 1:
        raise ValueError("请选择只含一个分子的 XML 结构")
    if fmt == "cdxml":
        for node in nodes:
            if node.tag == "n" and node.get("NodeType", "Element") not in ("Element", "Unspecified"):
                raise ValueError("ChemDraw 缩写或查询节点请先展开为显式元素")
            if node.tag == "b" and node.get("Order", "1") not in ("1", "2", "3"):
                raise ValueError("ChemDraw 结构需要明确的单、双或三键")
    # Re-serialization omits external DTDs. Only a self-contained structure
    # goes to the native reader, including for an ordinary ChemDraw DOCTYPE.
    return ElementTree.tostring(root, encoding="unicode")


def _is_periodic(text, fmt, cell):
    if fmt == "pdb":
        # PDB uses a 1 Å, right-angled, P 1 placeholder for noncrystal methods.
        record = next((line for line in text.splitlines() if line.startswith("CRYST1")), None)
        if record is not None:
            lengths = [float(record[start:end]) for start, end in ((6, 15), (15, 24), (24, 33))]
            angles = [float(record[start:end]) for start, end in ((33, 40), (40, 47), (47, 54))]
            group = record[55:66].replace(" ", "")
            return not (lengths == [1.] * 3 and angles == [90.] * 3 and group in ("", "P1"))
    if cell is not None:
        return True
    if fmt == "mol2" and "@<TRIPOS>CRYSIN" in text.upper():
        return True
    if fmt == "cif" and re.search(r"(?im)^\s*_(cell_length_|atom_site_fract_)", text):
        raise ValueError("CIF 含晶格声明，但无法确定有效的晶胞或笛卡尔坐标")
    return False


def _convert(raw, fmt, finite):
    try:
        from openbabel import openbabel as ob
    except ImportError as exc:
        raise ValueError("无法加载 Open Babel，请安装 OrcaView 桌面依赖或使用内嵌引擎的安装包") from exc
    text = raw.decode("utf-8-sig")
    if "\x00" in text:
        raise ValueError("分子文件应为文本")
    if fmt in ("cdxml", "cml"):
        text = _single_xml(text, fmt)
    else:
        _single_record(text, fmt)
    declared_cell = False
    if fmt in ("pdb", "mol2"):
        declared_cell = _is_periodic(text, fmt, None)
        if declared_cell and not finite:
            return {"periodic": True}
        # Both formats supply atom positions in Cartesian Å. The cell is
        # dispensable here and native readers must not bond periodic images.
        if fmt == "pdb":
            text = re.sub(r"(?m)^CRYST1[^\n]*\n?", "", text)
        else:
            text = re.sub(r"(?ims)^@<TRIPOS>CRYSIN[^\n]*\n.*?(?=^@<TRIPOS>|\Z)", "", text)
    conversion = ob.OBConversion()
    if not conversion.SetInFormat(fmt):
        raise ValueError(f"Open Babel 缺少 {fmt} 读取插件")
    if fmt == "cif":
        conversion.AddOption("b", conversion.INOPTIONS)
    mol = ob.OBMol()
    if not conversion.ReadString(mol, text) or mol.NumAtoms() == 0:
        raise ValueError("Open Babel 未读取到有效的分子结构")
    cell_data = mol.GetData(ob.UnitCell)
    cell = ob.toUnitCell(cell_data) if cell_data is not None else None
    periodic = declared_cell or _is_periodic(text, fmt, cell)
    if periodic and not finite:
        return {"periodic": True}
    if periodic and fmt == "cif":
        if cell is None or not math.isfinite(cell.GetCellVolume()) or cell.GetCellVolume() <= 0:
            raise ValueError("CIF 缺少有效的晶格矢量")
        for atom in ob.OBMolAtomIter(mol):
            occupancy = atom.GetData("_atom_site_occupancy")
            if occupancy is not None and not math.isclose(ob.toPairFloatingPoint(occupancy).GetGenericValue(), 1.0):
                raise ValueError("CIF 含部分占据的原子位点，需先选择有序结构")
        cell.FillUnitCell(mol)

    generated = fmt in ("smi", "inchi", "cdxml") or (fmt == "cml" and not periodic
                                                      and mol.GetDimension() < 3)
    if fmt in ("mol", "sdf"):
        header = text.splitlines()[1]
        dimension = re.search(r"(2D|3D)\s*$", header, re.I)
        generated = (dimension.group(1).upper() == "2D" if dimension else mol.GetDimension() < 3)
        if generated and any(atom.GetZ() != 0 for atom in ob.OBMolAtomIter(mol)):
            generated = False
    if generated:
        op = ob.OBOp.FindType("gen3D")
        if op is None or not op.Do(mol, "medium") or mol.GetDimension() != 3:
            raise ValueError("Open Babel 无法生成保留分子立体化学的三维构象")
        if mol.NumAtoms() > 1 and not mol.HasNonZeroCoords():
            raise ValueError("Open Babel 未生成有效三维坐标")

    # After detaching a crystal, the viewport perceives display bonds from
    # finite Cartesian separations only. Native crystal edges may span images.
    bonds = [] if periodic else [
        (bond.GetBeginAtomIdx() - 1, bond.GetEndAtomIdx() - 1, bond.GetBondOrder())
        for bond in ob.OBMolBondIter(mol)
    ]
    atoms = []
    for atom in ob.OBMolAtomIter(mol):
        if atom.GetAtomicNum() < 1:
            raise ValueError("结构含虚拟原子或未识别的元素")
        if atom.GetIsotope():
            raise ValueError("当前分子模型未保存同位素质量，无法完整读取此结构")
        atoms.append((ob.GetSymbol(atom.GetAtomicNum()), atom.GetX(), atom.GetY(), atom.GetZ()))
    return {"atoms": atoms, "bonds": bonds, "charge": mol.GetTotalCharge(),
            "multiplicity": mol.GetTotalSpinMultiplicity(), "generated": generated, "finite": periodic}


def main(args=None):
    args = sys.argv[1:] if args is None else args
    try:
        if not args or args[0] not in ("sdf", "mol", "mol2", "pdb", "smi", "inchi", "cif", "cdxml", "cml"):
            raise ValueError("未知的 Open Babel 读取格式")
        result = _convert(sys.stdin.buffer.read(), args[0], "--finite" in args[1:])
        encoded = json.dumps(result, allow_nan=False)
    except (ValueError, RuntimeError, OSError) as exc:
        sys.stdout.buffer.write(json.dumps({"error": str(exc)}).encode("utf-8"))
        return 1
    sys.stdout.buffer.write(encoded.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

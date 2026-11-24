"""Private, single-file Open Babel subprocess. The stdout protocol is UTF-8 JSON."""

from contextlib import ExitStack, contextmanager
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree


def prepare_windows_babel_data(source, destination):
    """Copy wheel data with the LF byte offsets used by OBBuilder's fragment index."""
    def copy_resource(src, dst):
        if Path(src).name == "rigid-fragments.txt":
            Path(dst).write_bytes(Path(src).read_bytes().replace(b"\r\n", b"\n"))
        else:
            shutil.copyfile(src, dst)

    shutil.copytree(source, destination, copy_function=copy_resource, dirs_exist_ok=True)


@contextmanager
def _windows_resources():
    if sys.platform != "win32":
        yield
        return
    import ctypes
    from openbabel import openbabel as ob

    package = Path(ob.__file__).resolve().parent
    plugins = package / "bin"
    if not (plugins / "plugin_forcefields.obf").is_file():
        # Other Open Babel distributions use a different plugin layout.
        yield
        return
    data = package / "share" / "openbabel" / ob.OBReleaseVersion()
    if not (data / "rigid-fragments.txt").is_file():
        data = plugins / "data"
    # The native loader enumerates plugins with ANSI Win32 calls. Load the
    # wheel's known plugin directory through LoadLibraryExW for Unicode paths.
    libraries = [ctypes.WinDLL(str(path)) for path in sorted(plugins.glob("*.obf"))]
    with ExitStack() as stack:
        with (data / "rigid-fragments.txt").open("rb") as source:
            raw_wheel = source.readline().endswith(b"\r\n")
        if raw_wheel:
            # pip installs the original CRLF table. Keep site-packages read-only.
            staged = Path(stack.enter_context(TemporaryDirectory()))
            prepare_windows_babel_data(data, staged)
            data = staged
        # Native streams first look for an ASCII filename in the working
        # directory. Only this private worker changes its working directory.
        stack.callback(os.chdir, Path.cwd())
        os.chdir(data)
        yield libraries


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
        raise ValueError("The file contains multiple molecules, models or data blocks. Select a single structure record.")


def _single_xml(text, fmt):
    if "<!ENTITY" in text:
        raise ValueError("Custom XML entities are not allowed in structure files.")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValueError("Incomplete chemical structure XML") from exc
    nodes = list(root.iter())
    tag = "fragment" if fmt == "cdxml" else "molecule"
    if sum(node.tag.rsplit("}", 1)[-1] == tag for node in nodes) != 1:
        raise ValueError("Select an XML structure containing a single molecule.")
    if fmt == "cdxml":
        for node in nodes:
            if node.tag == "n" and node.get("NodeType", "Element") not in ("Element", "Unspecified"):
                raise ValueError("Expand ChemDraw abbreviations and query nodes into explicit elements first.")
            if node.tag == "b" and node.get("Order", "1") not in ("1", "2", "3"):
                raise ValueError("Specify explicit single, double or triple bonds in the ChemDraw structure.")
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
        raise ValueError("The CIF declares a lattice but lacks a valid cell or Cartesian coordinates.")
    return False


def _convert(raw, fmt, finite):
    try:
        from openbabel import openbabel as ob
    except ImportError as exc:
        raise ValueError("Open Babel could not be loaded. Install the OrcaView desktop dependencies or use the distribution with the bundled engine.") from exc
    text = raw.decode("utf-8-sig")
    if "\x00" in text:
        raise ValueError("The molecular file must contain text.")
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
        raise ValueError(f"Open Babel input plugin for {fmt} is missing.")
    if fmt == "cif":
        conversion.AddOption("b", conversion.INOPTIONS)
    mol = ob.OBMol()
    if not conversion.ReadString(mol, text) or mol.NumAtoms() == 0:
        raise ValueError("Open Babel did not read a valid molecular structure.")
    cell_data = mol.GetData(ob.UnitCell)
    cell = ob.toUnitCell(cell_data) if cell_data is not None else None
    periodic = declared_cell or _is_periodic(text, fmt, cell)
    if periodic and not finite:
        return {"periodic": True}
    if periodic and fmt == "cif":
        if cell is None or not math.isfinite(cell.GetCellVolume()) or cell.GetCellVolume() <= 0:
            raise ValueError("Missing valid lattice vectors in CIF")
        for atom in ob.OBMolAtomIter(mol):
            occupancy = atom.GetData("_atom_site_occupancy")
            if occupancy is not None and not math.isclose(ob.toPairFloatingPoint(occupancy).GetGenericValue(), 1.0):
                raise ValueError("The CIF contains partially occupied sites. Select an ordered structure first.")
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
            raise ValueError("Open Babel could not generate a 3D conformer preserving the molecule's stereochemistry.")
        if mol.NumAtoms() > 1 and not mol.HasNonZeroCoords():
            raise ValueError("Open Babel did not generate valid 3D coordinates.")

    # After detaching a crystal, the viewport perceives display bonds from
    # finite Cartesian separations only. Native crystal edges may span images.
    bonds = [] if periodic else [
        (bond.GetBeginAtomIdx() - 1, bond.GetEndAtomIdx() - 1, bond.GetBondOrder())
        for bond in ob.OBMolBondIter(mol)
    ]
    atoms = []
    for atom in ob.OBMolAtomIter(mol):
        if atom.GetAtomicNum() < 1:
            raise ValueError("The structure contains dummy atoms or unknown elements.")
        if atom.GetIsotope():
            raise ValueError("The molecular model does not retain isotope masses and cannot fully import this structure.")
        atoms.append((ob.GetSymbol(atom.GetAtomicNum()), atom.GetX(), atom.GetY(), atom.GetZ()))
    return {"atoms": atoms, "bonds": bonds, "charge": mol.GetTotalCharge(),
            "multiplicity": mol.GetTotalSpinMultiplicity(), "generated": generated, "finite": periodic}


def main(args=None):
    args = sys.argv[1:] if args is None else args
    try:
        with _windows_resources():
            if args and args[0] in ("optimize-2d", "optimize-3d", "perceive-orders"):
                from orcaview.editing.optimization import optimize_worker
                result = optimize_worker(json.load(sys.stdin.buffer), args[0])
            elif args and args[0] in ("sdf", "mol", "mol2", "pdb", "smi", "inchi", "cif", "cdxml", "cml"):
                result = _convert(sys.stdin.buffer.read(), args[0], "--finite" in args[1:])
            else:
                raise ValueError("Unknown Open Babel input format")
        encoded = json.dumps(result, allow_nan=False)
    except ImportError:
        sys.stdout.buffer.write(json.dumps({"error": "Open Babel could not be loaded. Install the OrcaView desktop dependencies or use the distribution with the bundled engine."}).encode("utf-8"))
        return 1
    except (ValueError, RuntimeError, OSError) as exc:
        sys.stdout.buffer.write(json.dumps({"error": str(exc)}).encode("utf-8"))
        return 1
    sys.stdout.buffer.write(encoded.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

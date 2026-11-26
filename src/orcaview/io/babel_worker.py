"""Private, single-file Open Babel subprocess. The stdout protocol is UTF-8 JSON."""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from orcaview.io.structure_record import polymer_atom_role


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
    has_topology = fmt == "cdxml" or any(node.tag.rsplit("}", 1)[-1] in ("bond", "bondArray")
                                         for node in nodes)
    return ElementTree.tostring(root, encoding="unicode"), has_topology


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
    explicit_graph = fmt in ("mol", "sdf", "smi", "inchi")
    if fmt in ("cdxml", "cml"):
        text, explicit_graph = _single_xml(text, fmt)
    else:
        _single_record(text, fmt)
        if fmt == "mol2":
            # The bond count after the atom count and the BOND section are optional.
            explicit_graph = bool(re.search(r"(?im)^@<TRIPOS>MOLECULE[^\n]*\n[^\n]*\n[ \t]*\d+[ \t]+\d+\b"
                                            r"|^@<TRIPOS>BOND\b", text))
        elif fmt == "pdb":
            explicit_graph = bool(re.search(r"(?m)^CONECT\s+\d", text))
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

    payload = _molecule_payload(mol, ob, explicit_graph=explicit_graph, generated=generated,
                                periodic=periodic)
    if fmt == "pdb":
        payload["polymer_roles"], payload["backbone_links"] = _pdb_polymer_atoms(mol, ob, text)
    return payload


_AMINO_ACIDS = frozenset("ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL SEC PYL ASX GLX".split())
_DEOXY_RESIDUES = frozenset(("DA", "DC", "DG", "DT", "DI", "DU", "T", "THY"))


@dataclass(frozen=True)
class _BackboneSite:
    label: str
    residue: int
    chain: str
    segment: int
    sequence: int
    insertion: str
    serial: int

    def joins(self, other, explicit):
        if self.chain != other.chain or self.segment != other.segment:
            return False
        if self.residue == other.residue:
            return (self.label, other.label) in (
                ("N", "CA"), ("CA", "C"), ("P", "O5'"), ("O5'", "C5'"),
                ("C5'", "C4'"), ("C4'", "C3'"), ("C3'", "O3'"))
        if (self.label, other.label) not in (("C", "N"), ("O3'", "P")):
            return False
        return (explicit or (other.sequence == self.sequence + 1 and not other.insertion)
                or (other.sequence == self.sequence and bool(other.insertion)
                    and ord(other.insertion) == ord(self.insertion or "@") + 1))


def _pdb_polymer_atoms(mol, ob, text):
    # MODRES identifies residues such as selenomethionine that are written
    # as HETATM records, while free ligands can have amino-acid residue names.
    parents, segments, explicit = {}, {}, set()
    segment = 0
    for line in text.splitlines():
        if line.startswith("MODRES") and len(line) >= 27:
            parents[line[16].strip(), line[18:22].strip(), line[22].strip(), line[12:15].strip()] = line[24:27].strip()
        elif line.startswith("TER"):
            segment += 1
        elif line.startswith(("ATOM  ", "HETATM")) and line[6:11].strip().isdigit():
            segments[int(line[6:11])] = segment
        elif line.startswith("CONECT"):
            fields = [line[i:i+5].strip() for i in range(6, min(len(line), 31), 5)]
            if fields and fields[0].isdigit():
                explicit.update(tuple(sorted((int(fields[0]), int(n)))) for n in fields[1:] if n.isdigit())
    roles = ["."] * mol.NumAtoms()
    backbone = {}
    dna_chains = {r.GetChain() for r in ob.OBResidueIter(mol) if r.GetName().strip() in _DEOXY_RESIDUES
                  and any(not r.IsHetAtom(atom) for atom in ob.OBResidueAtomIter(r))}
    for residue in ob.OBResidueIter(mol):
        name = residue.GetName().strip()
        chain = residue.GetChain()
        key = (chain.strip(" \0"), str(residue.GetNum()), residue.GetInsertionCode().strip(" \0"), name)
        standard = parents.get(key)
        if standard is None and all(residue.IsHetAtom(atom) for atom in ob.OBResidueAtomIter(residue)):
            continue
        monomer = standard or name
        if monomer in _AMINO_ACIDS:
            polymer = "protein"
        elif monomer in _DEOXY_RESIDUES or (chain in dna_chains and monomer in ("A", "C", "G", "I")):
            polymer = "dna"
        else:
            continue
        for atom in ob.OBResidueAtomIter(residue):
            i = atom.GetIdx() - 1
            label = residue.GetAtomID(atom).strip().upper().replace("*", "'")
            roles[i] = polymer_atom_role(polymer, label, ob.GetSymbol(atom.GetAtomicNum()))
            if roles[i] == "B":
                serial = residue.GetSerialNum(atom)
                backbone[i] = _BackboneSite(label, residue.GetIdx(), chain, segments.get(serial, 0), residue.GetNum(),
                                            residue.GetInsertionCode().strip(" \0"), serial)
    if all(role == "." for role in roles):
        return "", None
    # The native PDB reader can also bond by distance over chain breaks.
    # Keep named-path connections separately from the unmodified 3D graph.
    links = []
    for edge in ob.OBMolBondIter(mol):
        i, j = edge.GetBeginAtomIdx() - 1, edge.GetEndAtomIdx() - 1
        a, b = backbone.get(i), backbone.get(j)
        if not a or not b:
            continue
        deposited = tuple(sorted((a.serial, b.serial))) in explicit
        if a.joins(b, deposited) or b.joins(a, deposited):
            links.append(tuple(sorted((i, j))))
    return "".join(roles), sorted(links)


def _molecule_payload(mol, ob, *, explicit_graph, generated, periodic=False, polymer_roles=""):
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
    return {"atoms": atoms, "bonds": bonds, "bonds_explicit": explicit_graph and not periodic,
            "polymer_roles": polymer_roles,
            "charge": mol.GetTotalCharge(),
            "multiplicity": mol.GetTotalSpinMultiplicity(), "generated": generated, "finite": periodic}


def _sequence_worker(kind, sequence):
    from openbabel import openbabel as ob

    conversion = ob.OBConversion()
    if not conversion.SetInFormat("fasta"):
        raise ValueError("The Open Babel FASTA reader is unavailable.")
    # A fixed header selects the requested template even for an all-ACGT peptide.
    header = "protein" if kind == "protein" else "DNA"
    mol = ob.OBMol()
    read = conversion.ReadString(mol, f">{header}\n{sequence}\n")
    chains = 1 if kind == "protein" else 2
    if not read or mol.NumResidues() != len(sequence) * chains or not mol.HasNonZeroCoords():
        raise ValueError("Open Babel could not build the complete sequence.")
    # FASTA templates contain explicit hydrogens and bond orders but omit formal
    # charges. Count these from the drawn atoms, including the actual end groups.
    charge = 0
    for atom in ob.OBMolAtomIter(mol):
        number, valence = atom.GetAtomicNum(), atom.GetExplicitValence()
        if number == 8 and valence == 1:
            atom.SetFormalCharge(-1)
        elif number == 7 and valence == 4:
            atom.SetFormalCharge(1)
        charge += atom.GetFormalCharge()
    mol.SetTotalCharge(charge)
    mol.SetTotalSpinMultiplicity(1)
    roles = ["S"] * mol.NumAtoms()
    for residue in ob.OBResidueIter(mol):
        for atom in ob.OBResidueAtomIter(residue):
            roles[atom.GetIdx() - 1] = polymer_atom_role(kind, residue.GetAtomID(atom), ob.GetSymbol(atom.GetAtomicNum()))
    return _molecule_payload(mol, ob, explicit_graph=True, generated=True, polymer_roles="".join(roles))


def main(args=None):
    args = sys.argv[1:] if args is None else args
    try:
        with _windows_resources():
            if args and args[0] in ("optimize-2d", "optimize-3d", "optimize-hbonds", "perceive-orders"):
                from orcaview.editing.optimization import optimize_worker
                result = optimize_worker(json.load(sys.stdin.buffer), args[0])
            elif args in (["sequence", "protein"], ["sequence", "dna"]):
                result = _sequence_worker(args[1], sys.stdin.buffer.read().decode("ascii"))
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

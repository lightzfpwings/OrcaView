"""Exchange a finite Cartesian molecule and its displayed topology with the native worker."""

from orcaview.core.geometry import display_bonds, occupied_valences
from orcaview.core.models import COORDINATE_STYLES


def geometry_payload(molecule):
    molecule.validate_structure()
    bonds = display_bonds(molecule)
    payload = {
        "atoms": [(atom.element, atom.x, atom.y, atom.z) for atom in molecule.atoms],
        "bonds": [(bond.a, bond.b, bond.order) for bond in bonds],
        "bond_styles": [bond.style for bond in bonds],
        "charge": molecule.charge,
        "multiplicity": molecule.multiplicity,
    }
    if any(b.style == "aromatic" for b in bonds):
        # OBKekulize distinguishes pyridine n from pyrrole [nH] using the
        # implicit hydrogen count present *before* it assigns integer orders.
        occupied = occupied_valences(molecule, bonds)
        payload["aromatic_nh"] = [i for i, atom in enumerate(molecule.atoms)
                                  if atom.element in ("N", "P") and occupied[i] == 2]
    return payload


def build_obmol(payload, ob, *, layout_only=False):
    """Use editor row IDs and translate supported chemical bonds for the native operation."""
    mol = ob.OBMol()
    mol.BeginModify()
    for element, x, y, z in payload["atoms"]:
        atom = mol.NewAtom()
        atom.SetAtomicNum(ob.GetAtomicNum(element))
        atom.SetVector(x, y, z)
    flags = {"wedge": ob.OBBond.Wedge, "hollow_wedge": ob.OBBond.Wedge,
             "hashed_wedge": ob.OBBond.Hash, "wavy": ob.OBBond.WedgeOrHash,
             "wavy_wedge": ob.OBBond.WedgeOrHash, "crossed": ob.OBBond.CisOrTrans}
    aromatic = []
    styles = payload.get("bond_styles", ["plain"] * len(payload["bonds"]))
    if len(styles) != len(payload["bonds"]):
        raise ValueError("Open Babel 无法建立当前连接表")
    for (a, b, order), style in zip(payload["bonds"], styles):
        if style in COORDINATE_STYLES or style == "partial_triple":
            if not layout_only:
                raise ValueError("当前力场不能表示配位键或 2.5 级键，请使用二维整理")
            # gen2D only needs a connected graph. Its temporary integer orders
            # are never written back over an explicitly drawn bond.
            order = 1 if style in COORDINATE_STYLES else 2
        if style == "aromatic":
            aromatic.append((a + 1, b + 1))
            order = 1
        if not mol.AddBond(a + 1, b + 1, order, flags.get(style, 0)):
            raise ValueError("Open Babel 无法建立当前连接表")
    mol.EndModify()
    mol.SetTotalCharge(payload["charge"])
    mol.SetTotalSpinMultiplicity(payload["multiplicity"])
    if aromatic:
        for a, b in aromatic:
            mol.GetAtom(a).SetAromatic()
            mol.GetAtom(b).SetAromatic()
            mol.GetBond(a, b).SetAromatic()
        for i in payload.get("aromatic_nh", ()):
            mol.GetAtom(i + 1).SetImplicitHCount(1)
        mol.SetAromaticPerceived()
        kekulized = ob.OBKekulize(mol)
        if not layout_only:
            # A partial bond may have been sketched outside an aromatic ring.
            # A force field needs a chemically representable Kekulé form.
            for atom in ob.OBMolAtomIter(mol):
                ob.OBAtomAssignTypicalImplicitHydrogens(atom)
            mol.SetAromaticPerceived(False)
            if not kekulized or not all(mol.GetBond(a, b).IsAromatic() for a, b in aromatic):
                raise ValueError("当前 1.5 级键无法表示为芳香环，无法进行力场优化")
    return mol

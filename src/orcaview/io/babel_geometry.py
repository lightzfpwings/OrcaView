"""Exchange a finite Cartesian molecule and its displayed topology with the native worker."""

from dataclasses import replace

from orcaview.core.geometry import covalent_bonds, occupied_valences
from orcaview.core.models import COORDINATE_STYLES


def geometry_payload(molecule, *, bonds=None):
    """Send only chemical connectivity to Open Babel, preserving bond order and indices."""
    molecule.validate_structure()
    if bonds is None:
        bonds = covalent_bonds(molecule)
    else:
        bonds = tuple(bond for bond in bonds if bond.is_covalent)
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


def with_perceived_orders(bonds, orders):
    if (not isinstance(orders, list) or len(orders) != len(bonds)
            or any(type(order) is not int or order not in (1, 2, 3) for order in orders)):
        raise ValueError("Open Babel could not construct this bond graph.")
    return tuple(replace(bond, order=order) for bond, order in zip(bonds, orders))


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
        raise ValueError("Open Babel could not construct this bond graph.")
    for (a, b, order), style in zip(payload["bonds"], styles):
        if style in COORDINATE_STYLES or style == "partial_triple":
            if not layout_only:
                raise ValueError("The available force fields cannot represent coordinate bonds or order-2.5 bonds. Use 2D cleanup.")
            # gen2D only needs a connected graph. Its temporary integer orders
            # are never written back over an explicitly drawn bond.
            order = 1 if style in COORDINATE_STYLES else 2
        if style == "aromatic":
            aromatic.append((a + 1, b + 1))
            order = 1
        if not mol.AddBond(a + 1, b + 1, order, flags.get(style, 0)):
            raise ValueError("Open Babel could not construct this bond graph.")
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
                raise ValueError("The current order-1.5 bonds do not form a supported aromatic system for force-field optimization.")
    return mol

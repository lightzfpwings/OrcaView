"""Transfer one bonded molecule using local indices and an OrcaView MIME type."""

from dataclasses import asdict, replace
import json

from PySide6.QtCore import QMimeData

from orcaview.core.geometry import connected_component, display_bonds
from orcaview.core.models import Atom, Bond
from orcaview.editing.commands import InsertFragment


FRAGMENT_MIME = "application/x-orcaview-molecule+json"


def copy_fragment(snapshot, selected):
    if not selected:
        raise ValueError("Select atoms from one molecule to copy.")
    bonds = display_bonds(snapshot.molecule)
    component = connected_component(bonds, selected[0])
    if not component.issuperset(selected):
        raise ValueError("Select atoms from one molecule to copy.")
    indices = sorted(component)
    local = {old: new for new, old in enumerate(indices)}
    fragment = InsertFragment(
        tuple(snapshot.molecule.atoms[i] for i in indices),
        tuple(replace(bond, a=local[bond.a], b=local[bond.b]) for bond in bonds
              if bond.a in local and bond.b in local),
        tuple(snapshot.sketch_xy[i] for i in indices) if snapshot.sketch_xy is not None else None,
    )
    data = QMimeData()
    data.setData(FRAGMENT_MIME, json.dumps({"version": 1, **asdict(fragment)}, allow_nan=False).encode("utf-8"))
    return data, len(indices)


def read_fragment(mime):
    if mime is None or not mime.hasFormat(FRAGMENT_MIME):
        raise ValueError("The clipboard does not contain an OrcaView molecule.")
    try:
        data = json.loads(bytes(mime.data(FRAGMENT_MIME)))
        if type(data) is not dict or type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("Unsupported clipboard version")
        sketch_xy = data["sketch_xy"]
        if not isinstance(data["atoms"], list) or not isinstance(data["bonds"], list):
            raise ValueError("Invalid clipboard atoms or bonds")
        if sketch_xy is not None and not isinstance(sketch_xy, list):
            raise ValueError("Invalid clipboard sketch")
        return InsertFragment(
            tuple(Atom(**atom) for atom in data["atoms"]),
            tuple(Bond(**bond) for bond in data["bonds"]),
            tuple(tuple(point) for point in sketch_xy) if sketch_xy is not None else None,
        )
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise ValueError("The molecule on the clipboard could not be read.") from exc

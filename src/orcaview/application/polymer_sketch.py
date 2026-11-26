"""Resolve source residue annotations onto the atom order of an editable geometry."""

import json

from orcaview.application.document import HISTORY_RESTORE_KIND
from orcaview.core.geometry import display_bonds
from orcaview.core.models import COORDINATE_STYLES
from orcaview.core.polymer_backbone import topology_roles, validate_backbone_links
from orcaview.core.snapshots import GeometryRef


def _source_roles(snapshot, params):
    operation = params.get("operation")
    roles = params.get("polymer_roles", "")
    if roles:
        # Pasted atoms occupy the tail of the insertion snapshot.
        size = len(snapshot.atom_ids)
        valid_size = len(roles) == size or (operation == "insert-fragment" and len(roles) < size)
        if valid_size and not set(roles).difference("BS."):
            return roles
    if operation == "generate-biopolymer":
        # a67 retained the polymer type and full connectivity but no residue names.
        try:
            kind = json.loads(params["request"])["polymer"]
        except (KeyError, ValueError, TypeError):
            return ""
        if kind in ("protein", "dna"):
            return topology_roles(snapshot.molecule, kind)
    return ""


def _fill_new_roles(snapshot, known):
    roles = [known.get(atom_id) for atom_id in snapshot.atom_ids]
    new = {i for i, role in enumerate(roles) if role is None}
    if new:
        inferred = topology_roles(snapshot.molecule)
        for i in new:
            roles[i] = inferred[i] if inferred else "."
        # New substituents on a known polymer are outside its annotated backbone.
        # A separately drawn or pasted molecule keeps its own depiction.
        neighbors = {}
        for bond in snapshot.molecule.bonds:
            if bond.is_covalent and (bond.a in new or bond.b in new):
                neighbors.setdefault(bond.a, []).append(bond.b)
                neighbors.setdefault(bond.b, []).append(bond.a)
        pending = [i for i in neighbors if i not in new and roles[i] in ("B", "S")]
        while pending:
            for i in neighbors[pending.pop()]:
                if i in new:
                    new.remove(i)
                    if roles[i] == ".":
                        roles[i] = "S"
                    pending.append(i)
    return "".join(roles)


def _source_links(params, roles):
    if "backbone_links" not in params:
        return None
    try:
        links = tuple(tuple(edge) for edge in json.loads(params["backbone_links"]))
        validate_backbone_links(links, roles)
        return links
    except (ValueError, TypeError):
        return None


def _ancestors(document, snapshot):
    while snapshot is not None:
        params = dict(snapshot.provenance.parameters)
        yield snapshot, params
        parent = snapshot.parent
        if snapshot.provenance.kind == HISTORY_RESTORE_KIND:
            # Undo and redo restore the original branch's bonds as well as atom IDs.
            parent = GeometryRef(snapshot.ref.document_id, int(params["target_revision"]),
                                 snapshot_id=params["target_snapshot_id"])
        snapshot = document.resolve(parent) if parent is not None else None


def sketch_annotations(document, snapshot):
    """Return row-aligned roles and optional source-verified backbone links for the 2D view."""
    rows = {atom_id: i for i, atom_id in enumerate(snapshot.atom_ids)}
    known, groups, edits = {}, {}, {}
    links = set()
    for source, params in _ancestors(document, snapshot):
        if params.get("operation") == "set-bond":
            try:
                edit = json.loads(params["request"])
                pair = tuple(sorted((rows[edit["atom_a"]], rows[edit["atom_b"]])))
                edits.setdefault(pair, bool(edit["order"]) and edit.get("style") not in (*COORDINATE_STYLES, "hydrogen_bond"))
            except (ValueError, KeyError, TypeError):
                pass
        roles = _source_roles(source, params)
        if roles:
            ids = source.atom_ids[-len(roles):]
            new_rows = {i: rows[atom_id] for i, atom_id in enumerate(ids) if atom_id in rows and atom_id not in known}
            for i in new_rows:
                known[ids[i]] = roles[i]
            edges = _source_links(params, roles)
            if edges is not None:
                for i in new_rows:
                    if roles[i] == "B":
                        groups[new_rows[i]] = source.ref.snapshot_id
                links.update(tuple(sorted((new_rows[a], new_rows[b]))) for a, b in edges if a in new_rows and b in new_rows)
        if len(known) == len(rows):
            break
    if not known:
        return "", None
    roles = _fill_new_roles(snapshot, known)
    if not groups:
        return roles, None
    # Additional polymers from sequences or older projects use their own covalent edges.
    if roles.count("B") > len(groups) or len(set(groups.values())) > 1:
        for bond in display_bonds(document.molecule_with_topology(snapshot)):
            a, b = bond.a, bond.b
            if (roles[a] == roles[b] == "B" and bond.is_covalent and bond.style not in COORDINATE_STYLES
                    and (a not in groups or groups[a] != groups.get(b))):
                links.add(tuple(sorted((a, b))))
    for (a, b), connected in edits.items():
        if connected and roles[a] == roles[b] == "B":
            links.add((a, b))
        else:
            links.discard((a, b))
    return roles, tuple(sorted(links))

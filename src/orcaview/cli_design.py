"""Batch molecular design through the same revisioned editor used by the desktop."""

from dataclasses import asdict
import json
import math
from pathlib import Path
import sys

from orcaview.application.project import save_project
from orcaview.core.geometry import display_bonds
from orcaview.core.models import Atom
from orcaview.core.point_group import geometric_symmetry
from orcaview.core.snapshots import SelectionContext
from orcaview.core.symmetry import DEFAULT_TOLERANCE
from orcaview.editing import (
    AddAtoms, AddHydrogen, AttachAtom, CoordinateDefinition, DeleteAtoms, EditorService,
    GeometryEditCommand, InsertRing, MoveAtom, MoveSketchAtom, ReorderAtoms, ReplaceElement,
    SetBond, SetBondLength, SetDistance, SetElectronicState, SetSketchLayout, measure,
)
from orcaview.editing.coordinates import bond_moving_atoms
from orcaview.editing.diagnostics import design_diagnostics
from orcaview.editing.modeling import modeling_operation


_EDIT_TYPES = {cls.kind: cls for cls in (
    AddAtoms, AddHydrogen, AttachAtom, DeleteAtoms, InsertRing, MoveAtom, MoveSketchAtom,
    ReorderAtoms, ReplaceElement, SetBond, SetElectronicState, SetSketchLayout,
)}
_MODELING = {"add-hydrogens": "H", "clean-2d": "2D", "optimize-3d": "3D"}
_OTHER_ACTIONS = ("select", "measure", "set-bond-length", "set-distance", "undo", "redo",
                  "use-geometry", "diagnostics", "symmetry")


def register(sub):
    names = ", ".join(sorted((*_EDIT_TYPES, *_MODELING, *_OTHER_ACTIONS)))
    parser = sub.add_parser("design", help="Inspect or edit a structure with a sequence of JSON operations",
                            epilog="Operations: " + names + ". See docs/CLI_DESIGN.md for their arguments.")
    parser.add_argument("input", type=Path, help="Structure, result or OrcaView project")
    parser.add_argument("--finite", action="store_true", help="Import a periodic input as a finite structure")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--apply", action="append", metavar="JSON", help="One operation, repeat in execution order")
    source.add_argument("--script", metavar="FILE", help="Read a JSON array of operations; use - for standard input")
    parser.add_argument("-o", "--output", type=Path, help="Save the final project after all operations succeed")
    parser.set_defaults(handler=run_design)


def _array(data, label):
    if not isinstance(data, list):
        raise ValueError(f"{label} must be a JSON array")
    return data


def _atom_id(head, ref):
    if type(ref) is int:
        return head.id_at(ref - 1)
    if isinstance(ref, str):
        head.index_of(ref)
        return ref
    raise ValueError("An atom must be a one-based row or a stable atom ID")


def _edit_params(head, params):
    values = dict(params)
    for key in ("atom_id", "anchor_id", "atom_a", "atom_b"):
        if key in values:
            values[key] = _atom_id(head, values[key])
    for key in ("atom_ids", "moving_atom_ids", "fixed_atom_ids"):
        if key in values:
            values[key] = tuple(_atom_id(head, ref) for ref in _array(values[key], key))
    if "atom" in values:
        values["atom"] = Atom(**values["atom"])
    if "atoms" in values:
        values["atoms"] = tuple(Atom(**atom) for atom in _array(values["atoms"], "atoms"))
    if "xy" in values:
        values["xy"] = tuple(tuple(_array(row, "xy entry")) for row in _array(values["xy"], "xy"))
    if "center" in values:
        values["center"] = tuple(_array(values["center"], "center"))
    return values


def _use_geometry(editor, snapshot):
    for entry in editor.document.records()[0]:
        ref = entry.ref
        if (isinstance(snapshot, str) and ref.snapshot_id == snapshot
                or type(snapshot) is int and ref.revision == snapshot and ref.frame_id is None):
            editor.use_result_geometry(ref)
            return
    raise ValueError("Unknown revision number or snapshot ID")


def _symmetry(head, tolerance=DEFAULT_TOLERANCE):
    group, axis = geometric_symmetry(head.molecule, tolerance)
    order = "infinite" if math.isinf(axis.order) else int(axis.order)
    return {"point_group": group, "principal_axis": axis.direction, "order": order}


def _measure(head, atom_ids, kind="distance"):
    coord = CoordinateDefinition(head.ref, kind, atom_ids)
    return {"kind": kind, "atom_ids": atom_ids, "value": measure(head, coord), "unit": coord.unit}


def _bond_length(head, atom_ids, target):
    coord = CoordinateDefinition(head.ref, "distance", atom_ids)
    moving = bond_moving_atoms(head, coord, display_bonds(head.molecule))
    return SetBondLength(coord, target, moving, atom_ids[:1])


def _set_distance(head, atom_ids, target, moving_atom_ids, fixed_atom_ids=()):
    coord = CoordinateDefinition(head.ref, "distance", atom_ids)
    return SetDistance(coord, target, moving_atom_ids, fixed_atom_ids)


def _step(editor, name, params):
    head = editor.document.head
    values = _edit_params(head, params)
    if name in ("delete-atoms", "measure", "set-distance", "set-bond-length"):
        values.setdefault("atom_ids", editor.selection.atom_ids)
    if name in _EDIT_TYPES:
        operation = _EDIT_TYPES[name](**values)
    elif name == "set-bond-length":
        operation = _bond_length(head, **values)
    elif name == "set-distance":
        operation = _set_distance(head, **values)
    elif name in _MODELING:
        if values:
            raise ValueError(f"{name} takes no arguments")
        operation = modeling_operation(head, _MODELING[name])
        if name == "clean-2d" and operation.xy == head.sketch_xy:
            return {"changed": False}
    elif name == "select":
        editor.set_selection(SelectionContext(head.ref, **values))
        return {"atom_ids": editor.selection.atom_ids}
    elif name == "measure":
        return _measure(head, **values)
    elif name == "symmetry":
        return _symmetry(head, **values)
    elif name == "use-geometry":
        _use_geometry(editor, **values)
        return {}
    elif name in ("undo", "redo", "diagnostics"):
        if values:
            raise ValueError(f"{name} takes no arguments")
        if name == "diagnostics":
            return {"issues": design_diagnostics(head.molecule)}
        (editor.undo if name == "undo" else editor.redo)()
        return {}
    else:
        raise ValueError(f"Unknown design operation: {name}")
    result = editor.commit(editor.preview(GeometryEditCommand(head.ref, operation)))
    details = {"added_atom_ids": [result.snapshot.id_at(i) for i in result.mapping.added_indices]}
    if name == "optimize-3d":
        details["force_field"] = operation.method
    return details


def _summary(editor):
    head = editor.document.head
    molecule = head.molecule
    bonds = display_bonds(molecule)
    return {
        "geometry": asdict(head.ref), "name": molecule.name, "unit": "angstrom",
        "charge": molecule.charge, "multiplicity": molecule.multiplicity,
        "atoms": [dict(row=i, id=atom_id, **asdict(atom))
                  for i, (atom_id, atom) in enumerate(zip(head.atom_ids, molecule.atoms), 1)],
        "bonds": [dict(a=b.a + 1, b=b.b + 1, order=b.order, style=b.style) for b in bonds],
        "bond_source": "stored" if molecule.bonds or molecule.bonds_explicit else "inferred",
        "sketch_xy": head.sketch_xy, "selected_atom_ids": editor.selection.atom_ids,
        "diagnostics": design_diagnostics(molecule),
        "history": [asdict(s.ref) for s in editor.document.records()[0]],
    }


def run_design(args):
    from orcaview.cli_io import load_session

    if args.script is not None:
        raw = sys.stdin.read() if args.script == "-" else Path(args.script).read_text(encoding="utf-8-sig")
        steps = _array(json.loads(raw), "Design script")
    else:
        steps = [json.loads(text) for text in args.apply or ()]
    if args.output and args.output.resolve() == args.input.resolve() and args.input.suffix.lower() != ".json":
        raise ValueError("Choose a project output path distinct from the input structure")
    session = load_session(args.input, finite=args.finite)
    editor = EditorService(session.document)
    events = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or not isinstance(step.get("op"), str):
            raise ValueError(f"Design operation {index} requires an object with a string op")
        name = step["op"]
        try:
            details = _step(editor, name, {k: v for k, v in step.items() if k != "op"})
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Design operation {index} ({name}): {exc}") from exc
        events.append({"op": name, "snapshot_id": editor.expected.snapshot_id, **details})
    report = json.dumps({**_summary(editor), "operations": events}, ensure_ascii=False, allow_nan=False)
    if args.output:
        save_project(session, args.output)
    print(report)
    return 0

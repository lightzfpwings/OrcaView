"""Preview/CAS publication and an in-memory undo stack on M1's public API."""

from dataclasses import asdict, dataclass, replace
import json
from threading import RLock
from typing import Optional, Tuple

from orcaview.application.document import MoleculeDocument, StaleRevisionError
from orcaview.core._validation import Versioned, identifiers, require_tuple
from orcaview.core.models import Bond, DIRECTIONAL_STYLES, Molecule
from orcaview.core.geometry import display_bonds
from orcaview.core.provenance import Provenance, new_id
from orcaview.core.snapshots import GeometryRef, GeometrySnapshot, SelectionContext

from .commands import (AddAtoms, AddHydrogen, AddHydrogens, AttachAtom, DeleteAtoms, GeometryEditCommand, InsertRing, MoveAtom,
                       OptimizeCoordinates, ReorderAtoms, ReplaceElement, SetBond, SetBondLength, SetDistance,
                       SetElectronicState, UseResultGeometry)
from .coordinates import bond_moving_atoms, edit_distance
from .hydrogens import attached_hydrogen
from .rings import insert_ring


class EditStateError(ValueError):
    """The requested transition is not valid for this editor's pending/history state."""


class _UnchangedEdit(ValueError):
    """A preview reproduced the current geometry and atom identities."""


@dataclass(frozen=True)
class AtomMapping(Versioned):
    """ID-based row maps. None in a preview marks an atom not yet assigned an ID."""

    source_ids: Tuple[str, ...]
    target_ids: Tuple[Optional[str], ...]

    def __post_init__(self):
        identifiers(self.source_ids, "源原子 ID")
        require_tuple(self.target_ids, "目标原子映射")
        identifiers(tuple(i for i in self.target_ids if i is not None), "目标原子 ID")

    @property
    def source_to_target(self) -> Tuple[Optional[int], ...]:
        lookup = {atom_id: i for i, atom_id in enumerate(self.target_ids) if atom_id is not None}
        return tuple(lookup.get(atom_id) for atom_id in self.source_ids)

    @property
    def target_to_source(self) -> Tuple[Optional[int], ...]:
        lookup = {atom_id: i for i, atom_id in enumerate(self.source_ids)}
        return tuple(lookup.get(atom_id) for atom_id in self.target_ids)

    @property
    def removed_ids(self) -> Tuple[str, ...]:
        active = set(self.target_ids)
        return tuple(i for i in self.source_ids if i not in active)

    @property
    def added_indices(self) -> Tuple[int, ...]:
        old = set(self.source_ids)
        return tuple(i for i, atom_id in enumerate(self.target_ids) if atom_id not in old)


@dataclass(frozen=True)
class EditPreview(Versioned):
    preview_id: str
    command: GeometryEditCommand
    before: GeometrySnapshot
    molecule: Molecule
    mapping: AtomMapping
    selection_before: SelectionContext
    selection_after_ids: Tuple[str, ...]
    electronic_state_error: Optional[str]


@dataclass(frozen=True)
class EditHistoryEntry(Versioned):
    command: GeometryEditCommand
    before: GeometrySnapshot
    after: GeometrySnapshot
    selection_before: SelectionContext
    selection_after: SelectionContext


@dataclass(frozen=True)
class EditResult(Versioned):
    snapshot: GeometrySnapshot
    mapping: AtomMapping
    selection: SelectionContext
    action: str
    electronic_state_error: Optional[str]


def _state_error(molecule: Molecule) -> Optional[str]:
    if not molecule.atoms:
        return None
    try:
        molecule.validate()
    except ValueError as exc:
        return str(exc)
    return None


def _subset(base: GeometrySnapshot, order: Tuple[str, ...]):
    """Remap explicit bonds through stable IDs; never infer chemical bonds."""
    indices = tuple(base.index_of(atom_id) for atom_id in order)
    old_to_new = {old: new for new, old in enumerate(indices)}
    bonds = tuple(replace(b, a=old_to_new[b.a], b=old_to_new[b.b])
                  for b in base.molecule.bonds if b.a in old_to_new and b.b in old_to_new)
    return replace(base.molecule, atoms=tuple(base.molecule.atoms[i] for i in indices), bonds=bonds,
                   bonds_explicit=not order or base.molecule.bonds_explicit or bool(base.molecule.bonds and not bonds))


def _result_atom_ids(document, target, live_ids):
    active = set(live_ids)
    mapped = [atom_id if atom_id in active else None for atom_id in target.atom_ids]
    if None not in mapped:
        return tuple(mapped)
    # A prior adoption may have assigned a fresh ID to a deleted atom.
    # Reuse that ID only while it is live and its original source is recorded.
    for snapshot in reversed(document.records()[0]):
        origin = snapshot.provenance
        if (origin.producer != "orcaview.editing" or len(mapped) != len(snapshot.atom_ids)
                or dict(origin.parameters).get("result_geometry_snapshot_id") != target.ref.snapshot_id):
            continue
        for i, old in enumerate(snapshot.atom_ids):
            if mapped[i] is None and old in active:
                mapped[i] = old
        if None not in mapped:
            break
    return tuple(mapped)


def _apply(document: MoleculeDocument, base: GeometrySnapshot, command: GeometryEditCommand):
    op, molecule, ids = command.operation, base.molecule, base.atom_ids
    if isinstance(op, (OptimizeCoordinates, AddHydrogens)):
        bonds = display_bonds(molecule)
        if op.perceived_bonds is not None:
            old_edges = {tuple(sorted((b.a, b.b))) for b in bonds}
            new_edges = {tuple(sorted((b.a, b.b))) for b in op.perceived_bonds}
            if molecule.bonds_explicit or molecule.bonds or new_edges != old_edges:
                raise ValueError("优化返回的连接表无效")
            bonds = op.perceived_bonds
        if isinstance(op, AddHydrogens):
            atoms = tuple(atom for _, atom in op.attachments)
            anchors = {atom_id: index for index, atom_id in enumerate(ids)}
            if any(parent not in anchors for parent, _ in op.attachments):
                raise ValueError("当前快照不存在该原子 ID")
            added = tuple(Bond(anchors[parent], i) for i, (parent, _) in enumerate(op.attachments, len(ids)))
            return replace(molecule, atoms=molecule.atoms + atoms, bonds=bonds + added,
                           bonds_explicit=True), ids + (None,) * len(atoms)
        if len(op.coordinates) != len(ids):
            raise ValueError("优化坐标与原子数不一致")
        atoms = tuple(replace(atom, x=x, y=y, z=z) for atom, (x, y, z) in zip(molecule.atoms, op.coordinates))
        return replace(molecule, atoms=atoms, bonds=bonds, bonds_explicit=True), ids
    if isinstance(op, AddAtoms):
        return replace(molecule, atoms=molecule.atoms + op.atoms), ids + (None,) * len(op.atoms)
    if isinstance(op, (AttachAtom, AddHydrogen)):
        anchor = base.index_of(op.anchor_id)
        bonds = display_bonds(molecule)
        if isinstance(op, AddHydrogen):
            atom = attached_hydrogen(molecule, anchor, bonds)
            bond = Bond(anchor, len(ids))
        else:
            atom = op.atom
            bond = Bond(anchor, len(ids), op.order, op.style)
        return replace(molecule, atoms=molecule.atoms + (atom,), bonds=bonds + (bond,),
                       bonds_explicit=True), ids + (None,)
    if isinstance(op, InsertRing):
        anchor = None if op.anchor_id is None else base.index_of(op.anchor_id)
        updated = insert_ring(molecule, op, anchor)
        return updated, ids + (None,) * (len(updated.atoms) - len(ids))
    if isinstance(op, DeleteAtoms):
        # Validate every requested ID before deriving the surviving state.
        SelectionContext(base.ref, op.atom_ids).indices(base)
        removed = set(op.atom_ids)
        order = tuple(i for i in ids if i not in removed)
        return _subset(base, order), order
    if isinstance(op, ReorderAtoms):
        if set(op.atom_ids) != set(ids):
            raise ValueError("重排必须恰好包含当前所有原子 ID")
        return _subset(base, op.atom_ids), op.atom_ids
    if isinstance(op, ReplaceElement):
        index = base.index_of(op.atom_id)
        atoms = tuple(replace(atom, element=op.element) if i == index else atom
                      for i, atom in enumerate(molecule.atoms))
        return replace(molecule, atoms=atoms), ids
    if isinstance(op, MoveAtom):
        row = base.index_of(op.atom_id)
        atoms = list(molecule.atoms)
        atoms[row] = replace(atoms[row], x=op.x, y=op.y, z=op.z)
        return replace(molecule, atoms=tuple(atoms)), ids
    if isinstance(op, SetBond):
        a, b = base.index_of(op.atom_a), base.index_of(op.atom_b)
        edge = {a, b}
        bonds = list(display_bonds(molecule))
        for i, bond in enumerate(bonds):
            if {bond.a, bond.b} == edge:
                if op.order:
                    if op.style not in DIRECTIONAL_STYLES:
                        a, b = bond.a, bond.b
                    bonds[i] = Bond(a, b, op.order, op.style)
                else:
                    bonds.pop(i)
                break
        else:
            if not op.order:
                raise ValueError("所选原子之间没有键")
            if op.style not in DIRECTIONAL_STYLES:
                a, b = sorted(edge)
            bonds.append(Bond(a, b, op.order, op.style))
        return replace(molecule, bonds=tuple(bonds), bonds_explicit=True), ids
    if isinstance(op, SetElectronicState):
        return replace(molecule, charge=op.charge, multiplicity=op.multiplicity), ids
    if isinstance(op, UseResultGeometry):
        target = document.resolve(op.source)
        chosen = target.molecule
        if target.ref.frame_id is not None and not (chosen.bonds_explicit or chosen.bonds):
            # Coordinate-only output frames share their parent's atom identities.
            parent = document.resolve(target.parent)
            if parent.molecule.bonds or parent.molecule.bonds_explicit:
                topology = _subset(parent, target.atom_ids)
                chosen = replace(chosen, bonds=topology.bonds, bonds_explicit=topology.bonds_explicit)
        return chosen, _result_atom_ids(document, target, ids)
    if isinstance(op, SetDistance):
        edited = edit_distance(base, op.coordinate, op.target, op.moving_atom_ids, op.fixed_atom_ids)
        if isinstance(op, SetBondLength):
            bonds = display_bonds(molecule)
            if set(op.moving_atom_ids) != set(bond_moving_atoms(base, op.coordinate, bonds)):
                raise ValueError("键长编辑必须移动该端的整个基团")
            edited = replace(edited, bonds=bonds, bonds_explicit=True)
        return edited, ids
    raise ValueError("不支持的编辑操作")


class EditorService:
    """One document's edit history, independent of the display and Qt.

    Preview objects are single-use capabilities of this service instance. New
    IDs are assigned by M1 only on commit. Undo/redo append whole historical
    revisions through history-restore/1; they never rewrite old snapshots.
    External head changes require an explicit reset_to_head, which discards
    this service's pending preview and undo/redo stacks.
    """

    contract_version = 1

    def __init__(self, document: MoleculeDocument, selection: Optional[SelectionContext] = None):
        if not isinstance(document, MoleculeDocument):
            raise ValueError("编辑服务需要 MoleculeDocument")
        base = document.head
        selection = SelectionContext(base.ref, ()) if selection is None else selection
        if not isinstance(selection, SelectionContext):
            raise ValueError("编辑选择必须是 SelectionContext")
        selection.indices(base)
        self._document = document
        self._expected = base.ref
        self._selection = selection
        self._pending = None
        self._undo = []
        self._redo = []
        self._lock = RLock()

    @property
    def document(self) -> MoleculeDocument:
        return self._document

    @property
    def expected(self) -> GeometryRef:
        with self._lock:
            return self._expected

    @property
    def selection(self) -> SelectionContext:
        with self._lock:
            return self._selection

    @property
    def pending(self) -> Optional[EditPreview]:
        with self._lock:
            return self._pending

    @property
    def undo_entries(self) -> Tuple[EditHistoryEntry, ...]:
        with self._lock:
            return tuple(self._undo)

    @property
    def redo_entries(self) -> Tuple[EditHistoryEntry, ...]:
        with self._lock:
            return tuple(self._redo)

    @property
    def can_undo(self) -> bool:
        with self._lock:
            return bool(self._undo) and self._pending is None and self._document.head.ref == self._expected

    @property
    def can_redo(self) -> bool:
        with self._lock:
            return bool(self._redo) and self._pending is None and self._document.head.ref == self._expected

    def _check_head(self) -> GeometrySnapshot:
        base = self._document.head
        if base.ref != self._expected:
            raise StaleRevisionError("文档已被其他编辑修改；请显式重置编辑历史后继续")
        return base

    def set_selection(self, selection: SelectionContext) -> SelectionContext:
        with self._lock:
            base = self._check_head()
            if self._pending is not None:
                raise EditStateError("请先确认或取消当前预览再更改编辑选择")
            if not isinstance(selection, SelectionContext):
                raise ValueError("编辑选择必须是 SelectionContext")
            selection.indices(base)
            self._selection = selection
            return selection

    def preview(self, command: GeometryEditCommand) -> EditPreview:
        with self._lock:
            base = self._check_head()
            if not isinstance(command, GeometryEditCommand):
                raise ValueError("需要 GeometryEditCommand")
            if command.expected != self._expected:
                raise StaleRevisionError("命令基准与编辑服务的当前修订不一致")
            molecule, ids = _apply(self._document, base, command)
            molecule.validate_structure(allow_empty=True)
            if molecule == base.molecule and ids == base.atom_ids:
                raise _UnchangedEdit("编辑没有改变分子或原子顺序")
            active = set(ids)
            preview = EditPreview(
                new_id(), command, base, molecule, AtomMapping(base.atom_ids, ids), self._selection,
                tuple(i for i in self._selection.atom_ids if i in active), _state_error(molecule),
            )
            self._check_head()
            self._pending = preview
            return preview

    def _check_preview(self, preview: EditPreview):
        if self._pending is None or preview is not self._pending:
            raise EditStateError("预览不属于当前服务、已被替代或已结束")

    def commit(self, preview: EditPreview) -> EditResult:
        with self._lock:
            self._check_preview(preview)
            self._check_head()
            command = preview.command
            parameters = (
                ("operation", command.operation.kind),
                ("base_snapshot_id", command.expected.snapshot_id),
                ("preview_id", preview.preview_id),
                ("request", json.dumps(asdict(command.operation), ensure_ascii=False, allow_nan=False,
                                       sort_keys=True, separators=(",", ":"))),
            )
            if isinstance(command.operation, UseResultGeometry):
                parameters += (("result_geometry_snapshot_id", command.operation.source.snapshot_id),)
            origin = Provenance("edit", "orcaview.editing", "1", parameters=parameters)
            after = self._document.publish_revision(
                command.expected, preview.molecule, preview.mapping.target_ids, origin,
                source_unit="angstrom",
            )
            selection = SelectionContext(after.ref, preview.selection_after_ids, preview.selection_before.mode)
            entry = EditHistoryEntry(command, preview.before, after, preview.selection_before, selection)
            self._undo.append(entry)
            self._redo.clear()
            self._expected, self._selection, self._pending = after.ref, selection, None
            return EditResult(after, AtomMapping(preview.before.atom_ids, after.atom_ids), selection,
                              "commit", preview.electronic_state_error)

    def cancel(self, preview: EditPreview) -> None:
        """Cancel even an externally stale preview, without touching the document."""
        with self._lock:
            self._check_preview(preview)
            self._pending = None

    def use_result_geometry(self, source: GeometryRef) -> Optional[EditResult]:
        """Adopt the displayed snapshot as one undoable edit, unless it is already active."""
        with self._lock:
            command = GeometryEditCommand(self._expected, UseResultGeometry(source))
            try:
                preview = self.preview(command)
            except _UnchangedEdit:
                return None
            return self.commit(preview)

    def _restore(self, undo: bool) -> EditResult:
        with self._lock:
            if self._pending is not None:
                raise EditStateError("请先确认或取消当前预览")
            before = self._check_head()
            source, destination = (self._undo, self._redo) if undo else (self._redo, self._undo)
            if not source:
                raise EditStateError("没有可撤销的编辑" if undo else "没有可重做的编辑")
            entry = source[-1]
            target = entry.before if undo else entry.after
            saved = entry.selection_before if undo else entry.selection_after
            after = self._document.restore_revision(self._expected, target.ref)
            selection = SelectionContext(after.ref, saved.atom_ids, saved.mode)
            source.pop()
            destination.append(entry)
            self._expected, self._selection = after.ref, selection
            return EditResult(after, AtomMapping(before.atom_ids, after.atom_ids), selection,
                              "undo" if undo else "redo", _state_error(after.molecule))

    def undo(self) -> EditResult:
        return self._restore(True)

    def redo(self) -> EditResult:
        return self._restore(False)

    def reset_to_head(self) -> SelectionContext:
        """Explicitly accept an external change and discard local command history."""
        with self._lock:
            base = self._document.head
            active = set(base.atom_ids)
            selection = SelectionContext(base.ref, tuple(i for i in self._selection.atom_ids if i in active),
                                         self._selection.mode)
            self._undo.clear()
            self._redo.clear()
            self._pending = None
            self._expected, self._selection = base.ref, selection
            return selection

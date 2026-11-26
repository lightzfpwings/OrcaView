"""Append-only geometry history and result bindings, independent of the current view."""

from dataclasses import replace
from threading import RLock
from typing import Optional, Tuple

from orcaview.core._validation import require_tuple
from orcaview.core.models import Molecule
from orcaview.core.provenance import ArtifactRef, Provenance, new_id
from orcaview.core.results import ResultDataset
from orcaview.core.snapshots import GeometryRef, GeometrySnapshot, SketchCoordinates


HISTORY_RESTORE_KIND = "history-restore"
HISTORY_RESTORE_VERSION = "1"


def _restore_provenance(target: GeometryRef) -> Provenance:
    return Provenance(
        HISTORY_RESTORE_KIND, "orcaview.document", HISTORY_RESTORE_VERSION,
        parameters=(("target_document_id", target.document_id),
                    ("target_revision", str(target.revision)),
                    ("target_snapshot_id", target.snapshot_id)),
    )


class GeometryLookupError(ValueError):
    """The requested revision or frame does not exist in this document."""


class StaleRevisionError(ValueError):
    """An edit was based on a revision other than the current head."""


class MoleculeDocument:
    def __init__(self, initial: GeometrySnapshot):
        if initial.ref.revision != 1 or initial.ref.frame_id is not None or initial.parent is not None:
            raise ValueError("A document must start at revision 1 with no parent reference")
        if initial.provenance.kind == HISTORY_RESTORE_KIND:
            raise ValueError("The initial geometry cannot declare a history restore")
        self._head = initial
        self._snapshots = {initial.ref.snapshot_id: initial}
        self._frame_keys = set()
        self._known_atoms = set(initial.atom_ids)
        self._datasets = {}
        self._artifacts = {a.artifact_id: a for a in initial.provenance.parents}
        self._lock = RLock()

    @classmethod
    def from_molecule(cls, molecule: Molecule, provenance: Optional[Provenance] = None,
                      source_unit: str = "angstrom"):
        return cls(GeometrySnapshot(
            GeometryRef(new_id(), 1), molecule, tuple(new_id() for _ in molecule.atoms),
            provenance if provenance is not None else Provenance("created"), source_unit=source_unit,
        ))

    @property
    def head(self) -> GeometrySnapshot:
        with self._lock:
            return self._head

    def resolve(self, ref: GeometryRef) -> GeometrySnapshot:
        with self._lock:
            snapshot = self._snapshots.get(ref.snapshot_id)
            if snapshot is None or snapshot.ref != ref:
                raise GeometryLookupError(f"The document does not contain the requested revision or frame: {ref}")
            return snapshot

    def publish_revision(self, expected: GeometryRef, molecule: Molecule,
                         atom_ids: Tuple[Optional[str], ...],
                         provenance: Optional[Provenance] = None, *,
                         source_unit: str = "angstrom", sketch_xy: Optional[SketchCoordinates] = None) -> GeometrySnapshot:
        """Pass the surviving IDs in new row order and None for each newly added atom."""
        require_tuple(atom_ids, "Revision atom mapping")
        with self._lock:
            base = self._head
            if expected != base.ref:
                raise StaleRevisionError("The base geometry has changed or is not the current revision")
            active = set(base.atom_ids)
            if any(i is not None and (not isinstance(i, str) or i not in active) for i in atom_ids):
                raise ValueError("Only atom IDs from the base revision may be reused. Pass None for new atoms")
            if isinstance(provenance, Provenance) and provenance.kind == HISTORY_RESTORE_KIND:
                raise ValueError("History restores must use restore_revision")
            snapshot = GeometrySnapshot(
                GeometryRef(base.ref.document_id, base.ref.revision + 1), molecule,
                tuple(new_id() if i is None else i for i in atom_ids),
                provenance if provenance is not None else Provenance("edit"), parent=base.ref, source_unit=source_unit,
                sketch_xy=sketch_xy if sketch_xy is not None else base.remap_sketch(molecule, atom_ids),
            )
            self._append(snapshot)
            return snapshot

    def restore_revision(self, expected: GeometryRef, target: GeometryRef) -> GeometrySnapshot:
        """Append an exact historical revision, preserving its atom IDs for undo/redo.

        The caller keeps the edit stack and passes the current head plus the original
        before/after reference. Historical snapshots and result bindings stay intact.
        """
        with self._lock:
            base = self._head
            if expected != base.ref:
                raise StaleRevisionError("The base geometry has changed or is not the current revision")
            if not isinstance(target, GeometryRef):
                raise ValueError("The restore target must be a complete GeometryRef")
            original = self.resolve(target)
            if target.frame_id is not None or target == base.ref:
                raise ValueError("The restore target must be a published historical revision")
            snapshot = GeometrySnapshot(
                GeometryRef(base.ref.document_id, base.ref.revision + 1),
                original.molecule, original.atom_ids, _restore_provenance(target),
                parent=base.ref, source_unit=original.source_unit, sketch_xy=original.sketch_xy,
            )
            self._append(snapshot)
            return snapshot

    def molecule_with_topology(self, snapshot: GeometrySnapshot, *, sketch: bool = False) -> Molecule:
        """Use the owning revision's authored bonds for a coordinate-only result frame."""
        molecule = snapshot.sketch_molecule() if sketch else snapshot.molecule
        if snapshot.ref.frame_id is None or molecule.bonds_explicit or molecule.bonds:
            return molecule
        parent = self.resolve(snapshot.parent)
        if not (parent.molecule.bonds_explicit or parent.molecule.bonds):
            return molecule
        rows = {atom_id: i for i, atom_id in enumerate(snapshot.atom_ids)}
        bonds = tuple(replace(b, a=rows[parent.atom_ids[b.a]], b=rows[parent.atom_ids[b.b]])
                      for b in parent.molecule.bonds)
        return replace(molecule, bonds=bonds, bonds_explicit=parent.molecule.bonds_explicit)

    def add_frame(self, base: GeometryRef, frame_id: str, molecule: Molecule,
                  atom_ids: Tuple[str, ...], provenance: Provenance,
                  source_unit: str = "angstrom") -> GeometrySnapshot:
        """Attach an actual source frame to a revision without moving the editable head."""
        with self._lock:
            if base.frame_id is not None or frame_id is None:
                raise ValueError("An actual frame requires its owning revision and an explicit frame ID")
            snapshot = GeometrySnapshot(GeometryRef(base.document_id, base.revision, frame_id),
                                        molecule, atom_ids, provenance, base, source_unit)
            self._append(snapshot)
            return snapshot

    def _append(self, snapshot: GeometrySnapshot) -> None:
        ref, head = snapshot.ref, self._head
        if ref.document_id != head.ref.document_id or ref.snapshot_id in self._snapshots:
            raise ValueError("The geometry reference is duplicated or belongs to another document")
        artifacts = self._check_artifacts(snapshot.provenance.parents)
        if ref.frame_id is None:
            if snapshot.parent != head.ref or ref.revision != head.ref.revision + 1:
                raise ValueError("The revision chain is discontinuous or the parent revision is invalid")
            is_restore = snapshot.provenance.kind == HISTORY_RESTORE_KIND
            if is_restore:
                self._check_restoration(snapshot)
            added = set(snapshot.atom_ids).difference(head.atom_ids)
            if added.intersection(self._known_atoms) and not is_restore:
                raise ValueError("Removed atom IDs cannot be reused for new atoms")
            self._known_atoms.update(added)
            self._head = snapshot
        else:
            if snapshot.provenance.kind == HISTORY_RESTORE_KIND:
                raise ValueError("An actual frame cannot declare a history restore")
            parent = snapshot.parent
            if (parent is None or parent.frame_id is not None or parent.revision != ref.revision
                    or parent.document_id != ref.document_id):
                raise ValueError("The frame must reference its owning revision")
            frame_key = (ref.revision, ref.frame_id)
            if frame_key in self._frame_keys:
                raise ValueError("The frame ID already exists in this revision")
            base = self.resolve(parent)
            elements = dict(zip(base.atom_ids, (a.element for a in base.molecule.atoms)))
            if (set(snapshot.atom_ids) != set(elements)
                    or any(elements[i] != a.element for i, a in zip(snapshot.atom_ids, snapshot.molecule.atoms))):
                raise ValueError("Frame atom identities or corresponding elements do not match")
            if ((snapshot.molecule.charge, snapshot.molecule.multiplicity)
                    != (base.molecule.charge, base.molecule.multiplicity)):
                raise ValueError("Frames must use the charge and multiplicity of their revision")
            self._frame_keys.add(frame_key)
        self._snapshots[ref.snapshot_id] = snapshot
        self._artifacts.update(artifacts)

    def _check_restoration(self, snapshot: GeometrySnapshot) -> None:
        """Validate persisted evidence before permitting historical IDs to reactivate."""
        parameters = dict(snapshot.provenance.parameters)
        target = self._snapshots.get(parameters.get("target_snapshot_id"))
        if (target is None or target.ref.frame_id is not None or target.ref == self._head.ref
                or snapshot.provenance != _restore_provenance(target.ref)):
            raise ValueError("Restored history must reference a published historical revision in this file using a supported protocol")
        if (snapshot.molecule != target.molecule or snapshot.atom_ids != target.atom_ids
                or snapshot.source_unit != target.source_unit or snapshot.sketch_xy != target.sketch_xy):
            raise ValueError("A history restore must preserve the target geometry, atom mapping, bonds, electronic state and source units")

    def _check_artifacts(self, refs):
        batch = {}
        for item in refs:
            previous = batch.get(item.artifact_id, self._artifacts.get(item.artifact_id))
            if previous is not None and item != previous:
                raise ValueError("Conflicting provenance records for the same file ID")
            batch[item.artifact_id] = item
        return batch

    def artifact(self, artifact_id: str) -> ArtifactRef:
        with self._lock:
            try:
                return self._artifacts[artifact_id]
            except KeyError as exc:
                raise ValueError("The file ID is not present in the document") from exc

    def add_dataset(self, dataset: ResultDataset) -> None:
        with self._lock:
            dataset.validate_geometry(self.resolve(dataset.geometry))
            previous = self._datasets.get(dataset.dataset_id)
            if previous is not None and previous != dataset:
                raise ValueError("This dataset ID is bound to other content")
            refs = dataset.provenance.parents
            if dataset.array_ref is not None:
                refs += (dataset.array_ref,)
            self._artifacts.update(self._check_artifacts(refs))
            self._datasets[dataset.dataset_id] = dataset

    def dataset(self, dataset_id: str) -> ResultDataset:
        with self._lock:
            try:
                return self._datasets[dataset_id]
            except KeyError as exc:
                raise ValueError("The requested dataset is not present in the document") from exc

    def records(self) -> Tuple[Tuple[GeometrySnapshot, ...], Tuple[ResultDataset, ...]]:
        """Capture one coherent, immutable generation for persistence."""
        with self._lock:
            return tuple(self._snapshots.values()), tuple(self._datasets.values())

    @classmethod
    def restore(cls, snapshots: Tuple[GeometrySnapshot, ...], datasets: Tuple[ResultDataset, ...]):
        if not snapshots:
            raise ValueError("The project has no initial geometry")
        doc = cls(snapshots[0])
        for snapshot in snapshots[1:]:
            doc._append(snapshot)
        for dataset in datasets:
            if dataset.dataset_id in doc._datasets:
                raise ValueError("The project contains duplicate dataset IDs")
            doc.add_dataset(dataset)
        return doc

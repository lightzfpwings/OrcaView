"""Ordered stable-ID selection, independent of Qt and molecular editing.

``SelectionContext`` always names one exact geometry. ``rebind`` is an explicit
navigation action: it keeps surviving IDs in their selection order and drops
IDs absent from the target snapshot. It never changes scientific coordinates.
"""

from typing import Optional, Tuple

from orcaview.core._validation import identifiers
from orcaview.core.snapshots import GeometrySnapshot, SelectionContext


class SelectionService:
    """Maintain an immutable selection context for one displayed snapshot.

    All methods return the resulting ``SelectionContext``. Unknown IDs,
    duplicate IDs and invalid operations fail before changing selection state.
    ``add`` appends newly selected IDs in argument order; ``toggle`` first
    removes selected arguments and appends previously unselected arguments.
    """

    contract_version = 1

    def __init__(self, snapshot: GeometrySnapshot,
                 selection: Optional[SelectionContext] = None):
        if not isinstance(snapshot, GeometrySnapshot):
            raise ValueError("The selection service requires a GeometrySnapshot")
        if selection is None:
            selection = SelectionContext(snapshot.ref, ())
        if not isinstance(selection, SelectionContext):
            raise ValueError("The initial selection must be a SelectionContext")
        selection.indices(snapshot)
        self._snapshot = snapshot
        self._selection = selection

    @property
    def snapshot(self) -> GeometrySnapshot:
        return self._snapshot

    @property
    def selection(self) -> SelectionContext:
        return self._selection

    def select(self, atom_ids: Tuple[str, ...],
               operation: str = "replace") -> SelectionContext:
        identifiers(atom_ids, "Selected atom IDs")
        if operation not in ("replace", "add", "remove", "toggle"):
            raise ValueError("Supported selection operations are replace, add, remove and toggle")
        # Validate even IDs being removed; a stale index or foreign ID must not
        # silently pass because it happens to be absent from the current set.
        SelectionContext(self._snapshot.ref, atom_ids).indices(self._snapshot)
        previous = self._selection.atom_ids
        selected = self._selection.atom_set
        requested = frozenset(atom_ids)
        if operation == "replace":
            result = atom_ids
        elif operation == "add":
            result = previous + tuple(i for i in atom_ids if i not in selected)
        elif operation == "remove":
            result = tuple(i for i in previous if i not in requested)
        else:
            result = (tuple(i for i in previous if i not in requested)
                      + tuple(i for i in atom_ids if i not in selected))
        self._selection = SelectionContext(self._snapshot.ref, result,
                                           self._selection.mode)
        return self._selection

    def clear(self) -> SelectionContext:
        return self.select(())

    def rebind(self, snapshot: GeometrySnapshot) -> SelectionContext:
        """Explicitly navigate within a document, retaining surviving IDs.

        Reordering coordinates does not reorder selection. Moving to a deleted
        atom's earlier revision does not automatically reselect it; undo callers
        can restore a saved context explicitly via a new service instance.
        """
        if not isinstance(snapshot, GeometrySnapshot):
            raise ValueError("The selection service requires a GeometrySnapshot")
        if snapshot.ref.document_id != self._snapshot.ref.document_id:
            raise ValueError("Selections cannot be rebound across documents automatically")
        active = frozenset(snapshot.atom_ids)
        selection = SelectionContext(
            snapshot.ref,
            tuple(i for i in self._selection.atom_ids if i in active),
            self._selection.mode,
        )
        self._snapshot = snapshot
        self._selection = selection
        return selection


__all__ = ["SelectionService"]

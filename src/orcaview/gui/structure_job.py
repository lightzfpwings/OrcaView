"""Prepare a modeling command off the GUI thread for one immutable snapshot."""

from PySide6.QtCore import QObject, QRunnable, Signal

from orcaview.editing import AddHydrogens, GeometryEditCommand, OptimizeCoordinates
from orcaview.editing.hydrogens import missing_hydrogens
from orcaview.editing.optimization import optimize_structure


class _Completion(QObject):
    finished = Signal(object, object, str)


class StructureJob(QRunnable):
    def __init__(self, snapshot, mode):
        super().__init__()
        self.snapshot = snapshot
        self.mode = mode
        self.completion = _Completion()

    def run(self):
        base = self.snapshot
        try:
            if self.mode == "H":
                added, perceived = missing_hydrogens(base.molecule)
                operation = AddHydrogens(tuple((base.atom_ids[i], h) for i, h in added), perceived)
            else:
                result = optimize_structure(base.molecule, self.mode)
                xyz = tuple((atom.x, atom.y, atom.z) for atom in result.molecule.atoms)
                implicit = not (base.molecule.bonds or base.molecule.bonds_explicit)
                operation = OptimizeCoordinates(result.method, xyz, result.molecule.bonds if implicit else None)
            command = GeometryEditCommand(base.ref, operation)
        except Exception as exc:
            # Report native-worker errors on the editing page without publishing a revision.
            self.completion.finished.emit(self, None, str(exc))
        else:
            self.completion.finished.emit(self, command, "")

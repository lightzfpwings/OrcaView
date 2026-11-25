"""Prepare a modeling command off the GUI thread for one immutable snapshot."""

from PySide6.QtCore import QObject, QRunnable, Signal

from orcaview.editing import GeometryEditCommand
from orcaview.editing.modeling import modeling_operation


class _Completion(QObject):
    finished = Signal(object, object, str)


class StructureJob(QRunnable):
    def __init__(self, snapshot, mode):
        super().__init__()
        self.snapshot = snapshot
        self.mode = mode
        self.completion = _Completion()

    def run(self):
        try:
            command = GeometryEditCommand(self.snapshot.ref, modeling_operation(self.snapshot, self.mode))
        except Exception as exc:
            # Report native-worker errors on the editing page without publishing a revision.
            self.completion.finished.emit(self, None, str(exc))
        else:
            self.completion.finished.emit(self, command, "")

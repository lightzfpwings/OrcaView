"""Prepare a modeling command off the GUI thread for one immutable snapshot."""

from PySide6.QtCore import QObject, QRunnable, Signal

from orcaview.editing import GenerateBiopolymer, GeometryEditCommand
from orcaview.editing.modeling import modeling_operation


class _Completion(QObject):
    finished = Signal(object, object, str)


class StructureJob(QRunnable):
    def __init__(self, snapshot, mode, **options):
        super().__init__()
        self.snapshot = snapshot
        self.mode = mode
        self.options = options
        self.completion = _Completion()

    def run(self):
        try:
            if self.mode == "biopolymer":
                polymer, value = self.options["polymer"], self.options["value"].strip()
                if value[:1].isdigit() or value.lower().startswith("pdb_"):
                    from orcaview.io.biopolymer_record import load_pdb_record
                    record = load_pdb_record(polymer, value)
                    source, value = "pdb", value.upper()
                else:
                    from orcaview.io.biopolymer_sequence import build_sequence_record
                    record = build_sequence_record(polymer, value)
                    source = "sequence"
                operation = GenerateBiopolymer(record.molecule, polymer, source, value, record.polymer_roles)
            else:
                operation = modeling_operation(self.snapshot, self.mode, **self.options)
            command = GeometryEditCommand(self.snapshot.ref, operation)
        except Exception as exc:
            # Report native-worker errors on the editing page without publishing a revision.
            self.completion.finished.emit(self, None, str(exc))
        else:
            self.completion.finished.emit(self, command, "")

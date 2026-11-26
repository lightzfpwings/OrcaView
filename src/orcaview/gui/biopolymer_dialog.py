"""Build an editable protein or DNA structure from a sequence or PDB entry."""

from PySide6.QtCore import QThreadPool, Slot
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout

from orcaview.gui.structure_job import StructureJob
from orcaview.i18n import diagnostic_text, tr


class BiopolymerDialog(QDialog):
    def __init__(self, polymer, snapshot, parent=None):
        super().__init__(parent)
        self.polymer = polymer
        self.snapshot = snapshot
        self.command = None
        self._job = None
        self.setWindowTitle(tr("Build a protein") if polymer == "protein" else tr("Build DNA"))
        self.resize(440, 300)
        layout = QVBoxLayout(self)
        label = QLabel(tr("PDB ID or sequence"))
        layout.addWidget(label)
        self.entry = QPlainTextEdit()
        self.entry.setObjectName("biopolymerInput")
        self.entry.setTabChangesFocus(True)
        self.entry.setPlaceholderText(tr("1CRN or a one-letter amino acid sequence")
                                      if polymer == "protein" else tr("1BNA or a DNA sequence (5′ to 3′)"))
        label.setBuddy(self.entry)
        self.entry.setAccessibleName(label.text())
        layout.addWidget(self.entry, 1)
        hint = QLabel(tr("A PDB ID retrieves deposited coordinates from RCSB. A sequence builds an idealized peptide chain offline.")
                      if polymer == "protein" else
                      tr("A PDB ID retrieves deposited coordinates from RCSB. A sequence builds a double helix with its reverse complement offline."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        if snapshot.atom_ids:
            note = QLabel(tr("Generating replaces the current structure. Undo restores it."))
            note.setWordWrap(True)
            layout.addWidget(note)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.hide()
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.generate = buttons.addButton(tr("Generate structure"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.generate.setObjectName("biopolymerGenerate")
        self.generate.setDefault(True)
        self.generate.setEnabled(False)
        self.generate.clicked.connect(self._generate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.entry.textChanged.connect(self._input_changed)
        self.entry.setFocus()

    def _input_changed(self):
        self.status.hide()
        self.generate.setEnabled(bool(self.entry.toPlainText().strip()))

    def _generate(self):
        if self._job is not None:
            return
        self._job = StructureJob(self.snapshot, "biopolymer", polymer=self.polymer, value=self.entry.toPlainText())
        self._job.completion.finished.connect(self._finished)
        self.generate.setEnabled(False)
        self.entry.setReadOnly(True)
        self.status.setText(tr("Preparing structure…"))
        self.status.show()
        QThreadPool.globalInstance().start(self._job)

    @Slot(object, object, str)
    def _finished(self, job, command, error):
        if job is not self._job:
            return
        self._job = None
        if command is None:
            self.entry.setReadOnly(False)
            self.entry.setFocus()
            self.generate.setEnabled(True)
            self.status.setText(diagnostic_text(error))
            return
        self.command = command
        self.accept()

    def done(self, result):
        if self._job is not None:
            self._job.completion.finished.disconnect(self._finished)
            self._job = None
        super().done(result)

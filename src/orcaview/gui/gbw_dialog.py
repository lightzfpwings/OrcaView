"""Ask how to open an ORCA wavefunction before starting a converter."""

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout,
)

from orcaview.i18n import tr
from orcaview.orca.gbw import file_state
from orcaview.preferences import read_preferences, write_preferences


class GbwOpenDialog(QDialog):
    def __init__(self, path, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Open ORCA wavefunction"))
        self.destination = path.with_suffix(".molden.input")
        self.expected = file_state(self.destination)
        self.converter = None
        self.choice = None
        layout = QVBoxLayout(self)
        question = (tr("{name} already exists. Open it or replace it with a new conversion?",
                       name=self.destination.name) if self.expected else
                    tr("Convert {source} to {target} and view its molecular orbitals?",
                       source=path.name, target=self.destination.name))
        prompt = QLabel()
        prompt.setTextFormat(Qt.TextFormat.PlainText)
        prompt.setText(question)
        prompt.setWordWrap(True)
        layout.addWidget(prompt)
        line = QHBoxLayout()
        label = QLabel(tr("ORCA converter"))
        self.location = QLineEdit()
        self.location.setReadOnly(True)
        self.location.setPlaceholderText(tr("Built-in GBW converter"))
        self.location.setToolTip(tr("Built-in GBW converter"))
        label.setBuddy(self.location)
        browse = QPushButton(tr("Browse…"))
        browse.clicked.connect(self._browse)
        for widget in (label, self.location, browse):
            line.addWidget(widget)
        layout.addLayout(line)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        role = QDialogButtonBox.ButtonRole
        self.convert = buttons.addButton(tr("Replace and open") if self.expected else tr("Convert and open"),
                                         role.ActionRole)
        self.convert.clicked.connect(self._convert)
        if self.expected:
            existing = buttons.addButton(tr("Open existing Molden"), role.AcceptRole)
            existing.clicked.connect(self._existing)
            existing.setDefault(True)
        else:
            self.convert.setDefault(True)
        layout.addWidget(buttons)
        self.resize(540, self.sizeHint().height())

    def _browse(self):
        saved = read_preferences("orca-tools", {"converter": ""})["converter"]
        directory = Path(saved).parent if saved else Path.home()
        name, _ = QFileDialog.getOpenFileName(self, tr("Select ORCA converter"),
                                              str(self.converter.parent if self.converter else directory),
                                              "orca_2mkl (orca_2mkl orca_2mkl.exe)")
        if name:
            selected = Path(name)
            if selected.name.lower() not in ("orca_2mkl", "orca_2mkl.exe") or not os.access(selected, os.X_OK):
                QMessageBox.warning(self, tr("ORCA converter"), tr("Select an executable orca_2mkl file."))
                return
            self.converter = selected.resolve()
            self.location.setText(str(self.converter))
            self.location.setToolTip(str(self.converter))

    def _convert(self):
        if self.converter is not None:
            try:
                write_preferences("orca-tools", {"converter": str(self.converter)})
            except OSError:
                pass
        self.choice = "convert"
        self.accept()

    def _existing(self):
        self.choice = "existing"
        self.accept()

"""Edit and export an independent UTF-8 ORCA input document."""

from difflib import SequenceMatcher
from pathlib import Path
import re

from PySide6.QtCore import QIODevice, QSaveFile
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)

from orcaview.gui.file_dialogs import document_directory, suggested_file
from orcaview.gui.typography import fixed_font
from orcaview.i18n import tr


_LINE_BREAK = re.compile(r"\r\n|[\r\n\u2029]")


class NativeInputDialog(QDialog):
    def __init__(self, parent, seed_text):
        super().__init__(parent)
        self.resize(820, 620)
        self.editor = QPlainTextEdit()
        self.editor.setAccessibleName(tr("ORCA input text"))
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFont(fixed_font())
        self.editor.document().modificationChanged.connect(self.setWindowModified)

        buttons = QHBoxLayout()
        for label, shortcut, action in (
            (tr("Open .inp…"), QKeySequence.StandardKey.Open, self.open_input),
            (tr("Save .inp as…"), QKeySequence.StandardKey.SaveAs, self.save_as),
        ):
            button = QPushButton(label)
            button.setAutoDefault(False)
            button.setShortcut(shortcut)
            button.clicked.connect(action)
            buttons.addWidget(button)
        buttons.addStretch()
        close = QPushButton(tr("Close"))
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addLayout(buttons)
        self._load_content(seed_text, None)
        self.editor.setFocus()

    def _load_content(self, content, path):
        self._path = path
        self._remember_format(content)
        self.editor.setPlainText("\n".join(self._original_lines))
        self.editor.document().setModified(False)
        self._update_title()

    def _remember_format(self, content):
        self._bom = content.startswith("\ufeff")
        text = content[1:] if self._bom else content
        self._original_lines = _LINE_BREAK.split(text)
        self._breaks = _LINE_BREAK.findall(text)

    def _update_title(self):
        source = str(self._path) if self._path else tr("Project input preview")
        self.setWindowTitle(tr("{source}[*] — Native ORCA input editor", source=source))

    def _content(self):
        # toPlainText converts nonbreaking spaces to ordinary spaces.
        lines = self.editor.document().toRawText().split("\u2029")
        default_break = self._breaks[0] if self._breaks else "\n"
        content = default_break.join(lines)
        if len(set(self._breaks)) > 1:
            # Keep individual line endings in mixed-format files, including
            # changed lines that still occupy the corresponding original row.
            breaks = [default_break] * (len(lines) - 1)
            matcher = SequenceMatcher(None, self._original_lines, lines)
            for tag, old_start, old_stop, start, stop in matcher.get_opcodes():
                if tag in ("equal", "replace"):
                    for old, new in zip(range(old_start, old_stop), range(start, stop)):
                        if old < len(self._breaks) and new < len(breaks):
                            breaks[new] = self._breaks[old]
            content = "".join(line + br for line, br in zip(lines, breaks)) + lines[-1]
        return ("\ufeff" if self._bom else "") + content

    def open_input(self):
        directory = self._path.parent if self._path else document_directory(self)
        name, _ = QFileDialog.getOpenFileName(self, tr("Open ORCA input"), str(directory), tr("ORCA input") + " (*.inp)")
        if not name:
            return False
        path = Path(name)
        try:
            content = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, tr("Could not open UTF-8 input file"), str(exc))
            return False
        if self.editor.document().isModified():
            decision = self._unsaved_decision()
            if decision == QMessageBox.StandardButton.Save:
                if not self.save_as():
                    return False
                # Saving may have replaced the file that was just read.
                if self._path.resolve() == path.resolve():
                    return True
            elif decision != QMessageBox.StandardButton.Discard:
                return False
        self._load_content(content, path)
        return True

    def save_as(self):
        suggested = str(self._path) if self._path else suggested_file(self, "calculation", ".inp")
        name, _ = QFileDialog.getSaveFileName(self, tr("Save ORCA input as"), suggested, tr("ORCA input") + " (*.inp)")
        if not name:
            return False
        path = Path(name)
        if path.suffix.lower() != ".inp":
            path = Path(str(path) + ".inp")
            if path.exists():
                choice = QMessageBox.question(self, tr("Replace file"), tr("Replace the existing file {path}?", path=path),
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                              QMessageBox.StandardButton.No)
                if choice != QMessageBox.StandardButton.Yes:
                    return False
        content = self._content()
        target = QSaveFile(str(path))
        data = content.encode("utf-8")
        if not target.open(QIODevice.OpenModeFlag.WriteOnly):
            QMessageBox.warning(self, tr("Could not save ORCA input"), target.errorString())
            return False
        if target.write(data) != len(data):
            error = target.errorString()
            target.cancelWriting()
            QMessageBox.warning(self, tr("Could not save ORCA input"), error)
            return False
        if not target.commit():
            QMessageBox.warning(self, tr("Could not save ORCA input"), target.errorString())
            return False
        self._path = path
        self._remember_format(content)
        self.editor.document().setModified(False)
        self._update_title()
        return True

    def _unsaved_decision(self):
        options = QMessageBox.StandardButton
        return QMessageBox.question(self, tr("Unsaved ORCA input"), tr("Save changes to the current input?"),
                                    options.Save | options.Discard | options.Cancel, options.Cancel)

    def reject(self):
        if self.editor.document().isModified():
            decision = self._unsaved_decision()
            if decision == QMessageBox.StandardButton.Save:
                if not self.save_as():
                    return
            elif decision != QMessageBox.StandardButton.Discard:
                return
        super().reject()


def edit_native_input(parent, seed_text):
    return NativeInputDialog(parent, seed_text).exec()

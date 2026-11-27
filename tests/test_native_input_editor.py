import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from orcaview.gui.native_input import NativeInputDialog
    HAS_QT = True
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'Optional Qt dependency is not installed')
class NativeInputEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.dialog = NativeInputDialog(None, "! HF def2-SVP\n")
        self.dialog.show()
        self.app.processEvents()
        self.addCleanup(self._close_dialog)

    def _close_dialog(self):
        self.dialog.editor.document().setModified(False)
        self.dialog.close()
        self.app.processEvents()

    def _append(self, text):
        self.dialog.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.dialog.editor.insertPlainText(text)

    def _open(self, path):
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")):
            return self.dialog.open_input()

    def _save(self, path):
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            return self.dialog.save_as()

    def test_preview_and_opened_text_export_without_reformatting(self):
        self.assertEqual(self.dialog.editor.toPlainText(), "! HF def2-SVP\n")
        source = self.folder / "source.inp"
        sample = "\ufeff! HF\t\r\n# 注释\u00a0保持\n$basis\r  1  2  \r\nend"
        source.write_bytes(sample.encode())
        self.assertTrue(self._open(source))
        self.assertTrue(self._save(self.folder / "exact-copy"))
        self.assertEqual((self.folder / "exact-copy.inp").read_bytes(), source.read_bytes())
        self._append("\n# added")
        self.assertTrue(self._save(self.folder / "edited.inp"))
        self.assertEqual((self.folder / "edited.inp").read_bytes(),
                         (sample + "\r\n# added").encode())
        self.assertEqual(source.read_bytes(), sample.encode())
        self.assertFalse(self.dialog.editor.document().isModified())

    def test_missing_invalid_and_canceled_open_preserve_edits(self):
        self._append("# draft")
        draft = self.dialog.editor.toPlainText()
        bad = self.folder / "invalid.inp"
        bad.write_bytes(b"\xff\xfe")
        with patch.object(QMessageBox, "warning") as warning, patch.object(QMessageBox, "question") as decision:
            self.assertFalse(self._open(bad))
            self.assertFalse(self._open(self.folder / "missing.inp"))
            self.assertFalse(self._open(""))
            self.assertEqual(warning.call_count, 2)
            decision.assert_not_called()
        self.assertEqual(self.dialog.editor.toPlainText(), draft)
        self.assertTrue(self.dialog.editor.document().isModified())

    def test_unsaved_replacement_can_cancel_discard_or_save(self):
        source = self.folder / "next.inp"
        source.write_bytes(b"new input\n")
        self._append("# draft")
        draft = self.dialog.editor.toPlainText()
        buttons = QMessageBox.StandardButton
        with patch.object(QMessageBox, "question", return_value=buttons.Cancel):
            self.assertFalse(self._open(source))
        with patch.object(QMessageBox, "question", return_value=buttons.Save), \
                patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
            self.assertFalse(self._open(source))
        self.assertEqual(self.dialog.editor.toPlainText(), draft)
        self.assertTrue(self.dialog.editor.document().isModified())
        saved = self.folder / "draft.inp"
        with patch.object(QMessageBox, "question", return_value=buttons.Save), \
                patch.object(QFileDialog, "getSaveFileName", return_value=(str(saved), "")):
            self.assertTrue(self._open(source))
        self.assertEqual(saved.read_text(), draft)
        self.assertEqual(self.dialog.editor.toPlainText(), "new input\n")
        self._append("# discarded")
        with patch.object(QMessageBox, "question", return_value=buttons.Discard):
            self.assertTrue(self._open(source))
        self.assertEqual(self.dialog.editor.toPlainText(), "new input\n")

    def test_save_failure_and_declined_suffix_overwrite_keep_original(self):
        self._append("# unsaved")
        existing = self.folder / "existing.inp"
        existing.write_bytes(b"original")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.assertFalse(self._save(self.folder / "existing"))
        self.assertEqual(existing.read_bytes(), b"original")
        with patch.object(QMessageBox, "warning") as warning:
            self.assertFalse(self._save(self.folder / "missing" / "failed.inp"))
            warning.assert_called_once()
        self.assertFalse(self._save(""))
        self.assertTrue(self.dialog.editor.document().isModified())
        self.assertTrue(self.dialog.editor.toPlainText().endswith("unsaved"))

    def test_save_over_open_target_never_displays_stale_file(self):
        target = self.folder / "next.inp"
        target.write_bytes(b"old content")
        self._append("saved in selected file")
        draft = self.dialog.editor.toPlainText()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Save), \
                patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "")):
            self.assertTrue(self._open(target))
        self.assertEqual(self.dialog.editor.toPlainText(), draft)
        self.assertEqual(target.read_text(), draft)
        self.assertFalse(self.dialog.editor.document().isModified())

    def test_escape_and_window_close_preserve_unsaved_edits_on_cancel(self):
        self._append("# keep")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel) as question:
            QTest.keyClick(self.dialog.editor, Qt.Key.Key_Escape)
            self.assertTrue(self.dialog.isVisible())
            self.assertFalse(self.dialog.close())
            self.assertTrue(self.dialog.isVisible())
            self.assertTrue(self.dialog.editor.document().isModified())
            self.assertEqual(question.call_count, 2)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.dialog.close())
            self.assertFalse(self.dialog.isVisible())

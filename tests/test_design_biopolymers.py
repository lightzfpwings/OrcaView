"""Exercise the Design buttons, asynchronous build dialog and document history."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.io.structure_record import StructureRecord

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QThreadPool, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.biopolymer_dialog import BiopolymerDialog
    from orcaview.gui.design_panel import DesignPanel
except ModuleNotFoundError as exc:
    if not exc.name.startswith("PySide6"):
        raise
    DesignPanel = None


@unittest.skipUnless(DesignPanel, "requires Qt")
class DesignBiopolymers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.session = Session()
        self.panel = DesignPanel()
        self.panel.set_document(self.session.document)
        self.addCleanup(self.panel.close)

    def test_buttons_apply_once_and_restore_geometry_and_atom_ids(self):
        from dataclasses import replace
        document = self.session.document
        for polymer, button, value, module, reader in (
            ("protein", self.panel.protein_button, "aG", "biopolymer_sequence", "build_sequence_record"),
            ("dna", self.panel.dna_button, "1bna", "biopolymer_record", "load_pdb_record"),
        ):
            with self.subTest(polymer=polymer):
                original = document.head
                generated = replace(original.molecule, name=polymer)
                def enter():
                    dialog = self.app.activeModalWidget()
                    dialog.entry.setPlainText(value)
                    dialog.generate.click()
                    QTimer.singleShot(5000, dialog, dialog.reject)

                with patch(f"orcaview.io.{module}.{reader}", return_value=StructureRecord(generated)) as read:
                    QTimer.singleShot(0, enter)
                    button.click()
                    read.assert_called_once_with(polymer, value)
                head = document.head
                self.assertEqual(head.parent, original.ref)
                self.assertEqual(head.molecule, generated)
                self.assertEqual(self.panel.viewport.molecule, generated)
                self.assertFalse(set(head.atom_ids).intersection(original.atom_ids))
                request = json.loads(dict(head.provenance.parameters)["request"])
                self.assertEqual(request["source"], "sequence" if polymer == "protein" else "pdb")
                with TemporaryDirectory() as temp:
                    project = Path(temp) / "design.oview.json"
                    save_project(self.session, project)
                    self.assertEqual(load_project(project).document.head, head)
                self.panel.undo_button.click()
                self.assertEqual(document.head.atom_ids, original.atom_ids)
                self.assertEqual(document.head.molecule, original.molecule)
                self.panel.redo_button.click()
                self.assertEqual(document.head.atom_ids, head.atom_ids)

    def test_error_can_be_corrected_and_cancel_drops_pending_result(self):
        document = self.session.document
        original = document.head
        dialog = BiopolymerDialog("dna", original)
        self.addCleanup(dialog.close)
        dialog.show()
        self.assertFalse(dialog.generate.isEnabled())
        dialog.entry.setPlainText("ACU")
        dialog.generate.click()
        for _ in range(200):
            if dialog.generate.isEnabled():
                break
            QTest.qWait(10)
        self.assertEqual(dialog.entry.toPlainText(), "ACU")
        self.assertIn("A, C, G and T", dialog.status.text())
        gate = Event()
        def delayed(*args):
            gate.wait(2)
            return StructureRecord(original.molecule)
        with patch("orcaview.io.biopolymer_record.load_pdb_record", side_effect=delayed):
            dialog.entry.setPlainText("1BNA")
            dialog.generate.click()
            dialog.reject()
            gate.set()
            self.assertTrue(QThreadPool.globalInstance().waitForDone(3000))
            self.app.processEvents()
        self.assertIsNone(dialog.command)
        self.assertIs(document.head, original)

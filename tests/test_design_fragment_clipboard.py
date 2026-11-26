"""Copy/paste a disconnected molecule through the Design keyboard shortcuts."""

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QMimeData
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.design_panel import DesignPanel
    from orcaview.gui.fragment_clipboard import FRAGMENT_MIME
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    DesignPanel = None

from orcaview.application.session import Session
from orcaview.core.geometry import connected_component, display_bonds
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.editing import SetSketchLayout


@unittest.skipIf(DesignPanel is None, "requires Qt")
class FragmentClipboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.clipboard = self.app.clipboard()
        previous = self.clipboard.mimeData()
        saved = QMimeData()
        if previous is not None:
            for name in previous.formats():
                saved.setData(name, previous.data(name))
        if saved.formats():
            self.addCleanup(self.clipboard.setMimeData, saved)
        else:
            self.addCleanup(self.clipboard.clear)
        self.atoms = (Atom("O", 0., 0., .4), Atom("F", 3., 0., .5), Atom("H", .9, .1, .3),
                      Atom("H", 3.2, .85, .8), Atom("H", -.5, .7, .1))
        self.bonds = (Bond(2, 0, 1, "wedge"), Bond(0, 4), Bond(1, 3), Bond(2, 1, 1, "hydrogen_bond"))
        self.doc = Session(Molecule("Water and HF", self.atoms, self.bonds, bonds_explicit=True)).document
        self.panel = DesignPanel()
        self.addCleanup(self.panel.close)
        self.panel.set_document(self.doc)
        self.panel.resize(1160, 680)
        self.panel.show()
        self.panel.activateWindow()
        self.app.processEvents()

    def shortcut(self, widget, key):
        widget.setFocus()
        self.app.processEvents()
        sequence = QKeySequence(key)
        QTest.keySequence(widget, sequence)
        self.app.processEvents()

    def assert_rigid_copy(self, original, new):
        self.assertEqual(len(original), len(new))
        shift = [b - a for a, b in zip(original[0], new[0])]
        for old, copied in zip(original, new):
            for a, b, delta in zip(old, copied, shift):
                self.assertAlmostEqual(b - a, delta)

    def test_shortcuts_copy_one_component_with_its_sketch_and_reversible_selection(self):
        xy = ((4., 1.), (-2., 1.), (5., 1.), (-3., .5), (3.6, 1.8))
        self.panel._execute(SetSketchLayout(xy))
        original = self.doc.head
        self.panel._select([2])
        self.shortcut(self.panel.viewport, QKeySequence.StandardKey.Copy)
        self.assertIs(self.doc.head, original)
        payload = bytes(self.clipboard.mimeData().data(FRAGMENT_MIME))
        self.assertTrue(all(atom_id.encode() not in payload for atom_id in original.atom_ids))
        self.shortcut(self.panel.canvas, QKeySequence.StandardKey.Paste)
        pasted = self.doc.head
        self.assertEqual(pasted.ref.revision, original.ref.revision + 1)
        self.assertEqual(pasted.atom_ids[:5], original.atom_ids)
        self.assertEqual(pasted.molecule.atoms[:5], self.atoms)
        self.assertEqual(pasted.molecule.bonds, self.bonds + (Bond(6, 5, 1, "wedge"), Bond(5, 7)))
        self.assertEqual(connected_component(pasted.molecule.bonds, 5), {5, 6, 7})
        self.assert_rigid_copy([original.coordinates()[i] for i in (0, 2, 4)], pasted.coordinates()[5:])
        self.assertEqual(pasted.sketch_xy[:5], xy)
        self.assert_rigid_copy([xy[i] for i in (0, 2, 4)], pasted.sketch_xy[5:])
        self.assertEqual(self.panel.editor.selection.atom_ids, pasted.atom_ids[5:])
        self.panel.undo_button.click()
        self.assertEqual(self.doc.head.molecule, original.molecule)
        self.assertEqual(self.doc.head.sketch_xy, xy)
        self.assertEqual(self.panel.editor.selection.atom_ids, (original.atom_ids[2],))
        self.panel.redo_button.click()
        self.assertEqual(self.doc.head.atom_ids, pasted.atom_ids)
        self.assertEqual(self.panel.editor.selection.atom_ids, pasted.atom_ids[5:])
        self.shortcut(self.panel.viewport, QKeySequence.StandardKey.Paste)
        twice = self.doc.head
        self.assertEqual(len(set(twice.atom_ids)), 11)
        self.assertGreater(min(a.x for a in twice.molecule.atoms[8:]), max(a.x for a in pasted.molecule.atoms))

    def test_inferred_bonds_and_cross_document_paste_without_ids(self):
        source = Session().document
        self.panel.set_document(source)
        self.panel._select([1])
        self.shortcut(self.panel.canvas, QKeySequence.StandardKey.Copy)
        target = Session(Molecule("New structure", (), bonds_explicit=True)).document
        self.panel.set_document(target)
        self.shortcut(self.panel.canvas, QKeySequence.StandardKey.Paste)
        self.assertEqual(target.head.molecule.atoms, source.head.molecule.atoms)
        self.assertEqual(target.head.molecule.bonds, display_bonds(source.head.molecule))
        self.assertTrue(target.head.molecule.bonds_explicit)
        self.assertTrue(set(target.head.atom_ids).isdisjoint(source.head.atom_ids))
        self.assertIsNone(target.head.sketch_xy)

    def test_text_focus_unrelated_clipboard_and_invalid_selection(self):
        self.panel._select([0])
        field = self.panel.coordinates[0].lineEdit()
        field.selectAll()
        self.shortcut(field, QKeySequence.StandardKey.Copy)
        self.assertTrue(self.clipboard.mimeData().hasText())
        self.assertFalse(self.clipboard.mimeData().hasFormat(FRAGMENT_MIME))
        text = self.clipboard.text()
        before = self.doc.head
        for selected in ([], [0, 1]):
            self.panel._select(selected)
            self.shortcut(self.panel.canvas, QKeySequence.StandardKey.Copy)
            self.assertEqual(self.clipboard.text(), text)
        self.shortcut(self.panel.canvas, QKeySequence.StandardKey.Paste)
        self.assertIs(self.doc.head, before)
        for invalid in (b"not json", json.dumps({"version": 1, "atoms": [], "bonds": [], "sketch_xy": None}).encode()):
            mime = QMimeData()
            mime.setData(FRAGMENT_MIME, invalid)
            self.clipboard.setMimeData(mime)
            self.shortcut(self.panel.viewport, QKeySequence.StandardKey.Paste)
            self.assertIs(self.doc.head, before)

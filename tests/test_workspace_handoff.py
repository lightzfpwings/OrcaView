"""Exercise visual and molecular handoffs among the three desktop workspaces."""

from dataclasses import replace
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orcaview.application.session import Session
from orcaview.core.models import Atom, Bond, Molecule
from orcaview.core.provenance import Provenance
from orcaview.editing import DeleteAtoms, EditorService, GeometryEditCommand

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QAbstractAnimation, Qt
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QStyle
    from orcaview.gui.main_window import MainWindow
    from orcaview.gui.result_demo import build_result_demo
    from orcaview.gui.result_import import SummaryView, read_native_session
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    MainWindow = None


class ResultGeometryTests(unittest.TestCase):
    def test_coordinate_only_frame_uses_parent_bonds_and_live_atom_ids(self):
        mol = Molecule("CO", (Atom("C", 0, 0, 0), Atom("O", 1.14, 0, 0)),
                       (Bond(0, 1, 3),), bonds_explicit=True)
        doc = Session(mol).document
        root = doc.head
        frame_atoms = root.molecule.atoms[1], Atom("C", -0.12, 0, 0)
        frame = doc.add_frame(root.ref, "scf", replace(mol, atoms=frame_atoms, bonds=(), bonds_explicit=False),
                              root.atom_ids[::-1], Provenance("fixture"))
        editor = EditorService(doc)
        editor.commit(editor.preview(GeometryEditCommand(root.ref, DeleteAtoms(root.atom_ids[:1]))))
        deleted = doc.head
        restored = editor.use_result_geometry(frame.ref).snapshot
        self.assertEqual(restored.molecule.atoms, frame_atoms)
        self.assertEqual(restored.molecule.bonds, (Bond(1, 0, 3),))
        self.assertTrue(restored.molecule.bonds_explicit)
        self.assertEqual(restored.atom_ids[0], root.atom_ids[1])
        self.assertNotIn(restored.atom_ids[1], root.atom_ids)
        self.assertEqual(editor.undo().snapshot.molecule, deleted.molecule)
        self.assertEqual(editor.redo().snapshot.atom_ids, restored.atom_ids)
        self.assertIsNone(editor.use_result_geometry(frame.ref))
        self.assertIs(doc.resolve(frame.ref), frame)
        other = Session(mol).document
        with self.assertRaises(ValueError):
            editor.use_result_geometry(other.head.ref)


@unittest.skipIf(MainWindow is None, "requires Qt")
class WorkspaceHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.dirty = False
        self.window.close()
        self.app.processEvents()

    def test_empty_design_yes_no_and_result_history_after_undo(self):
        w = self.window
        session, dataset_id = build_result_demo()
        w.open_result_session(session, dataset_id, mark_dirty=False)
        tabs, design, result = w.workspace_tabs, w.design_panel, w.foundation_panel
        tabs.setCurrentWidget(design)
        head = session.document.head
        design._select(range(len(head.atom_ids)))
        design.delete_button.click()
        self.app.processEvents()
        empty = session.document.head
        self.assertEqual(empty.atom_ids, ())
        buttons = QMessageBox.StandardButton
        with patch.object(QMessageBox, "exec", side_effect=[buttons.Yes, buttons.No, buttons.No]) as prompt:
            tabs.setCurrentWidget(w.input_page)
            self.assertIs(tabs.currentWidget(), design)
            tabs.setCurrentWidget(w.input_page)
            self.assertIs(tabs.currentWidget(), w.input_page)
            for widget in (w.inspector_dock, w.tree_dock, w.bottom_dock, w.viewport):
                self.assertTrue(widget.isHidden())
            for action in (w.find_method_action, w.native_editor_action, w.export_action, w.fit_action):
                self.assertFalse(action.isEnabled())
            self.assertEqual(w.statusBar().currentMessage(), "")
            self.assertFalse(w.method.isEnabled())
            self.assertEqual(w.input_preview.toPlainText(), "")
            self.assertEqual(w.tree.topLevelItemCount(), 0)
            self.assertTrue(w.open_file_action.isEnabled())
            tabs.setCurrentWidget(result)
            self.assertIs(tabs.currentWidget(), result)
            self.assertEqual(prompt.call_count, 3)
            self.assertTrue(result.result_contents.isHidden())
            self.assertFalse(result.design_button.isEnabled())
            self.assertEqual((result.datasets.rowCount(), result.atoms.rowCount(), result.spectra.topLevelItemCount()),
                             (0, 0, 0))
            result.view_dataset(dataset_id)
            self.assertIsNone(result.selection_context)
            self.assertIsNone(result.viewport.molecule)
            self.assertIs(session.document.head, empty)
            tabs.setCurrentWidget(design)
            design.undo_button.click()
            self.assertEqual(session.document.head.atom_ids, head.atom_ids)
            tabs.setCurrentWidget(result)
            result.view_dataset(dataset_id)
            self.assertEqual(result.selection_context.geometry, session.document.dataset(dataset_id).geometry)
            tabs.setCurrentWidget(w.input_page)
            self.assertEqual(prompt.call_count, 3)
            self.assertTrue(w.inspector_dock.isVisible() and w.tree_dock.isVisible() and w.bottom_dock.isVisible())
            self.assertTrue(w.find_method_action.isEnabled() and w.method.isEnabled())
            self.assertEqual(w.input_preview.toPlainText(), session.input_text())

    def test_empty_project_reopens_in_design_and_opening_structure_restores_input(self):
        w = self.window
        design = w.design_panel
        w.workspace_tabs.setCurrentWidget(design)
        design._select(range(len(w.session.document.head.atom_ids)))
        design.delete_button.click()
        self.assertFalse(w.session.molecule.atoms)
        with TemporaryDirectory() as folder:
            path = str(Path(folder) / "empty.oview.json")
            with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")):
                self.assertTrue(w.save_project_dialog())
            with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.No) as prompt:
                w.workspace_tabs.setCurrentWidget(w.input_page)
                w._open_project_path(path)
                self.assertFalse(w.session.molecule.atoms)
                self.assertIs(w.workspace_tabs.currentWidget(), design)
                self.assertEqual(prompt.call_count, 1)
                w.workspace_tabs.setCurrentWidget(w.input_page)
                with patch.object(QFileDialog, "getOpenFileName", return_value=("examples/water.xyz", "")):
                    w.open_file()
                self.assertEqual(len(w.session.molecule.atoms), 3)
                self.assertTrue(w.bottom_dock.isVisible() and w.inspector_dock.isVisible())
                self.assertTrue(w.export_button.isEnabled())
                self.assertEqual(w.input_preview.toPlainText(), w.session.input_text())

    def test_empty_draft_keeps_bound_report_when_an_independent_log_is_opened(self):
        w = self.window
        path = Path("examples/m5_orca/water-sp.out")
        session = read_native_session(path)
        w.open_result_session(session, mark_dirty=False)
        design, result = w.design_panel, w.foundation_panel
        w.workspace_tabs.setCurrentWidget(design)
        design._select(range(len(session.document.head.atom_ids)))
        design.delete_button.click()
        report = session.log_report
        other = replace(report, status="another log")
        summary = w.output_summary.toPlainText()
        with patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.No):
            w._show_log_only(path, other)
            w._show_summary(path, SummaryView("another summary", other))
        self.assertIs(w.workspace_tabs.currentWidget(), result)
        self.assertIsNone(result.selection_context)
        self.assertEqual(w.output_summary.toPlainText(), summary)
        self.assertEqual(w.statusBar().currentMessage(), "")
        w.workspace_tabs.setCurrentWidget(design)
        design.undo_button.click()
        w.workspace_tabs.setCurrentWidget(result)
        self.assertIs(result._report, report)
        self.assertGreater(result.datasets.rowCount(), 0)

    def test_crossfade_is_interruptible_and_preserves_the_working_layout(self):
        window = self.window
        tabs, design, result = window.workspace_tabs, window.design_panel, window.foundation_panel
        transition = window.workspace_transition
        transition._animation.setDuration(60_000)
        head = window.session.document.head
        animated = window.style().styleHint(QStyle.StyleHint.SH_Widget_Animate)
        for target in (design, result, design, window.input_page):
            tabs.setCurrentWidget(target)
            self.app.processEvents()
            self.assertIs(tabs.currentWidget(), target)
            if animated:
                self.assertEqual(transition._animation.state(), QAbstractAnimation.State.Running)
                self.assertTrue(transition.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
                transition._animation.setCurrentTime(30_000)
            else:
                self.assertTrue(transition.isHidden())
        transition._animation.setCurrentTime(60_000)
        self.assertTrue(transition.isHidden())
        self.assertIsNone(transition._image)
        self.assertTrue(window.tree_dock.isVisible() and window.bottom_dock.isVisible())
        self.assertIs(window.session.document.head, head)

    def test_result_button_uses_actual_frame_and_preserves_bound_dataset_on_undo(self):
        session, dataset_id = build_result_demo()
        doc = session.document
        original = doc.head
        changed_state = replace(original.molecule, charge=1, multiplicity=2)
        original = doc.publish_revision(original.ref, changed_state, original.atom_ids, Provenance("fixture"))
        data = doc.dataset(dataset_id)
        frame = doc.resolve(data.geometry)
        window = self.window
        window.open_result_session(session, dataset_id, mark_dirty=False)
        window.workspace_tabs.setCurrentWidget(window.design_panel)
        self.assertIs(doc.head, original)
        window.workspace_tabs.setCurrentWidget(window.foundation_panel)
        window.foundation_panel.design_button.click()
        self.assertIs(window.workspace_tabs.currentWidget(), window.design_panel)
        self.assertEqual((doc.head.molecule, doc.head.atom_ids), (frame.molecule, frame.atom_ids))
        self.assertTrue(window.dirty)
        self.assertEqual((window.charge.value(), window.multiplicity.value()), (0, 1))
        window.workspace_tabs.setCurrentWidget(window.input_page)
        self.assertEqual(window.input_preview.toPlainText(), session.input_text())
        window.workspace_tabs.setCurrentWidget(window.design_panel)
        window.design_panel.undo_button.click()
        self.assertEqual((doc.head.molecule, doc.head.atom_ids), (original.molecule, original.atom_ids))
        self.assertEqual((window.charge.value(), window.multiplicity.value()), (1, 2))
        window.workspace_tabs.setCurrentWidget(window.foundation_panel)
        self.assertEqual(window.foundation_panel.selection_context.geometry, frame.ref)
        self.assertIs(doc.dataset(dataset_id), data)

    def test_same_structure_and_log_without_geometry_do_not_replace_the_design(self):
        window = self.window
        result = window.foundation_panel
        session = read_native_session(Path("examples/m5_orca/water-sp.out"))
        window.open_result_session(session, mark_dirty=False)
        head = session.document.head
        result.design_button.click()
        self.assertIs(window.workspace_tabs.currentWidget(), window.design_panel)
        self.assertIs(session.document.head, head)
        self.assertFalse(window.dirty)
        window.workspace_tabs.setCurrentWidget(result)
        result.set_log_report(session.log_report, standalone=True)
        self.assertIsNone(result.selection_context)
        self.assertFalse(result.design_button.isEnabled())
        result.design_button.click()
        self.assertIs(window.workspace_tabs.currentWidget(), result)
        self.assertIs(session.document.head, head)

"""Design buttons, background completion, editor history and ORCA input handoff."""

from dataclasses import replace
from importlib.util import find_spec
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch

from orcaview.core.models import Bond
from orcaview.editing.optimization import OptimizationResult

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QSignalSpy, QTest
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton
    from orcaview.gui.main_window import MainWindow
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    MainWindow = None


@unittest.skipIf(MainWindow is None, "Requires Qt")
class DesignModelingActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.panel = self.window.design_panel
        self.window.show()
        self.window.workspace_tabs.setCurrentWidget(self.panel)
        self.app.processEvents()
        self.panel.findChild(QPushButton, "designNew").click()
        self.app.processEvents()
        self.document = self.window.session.document

    def tearDown(self):
        self.window.dirty = False
        self.window.close()
        self.app.processEvents()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 15
        while not predicate():
            self.app.processEvents()
            if time.monotonic() > deadline:
                self.fail(f"Timed out waiting for the modeling job: {self.panel.status.text()}")
            time.sleep(.005)
        self.app.processEvents()

    def run_optimization(self, button):
        self.assertTrue(button.isEnabled())
        button.click()
        self.wait_until(lambda: self.panel._structure_job is None)
        return self.document.head

    def draw_second_carbon(self):
        panel = self.panel
        panel.findChild(QPushButton, "designBond1").click()
        start = panel.canvas.atom_position(0).toPoint()
        end = start + QPoint(65, -35)
        QTest.mousePress(panel.canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(panel.canvas, end)
        QTest.mouseRelease(panel.canvas, Qt.MouseButton.LeftButton, pos=end)
        panel.select_tool.click()
        return self.document.head

    def select_atom(self, index, *, shift=False):
        canvas = self.panel.canvas
        modifier = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, modifier, canvas.atom_position(index).toPoint())

    def add_one_h(self, index=0, *, in_3d=False):
        if not self.panel.hydrogens.isChecked():
            QTest.mouseClick(self.panel.hydrogens, Qt.MouseButton.LeftButton)
        if in_3d:
            view = self.panel.viewport
            view.repaint()
            x, y, *_ = view._projected[index]
            QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=QPoint(round(x), round(y)))
        else:
            self.select_atom(index)
        return self.document.head

    def fill_h(self):
        QTest.mouseDClick(self.panel.hydrogens, Qt.MouseButton.LeftButton)
        self.wait_until(lambda: self.panel._structure_job is None)
        return self.document.head

    def check_undo_redo(self, previous, changed):
        self.assertEqual(changed.parent, previous.ref)
        self.panel.undo_button.click()
        self.assertEqual((self.document.head.molecule, self.document.head.atom_ids, self.document.head.sketch_xy),
                         (previous.molecule, previous.atom_ids, previous.sketch_xy))
        self.panel.redo_button.click()
        self.assertEqual((self.document.head.molecule, self.document.head.atom_ids, self.document.head.sketch_xy),
                         (changed.molecule, changed.atom_ids, changed.sketch_xy))

    def test_h_toolbar_position_and_equal_control_heights(self):
        panel = self.panel
        h_button = panel.findChild(QPushButton, "designAddHydrogens")
        self.assertIs(h_button, panel.hydrogens)
        self.assertEqual(h_button.text(), "+H")
        self.assertIsNone(h_button.menu())
        controls = [panel.select_tool, panel.atom_tool, panel.element]
        controls.extend(panel.findChild(QPushButton, f"designBond{order}") for order in (1, 2, 3, 0))
        controls.extend([panel.ring_tool, h_button, panel.undo_button, panel.redo_button, panel.delete_button,
                         panel.findChild(QPushButton, "designNew")])
        for width in (1120, 1440):
            self.window.resize(width, 780)
            self.app.processEvents()
            self.assertTrue(all(control.isVisibleTo(panel) for control in controls))
            self.assertEqual({control.height() for control in controls}, {panel.ring_tool.height()})
            self.assertEqual(panel.ring_tool.width(), panel.element.width())
            self.assertEqual(len({control.mapTo(panel, QPoint()).y() for control in controls}), 1)
            left = panel.ring_tool.mapTo(panel, QPoint()).x()
            gap = h_button.mapTo(panel, QPoint()).x() - left - panel.ring_tool.width()
            self.assertTrue(0 <= gap <= 16, gap)

    def test_h_tool_clicks_target_clicked_atoms_in_both_views(self):
        panel = self.panel
        skeleton = self.draw_second_carbon()
        self.assertEqual(panel.editor.selection.atom_ids, (skeleton.atom_ids[1],))
        QTest.mouseClick(panel.hydrogens, Qt.MouseButton.LeftButton)
        self.assertTrue(panel.hydrogens.isChecked())
        self.assertIs(self.document.head, skeleton)
        for view in (panel.canvas, panel.viewport):
            self.assertEqual(view.cursor().shape(), Qt.CursorShape.BitmapCursor)
            QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=QPoint(3, 3))
        self.assertIs(self.document.head, skeleton)
        first = self.add_one_h(0)
        second = self.add_one_h(0)
        self.assertEqual(first.parent, skeleton.ref)
        self.assertEqual(second.molecule.bonds, skeleton.molecule.bonds + (Bond(0, 2), Bond(0, 3)))
        third = self.add_one_h(1, in_3d=True)
        self.assertEqual(third.molecule.bonds[-1], Bond(1, 4))
        self.assertEqual(panel.editor.selection.atom_ids, (skeleton.atom_ids[1],))
        self.check_undo_redo(second, third)
        panel.canvas.setFocus()
        QTest.keyClick(panel.canvas, Qt.Key.Key_Escape)
        self.assertFalse(panel.hydrogens.isChecked())
        self.assertTrue(panel.select_tool.isChecked())
        self.assertEqual(panel.canvas.cursor().shape(), Qt.CursorShape.ArrowCursor)
        self.assertEqual(panel.viewport.cursor().shape(), Qt.CursorShape.ArrowCursor)

    def test_double_click_fills_entire_structure_once_and_saturation_is_a_noop(self):
        skeleton = self.draw_second_carbon()
        partial = self.add_one_h(1)
        self.assertEqual(len(partial.atom_ids), 3)
        observed = QSignalSpy(self.panel.geometry_changed)
        # Qt delivers this click before the double-click event on a real machine.
        QTest.mouseClick(self.panel.hydrogens, Qt.MouseButton.LeftButton)
        filled = self.fill_h()
        self.assertEqual(observed.count(), 1)
        self.assertEqual(filled.atom_ids[:3], partial.atom_ids)
        self.assertEqual(filled.molecule.atoms[:3], partial.molecule.atoms)
        self.assertEqual(len(filled.atom_ids), 8)
        self.assertEqual([b.a for b in filled.molecule.bonds[2:]], [0, 0, 0, 1, 1])
        self.assertEqual(self.panel.editor.selection.atom_ids, (skeleton.atom_ids[1],))
        self.assertIs(self.fill_h(), filled)
        self.assertEqual(observed.count(), 1)
        self.check_undo_redo(partial, filled)

    def test_rapid_clicks_keep_3d_target_under_cursor(self):
        panel = self.panel
        panel.hydrogens.click()
        view = panel.viewport
        view.repaint()
        x, y, *_ = view._projected[0]
        spot = QPoint(round(x), round(y))
        screen = view.mapToGlobal(spot)
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=spot)
        self.app.processEvents()
        QTest.mouseDClick(view, Qt.MouseButton.LeftButton, pos=view.mapFromGlobal(screen))
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=view.mapFromGlobal(screen))
        self.assertEqual(self.document.head.molecule.bonds, (Bond(0, 1), Bond(0, 2)))
        view.repaint()
        x, y, *_ = view._projected[0]
        self.assertEqual(view.mapToGlobal(QPoint(round(x), round(y))), screen)

    def test_repeated_sketch_clicks_at_edge_do_not_recenter_the_target(self):
        canvas = self.panel.canvas
        start = canvas.atom_position(0).toPoint()
        spot = QPoint(canvas.width() - 14, start.y())
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=spot)
        self.assertEqual(canvas.atom_position(0).toPoint(), spot)
        self.panel.hydrogens.click()
        screen = canvas.mapToGlobal(spot)
        for _ in range(3):
            QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=canvas.mapFromGlobal(screen))
            self.app.processEvents()
            self.assertEqual(canvas.mapToGlobal(canvas.atom_position(0).toPoint()), screen)
        self.assertEqual(self.document.head.molecule.bonds, tuple(Bond(0, i) for i in range(1, 4)))

    @unittest.skipUnless(find_spec("openbabel"), "Requires the desktop Open Babel package")
    def test_double_click_does_not_add_hydrogens_to_coordinate_only_benzene(self):
        from orcaview.gui.main_window import demo_benzene
        from orcaview.application.session import Session
        self.document = Session(demo_benzene()).document
        self.panel.set_document(self.document)
        initial = self.document.head
        self.assertIs(self.fill_h(), initial)
        self.assertIn("没有可自动补加", self.panel.status.text())

    def test_unlimited_additions_display_diagnostics_and_can_be_undone(self):
        self.select_atom(0)
        for _ in range(4):
            methane = self.add_one_h()
        fifth = self.add_one_h()
        self.assertEqual(fifth.molecule.bonds, methane.molecule.bonds + (Bond(0, 5),))
        problems = self.panel.problems
        self.assertTrue(problems.isVisibleTo(self.panel))
        self.assertIn("C1", problems.text())
        self.assertIn("5", problems.text())
        self.assertIn("电子", problems.text())
        self.panel.undo_button.click()
        self.assertEqual(self.document.head.molecule, methane.molecule)
        self.assertFalse(problems.isVisibleTo(self.panel))
        self.panel.redo_button.click()
        self.assertEqual(self.document.head.atom_ids, fifth.atom_ids)
        self.assertTrue(problems.isVisibleTo(self.panel))
        sixth = self.add_one_h()
        self.assertEqual(sixth.molecule.bonds, fifth.molecule.bonds + (Bond(0, 6),))
        self.assertIn("6", problems.text())
        self.assertNotIn("电子", problems.text())

    def assert_input_geometry(self, head):
        self.window.workspace_tabs.setCurrentWidget(self.window.input_page)
        self.app.processEvents()
        preview = self.window.input_preview.toPlainText()
        lines = preview.split("* xyz 0 1\n")[1].splitlines()
        self.assertEqual(lines[-1], "*")
        self.assertEqual(len(lines[:-1]), len(head.atom_ids))
        for atom, line in zip(head.molecule.atoms, lines):
            element, x, y, z = line.split()
            self.assertEqual(element, atom.element)
            for written, value in zip((x, y, z), (atom.x, atom.y, atom.z)):
                self.assertAlmostEqual(float(written), value, places=7)
        self.assertEqual(self.window.viewport.molecule, head.molecule)
        self.window.workspace_tabs.setCurrentWidget(self.panel)
        return preview

    @unittest.skipUnless(find_spec("openbabel"), "Requires the desktop Open Babel package")
    def test_clean_sketch_and_relax_methane_then_export_and_reopen(self):
        self.select_atom(0)
        for _ in range(4):
            methane = self.add_one_h()
        original_input = self.assert_input_geometry(methane)
        self.panel.viewport.rotate_view("x", 24)
        self.panel.viewport.zoom = 1.3
        original_camera = self.panel.viewport.camera_transform(0, 0, 1)
        planar = self.run_optimization(self.panel.clean_2d)
        self.assertEqual(planar.atom_ids, methane.atom_ids)
        self.assertEqual(planar.molecule, methane.molecule)
        self.assertEqual(self.panel.viewport.molecule, methane.molecule)
        self.assertEqual(self.panel.viewport.zoom, 1.3)
        self.assertEqual(self.panel.viewport.camera_transform(0, 0, 1), original_camera)
        self.assertIsNotNone(planar.sketch_xy)
        self.assertNotEqual(planar.sketch_xy, tuple((a.x, a.y) for a in methane.molecule.atoms))
        self.assertEqual(tuple((a.x, a.y) for a in self.panel.canvas.molecule.atoms), planar.sketch_xy)
        changed = QSignalSpy(self.panel.geometry_changed)
        self.assertIs(self.run_optimization(self.panel.clean_2d), planar)
        self.assertEqual(changed.count(), 0)
        self.assertEqual(self.panel.status.text(), "二维草图已规整。")
        self.check_undo_redo(methane, planar)
        self.assertEqual(self.assert_input_geometry(planar), original_input)
        before_relax = self.document.head
        relaxed = self.run_optimization(self.panel.optimize_3d)
        self.assertEqual(relaxed.atom_ids, planar.atom_ids)
        self.assertEqual(relaxed.molecule.bonds, planar.molecule.bonds)
        self.assertEqual(relaxed.sketch_xy, planar.sketch_xy)
        self.assertEqual(tuple((a.x, a.y) for a in self.panel.canvas.molecule.atoms), planar.sketch_xy)
        self.assertRegex(self.panel.status.text(), "MMFF94|UFF")
        self.assertGreater(max(a.z for a in relaxed.molecule.atoms) - min(a.z for a in relaxed.molecule.atoms), 1.)
        center, *hydrogens = relaxed.coordinates()
        self.assertTrue(all(1.0 < math.dist(center, h) < 1.2 for h in hydrogens))
        self.check_undo_redo(before_relax, relaxed)
        preview = self.assert_input_geometry(relaxed)
        with TemporaryDirectory() as temp:
            inp, project = Path(temp) / "methane.inp", Path(temp) / "methane.oview.json"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(inp), "")):
                self.window.export_input()
            self.assertEqual(inp.read_text(), preview)
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(project), "")):
                self.assertTrue(self.window.save_project_dialog())
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(project), "")):
                self.window.open_project()
            restored = self.window.session.document.head
            self.assertEqual((restored.molecule, restored.atom_ids, restored.sketch_xy),
                             (relaxed.molecule, relaxed.atom_ids, planar.sketch_xy))
            self.assertEqual(self.assert_input_geometry(restored), preview)

    @unittest.skipUnless(find_spec("openbabel"), "Requires the desktop Open Babel package")
    def test_hydrogenated_six_ring_relaxes_from_flat_carbon_skeleton(self):
        from openbabel import openbabel as ob
        from orcaview.io.babel_geometry import build_obmol, geometry_payload

        panel = self.panel
        ring_menu = panel.ring_menu
        action = next(action for action in ring_menu.actions() if tuple(action.data()) == (6, False))
        ring_menu.popup(panel.ring_tool.mapToGlobal(panel.ring_tool.rect().bottomLeft()))
        self.app.processEvents()
        QTest.mouseClick(ring_menu, Qt.MouseButton.LeftButton, pos=ring_menu.actionGeometry(action).center())
        QTest.mouseClick(panel.canvas, Qt.MouseButton.LeftButton, pos=panel.canvas.atom_position(0).toPoint())
        self.assertEqual(len(self.document.head.atom_ids), 6)
        panel.select_tool.click()
        filled = self.fill_h()
        self.assertEqual([a.element for a in filled.molecule.atoms], ["C"] * 6 + ["H"] * 12)
        self.assertEqual(len(set(a.z for a in filled.molecule.atoms[:6])), 1)
        relaxed = self.run_optimization(panel.optimize_3d)
        self.assertEqual(relaxed.atom_ids, filled.atom_ids)
        self.assertEqual(relaxed.molecule.bonds, filled.molecule.bonds)
        self.assertEqual(relaxed.sketch_xy, tuple((a.x, a.y) for a in filled.molecule.atoms))
        mol = build_obmol(geometry_payload(relaxed.molecule), ob)
        torsions = [mol.GetTorsion(*(1 + (i + j) % 6 for j in range(4))) for i in range(6)]
        self.assertTrue(all(30. < abs(t) < 75. for t in torsions), torsions)
        self.assertTrue(all(t * torsions[i - 1] < 0. for i, t in enumerate(torsions)), torsions)
        sites = relaxed.coordinates()[6:]
        self.assertGreater(min(math.dist(first, second) for i, first in enumerate(sites) for second in sites[i+1:]),
                           1.5)

    def test_editing_a_cleaned_sketch_and_extending_its_topology(self):
        original = self.draw_second_carbon()
        layout = ((4., 5.), (5.5, 5.))
        with patch("orcaview.gui.structure_job.clean_sketch", return_value=layout):
            cleaned = self.run_optimization(self.panel.clean_2d)
        self.assertEqual(cleaned.sketch_xy, layout)
        canvas = self.panel.canvas
        start = canvas.atom_position(1).toPoint()
        end = start + QPoint(-12, 36)
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        dragged = self.document.head
        self.assertEqual(dragged.molecule, original.molecule)
        self.assertNotEqual(dragged.sketch_xy[1], layout[1])
        self.assertEqual(canvas.atom_position(1).toPoint(), end)

        self.panel.coordinates[2].setValue(2.5)
        self.panel.apply_button.click()
        moved = self.document.head
        self.assertEqual(moved.molecule.atoms[1].z, 2.5)
        self.assertEqual(moved.sketch_xy, dragged.sketch_xy)
        self.panel.findChild(QPushButton, "designBond1").click()
        start = canvas.atom_position(1).toPoint()
        end = start + QPoint(60, -20)
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        extended = self.document.head
        self.assertEqual(extended.sketch_xy[:2], moved.sketch_xy)
        self.assertEqual(canvas.atom_position(2).toPoint(), end)
        self.assertEqual(extended.molecule.atoms[:2], moved.molecule.atoms)
        parent, new = extended.molecule.atoms[1:]
        self.assertAlmostEqual(new.x - parent.x, extended.sketch_xy[2][0] - extended.sketch_xy[1][0])
        self.assertAlmostEqual(new.y - parent.y, extended.sketch_xy[2][1] - extended.sketch_xy[1][1])
        self.assertEqual(new.z, parent.z)

    def test_undo_while_cleaning_the_sketch_discards_the_late_layout(self):
        original = self.draw_second_carbon()
        release, entered = Event(), Event()

        def clean(molecule, sketch_xy):
            entered.set()
            if not release.wait(timeout=10):
                raise ValueError("test worker timed out")
            return ((0., 0.), (1.5, 0.))

        with patch("orcaview.gui.structure_job.clean_sketch", side_effect=clean):
            self.panel.clean_2d.click()
            self.wait_until(entered.is_set)
            self.assertFalse(self.panel.optimize_3d.isEnabled())
            try:
                self.panel.undo_button.click()
                undone = self.document.head
                self.assertNotEqual(undone.atom_ids, original.atom_ids)
            finally:
                release.set()
            self.wait_until(lambda: self.panel._structure_job is None)
        self.assertIs(self.document.head, undone)
        self.assertIsNone(undone.sketch_xy)
        self.assertIn("结构已更改", self.panel.status.text())

    def test_cleanup_finishing_on_the_input_page_preserves_the_displayed_input(self):
        original = self.draw_second_carbon()
        preview = self.assert_input_geometry(original)
        layout = ((0., 0.), (1.5, 0.))
        release, entered = Event(), Event()

        def clean(molecule, sketch_xy):
            entered.set()
            if not release.wait(timeout=10):
                raise ValueError("test worker timed out")
            return layout

        with patch("orcaview.gui.structure_job.clean_sketch", side_effect=clean):
            self.panel.clean_2d.click()
            self.wait_until(entered.is_set)
            try:
                self.window.workspace_tabs.setCurrentWidget(self.window.input_page)
            finally:
                release.set()
            self.wait_until(lambda: self.panel._structure_job is None)
        self.assertEqual(self.window.input_preview.toPlainText(), preview)
        self.assertEqual(self.window.viewport.molecule, original.molecule)
        self.assertEqual(self.document.head.sketch_xy, layout)
        self.window.workspace_tabs.setCurrentWidget(self.panel)
        self.assertEqual(tuple((a.x, a.y) for a in self.panel.canvas.molecule.atoms), layout)

    def test_worker_failure_keeps_current_revision_and_enables_retry(self):
        initial = self.draw_second_carbon()
        with patch("orcaview.gui.structure_job.optimize_structure", side_effect=ValueError("backend failure")):
            self.assertIs(self.run_optimization(self.panel.optimize_3d), initial)
        self.assertEqual(self.panel.status.text(), "backend failure")
        self.assertTrue(self.panel.optimize_3d.isEnabled())
        self.panel.undo_button.click()
        self.assertEqual(len(self.document.head.molecule.atoms), 1)

    def check_late_completion(self, replace_document):
        release = Event()
        entered = Event()

        before = self.draw_second_carbon()

        def paused_optimization(molecule, mode):
            entered.set()
            if not release.wait(timeout=10):
                raise ValueError("test worker timed out")
            changed = replace(molecule.atoms[0], z=2.)
            return OptimizationResult(replace(molecule, atoms=(changed, molecule.atoms[1])), "MMFF94")

        with patch("orcaview.gui.structure_job.optimize_structure", side_effect=paused_optimization):
            self.panel.optimize_3d.click()
            self.wait_until(entered.is_set)
            completed = QSignalSpy(self.panel._structure_job.completion.finished)
            try:
                if replace_document:
                    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard):
                        self.panel.findChild(QPushButton, "designNew").click()
                    self.assertIsNot(self.window.session.document, self.document)
                else:
                    QTest.mouseClick(self.panel.canvas, Qt.MouseButton.LeftButton,
                                     pos=self.panel.canvas.atom_position(0).toPoint())
                    self.panel.coordinates[0].setValue(1.5)
                    self.panel.apply_button.click()
                    self.assertEqual(self.document.head.molecule.atoms[0].x, 1.5)
                expected = self.window.session.document.head
            finally:
                release.set()
            self.wait_until(lambda: completed.count() > 0 and self.panel._structure_job is None)
            self.assertIs(self.window.session.document.head, expected)
            if replace_document:
                self.assertIs(self.document.head, before)
            else:
                self.assertIn("结构已更改", self.panel.status.text())

    def test_finishing_after_coordinate_edit_discards_stale_coordinates(self):
        self.check_late_completion(replace_document=False)

    def test_finishing_after_new_document_cannot_edit_either_document(self):
        self.check_late_completion(replace_document=True)

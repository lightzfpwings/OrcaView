"""Drive the GBW choice dialog, asynchronous import and orbital workspace."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPoint, QRect, Qt, QTimer
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QColorDialog, QDialogButtonBox, QFileDialog, QStyle, QStyleOptionComboBox
    from orcaview.gui.main_window import MainWindow
    from orcaview.gui.structure_export import save_structure_image
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None

from orcaview.application.project import save_project


@unittest.skipUnless(QApplication, "Requires Qt")
class OrbitalWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.work = TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        prefs = patch.dict(os.environ, ORCAVIEW_CONFIG_DIR=str(self.root / "prefs"))
        prefs.start()
        self.addCleanup(prefs.stop)
        self.gbw = self.root / "试样.轨道 1.GBW"
        self.gbw.write_bytes(b"test gbw")
        self.target = self.gbw.with_suffix(".molden.input")
        self.example = Path(__file__).resolve().parents[1] / "examples/orbitals/OH.molden.input"
        self.w = MainWindow()
        self.w.show()
        self.addCleanup(self.close_window)
        self.app.processEvents()

    def close_window(self):
        self.w.dirty = False
        self.w.close()

    def convert(self, raw, work, converter, cancel):
        self.assertEqual(raw, b"test gbw")
        output = work / "wave.molden.input"
        output.write_bytes(self.example.read_bytes())
        return output

    def open(self, path, choice=None):
        def choose():
            dialog = self.app.activeModalWidget()
            if choice == "cancel":
                dialog.reject()
            elif choice == "convert":
                dialog.convert.click()
            else:
                box = dialog.findChild(QDialogButtonBox)
                next(b for b in box.buttons() if b.text() == "Open existing Molden").click()

        if choice:
            QTimer.singleShot(0, choose)
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")), \
             patch("orcaview.gui.gbw_dialog.find_converter", return_value=Path("orca_2mkl")):
            self.w.open_file_action.trigger()

    def finish_open(self):
        deadline = time.monotonic() + 8
        while self.w._read_future is not None and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertIsNone(self.w._read_future)
        self.assertTrue(self.w.open_file_action.isEnabled())

    def test_gbw_choice_spin_frontiers_and_project_reopen(self):
        initial = self.w.session
        with patch("orcaview.application.structure_import.run_converter", side_effect=self.convert) as converter:
            self.open(self.gbw, "cancel")
            self.assertIs(self.w.session, initial)
            self.assertFalse(self.target.exists())
            converter.assert_not_called()
            self.open(self.gbw, "convert")
            self.finish_open()
            converter.assert_called_once()
        panel = self.w.orbital_panel
        self.assertEqual(self.w.session.source_path, str(self.target))
        self.assertIs(self.w.workspace_tabs.currentWidget(), panel)
        panel.finish_for_capture()
        self.assertEqual(panel.spin.currentData(), "Beta")  # higher-energy occupied frontier
        self.assertIn("HOMO", panel.table.item(panel.table.currentRow(), 0).text())
        self.assertEqual({f[-1] for f in panel.viewport.surface.faces}, {-1, 1})
        panel.spin.setCurrentIndex(panel.spin.findData("Alpha"))
        self.assertEqual(panel.table.currentRow(), 4)
        panel.table.setCurrentCell(5, 0)
        panel.level.setValue(.070)
        panel.finish_for_capture()
        self.assertEqual(panel._requested, (5, .070, panel.quality.currentData()))
        self.assertTrue(panel.viewport.surface.faces)
        project = self.root / "oh.oview.json"
        save_project(self.w.session, project)
        self.w._open_project_path(str(project))
        self.assertIsNone(panel.wave)
        self.assertFalse(self.w.workspace_tabs.isTabEnabled(3))
        panel.finish_loading()
        self.assertTrue(self.w.workspace_tabs.isTabEnabled(3))
        self.w.workspace_tabs.setCurrentWidget(panel)
        panel.finish_for_capture()
        self.assertEqual(len(panel.wave.orbitals), 38)
        self.assertEqual(panel.viewport.molecule, self.w.session.molecule)
        with patch("orcaview.application.structure_import.run_converter") as forbidden:
            self.open(self.gbw, "existing")
            self.finish_open()
            forbidden.assert_not_called()
        self.assertEqual(len(self.w.session.document.head.provenance.parents), 1)
        self.open(self.example.parent.parent / "water.xyz")
        self.assertEqual(self.w.workspace_tabs.indexOf(panel), 3)
        self.assertFalse(self.w.workspace_tabs.isTabEnabled(3))
        self.assertIsNone(panel.wave)

    def test_user_cancel_during_conversion_never_publishes(self):
        started, finished = Event(), Event()
        initial = self.w.session

        def delayed(raw, work, converter, cancel):
            started.set()
            try:
                self.assertTrue(cancel.wait(5))
                return self.convert(raw, work, converter, cancel)
            finally:
                finished.set()

        with patch("orcaview.application.structure_import.run_converter", delayed):
            self.open(self.gbw, "convert")
            self.assertTrue(started.wait(5))
            future = self.w._read_future
            self.w.cancel_read_button.click()
            self.assertTrue(finished.wait(5))
            self.assertTrue(future.exception(timeout=5))
        self.assertIs(self.w.session, initial)
        self.assertFalse(self.target.exists())
        self.assertFalse(list(self.root.glob(".orcaview-*")))

    def test_declining_discard_keeps_existing_molden_and_document(self):
        self.target.write_bytes(b"pre-existing Molden")
        initial = self.w.session
        with patch("orcaview.application.structure_import.run_converter", self.convert), \
             patch.object(self.w, "_guard_discard", return_value=False):
            self.open(self.gbw, "convert")
            self.finish_open()
        self.assertIs(self.w.session, initial)
        self.assertEqual(self.target.read_bytes(), b"pre-existing Molden")
        self.assertFalse(list(self.root.glob(".orcaview-*")))


    def test_only_loaded_wavefunction_or_cube_enables_permanent_tab(self):
        tabs, panel = self.w.workspace_tabs, self.w.orbital_panel
        self.assertEqual([tabs.tabText(i) for i in (2, 3)], ["Result", "Orbitals"])
        self.assertFalse(tabs.isTabEnabled(3))
        tabs.setCurrentIndex(3)
        tabs.setCurrentWidget(panel)
        QTest.mouseClick(tabs.tabBar(), Qt.MouseButton.LeftButton, pos=tabs.tabBar().tabRect(3).center())
        self.assertIs(tabs.currentWidget(), self.w.input_page)
        path = self.root / "water.CUB"
        path.write_bytes((self.example.parent / "water-homo.cube").read_bytes())
        self.open(path)
        self.finish_open()
        self.assertIs(tabs.currentWidget(), panel)
        self.assertTrue(tabs.isTabEnabled(3))
        panel.finish_for_capture()
        self.assertEqual(panel.table.columnCount(), 1)
        self.assertEqual(panel.table.item(0, 0).text(), "4")
        self.assertFalse(panel.spin.isVisible())
        project = self.root / "water.oview.json"
        save_project(self.w.session, project)
        self.w._open_project_path(project)
        self.assertFalse(tabs.isTabEnabled(3))
        panel.finish_loading()
        self.assertTrue(tabs.isTabEnabled(3))
        tabs.setCurrentIndex(3)
        panel.finish_for_capture()
        self.assertTrue(panel.viewport.surface.faces)
        for action, reason in (("changed", "changed"), ("missing", "not found")):
            if action == "changed":
                path.write_bytes(path.read_bytes()+b"\n")
            else:
                path.unlink()
            self.w._open_project_path(project)
            panel.finish_loading()
            self.assertFalse(tabs.isTabEnabled(3))
            self.assertIn(reason, tabs.tabToolTip(3))
            tabs.setCurrentIndex(3)
            self.assertIs(tabs.currentWidget(), self.w.input_page)
            self.assertEqual(len(self.w.session.molecule.atoms), 3)
        geometry = self.root / "geometry.molden"
        geometry.write_bytes(self.example.read_bytes().split(b"[GTO]")[0])
        self.open(geometry)
        self.finish_open()
        self.assertFalse(tabs.isTabEnabled(3))

    def test_palette_custom_colors_export_preferences_and_quality(self):
        self.open(self.example.parent / "water-homo.cube")
        self.finish_open()
        panel = self.w.orbital_panel
        panel.finish_for_capture()
        self.assertEqual(panel.quality.currentData(), "smooth")
        smooth = panel.viewport.surface
        panel.palette_choice.setCurrentIndex(2)
        self.assertIs(panel.viewport.surface, smooth)
        self.assertEqual(panel.colors, {1: "#2c926b", -1: "#8855b5"})
        with patch.object(QColorDialog, "getColor", return_value=QColor("#18b632")):
            panel.color_buttons[1].click()
        with patch.object(QColorDialog, "getColor", return_value=QColor()):
            panel.color_buttons[-1].click()
        self.assertEqual(panel.colors, {1: "#18b632", -1: "#8855b5"})
        self.assertEqual(panel.palette_choice.currentIndex(), -1)
        self.assertIs(panel.viewport.surface, smooth)
        self.assertIsNone(panel.future)
        panel.quality.setCurrentIndex(panel.quality.findData("fine"))
        panel.finish_for_capture()
        self.assertGreater(len(panel.viewport.surface.faces), len(smooth.faces))
        self.assertTrue(self.w.structure_image_action.isEnabled())
        view = panel.viewport
        image_file = self.root / "colored.png"
        save_structure_image(view, image_file, "PNG", view.width(), view.height())
        image = QImage(str(image_file))
        green = purple = 0
        for x in range(0, image.width(), 6):
            for y in range(0, image.height(), 6):
                r, g, b, _ = image.pixelColor(x, y).getRgb()
                green += g > max(r, b)+25
                purple += b > r+10 and r > g+12
        self.assertGreater(min(green, purple), 40)
        from orcaview.gui.orbital_panel import OrbitalPanel
        another = OrbitalPanel()
        try:
            self.assertEqual(another.colors, panel.colors)
            self.assertEqual(another.quality.currentData(), "fine")
            self.assertEqual(another.quality.currentText(), "Best")
        finally:
            another.shutdown()
            another.close()

    def test_quality_dropdown_fits_all_four_rows_and_selects_by_mouse_and_keyboard(self):
        self.w.resize(self.w.minimumSize())
        self.open(self.example.parent / "water-homo.cube")
        self.finish_open()
        panel = self.w.orbital_panel
        field = panel.quality
        self.assertEqual([field.itemText(i) for i in range(field.count())], ["Coarse", "Standard", "Smooth", "Best"])
        self.assertEqual(field.currentData(), "smooth")
        view = field.view()

        def wait_closed():
            end = time.monotonic()+2
            while view.isVisible() and time.monotonic() < end:
                QTest.qWait(10)
            self.assertFalse(view.isVisible())

        for labels in (("粗糙", "标准", "平滑", "极佳"), ("Grob", "Standard", "Glatt", "Beste Qualität")):
            for i, label in enumerate(labels):
                field.setItemText(i, label)
            self.app.processEvents()
            opt = QStyleOptionComboBox()
            field.initStyleOption(opt)
            arrow = field.style().subControlRect(QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxArrow, field)
            edit = field.style().subControlRect(QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxEditField, field)
            self.assertFalse(edit.intersects(arrow))
            self.assertGreaterEqual(edit.width(), max(map(field.fontMetrics().horizontalAdvance, labels)))
            QTest.mouseClick(field, Qt.LeftButton, pos=arrow.center())
            self.assertTrue(view.isVisible())
            self.assertFalse(view.window().geometry().intersects(QRect(field.mapToGlobal(QPoint()), field.size())))
            for i, label in enumerate(labels):
                row = view.visualRect(field.model().index(i, 0))
                self.assertTrue(view.viewport().rect().contains(row))
                self.assertGreaterEqual(row.width(), view.fontMetrics().horizontalAdvance(label))
                self.assertGreaterEqual(row.height(), view.fontMetrics().height())
            target = view.visualRect(field.model().index(0, 0)).center()
            QTest.mouseMove(view.viewport(), target)
            # Cocoa can coalesce synthetic mouse moves during its opening-click guard.
            QTest.qWait(QApplication.doubleClickInterval()+1)
            QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=target)
            wait_closed()
            self.assertEqual(field.currentData(), "coarse")
            field.showPopup()
            QTest.keyClick(view, Qt.Key_End)
            QTest.keyClick(view, Qt.Key_Return)
            wait_closed()
            self.assertEqual(field.currentText(), labels[-1])
        panel.finish_for_capture()
        self.assertEqual(panel._requested[-1], "fine")

    def test_atomless_cube_can_switch_scalar_fields_and_export(self):
        path = self.root / "two fields.cube"
        path.write_text("Example\nTwo fields\n0 12 20 30 2\n-2 1 0 0\n-2 0 1 0\n-2 0 0 1\n"
                        + " ".join(f"{x+y+z} {(x-y)*.000002}" for x in (0,1) for y in (0,1) for z in (0,1)))
        self.open(path)
        self.finish_open()
        panel = self.w.orbital_panel
        self.assertIs(self.w.workspace_tabs.currentWidget(), panel)
        self.assertTrue(self.w.fit_action.isEnabled())
        self.assertEqual(panel.table.rowCount(), 2)
        self.assertEqual(panel.viewport._center, (12.5, 20.5, 30.5))
        panel.table.setCurrentCell(1, 0)
        self.assertAlmostEqual(panel.level.value(), .000001)
        panel.finish_for_capture()
        self.app.processEvents()
        self.assertTrue(self.w.structure_image_action.isEnabled())
        self.assertEqual({f[-1] for f in panel.viewport.surface.faces}, {-1, 1})
        self.w.workspace_tabs.setCurrentWidget(self.w.design_panel)
        self.assertFalse(self.w.fit_action.isEnabled())

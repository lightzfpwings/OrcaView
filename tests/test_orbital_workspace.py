"""Drive the GBW choice dialog, asynchronous import and orbital workspace."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QAbstractAnimation, QPoint, QRect, Qt, QTimer
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
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")):
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

    def test_natural_occupations_and_sidebar_follow_the_selected_orbital(self):
        self.open(self.example.parent / "OH.uno.molden.input")
        self.finish_open()
        panel = self.w.orbital_panel
        panel.finish_for_capture()
        self.assertEqual(panel.wave.kind, "uno")
        self.assertEqual(panel.table.horizontalHeaderItem(1).text(), "Natural occupation")
        self.assertEqual(panel.table.currentRow(), 4)
        sidebar = panel.decomposition
        sidebar.button.click()
        sidebar.method.setCurrentIndex(sidebar.method.findData("nao"))
        sidebar.group.setCurrentIndex(sidebar.group.findData("both"))
        panel.table.setCurrentCell(2, 0)
        sidebar.finish(wait=True)
        self.assertEqual(sidebar.table.columnCount(), 3)
        self.assertEqual(sidebar.table.rowCount(), 5)
        self.assertEqual(sidebar.table.item(1, 0).text(), "0 O")
        self.assertEqual(sidebar.table.item(1, 1).text(), "p")
        self.assertEqual(sidebar.table.item(1, 2).text(), "69.570")
        self.assertIn("Orbital 2", sidebar.status.text())
        sidebar.method.setCurrentIndex(sidebar.method.findData("becke"))
        sidebar.finish(wait=True)
        self.assertFalse(sidebar.group.isEnabled())
        self.assertEqual(sidebar.table.rowCount(), 2)
        sidebar.method.setCurrentIndex(sidebar.method.findData("mulliken"))
        self.assertEqual(sidebar.group.currentData(), "both")
        self.open(self.example.parent / "OH.unso.molden.input")
        self.finish_open()
        panel.finish_for_capture()
        self.assertFalse(sidebar.button.isChecked())
        self.assertEqual(panel.table.horizontalHeaderItem(1).text(), "Spin occupation")
        occupied = panel.table.rowCount()-1
        panel.table.setCurrentCell(occupied, 0)
        self.assertLess(float(panel.table.item(occupied, 1).text()), 0)
        self.assertFalse(sidebar.method.model().item(sidebar.method.findData("bickelhaupt")).isEnabled())
        sidebar.button.click()
        sidebar.finish(wait=True)
        self.assertIn(f"Orbital {occupied}", sidebar.status.text())
        project = self.root / "spin-density.oview.json"
        save_project(self.w.session, project)
        self.w._open_project_path(project)
        panel.finish_loading()
        self.assertEqual(panel.wave.kind, "unso")

    def test_derived_natural_orbitals_and_explicit_cube_amplitude(self):
        self.open(self.example)
        self.finish_open()
        panel = self.w.orbital_panel
        panel.finish_for_capture()
        panel.representation.setCurrentIndex(panel.representation.findData("natural"))
        panel.finish_for_capture()
        self.assertEqual(panel.wave.kind, "natural")
        self.assertEqual(panel.table.columnCount(), 3)
        self.assertTrue(panel.viewport.surface.faces)
        panel.representation.setCurrentIndex(0)
        panel.finish_for_capture()
        self.assertEqual(panel.table.columnCount(), 4)
        self.assertEqual(panel.wave.kind, "mo")
        self.open(self.example.parent / "water-homo.cube")
        self.finish_open()
        panel.finish_for_capture()
        sidebar = panel.decomposition
        sidebar.button.click()
        self.assertTrue(sidebar.amplitude.isVisible())
        self.assertIsNone(sidebar.future)
        self.assertFalse(sidebar.method.model().item(sidebar.method.findData("lowdin")).isEnabled())
        sidebar.amplitude.click()
        sidebar.finish(wait=True)
        self.assertEqual(sidebar.table.rowCount(), 3)
        self.assertIn("Total within grid 100.00%", sidebar.status.text())

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
        self.assertEqual(panel.quality.currentData(), "standard")
        standard = panel.viewport.surface
        menu = panel.palette_choice
        custom = menu.count()-1
        self.assertEqual(custom, 9)
        self.assertEqual((menu.itemText(custom), menu.itemData(custom)), ("Custom", "custom"))
        pairs = set()
        for row in range(custom):
            menu.setCurrentIndex(row)
            swatch = menu.itemIcon(row).pixmap(menu.iconSize()).toImage()
            pair = (panel.colors[1], panel.colors[-1])
            self.assertEqual(tuple(swatch.pixelColor(x, 6).name() for x in (6, 20)), pair)
            pairs.add(pair)
            self.assertIs(panel.viewport.surface, standard)
        self.assertEqual(len(pairs), custom)
        menu.setCurrentIndex(2)
        menu.setCurrentIndex(custom)
        self.assertIs(panel.viewport.surface, standard)
        self.assertEqual(panel.colors, {1: "#2c926b", -1: "#8855b5"})
        menu.setCurrentIndex(2)
        with patch.object(QColorDialog, "getColor", return_value=QColor()):
            panel.color_buttons[1].click()
        self.assertEqual(menu.currentIndex(), 2)
        with patch.object(QColorDialog, "getColor", return_value=QColor("#18b632")):
            panel.color_buttons[1].click()
        with patch.object(QColorDialog, "getColor", return_value=QColor()):
            panel.color_buttons[-1].click()
        self.assertEqual(panel.colors, {1: "#18b632", -1: "#8855b5"})
        self.assertEqual(menu.currentIndex(), custom)
        menu.setCurrentIndex(4)
        menu.setCurrentIndex(custom)
        self.assertEqual(panel.colors, {1: "#18b632", -1: "#8855b5"})
        self.assertIs(panel.viewport.surface, standard)
        self.assertIsNone(panel.future)
        panel.quality.setCurrentIndex(panel.quality.findData("fine"))
        panel.finish_for_capture()
        self.assertGreater(len(panel.viewport.surface.faces), len(standard.faces))
        panel.quality.setCurrentIndex(panel.quality.findData("standard"))
        self.assertIs(panel.viewport.surface, standard)
        panel.quality.setCurrentIndex(panel.quality.findData("fine"))
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
            self.assertEqual(another.palette_choice.currentData(), "custom")
            self.assertEqual(another.quality.currentData(), "fine")
            self.assertEqual(another.quality.currentText(), "Best")
        finally:
            another.shutdown()
            another.close()

    def test_legacy_custom_pair_survives_switching_to_a_preset_and_restarting(self):
        from orcaview.gui.orbital_panel import OrbitalPanel
        from orcaview.preferences import write_preferences

        write_preferences("orbital-surface", {"positive": "#aa0077", "negative": "#123456"})
        first = OrbitalPanel()
        try:
            self.assertEqual(first.palette_choice.currentData(), "custom")
            first.palette_choice.setCurrentIndex(first.palette_choice.findData("Charcoal / silver"))
        finally:
            first.shutdown()
            first.close()
        second = OrbitalPanel()
        try:
            menu = second.palette_choice
            self.assertEqual(menu.currentData(), "Charcoal / silver")
            menu.setCurrentIndex(menu.count()-1)
            self.assertEqual(second.colors, {1: "#aa0077", -1: "#123456"})
        finally:
            second.shutdown()
            second.close()

    def test_orbitals_crossfades_from_each_workspace_and_back(self):
        window, tabs, panel = self.w, self.w.workspace_tabs, self.w.orbital_panel
        overlay = window.workspace_transition
        animation = overlay._animation
        animation.setDuration(60_000)
        animated = window.style().styleHint(QStyle.StyleHint.SH_Widget_Animate)

        def check_transition(page):
            self.assertIs(tabs.currentWidget(), page)
            if animated:
                self.assertEqual(animation.state(), QAbstractAnimation.State.Running)
                self.assertFalse(overlay._image.isNull())
                self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
                animation.setCurrentTime(30_000)
            else:
                self.assertTrue(overlay.isHidden())

        tabs.setCurrentWidget(panel)
        self.assertTrue(overlay.isHidden())
        self.open(self.example.parent / "water-homo.cube")
        self.finish_open()
        check_transition(panel)
        panel.finish_for_capture()
        mesh, head = panel.viewport.surface, window.session.document.head
        for page in (window.input_page, window.design_panel, window.foundation_panel):
            tabs.setCurrentWidget(page)
            self.app.processEvents()
            check_transition(page)
            QTest.mouseClick(tabs.tabBar(), Qt.MouseButton.LeftButton, pos=tabs.tabBar().tabRect(tabs.indexOf(panel)).center())
            self.app.processEvents()
            check_transition(panel)
            self.assertTrue(window.tree_dock.isHidden() and window.bottom_dock.isHidden())
            self.assertIs(panel.viewport.surface, mesh)
        animation.setCurrentTime(animation.duration())
        self.assertTrue(overlay.isHidden())
        self.assertIsNone(overlay._image)
        self.assertIs(window.session.document.head, head)

    def test_quality_dropdown_fits_all_four_rows_and_selects_by_mouse_and_keyboard(self):
        self.w.resize(self.w.minimumSize())
        self.open(self.example.parent / "water-homo.cube")
        self.finish_open()
        panel = self.w.orbital_panel
        field = panel.quality
        self.assertEqual([field.itemText(i) for i in range(field.count())], ["Coarse", "Standard", "Smooth", "Best"])
        self.assertEqual(field.currentData(), "standard")
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

    def test_gpu_preference_and_seam_free_phase_rendering_after_rotation(self):
        from orcaview.gui.orbital_gpu import create_renderer, preferred_adapters
        from orcaview.gui.orbital_raster import OrbitalRaster
        from orcaview.results.orbital_surface import OrbitalSurface

        adapters = [SimpleNamespace(info={"adapter_type": t}) for t in ("CPU", "IntegratedGPU", "DiscreteGPU")]
        self.assertEqual(preferred_adapters(adapters), [adapters[2], adapters[1]])
        vertices = []
        faces = []
        for left, right, z, sign in ((-1, 0, .5, 1), (0, 1, .5, -1), (-1, 1, -.5, 1)):
            k = len(vertices)
            vertices.extend(((left, -.5, z), (right, -.5, z), (right, .5, z), (left, .5, z)))
            faces.extend(((k, k+1, k+2, sign), (k, k+2, k+3, sign)))
        mesh = OrbitalSurface(tuple(vertices), tuple(faces), False, ((0., 0., 1.),)*len(vertices))
        viewport = self.w.orbital_panel.viewport
        viewport.set_phase_colors({1: "#ff0000", -1: "#0000ff"})
        center = (0., 0., 0.)
        try:
            raster = OrbitalRaster(mesh, center)
        except ImportError:
            self.skipTest("NumPy not installed")
        gpu = create_renderer()
        if gpu is not None:
            self.addCleanup(gpu.close)
        for direction in (1, -1):
            axes = ((direction, 0, 0), (0, direction, 0), (0, 0, 1))
            camera = (axes, 40, 80, 50, 160, 100, 1.)
            images = [raster.render(center, *camera, viewport._rgba_table)]
            if gpu is not None:
                images.append(gpu.render(mesh, center, 2., *camera, viewport._phase_rgba))
                if direction == 1:
                    uploaded = gpu.vertex
                else:
                    self.assertIs(gpu.vertex, uploaded)
            for image in images:
                for x in range(42, 118):
                    for y in range(32, 68, 3):
                        color = image.pixelColor(x, y)
                        self.assertEqual(color.alpha(), 204, (x, y))
                        self.assertEqual(color.red() > color.blue(), (x < 80) == (direction == 1))

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

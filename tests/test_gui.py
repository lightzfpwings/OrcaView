"""可选 GUI 的关键交互校验，核心环境中明确跳过。"""

import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orcaview.core._state_methods import ROCIS_METHODS, SPIN_FLIP_METHODS
from orcaview.core.integrals import auxiliary_options, basis_options, grid_options, integral_options, scalar_options
from orcaview.core.methods import (
    ACTIVE_SPACE_METHODS, ELECTRON_CHANNEL_METHODS, EXCITED_STATE_METHODS, METHODS,
    METHOD_GROUPS, REFERENCE_FUNCTIONAL_METHODS, dispersion_options, frozen_core_options, pno_options, reference_options,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, QRect, Qt, QTimer
    from PySide6.QtGui import QAction
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QComboBox, QFileDialog, QLabel, QMenu, QMessageBox
    from orcaview.gui.main_window import MainWindow
    HAS_QT = True
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "未安装可选 Qt 依赖")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self._close)

    def _close(self):
        self.window.dirty = False
        self.window.close()
        self.app.processEvents()

    def test_version_corners_remain_visible_with_status_messages_on_all_pages(self):
        from orcaview.gui.version_info import desktop_version_info

        window = self.window
        window.resize(window.minimumSize())
        self.app.processEvents()
        minimum_width = window.width()
        versions = desktop_version_info()
        platform = window.findChild(QLabel, "platformBadge")
        system = window.findChild(QLabel, "systemVersion")
        software = window.findChild(QLabel, "softwareVersion")
        message = window.findChild(QLabel, "statusMessage")
        status = window.statusBar()

        def bounds(widget):
            return QRect(widget.mapTo(window, QPoint()), widget.size())

        notice = "正在读取 " + "orbital-calculation-" * 24 + ".out"
        for page in range(window.workspace_tabs.count()):
            with self.subTest(page=page):
                window.workspace_tabs.setCurrentIndex(page)
                window.pending_result_button.show()
                window.cancel_read_button.show()
                status.showMessage(notice, 60000)
                self.app.processEvents()
                self.assertEqual(window.width(), minimum_width)
                self.assertEqual(status.currentMessage(), notice)
                self.assertTrue(message.isVisible())
                self.assertTrue(message.text().startswith("正在读取"))
                for label, expected in ((platform, versions.platform_name), (system, versions.system_version),
                                        (software, versions.software_version)):
                    self.assertTrue(label.isVisible())
                    self.assertEqual(label.text(), expected)
                    self.assertTrue(window.rect().contains(bounds(label)))
                    self.assertGreaterEqual(label.contentsRect().width(), label.fontMetrics().horizontalAdvance(expected))
                self.assertLess(bounds(platform).top(), window.height() // 6)
                self.assertLess(window.width() - bounds(platform).right(), 64)
                self.assertLess(bounds(system).left(), 64)
                self.assertLess(window.width() - bounds(software).right(), 64)
                self.assertLess(window.height() - bounds(system).bottom(), 32)
                self.assertLess(window.height() - bounds(software).bottom(), 32)
                for control in (message, window.pending_result_button, window.cancel_read_button):
                    self.assertTrue(control.isVisible())
                    self.assertGreater(bounds(control).left(), bounds(system).right())
                    self.assertLess(bounds(control).right(), bounds(software).left())
                self.assertFalse(bounds(message).intersects(bounds(window.pending_result_button)))
                self.assertFalse(bounds(message).intersects(bounds(window.cancel_read_button)))
                status.clearMessage()
                self.app.processEvents()
                self.assertFalse(message.isVisible() and message.text().startswith("正在读取"))
                self.assertTrue(system.isVisible() and software.isVisible())

    def test_invalid_electronic_state_blocks_export(self):
        self.window.multiplicity.setValue(2)  # 中性苯的偶数电子不能是二重态。
        self.app.processEvents()
        self.assertFalse(self.window.export_button.isEnabled())
        self.assertIn("cannot be exported", self.window.input_preview.toPlainText())
        self.window.multiplicity.setValue(1)
        self.assertTrue(self.window.export_button.isEnabled())

    def test_rotation_and_selection_preserve_geometry(self):
        before = self.window.session.molecule
        snapshot = self.window.session.document.head
        viewport = self.window.viewport
        viewport.yaw += 0.7
        viewport.zoom = 1.2
        viewport.repaint()
        self.app.processEvents()
        x, y, _, _ = viewport._projected[0]
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(round(x), round(y)))
        self.app.processEvents()
        self.assertEqual(viewport.selected, [0])
        self.assertIn("C1", self.window.selection.text())
        x, y, _, _ = viewport._projected[1]
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=QPoint(round(x), round(y)))
        self.assertEqual(viewport.selected, [0, 1])
        self.assertIn("C2", self.window.selection.text())
        self.assertEqual(len(self.window.selection.text().splitlines()), 2)
        self.assertEqual(self.window.session.molecule, before)
        self.assertIs(self.window.session.document.head, snapshot)
        self.assertEqual(self.window.session.document.head.content_hash, snapshot.content_hash)

    def test_top_view_and_axis_arrowheads_on_both_pages(self):
        """The orientation triad follows the display frame from both workspaces."""
        window = self.window
        original = window.session.document.head
        preview = window.input_preview.toPlainText()
        results_page = window.workspace_tabs.indexOf(window.foundation_panel)
        for page, viewport in ((0, window.viewport), (results_page, window.foundation_panel.viewport)):
            with self.subTest(page=page):
                window.workspace_tabs.setCurrentIndex(page)
                self.app.processEvents()
                for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
                    self.assertEqual(viewport.camera_transform(*axis), axis)
                # Sample the isolated orientation triad in logical pixels; a
                # plain two-pixel shaft cannot paint a wing on either side.
                image = viewport.grab().toImage().scaled(
                    viewport.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                ox, oy = image.width() - 48, image.height() - 52

                def has_color(dx, dy, rgb):
                    sample = image.pixelColor(ox + dx, oy + dy).getRgb()[:3]
                    return all(abs(a - b) < 50 for a, b in zip(sample, rgb))

                red, green, blue = (172, 83, 76), (57, 126, 96), (56, 111, 167)
                for side in (-1, 1):
                    self.assertTrue(any(has_color(n, side * 2, red) for n in range(20, 33)))
                    self.assertTrue(any(has_color(side * 2, -n, green) for n in range(20, 33)))
                self.assertTrue(has_color(0, 0, blue))
                self.assertTrue(any(has_color(-r, 0, blue) for r in range(4, 7)))

                start = viewport.rect().center()
                QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(viewport, start + QPoint(27, 19))
                QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=start + QPoint(27, 19))
                self.assertNotEqual(viewport.camera_transform(0, 0, 1), (0, 0, 1))
                # Rotate z into the screen plane to check its own arrowhead.
                viewport.yaw, viewport.pitch = math.pi / 2, 0.
                image = viewport.grab().toImage().scaled(
                    viewport.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                for side in (-1, 1):
                    self.assertTrue(any(has_color(n, side * 2, blue) for n in range(20, 33)))
                window._fit_active_view()
                self.assertEqual(viewport.camera_transform(0, 0, 1), (0, 0, 1))
        self.assertIs(window.session.document.head, original)
        self.assertEqual(window.input_preview.toPlainText(), preview)

    def test_linear_and_asymmetric_molecules_load_from_positive_z(self):
        from orcaview.io.xyz import parse_xyz

        viewport = self.window.viewport
        linear = parse_xyz("2\nhydrogen\nH 1 0 0\nH -1 0 0\n")
        viewport.set_molecule(linear)
        self.assertTrue(math.isinf(viewport.principal_axis.order))
        for actual, expected in zip(viewport.transform(*viewport.principal_axis.direction), (0, 0, 1)):
            self.assertAlmostEqual(actual, expected)
        viewport.yaw = 1.
        asymmetric = parse_xyz("4\nC1\nC 0 0 0\nH 1.1 0 0\nF 0 1.5 0\nCl .1 .2 2.0\n")
        viewport.set_molecule(asymmetric)
        self.assertIsNone(viewport.principal_axis.direction)
        self.assertEqual(viewport.transform(1, 2, 3), (1, 2, 3))

    def test_job_change_updates_native_preview(self):
        document = self.window.session.document
        snapshot = document.head
        self.window.job.setCurrentIndex(self.window.job.findData("OPT_FREQ"))
        self.app.processEvents()
        preview = self.window.input_preview.toPlainText()
        self.assertIn("Opt Freq", preview)
        self.assertIn("* xyz 0 1", preview)
        self.assertIs(self.window.session.document, document)
        self.assertIs(document.head, snapshot)

    def test_loaded_water_uses_display_z_and_exports_input_coordinates(self):
        # Water translated away from the origin with its bisector along input x.
        coordinates = (("O", 3., 2., 1.), ("H", 3.586541, 2.758602, 1.),
                       ("H", 3.586541, 1.241398, 1.))
        with TemporaryDirectory() as directory:
            xyz = Path(directory) / "sideways-water.xyz"
            xyz.write_text("3\nwater\n" + "".join(
                f"{element} {x} {y} {z}\n" for element, x, y, z in coordinates
            ), encoding="utf-8")
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(xyz), "")):
                self.window.open_xyz()
            viewport = self.window.viewport
            self.assertIn("C2v", viewport.symmetry_label)
            self.assertEqual(viewport.principal_axis.order, 2)
            self.assertAlmostEqual(abs(viewport.principal_axis.direction[0]), 1.)
            for actual, expected in zip(viewport.transform(*viewport.principal_axis.direction), (0, 0, 1)):
                self.assertAlmostEqual(actual, expected)
            initial = viewport.transform(1., 0., 0.)
            viewport.yaw += 0.45
            for actual, expected in zip(viewport.transform(*viewport.principal_axis.direction),
                                        viewport.camera_transform(0., 0., 1.)):
                self.assertAlmostEqual(actual, expected)
            self.window._fit_active_view()
            self.assertEqual(viewport.transform(1., 0., 0.), initial)
            self.window.workspace_tabs.setCurrentWidget(self.window.foundation_panel)
            history = self.window.foundation_panel.viewport
            self.assertEqual(history.symmetry_label, viewport.symmetry_label)
            self.assertEqual(history.transform(1., 0., 0.), initial)
            dst = Path(directory) / "water.inp"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(dst), "")):
                self.window.export_input()
            atom_lines = (line.split() for line in dst.read_text(encoding="utf-8").splitlines())
            exported = tuple((row[0], *map(float, row[1:])) for row in atom_lines
                             if len(row) == 4 and row[0] in ("H", "O"))
            self.assertEqual(exported, coordinates)

    def test_preview_and_export_round_input_coordinates_to_eight_places(self):
        source = (
            b"3\nprecision fixture\n"
            b"O 1.234567894 -2.345678916 -0.0\n"
            b"H 0.000000004 -0.000000004 -0.000000006\n"
            b"H 9.999999999 -1.234567891 0.0\n"
        )
        expected_block = (
            "* xyz 0 1\n"
            "  O   1.23456789 -2.34567892 -0.00000000\n"
            "  H   0.00000000 -0.00000000 -0.00000001\n"
            "  H   10.00000000 -1.23456789  0.00000000\n"
            "*\n"
        )
        from orcaview.orca.input import freeze_input
        with TemporaryDirectory() as directory:
            xyz = Path(directory) / "precision.xyz"
            xyz.write_bytes(source)
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(xyz), "")):
                self.window.open_xyz()
            head = self.window.session.document.head
            preview = self.window.input_preview.toPlainText()
            self.assertTrue(preview.endswith(expected_block), preview)
            exported = xyz.with_suffix(".inp")
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(exported), "")):
                self.window.export_input()
            self.assertEqual(exported.read_text(encoding="utf-8"), preview)
            frozen = freeze_input(head, self.window.session.calculation)
            self.assertEqual(frozen.input_bytes, preview.encode("utf-8"))
            self.assertEqual(self.window.session.document.head.molecule.atoms[0].x, 1.234567894)
            self.assertEqual(xyz.read_bytes(), source)

    def test_global_method_search_selects_across_families_and_accepts_cli_aliases(self):
        window = self.window
        action = next(item for item in window.findChildren(QAction) if item.text() == "Find method…")
        window.basis.setCurrentText("def2-TZVP")
        matches = []

        def search(query):
            def fill():
                dialog = self.app.activeModalWidget()
                combo = dialog.findChild(QComboBox)
                completer = combo.completer()
                completer.setCompletionPrefix("pNo-Cc")
                model = completer.completionModel()
                matches.extend(model.index(i, 0).data() for i in range(model.rowCount()))
                combo.setEditText(query)
                dialog.accept()
            QTimer.singleShot(0, fill)
            action.trigger()

        window.workspace_tabs.setCurrentWidget(window.foundation_panel)
        search("adc(2)")
        self.assertIn("DLPNO-CCSD", matches)
        self.assertEqual(window.workspace_tabs.currentIndex(), 0)
        self.assertEqual(window.session.calculation.method, "ADC2")
        self.assertEqual(window.method_group.currentText(), METHODS["ADC2"].family)
        search("pBe0")
        self.assertEqual(window.session.calculation.method, "PBE0")
        self.assertEqual(window.method_group.currentText(), METHODS["PBE0"].family)
        self.assertEqual(window.basis.currentData(), "def2-TZVP")
        with patch.object(QMessageBox, "warning") as warning:
            search("no-such-orca-method")
            warning.assert_called_once()
        self.assertEqual(window.session.calculation.method, "PBE0")

    def test_method_families_control_tasks_basis_and_frequency_preview(self):
        window = self.window
        self.assertEqual(window.method_group.currentText(), METHODS["B3LYP"].family)
        self.assertEqual(window.method.currentText(), "B3LYP")
        window.basis.setCurrentText("def2-TZVP")
        for family, names in METHOD_GROUPS.items():
            window.method_group.setCurrentText(family)
            self.assertEqual(tuple(window.method.itemText(i) for i in range(window.method.count())), names)
            for name in names:
                with self.subTest(method=name):
                    window.method.setCurrentText(name)
                    window.multiplicity.setValue(3 if name in SPIN_FLIP_METHODS or name in ROCIS_METHODS else 1)
                    preset = METHODS[name]
                    if name in ACTIVE_SPACE_METHODS:
                        window.active_electrons.setValue(2)
                        window.active_orbitals.setValue(2)
                        if name in EXCITED_STATE_METHODS:
                            window.nroots.setValue(2)
                    self.assertEqual(tuple(window.job.itemData(i) for i in range(window.job.count())), preset.job_types)
                    self.assertEqual(window.basis.isEnabled(), preset.uses_orbital_basis)
                    if preset.uses_orbital_basis:
                        self.assertIn(window.basis.currentData(), basis_options(name))
                    self.assertEqual(window.session.calculation.method, name)
                    self.assertTrue(window.export_button.isEnabled(), window.validation.text())
                    if not preset.uses_orbital_basis:
                        self.assertIn("fixed", window.basis.currentText())
                        self.assertNotIn("def2-TZVP", window.input_preview.toPlainText())
                    if "FREQ" in preset.job_types:
                        window.job.setCurrentIndex(window.job.findData("FREQ"))
                        self.assertEqual(window.method_hint.isVisible(), preset.uses_numerical_frequencies)
                        self.assertEqual("NumFreq" in window.input_preview.toPlainText(),
                                         preset.uses_numerical_frequencies)
                    self.assertEqual(window.input_preview.toPlainText(), window.session.input_text())

    def test_method_and_inactive_basis_survive_project_reopen(self):
        window = self.window
        window.basis.setCurrentText("def2-TZVPP")
        fixed_method = next(name for name, preset in METHODS.items() if not preset.uses_orbital_basis)
        window.method_group.setCurrentText(METHODS[fixed_method].family)
        window.method.setCurrentText(fixed_method)
        window.job.setCurrentIndex(window.job.findData("SP"))
        expected = window.session.calculation
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "method.oview.json")
            with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")):
                self.assertTrue(window.save_project_dialog())
            reopened = MainWindow()
            try:
                with patch.object(QFileDialog, "getOpenFileName", return_value=(path, "")):
                    reopened.open_project()
                self.assertFalse(reopened.dirty)
                self.assertEqual(reopened.session.calculation, expected)
                self.assertEqual(reopened.method.currentText(), fixed_method)
                self.assertEqual(reopened.job.currentData(), "SP")
                self.assertFalse(reopened.basis.isEnabled())
                reopened.method_group.setCurrentText(METHODS["B3LYP"].family)
                self.assertEqual(reopened.basis.currentText(), "def2-TZVPP")
                self.assertIn("def2-TZVPP", reopened.input_preview.toPlainText())
            finally:
                reopened.dirty = False
                reopened.close()

    def test_parameter_rows_validate_before_export_and_round_trip(self):
        window = self.window
        with TemporaryDirectory() as directory:
            for name in sorted(set(ACTIVE_SPACE_METHODS) | set(EXCITED_STATE_METHODS)):
                with self.subTest(method=name):
                    window.method_group.setCurrentText(METHODS[name].family)
                    window.method.setCurrentText(name)
                    window.multiplicity.setValue(3 if name in SPIN_FLIP_METHODS or name in ROCIS_METHODS else 1)
                    self.assertEqual(window.job.currentData(), "SP")
                    active = name in ACTIVE_SPACE_METHODS
                    excited = name in EXCITED_STATE_METHODS
                    root_count = 2 if active else 7
                    has_reference = name in REFERENCE_FUNCTIONAL_METHODS
                    self.assertEqual(window.active_electrons.isVisible(), active)
                    self.assertEqual(window.active_orbitals.isVisible(), active)
                    self.assertEqual(window.nroots.isVisible(), excited)
                    self.assertEqual(window.reference_functional.isVisible(), has_reference)
                    if active:
                        window.active_electrons.setValue(0)
                        self.assertEqual(window.active_electrons.text(), "Not set")
                        self.assertFalse(window.export_button.isEnabled())
                        self.assertIn("cannot be exported", window.input_preview.toPlainText())
                        window.active_electrons.setValue(4)
                        window.active_orbitals.setValue(3)
                    if excited:
                        window.nroots.setValue(root_count)
                    if has_reference:
                        window.reference_functional.setCurrentText("PBE0")
                    self.assertTrue(window.export_button.isEnabled(), window.validation.text())
                    spec = window.session.calculation
                    self.assertEqual(spec.method, name)
                    self.assertEqual(spec.active_electrons, 4 if active else None)
                    self.assertEqual(spec.active_orbitals, 3 if active else None)
                    self.assertEqual(spec.nroots, root_count if excited else None)
                    self.assertEqual(spec.reference_functional, "PBE0" if has_reference else None)
                    preview = window.input_preview.toPlainText()
                    path = str(Path(directory) / (name.replace("/", "_") + ".oview.json"))
                    with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")):
                        self.assertTrue(window.save_project_dialog())
                    window.method_group.setCurrentText(METHODS["B3LYP"].family)
                    self.assertIsNone(window.session.calculation.nroots)
                    self.assertIsNone(window.session.calculation.active_electrons)
                    with patch.object(window, "_guard_discard", return_value=True), \
                            patch.object(QFileDialog, "getOpenFileName", return_value=(path, "")):
                        window.open_project()
                    self.assertFalse(window.dirty)
                    self.assertEqual(window.session.calculation, spec)
                    self.assertEqual(window.input_preview.toPlainText(), preview)

    def test_auxiliary_slots_restrict_choices_and_round_trip(self):
        window = self.window
        cases = {}
        for method in METHODS:
            bases = basis_options(method)
            if not bases or method in ACTIVE_SPACE_METHODS:
                continue
            for approximation in integral_options(method, "SP"):
                for slot in auxiliary_options(method, bases[0], approximation):
                    cases.setdefault(slot, (method, bases[0], approximation))
            if len(cases) == 4:
                break
        self.assertEqual(set(cases), {"aux_j", "aux_jk", "aux_c", "cabs"})
        with TemporaryDirectory() as directory:
            for slot, (method, basis, approximation) in cases.items():
                with self.subTest(slot=slot):
                    window.method_group.setCurrentText(METHODS[method].family)
                    window.method.setCurrentText(method)
                    window.job.setCurrentIndex(window.job.findData("SP"))
                    window.basis.setCurrentText(basis)
                    window.integral_approximation.setCurrentIndex(window.integral_approximation.findData(approximation))
                    options = auxiliary_options(method, basis, approximation)
                    for role, control in window.auxiliary_bases.items():
                        self.assertEqual(control.isVisible(), role in options)
                        if role in options:
                            self.assertEqual(control.itemText(0), "Automatic")
                            actual = tuple(control.itemData(i) for i in range(1, control.count()))
                            self.assertEqual(actual, options[role])
                            control.setCurrentIndex(control.count() - 1)
                    self.assertTrue(window.export_button.isEnabled(), window.validation.text())
                    spec = window.session.calculation
                    self.assertEqual(getattr(spec, slot), options[slot][-1])
                    path = str(Path(directory) / f"{slot}.oview.json")
                    with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")):
                        self.assertTrue(window.save_project_dialog())
                    window.method_group.setCurrentText(METHODS["HF-3c"].family)
                    window.method.setCurrentText("HF-3c")
                    self.assertTrue(all(getattr(window.session.calculation, role) is None
                                        for role in window.auxiliary_bases))
                    with patch.object(window, "_guard_discard", return_value=True), \
                            patch.object(QFileDialog, "getOpenFileName", return_value=(path, "")):
                        window.open_project()
                    self.assertEqual(window.session.calculation, spec)
                    self.assertEqual(window.auxiliary_bases[slot].currentData(), options[slot][-1])

    def test_mdci_ri_override_shows_aux_c_and_reset_removes_it(self):
        window = self.window
        window.method_group.setCurrentText(METHODS["CCSD"].family)
        window.method.setCurrentText("CCSD")
        panel = window.block_options
        panel.toggle.setChecked(True)
        group = panel.groups["mdci"]
        group.toggle.setChecked(True)
        group.fields["KCOpt"].setCurrentText("KC_RI")
        control = window.auxiliary_bases["aux_c"]
        self.assertTrue(window.method_form.isRowVisible(control))
        control.setCurrentIndex(control.findData("def2-TZVPP/C"))
        self.assertIn("def2-TZVPP/C", window.input_preview.toPlainText())
        group.reset.click()
        self.assertFalse(window.method_form.isRowVisible(control))
        self.assertIsNone(window.session.calculation.aux_c)
        self.assertNotIn("/C", window.input_preview.toPlainText())

    def test_job_change_discards_inapplicable_integral_options(self):
        window = self.window
        window.method_group.setCurrentText(METHODS["HF"].family)
        window.method.setCurrentText("HF")
        window.job.setCurrentIndex(window.job.findData("SP"))
        only_single_point = set(integral_options("HF", "SP")) - set(integral_options("HF", "OPT"))
        self.assertTrue(only_single_point)
        for approximation in only_single_point:
            window.job.setCurrentIndex(window.job.findData("SP"))
            window.integral_approximation.setCurrentIndex(window.integral_approximation.findData(approximation))
            window.job.setCurrentIndex(window.job.findData("OPT"))
            self.assertEqual(window.integral_approximation.findData(approximation), -1)
            self.assertEqual(window.session.calculation.integral_approximation, "Auto")
            self.assertTrue(window.export_button.isEnabled())

    def test_open_shell_channel_and_pno_precision(self):
        window = self.window

        def assert_round_trip(spec):
            with TemporaryDirectory() as directory:
                path = str(Path(directory) / "settings.oview.json")
                with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")):
                    self.assertTrue(window.save_project_dialog())
                reopened = MainWindow()
                try:
                    with patch.object(QFileDialog, "getOpenFileName", return_value=(path, "")):
                        reopened.open_project()
                    self.assertEqual(reopened.session.calculation, spec)
                    self.assertEqual(reopened.electron_channel.currentData(), spec.electron_channel)
                    self.assertEqual(reopened.pno_preset.currentData(), spec.pno_preset)
                finally:
                    reopened.dirty = False
                    reopened.close()

        method = next(iter(ELECTRON_CHANNEL_METHODS))
        window.method_group.setCurrentText(METHODS[method].family)
        window.method.setCurrentText(method)
        self.assertFalse(window.electron_channel.isVisible())
        window.charge.setValue(1)
        window.multiplicity.setValue(2)
        self.assertTrue(window.electron_channel.isVisible())
        self.assertFalse(window.export_button.isEnabled())
        window.electron_channel.setCurrentIndex(window.electron_channel.findData("beta"))
        self.assertTrue(window.export_button.isEnabled(), window.validation.text())
        self.assertEqual(window.session.calculation.electron_channel, "beta")
        self.assertIsNone(window.session.calculation.reference_functional)
        assert_round_trip(window.session.calculation)
        window.charge.setValue(0)
        window.multiplicity.setValue(1)
        self.assertFalse(window.electron_channel.isVisible())
        self.assertIsNone(window.session.calculation.electron_channel)
        method = "DLPNO-CCSD(T)"
        window.method_group.setCurrentText(METHODS[method].family)
        window.method.setCurrentText(method)
        self.assertEqual(tuple(window.pno_preset.itemData(i) for i in range(window.pno_preset.count())),
                         pno_options(method))
        window.pno_preset.setCurrentIndex(window.pno_preset.findData("TightPNO"))
        self.assertIn("TightPNO", window.input_preview.toPlainText())
        self.assertEqual(window.session.calculation.pno_preset, "TightPNO")
        assert_round_trip(window.session.calculation)
        window.method_group.setCurrentText(METHODS["B3LYP"].family)
        self.assertFalse(window.pno_preset.isVisible())
        self.assertEqual(window.session.calculation.pno_preset, "Auto")

    def test_native_editor_starts_with_the_valid_preview_or_empty_input(self):
        window = self.window
        with patch("orcaview.gui.main_window.edit_native_input") as editor:
            action = next(item for item in window.findChildren(QAction) if item.text() == "Edit native ORCA input…")
            self.assertTrue(any(isinstance(menu, QMenu) and menu.title() == "File" for menu in action.associatedObjects()))
            action.trigger()
            editor.assert_called_once_with(window, window.input_preview.toPlainText())
            window.multiplicity.setValue(2)
            action.trigger()
            editor.assert_called_with(window, "")

    def test_dispersion_and_grid_are_saved_and_cleared_for_fixed_methods(self):
        window = self.window
        method = "B3LYP"
        for control, options in ((window.dispersion, dispersion_options(method)),
                                 (window.integration_grid, grid_options(method))):
            self.assertTrue(control.isVisible())
            self.assertEqual(tuple(control.itemData(i) for i in range(control.count())), options)
            self.assertGreater(len(options), 1)
            control.setCurrentIndex(control.count() - 1)
        spec = window.session.calculation
        self.assertEqual(spec.dispersion, window.dispersion.currentData())
        self.assertEqual(spec.integration_grid, window.integration_grid.currentData())
        self.assertIn(spec.dispersion, window.input_preview.toPlainText())
        self.assertIn(spec.integration_grid, window.input_preview.toPlainText())
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "dispersion-grid.oview.json")
            with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")):
                self.assertTrue(window.save_project_dialog())
            window.method_group.setCurrentText(METHODS["PM3"].family)
            window.method.setCurrentText("PM3")
            self.assertEqual(window.session.calculation.dispersion, "Auto")
            self.assertEqual(window.session.calculation.integration_grid, "Auto")
            with patch.object(window, "_guard_discard", return_value=True), \
                    patch.object(QFileDialog, "getOpenFileName", return_value=(path, "")):
                window.open_project()
            self.assertEqual(window.session.calculation, spec)

    def test_relativistic_basis_drives_hamiltonian_options(self):
        window = self.window
        method = window.method.currentText()
        basis = next(name for name in basis_options(method) if "X2C" in scalar_options(method, name))
        window.basis.setCurrentText(basis)
        self.assertTrue(window.relativity.isVisible())
        self.assertEqual(tuple(window.relativity.itemData(i) for i in range(window.relativity.count())),
                         scalar_options(method, basis))
        window.relativity.setCurrentIndex(window.relativity.findData("X2C"))
        self.assertEqual(window.session.calculation.relativity, "X2C")
        self.assertIn("X2C", window.input_preview.toPlainText())
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "relativity.oview.json")
            with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")):
                self.assertTrue(window.save_project_dialog())
            window.basis.setCurrentText("def2-SVP")
            self.assertEqual(window.session.calculation.relativity, "Auto")
            with patch.object(window, "_guard_discard", return_value=True), \
                    patch.object(QFileDialog, "getOpenFileName", return_value=(path, "")):
                window.open_project()
            self.assertEqual(window.basis.currentData(), basis)
            self.assertEqual(window.relativity.currentData(), "X2C")
        dkh_basis = next(name for name in basis_options(method) if "DKH2" in scalar_options(method, name))
        window.basis.setCurrentText(dkh_basis)
        window.job.setCurrentIndex(window.job.findData("FREQ"))
        self.assertIn("NumFreq", window.job.currentText())
        self.assertIn("NumFreq", window.input_preview.toPlainText())
        self.assertTrue(window.method_hint.isVisible())
        window.basis.setCurrentText("def2-SVP")
        self.assertIn("Analytical frequencies", window.job.currentText())
        self.assertFalse(window.method_hint.isVisible())

    def test_reference_spin_validation_and_frozen_core_project(self):
        window = self.window
        window.method_group.setCurrentText(METHODS["HF"].family)
        window.method.setCurrentText("HF")
        self.assertEqual(tuple(window.wavefunction.itemData(i) for i in range(window.wavefunction.count())),
                         reference_options("HF", window.job.currentData()))
        window.wavefunction.setCurrentIndex(window.wavefunction.findData("RHF"))
        self.assertTrue(window.export_button.isEnabled())
        window.charge.setValue(1)
        window.multiplicity.setValue(2)
        self.assertFalse(window.export_button.isEnabled())
        window.wavefunction.setCurrentIndex(window.wavefunction.findData("UHF"))
        self.assertTrue(window.export_button.isEnabled(), window.validation.text())
        self.assertIn("UHF", window.input_preview.toPlainText())
        window.charge.setValue(0)
        window.multiplicity.setValue(1)
        window.method_group.setCurrentText(METHODS["MP2"].family)
        window.method.setCurrentText("MP2")
        self.assertEqual(tuple(window.frozen_core.itemData(i) for i in range(window.frozen_core.count())),
                         frozen_core_options("MP2"))
        window.frozen_core.setCurrentIndex(window.frozen_core.findData("NoFrozenCore"))
        self.assertIn("NoFrozenCore", window.input_preview.toPlainText())
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "frozen-core.oview.json")
            with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")):
                self.assertTrue(window.save_project_dialog())
            window.method_group.setCurrentText(METHODS["B3LYP"].family)
            self.assertEqual(window.session.calculation.frozen_core, "Auto")
            with patch.object(window, "_guard_discard", return_value=True), \
                    patch.object(QFileDialog, "getOpenFileName", return_value=(path, "")):
                window.open_project()
            self.assertEqual(window.frozen_core.currentData(), "NoFrozenCore")


if __name__ == "__main__":
    unittest.main()

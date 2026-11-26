"""The normal-mode viewer uses the same camera as the structure viewer."""

import os
from pathlib import Path
import unittest

import orcaview
from orcaview.orca.normal_modes import parse_normal_modes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication, QPushButton
    from orcaview.gui.normal_mode_dialog import NormalModeDialog
    from orcaview.gui.viewport import MoleculeViewport
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


AXES = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


@unittest.skipUnless(QApplication, "requires Qt")
class NormalModeViewControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        root = Path(orcaview.__file__).resolve().parents[2]
        log = root / "artifacts/public/validation/ORCA-6.1.1-macOS-arm64/optfreq/job.out"
        cls.group, = parse_normal_modes(log.read_text(encoding="utf-8").splitlines(), 0, "")

    def setUp(self):
        self.dialog = NormalModeDialog((self.group,), frequency_line=self.group.frequency_line, mode_index=8)
        self.addCleanup(self.dialog.close)
        self.dialog.show()
        self.app.processEvents()
        self.view = self.dialog.viewport
        self.reference = MoleculeViewport(result_view=True)
        self.addCleanup(self.reference.close)
        self.reference.set_molecule(self.view.molecule)
        self.reference.resize(self.view.size())

    def assert_matching_camera(self):
        for axis in AXES:
            for observed, expected in zip(self.view.transform(*axis), self.reference.transform(*axis)):
                self.assertAlmostEqual(observed, expected)
        self.assertEqual(self.view.zoom, self.reference.zoom)
        self.assertEqual(self.view._pan, self.reference._pan)
        self.assertEqual(self.view._projection_scale(), self.reference._projection_scale())

    def test_camera_buttons_and_reset_match_the_structure_view(self):
        self.assert_matching_camera()
        self.assertEqual(self.dialog.view_controls.rotation_angle.value(), 15.)
        self.dialog.view_controls.rotation_angle.setValue(22.5)
        for name, axis, direction in (("rotateLeft", "y", -1), ("rotateRight", "y", 1),
                                      ("rotateForward", "x", 1), ("rotateBackward", "x", -1),
                                      ("rotateUp", "z", 1), ("rotateDown", "z", -1)):
            with self.subTest(button=name):
                self.dialog.findChild(QPushButton, name).click()
                self.reference.rotate_view(axis, direction * 22.5)
                self.assert_matching_camera()
        self.view.rotate_view("x", 51)
        self.view.zoom = 2.4
        self.view._pan = QPointF(60, -35)
        self.dialog.amplitude.setValue(.55)
        self.dialog.speed.setValue(2.3)
        self.dialog.findChild(QPushButton, "resetView").click()
        self.reference.fit()
        self.assert_matching_camera()
        self.assertEqual(self.dialog.amplitude.value(), .55)
        self.assertEqual(self.dialog.speed.value(), 2.3)
        self.assertEqual(self.dialog.view_controls.rotation_angle.value(), 22.5)
        self.assertTrue(self.dialog.play.isChecked())

    def test_restore_defaults_resets_camera_and_playback_parameters_for_current_mode(self):
        dialog = self.dialog
        atoms = dialog.viewport.molecule.atoms
        for playing in (False, True):
            with self.subTest(playing=playing):
                dialog.play.setChecked(playing)
                dialog.view_controls.rotation_angle.setValue(83.3)
                dialog.amplitude.setValue(.77)
                dialog.speed.setValue(2.7)
                self.view.rotate_view("z", 83.3)
                self.view.zoom = .8
                self.view._pan = QPointF(-7, 12)
                dialog._phase = 1.2
                dialog._draw_phase()
                dialog.restore_defaults.click()
                self.assertEqual((dialog.view_controls.rotation_angle.value(), dialog.amplitude.value(),
                                  dialog.speed.value(), dialog._phase), (15., .35, 1., 0.))
                self.assertEqual(self.view._local_positions, self.view._equilibrium_positions)
                self.assertEqual(self.view.molecule.atoms, atoms)
                self.assertEqual(dialog.mode_table.item(dialog.mode_table.currentRow(), 0).text(), "8")
                self.assertEqual(dialog._timer.isActive(), playing)
                self.assert_matching_camera()

    def test_rendering_frames_uses_camera_without_changing_interactive_pose(self):
        self.dialog.play.setChecked(False)
        self.view.rotate_view("y", 62)
        self.view.set_displacement(.15)
        positions = self.view._local_positions
        camera = self.view._camera
        def frame(distance=None):
            result = QImage(self.view.size(), QImage.Format.Format_RGB32)
            result.fill(0xffffffff)
            with QPainter(result) as painter:
                if distance is None:
                    self.view.paint_structure(painter)
                else:
                    self.view.paint_displacement(painter, distance)
            return result
        pose = frame()
        self.assertNotEqual(frame(.35), frame(-.35))
        self.assertEqual(frame(.15), pose)
        self.assertEqual(frame(), pose)
        self.assertIs(self.view._local_positions, positions)
        self.assertEqual(self.view._camera, camera)

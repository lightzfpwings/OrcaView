"""Exercise vibrational playback with Cartesian vectors printed by ORCA."""

from dataclasses import replace
import math
import os
from pathlib import Path
import unittest

import orcaview
from orcaview.orca.normal_modes import parse_normal_modes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.normal_mode_dialog import NormalModeDialog
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


@unittest.skipUnless(QApplication, "requires Qt")
class NormalModeDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        root = Path(orcaview.__file__).resolve().parents[2]
        log = root / "artifacts/public/validation/ORCA-6.1.1-macOS-arm64/optfreq/job.out"
        cls.water, = parse_normal_modes(log.read_text(encoding="utf-8").splitlines(), 0, "")

    def dialog(self, groups, **options):
        window = NormalModeDialog(groups, **options)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        return window

    def test_water_mode_follows_printed_vectors_with_one_common_scale(self):
        group = self.water
        mode = group.modes[-1]
        window = self.dialog((group,), frequency_line=group.frequency_line, mode_index=mode.index)
        viewport = window.viewport
        window.play.click()
        viewport.rotate_view("y", 51)
        pose = viewport._camera
        atoms = viewport.molecule.atoms
        bonds = viewport.visual_bonds
        viewport.set_displacement(0.)
        original_scale, rest = viewport._project_atoms()
        largest = max(math.hypot(*d) for d in mode.displacements)
        for amplitude in (.35, -.35, 0.):
            viewport.set_displacement(amplitude)
            scale, current = viewport._project_atoms()
            self.assertEqual(scale, original_scale)
            for before, point, vector in zip(rest, current, mode.displacements):
                dx, dy, dz = viewport.transform(*(v * amplitude / largest for v in vector))
                self.assertAlmostEqual(point[0]-before[0], dx * scale)
                self.assertAlmostEqual(point[1]-before[1], -dy * scale)
                self.assertAlmostEqual(point[2]-before[2], dz)
        self.assertEqual(viewport._camera, pose)
        self.assertIs(viewport.visual_bonds, bonds)
        self.assertIs(viewport.molecule.atoms, atoms)
        self.assertEqual(atoms, group.atoms)

    def test_pause_resume_equilibrium_and_hide(self):
        window = self.dialog((self.water,))
        self.assertTrue(window._timer.isActive())
        QTest.qWait(90)
        window.play.click()
        self.assertFalse(window._timer.isActive())
        positions = window.viewport._local_positions
        self.assertNotEqual(positions, window.viewport._equilibrium_positions)
        QTest.qWait(60)
        self.assertEqual(window.viewport._local_positions, positions)
        window.amplitude.setValue(.70)
        self.assertNotEqual(window.viewport._local_positions, positions)
        window.speed.setValue(2.)
        window.equilibrium.click()
        self.assertEqual(window.viewport._local_positions, window.viewport._equilibrium_positions)
        window.play.click()
        self.assertTrue(window._timer.isActive())
        window.close()
        self.assertFalse(window._timer.isActive())

    def test_compound_sections_imaginary_frequency_and_projected_zero_modes(self):
        first = self.water
        unstable = replace(first.modes[0], frequency=-285.15, source_line=first.source_line+120)
        second = replace(first, frequency_line=first.frequency_line+100, source_line=first.source_line+100,
                         geometry_line=first.geometry_line+100, modes=(unstable,), title="Job 2")
        window = self.dialog((first, second), frequency_line=second.frequency_line, mode_index=unstable.index)
        self.assertTrue(window.group_choice.isVisible())
        self.assertEqual(window.mode_table.rowCount(), 1)
        self.assertIn("-285.15", window.mode_table.item(0, 1).text())
        self.assertIn("imaginary", window.mode_table.item(0, 1).text())
        self.assertIn(str(unstable.source_line), window.source.text())
        self.assertTrue(window.select_mode(first.frequency_line, first.modes[-1].index))
        self.assertEqual(window.mode_table.currentRow(), len(first.modes)-1)
        self.assertFalse(window.select_mode(first.frequency_line, 0))
        self.assertEqual(window.mode_table.currentRow(), len(first.modes)-1)
        self.assertFalse(window.select_mode(-5, unstable.index))

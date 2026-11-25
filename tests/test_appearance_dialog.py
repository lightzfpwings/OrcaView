"""Molecular appearance controls and the import/save/cancel boundary."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication, "Requires PySide6")
class AppearanceDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from orcaview.appearance import AppearanceSettings
        from orcaview.gui.appearance_dialog import AppearanceDialog
        self.store = Mock()
        self.store.palettes.return_value = {"default": "OrcaView default", "night": "Night"}
        self.initial = AppearanceSettings(model="wireframe", atom_scale=0.75, bond_scale=1.35,
                                          bond_distance_factor=1.05, palette_id="night")
        self.dialog = AppearanceDialog(self.initial, self.store)
        self.addCleanup(self.dialog.close)

    def _import(self, pack):
        with patch.object(QFileDialog, "getOpenFileName", return_value=("my-pack.json", "")), \
                patch("orcaview.gui.appearance_dialog.read_palette", return_value=pack):
            self.dialog._import_pack()

    def test_controls_roundtrip_and_model_specific_sizes(self):
        from orcaview.appearance import AppearanceSettings
        dialog = self.dialog
        self.assertEqual(dialog.settings(), self.initial)
        for index, (model_id, atoms, bonds) in enumerate((
                ("ball-and-stick", True, True), ("space-filling", True, False),
                ("stick", False, True), ("wireframe", False, True))):
            dialog.model.setCurrentIndex(index)
            self.assertEqual(dialog.settings().model, model_id)
            self.assertEqual(dialog.atom_scale.isEnabled(), atoms)
            self.assertEqual(dialog.bond_scale.isEnabled(), bonds)
            self.assertEqual(dialog.distance_factor.isEnabled(), bonds)
        buttons = dialog.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).click()
        self.assertEqual(dialog.settings(), AppearanceSettings())
        buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        self.store.save.assert_not_called()

    def test_import_edits_remain_pending_until_accepted(self):
        pack = SimpleNamespace(id="night", name="New night")
        self._import(pack)
        self.assertEqual(self.dialog.palette.count(), 2)
        self.assertEqual(self.dialog.palette.currentText(), pack.name)
        self.dialog.reject()
        self.store.install_palette.assert_not_called()

    def test_only_final_palette_is_installed_and_install_failure_keeps_dialog_open(self):
        self._import(SimpleNamespace(id="night", name="Updated"))
        pack = SimpleNamespace(id="pastel", name="Pastel")
        self._import(pack)
        self.store.install_palette.side_effect = OSError("Cannot write pack")
        self.dialog.accept()
        self.assertNotEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertIn("Cannot write pack", self.dialog.error.text())
        self.store.install_palette.side_effect = None
        self.dialog.accept()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.store.install_palette.assert_called_with(pack)
        self.assertEqual(self.dialog.settings().palette_id, "pastel")

    def test_invalid_import_preserves_previous_settings(self):
        with patch.object(QFileDialog, "getOpenFileName", return_value=("broken.json", "")), \
                patch("orcaview.gui.appearance_dialog.read_palette", side_effect=ValueError("Invalid hex")):
            self.dialog._import_pack()
        self.assertEqual(self.dialog.settings(), self.initial)
        self.assertIn("Invalid hex", self.dialog.error.text())
        self.dialog.accept()
        self.store.install_palette.assert_not_called()

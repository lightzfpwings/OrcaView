"""Edit molecular rendering preferences and choose an element color pack."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from orcaview.appearance import (
    BOND_DISTANCE_RANGE, MODEL_LABELS, SCALE_RANGE, AppearanceSettings, read_palette,
)
from orcaview.gui.file_dialogs import document_directory
from orcaview.i18n import diagnostic_text, tr


class AppearanceDialog(QDialog):
    def __init__(self, settings, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._pending_packs = {}
        self.setWindowTitle(tr("Molecular appearance"))
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.model = QComboBox()
        for model_id, label in MODEL_LABELS.items():
            self.model.addItem(tr(label), model_id)
        form.addRow(tr("Display model"), self.model)
        self.atom_scale = self._spin_box(SCALE_RANGE, 0.1)
        self.bond_scale = self._spin_box(SCALE_RANGE, 0.1)
        self.distance_factor = self._spin_box(BOND_DISTANCE_RANGE, 0.05)
        form.addRow(tr("Atom size"), self.atom_scale)
        form.addRow(tr("Bond thickness"), self.bond_scale)
        form.addRow(tr("Bond distance factor"), self.distance_factor)
        distance_hint = QLabel(tr(
            "A bond is drawn when 0.1 Å < distance ≤ factor × (sum of covalent radii). "
            "This applies only to structures with inferred bonds."
        ))
        distance_hint.setTextFormat(Qt.TextFormat.PlainText)
        distance_hint.setWordWrap(True)
        form.addRow(distance_hint)

        palette_row = QHBoxLayout()
        self.palette = QComboBox()
        palette_row.addWidget(self.palette, 1)
        for palette_id, name in store.palettes().items():
            self.palette.addItem(tr(name) if palette_id == "default" else name, palette_id)
        import_button = QPushButton(tr("Import color pack…"))
        import_button.clicked.connect(self._import_pack)
        palette_row.addWidget(import_button)
        palette_label = QLabel(tr("Element color scheme"))
        palette_label.setBuddy(self.palette)
        form.addRow(palette_label, palette_row)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)

        actions = QDialogButtonBox.StandardButton
        buttons = QDialogButtonBox(actions.RestoreDefaults | actions.Save | actions.Cancel)
        buttons.button(actions.RestoreDefaults).setText(tr("Restore defaults"))
        buttons.button(actions.RestoreDefaults).clicked.connect(lambda: self._set_values(AppearanceSettings()))
        buttons.button(actions.Save).setText(tr("Save"))
        buttons.button(actions.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.model.currentIndexChanged.connect(self._update_size_controls)
        self._set_values(settings)
        self._update_size_controls()
        self.resize(max(500, self.sizeHint().width()), self.sizeHint().height())

    @staticmethod
    def _spin_box(bounds, step):
        spin = QDoubleSpinBox()
        spin.setRange(*bounds)
        spin.setDecimals(2)
        spin.setSingleStep(step)
        spin.setSuffix(" ×")
        return spin

    def _set_values(self, settings):
        self.model.setCurrentIndex(self.model.findData(settings.model))
        self.atom_scale.setValue(settings.atom_scale)
        self.bond_scale.setValue(settings.bond_scale)
        self.distance_factor.setValue(settings.bond_distance_factor)
        palette_index = self.palette.findData(settings.palette_id)
        self.palette.setCurrentIndex(palette_index if palette_index >= 0 else self.palette.findData("default"))
        self.error.hide()

    def _update_size_controls(self):
        model = self.model.currentData()
        self.atom_scale.setEnabled(model in ("ball-and-stick", "space-filling"))
        self.bond_scale.setEnabled(model != "space-filling")
        self.distance_factor.setEnabled(model != "space-filling")

    def _import_pack(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, tr("Import color pack…"), str(document_directory(self)), tr("Element color packs") + " (*.json)"
        )
        if not filename:
            return
        try:
            pack = read_palette(filename)
        except (OSError, ValueError) as exc:
            self._show_import_error(exc)
            return
        self._pending_packs[pack.id] = pack
        index = self.palette.findData(pack.id)
        if index < 0:
            self.palette.addItem(pack.name, pack.id)
            index = self.palette.count() - 1
        else:
            self.palette.setItemText(index, pack.name)
        self.palette.setCurrentIndex(index)
        self.error.hide()

    def _show_import_error(self, error):
        self.error.setText(tr("Could not import color pack: {error}", error=diagnostic_text(error)))
        self.error.show()

    def settings(self):
        return AppearanceSettings(model=self.model.currentData(), atom_scale=self.atom_scale.value(),
                                  bond_scale=self.bond_scale.value(), bond_distance_factor=self.distance_factor.value(),
                                  palette_id=self.palette.currentData())

    def accept(self):
        pack = self._pending_packs.get(self.palette.currentData())
        if pack is not None:
            try:
                self.store.install_palette(pack)
            except (OSError, ValueError) as exc:
                self._show_import_error(exc)
                return
        super().accept()

"""Select an atom-resolved result and configure its labels and continuous color scale."""

from dataclasses import asdict, replace
import json

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QPushButton, QSpinBox, QVBoxLayout,
)

from orcaview.gui.population_map import PALETTES, PopulationStyle, population_name
from orcaview.i18n import tr
from orcaview.preferences import read_preferences, write_preferences


def _saved_scales():
    raw = read_preferences("population", {"populationPresets": "{}"})["populationPresets"]
    try:
        entries = json.loads(raw)
    except ValueError:
        return {}
    saved = {}
    if isinstance(entries, dict):
        for name, fields in entries.items():
            try:
                saved[name] = PopulationStyle(**{**fields, "colors": tuple(fields["colors"])})
            except (TypeError, ValueError, KeyError):
                continue
    return saved


class PopulationDialog(QDialog):
    preview_changed = Signal(object, object)

    def __init__(self, datasets, selected_id, style, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Atomic populations"))
        self.setMinimumWidth(365)
        self.datasets = {d.dataset_id: d for d in datasets}
        self.saved = _saved_scales()
        self._loading = True
        self._custom_colors = self.colors = style.colors
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.quantity = QComboBox()
        for d in datasets:
            self.quantity.addItem(population_name(d), d.dataset_id)
        self.quantity.setCurrentIndex(max(0, self.quantity.findData(selected_id)))
        form.addRow(tr("Quantity"), self.quantity)

        self.labels = QCheckBox(tr("Show values beside atoms"))
        self.color_atoms = QCheckBox(tr("Color atoms by value"))
        self.legend = QCheckBox(tr("Show legend"))
        for control, value in ((self.labels, style.labels), (self.color_atoms, style.color_atoms), (self.legend, style.legend)):
            control.setChecked(value)
            form.addRow(control)
        self.precision = QSpinBox()
        self.precision.setRange(0, 8)
        form.addRow(tr("Decimal places"), self.precision)

        self.palette = QComboBox()
        for name in PALETTES:
            self.palette.addItem(tr(name), name)
        self.palette.addItem(tr("Custom"), "custom")
        for name in self.saved:
            self.palette.addItem(tr("Saved · {name}", name=name), "saved/" + name)
        form.addRow(tr("Color scale"), self.palette)
        self.stops = QHBoxLayout()
        form.addRow(tr("Color stops"), self.stops)
        self.reverse = QCheckBox(tr("Reverse colors"))
        form.addRow(self.reverse)
        self.range_mode = QComboBox()
        for key, name in (("data", "Data minimum and maximum"), ("symmetric", "Symmetric about zero"), ("manual", "Manual limits")):
            self.range_mode.addItem(tr(name), key)
        form.addRow(tr("Range"), self.range_mode)
        self.lower, self.upper = QDoubleSpinBox(), QDoubleSpinBox()
        for label, control in (("Minimum", self.lower), ("Maximum", self.upper)):
            control.setDecimals(8)
            control.setRange(-1e15, 1e15)
            control.setSingleStep(.1)
            control.setKeyboardTracking(False)
            form.addRow(tr(label), control)
        self.use_midpoint = QCheckBox(tr("Set midpoint"))
        self.midpoint = QDoubleSpinBox()
        self.midpoint.setDecimals(8)
        self.midpoint.setRange(-1e15, 1e15)
        self.midpoint.setSingleStep(.1)
        self.midpoint.setKeyboardTracking(False)
        form.addRow(self.use_midpoint, self.midpoint)

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.save_preset = self.buttons.addButton(tr("Save preset…"), QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.save_preset.clicked.connect(self._save_preset)
        self.palette.currentIndexChanged.connect(self._choose_palette)
        self.range_mode.currentIndexChanged.connect(self._range_changed)
        self.quantity.currentIndexChanged.connect(self._range_changed)
        for check in (self.labels, self.color_atoms, self.reverse, self.legend, self.use_midpoint):
            check.toggled.connect(self._update)
        for spin in (self.lower, self.upper, self.midpoint, self.precision):
            spin.valueChanged.connect(self._update)
        builtin = next((key for key, colors in PALETTES.items() if colors == style.colors), "custom")
        self.palette.setCurrentIndex(self.palette.findData(builtin))
        self._load_scale(style)

    def _load_scale(self, style):
        self._loading = True
        self.colors = style.colors
        self.reverse.setChecked(style.reverse)
        self.precision.setValue(style.digits)
        self.range_mode.setCurrentIndex(self.range_mode.findData(style.range_mode))
        self.lower.setValue(style.lower)
        self.upper.setValue(style.upper)
        self.use_midpoint.setChecked(style.midpoint is not None)
        self.midpoint.setValue(style.midpoint if style.midpoint is not None else 0)
        self._loading = False
        self._color_buttons()
        self._range_changed()

    def _choose_palette(self):
        if self._loading:
            return
        name = self.palette.currentData()
        if name.startswith("saved/"):
            self._load_scale(self.saved[name[6:]])
            return
        self.colors = self._custom_colors if name == "custom" else PALETTES[name]
        self._color_buttons()
        self._update()

    def _color_buttons(self):
        while self.stops.count():
            self.stops.takeAt(0).widget().deleteLater()
        for index, color in enumerate(self.colors):
            button = QPushButton()
            button.setMinimumSize(25, 23)
            button.setStyleSheet(f"background-color: {color}; border: 1px solid #87817d; border-radius: 3px;")
            tip = tr("Color stop {number} · {color}", number=index + 1, color=color)
            button.setAccessibleName(tip)
            button.setToolTip(tip)
            button.clicked.connect(lambda checked=False, i=index: self._edit_color(i))
            self.stops.addWidget(button)

    def _edit_color(self, index):
        color = QColorDialog.getColor(QColor(self.colors[index]), self, tr("Choose a color stop"))
        if color.isValid():
            colors = list(self.colors)
            colors[index] = color.name()
            self.colors = self._custom_colors = tuple(colors)
            with QSignalBlocker(self.palette):
                self.palette.setCurrentIndex(self.palette.findData("custom"))
            self._color_buttons()
            self._update()

    def _range_changed(self):
        if self._loading:
            return
        mode = self.range_mode.currentData()
        manual = mode == "manual"
        self.lower.setEnabled(manual)
        self.upper.setEnabled(manual)
        self.use_midpoint.setEnabled(manual)
        with QSignalBlocker(self.lower), QSignalBlocker(self.upper):
            if not manual:
                data = self.datasets[self.quantity.currentData()]
                lo, hi = PopulationStyle(range_mode=mode).bounds([v for v in data.values if v is not None])
                self.lower.setValue(lo)
                self.upper.setValue(hi)
            elif self.lower.value() == self.upper.value():
                self.lower.setValue(self.lower.value() - .5)
                self.upper.setValue(self.upper.value() + .5)
        self._update()

    def style_value(self):
        mode = self.range_mode.currentData()
        bounds = (self.lower.value(), self.upper.value()) if mode == "manual" else (-1., 1.)
        center = self.midpoint.value() if mode == "manual" and self.use_midpoint.isChecked() else None
        return PopulationStyle(self.colors, mode, *bounds, self.reverse.isChecked(), self.precision.value(),
                               self.labels.isChecked(), self.color_atoms.isChecked(), self.legend.isChecked(), center)

    def _update(self):
        if self._loading:
            return
        self.midpoint.setEnabled(self.range_mode.currentData() == "manual" and self.use_midpoint.isChecked())
        try:
            style = self.style_value()
            error = ""
        except ValueError as exc:
            error = tr(str(exc))
        self.status.setText(error)
        self.status.setVisible(bool(error))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not error)
        self.save_preset.setEnabled(not error)
        if not error:
            self.preview_changed.emit(self.quantity.currentData(), style)

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, tr("Save population preset"), tr("Preset name"))
        name = name.strip()
        if not ok or not name:
            return
        # Scale presets do not change whether atom labels or the legend are visible.
        current = replace(self.style_value(), labels=True, color_atoms=False, legend=True)
        saved = _saved_scales()
        saved[name] = current
        try:
            write_preferences("population", {"populationPresets": json.dumps({k: asdict(v) for k, v in saved.items()})})
        except OSError as error:
            self.status.setText(str(error))
            self.status.show()
            return
        self.saved = saved
        key = "saved/" + name
        if self.palette.findData(key) < 0:
            self.palette.addItem(tr("Saved · {name}", name=name), key)
        self.palette.setCurrentIndex(self.palette.findData(key))

"""Play reported ORCA normal modes on their own equilibrium geometries."""

import math

from PySide6.QtCore import QElapsedTimer, QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from orcaview.core.models import Molecule
from orcaview.gui.normal_mode_export import export_animation_button
from orcaview.gui.result_display import report_text
from orcaview.gui.view_controls import DEFAULT_ROTATION_STEP, ViewControls
from orcaview.gui.viewport import NormalModeViewport
from orcaview.i18n import tr
from orcaview.results.vibration_playback import AMPLITUDE_RANGE, DEFAULT_AMPLITUDE, DEFAULT_SPEED, SPEED_RANGE


class NormalModeDialog(QDialog):
    def __init__(self, groups, parent=None, *, frequency_line=None, mode_index=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Vibrational modes"))
        self.groups = tuple(group for group in groups if group.modes)
        if not self.groups:
            raise ValueError("No complete normal modes are available.")
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance)
        self._elapsed = QElapsedTimer()
        self._phase = 0.
        layout = QVBoxLayout(self)

        self.group_choice = QComboBox()
        self.group_choice.setAccessibleName(tr("Frequency calculation"))
        for group in self.groups:
            self.group_choice.addItem(tr("{title} · line {line}", title=report_text(group.title),
                                         line=group.frequency_line))
        self.group_choice.setVisible(len(self.groups) > 1)
        layout.addWidget(self.group_choice)

        self.viewport = NormalModeViewport()
        self.view_controls = ViewControls(lambda: self.viewport)
        self.restore_defaults = QPushButton(tr("Restore defaults"))
        self.restore_defaults.setAutoDefault(False)
        self.restore_defaults.clicked.connect(self._restore_defaults)
        view_row = QHBoxLayout()
        view_row.addWidget(self.view_controls)
        view_row.addStretch()
        view_row.addWidget(self.restore_defaults)
        layout.addLayout(view_row)

        panes = QSplitter(Qt.Orientation.Horizontal)
        self.mode_table = QTableWidget(0, 2)
        self.mode_table.setAccessibleName(tr("Vibrational modes"))
        self.mode_table.setHorizontalHeaderLabels([tr("Mode"), tr("Frequency (cm⁻¹)")])
        self.mode_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.mode_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mode_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.mode_table.verticalHeader().hide()
        self.mode_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.mode_table.horizontalHeader().setStretchLastSection(True)
        panes.addWidget(self.mode_table)
        panes.addWidget(self.viewport)
        panes.setChildrenCollapsible(False)
        panes.setStretchFactor(1, 1)
        panes.setSizes([205, 520])
        layout.addWidget(panes, 1)

        controls = QHBoxLayout()
        layout.addLayout(controls)
        self.play = QPushButton(tr("Pause"))
        self.play.setCheckable(True)
        self.play.setChecked(True)
        self.play.setAutoDefault(False)
        controls.addWidget(self.play)
        self.equilibrium = QPushButton(tr("Equilibrium"))
        self.equilibrium.setAutoDefault(False)
        self.equilibrium.clicked.connect(self._reset_motion)
        controls.addWidget(self.equilibrium)
        controls.addStretch()
        self.amplitude = QDoubleSpinBox()
        self.amplitude.setRange(*AMPLITUDE_RANGE)
        self.amplitude.setSingleStep(.05)
        self.amplitude.setValue(DEFAULT_AMPLITUDE)
        self.amplitude.setSuffix(" Å")
        self.amplitude.setToolTip(tr("Peak displacement of the most mobile atom."))
        self.speed = QDoubleSpinBox()
        self.speed.setRange(*SPEED_RANGE)
        self.speed.setDecimals(1)
        self.speed.setSingleStep(.1)
        self.speed.setValue(DEFAULT_SPEED)
        self.speed.setSuffix(" ×")
        self.speed.setToolTip(tr("At 1×, the display plays one cycle per second."))
        for text, control in ((tr("Amplitude"), self.amplitude), (tr("Playback speed"), self.speed)):
            label = QLabel(text)
            label.setBuddy(control)
            controls.addWidget(label)
            controls.addWidget(control)
        self.source = QLabel()
        self.source.setWordWrap(True)
        self.footer = QHBoxLayout()
        self.footer.addWidget(self.source, 1)
        self.export_button = export_animation_button(self)
        self.footer.addWidget(self.export_button)
        layout.addLayout(self.footer)

        self.play.toggled.connect(self._play_toggled)
        self.amplitude.valueChanged.connect(self._draw_phase)
        self.mode_table.currentCellChanged.connect(self._change_mode)
        self.group_choice.currentIndexChanged.connect(self._change_group)
        self.resize(820, 540)
        self._change_group(0)
        if frequency_line is not None:
            self.select_mode(frequency_line, mode_index)

    def select_mode(self, frequency_line, mode_index=None):
        """Select by the ORCA frequency-table line and printed mode number."""
        for number, group in enumerate(self.groups):
            if group.frequency_line != frequency_line:
                continue
            row = 0 if mode_index is None else next(
                (i for i, mode in enumerate(group.modes) if mode.index == mode_index), None)
            if row is None:
                return False
            self.group_choice.setCurrentIndex(number)
            self.mode_table.setCurrentCell(row, 0)
            return True
        return False

    def _change_group(self, number):
        group = self.groups[number]
        self.viewport.set_equilibrium(Molecule(group.title, group.atoms))
        with QSignalBlocker(self.mode_table):
            self.mode_table.setRowCount(len(group.modes))
            for row, mode in enumerate(group.modes):
                frequency = f"{mode.frequency:.2f}"
                if mode.frequency < 0:
                    frequency = tr("{frequency} (imaginary)", frequency=frequency)
                self.mode_table.setItem(row, 0, QTableWidgetItem(str(mode.index)))
                self.mode_table.setItem(row, 1, QTableWidgetItem(frequency))
            self.mode_table.setCurrentCell(0, 0)
        self._change_mode(0)

    def _change_mode(self, row):
        if row < 0:
            return
        group = self.groups[self.group_choice.currentIndex()]
        mode = group.modes[row]
        self.viewport.set_mode(mode.displacements)
        self.source.setText(tr("Geometry at line {geometry} · Mode vectors at line {vectors}",
                               geometry=group.geometry_line, vectors=mode.source_line))
        # Retain the viewing angle and the playback phase when comparing modes.
        self._draw_phase()

    def _draw_phase(self):
        self.viewport.set_displacement(self.amplitude.value() * math.sin(self._phase))

    def _advance(self):
        self._phase = (self._phase + math.tau * self.speed.value() * self._elapsed.restart() / 1000) % math.tau
        self._draw_phase()

    def _play_toggled(self, playing):
        self.play.setText(tr("Pause") if playing else tr("Play"))
        if playing and self.isVisible():
            self._elapsed.start()
            self._timer.start()
        else:
            self._timer.stop()

    def _reset_motion(self):
        self.play.setChecked(False)
        self._phase = 0.
        self._draw_phase()

    def _restore_defaults(self):
        self._phase = 0.
        self.amplitude.setValue(DEFAULT_AMPLITUDE)
        self.speed.setValue(DEFAULT_SPEED)
        self.view_controls.rotation_angle.setValue(DEFAULT_ROTATION_STEP)
        self.viewport.fit()
        self._draw_phase()
        if self._timer.isActive():
            self._elapsed.restart()

    def showEvent(self, event):
        super().showEvent(event)
        self._play_toggled(self.play.isChecked())

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

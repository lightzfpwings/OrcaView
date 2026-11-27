"""Browse signed isosurfaces from a Molden wavefunction or a Gaussian Cube."""

from concurrent.futures import CancelledError, ThreadPoolExecutor
import math
from pathlib import Path
from threading import Event

from PySide6.QtCore import QPoint, QRect, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QDoubleSpinBox, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from orcaview.application.structure_import import read_linked_orbitals
from orcaview.gui.orbital_viewport import OrbitalViewport, PHASE_COLORS
from orcaview.i18n import diagnostic_text, tr
from orcaview.io.cube import CubeData
from orcaview.io.molden_orbitals import MoldenOrbitals
from orcaview.preferences import read_preferences, write_preferences
from orcaview.results.orbital_surface import SURFACE_QUALITIES, make_cube_surface, make_orbital_surface


_PALETTES = (("Blue / orange", (PHASE_COLORS[1], PHASE_COLORS[-1])),
             ("Red / blue", ("#cf4547", "#386dc4")),
             ("Green / purple", ("#2c926b", "#8855b5")),
             ("Teal / gold", ("#11898b", "#cf942f")))


class _SurfaceQualityCombo(QComboBox):
    def __init__(self):
        super().__init__()
        self.setAccessibleName(tr("Surface quality"))
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.setMinimumContentsLength(6)
        # Use list rows so the macOS menu checkmark does not consume their text area.
        self.setStyleSheet("""
            QComboBox { combobox-popup: 0; }
            QAbstractItemView { border: 1px solid #DDD5CB; }
            QAbstractItemView::item { padding: 3px 8px; }
        """)
        for key, preset in SURFACE_QUALITIES.items():
            self.addItem(tr(preset.label), key)

    def showPopup(self):
        view = self.view()
        content_width = view.sizeHintForColumn(self.modelColumn()) + 2*view.frameWidth()
        view.setMinimumWidth(max(self.width(), content_width))
        super().showPopup()
        # Some styles still position the first list row over the closed field.
        popup = view.window()
        field = QRect(self.mapToGlobal(QPoint()), self.size())
        if popup.isVisible() and popup.geometry().intersects(field):
            screen = self.screen().availableGeometry()
            below, above = field.bottom()+1, field.top()-popup.height()
            if below+popup.height() <= screen.bottom()+1:
                top = below
            elif above >= screen.top():
                top = above
            else:
                return  # retain Qt's scrolling popup on short screens
            left = field.right()+1-popup.width() if self.isRightToLeft() else field.left()
            popup.move(max(screen.left(), min(left, screen.right()+1-popup.width())), top)


def _label(text, buddy, row):
    label = QLabel(text)
    label.setBuddy(buddy)
    row.addWidget(label)
    row.addWidget(buddy)
    return label


class OrbitalPanel(QWidget):
    availability_changed = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = self.wave = self.future = self._cancel = None
        self._requested = None
        self._rows = []
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orcaview-orbitals")
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._finish)
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setObjectName("heading")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.title)
        panes = QSplitter(Qt.Orientation.Horizontal)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 8, 0)
        spin_row = QHBoxLayout()
        self.spin = QComboBox()
        self.spin_label = _label(tr("Spin"), self.spin, spin_row)
        spin_row.setStretch(1, 1)
        side.addLayout(spin_row)
        self.grid_info = QLabel()
        self.grid_info.setWordWrap(True)
        self.grid_info.setTextFormat(Qt.TextFormat.PlainText)
        side.addWidget(self.grid_info)
        self.table = QTableWidget(0, 4)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setDefaultSectionSize(72)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        side.addWidget(self.table, 1)
        panes.addWidget(sidebar)
        scene = QWidget()
        right = QVBoxLayout(scene)
        right.setContentsMargins(4, 0, 0, 0)
        controls = QHBoxLayout()
        self.level = QDoubleSpinBox()
        self.level.setKeyboardTracking(False)
        self.level_label = _label(tr("Isovalue |ψ|"), self.level, controls)
        self.level_unit = QLabel("a<sub>0</sub><sup>−3/2</sup>")
        controls.addWidget(self.level_unit)
        controls.addSpacing(14)
        self.quality = _SurfaceQualityCombo()
        _label(tr("Surface quality"), self.quality, controls)
        controls.addStretch()
        right.addLayout(controls)
        palette_row = QHBoxLayout()
        self.palette_choice = QComboBox()
        for label, _ in _PALETTES:
            self.palette_choice.addItem(tr(label))
        self.palette_choice.setPlaceholderText(tr("Custom"))
        _label(tr("Colors"), self.palette_choice, palette_row)
        self.color_buttons = {}
        for sign, label in ((1, "Positive phase"), (-1, "Negative phase")):
            button = QPushButton(tr(label))
            button.clicked.connect(lambda checked=False, s=sign: self._choose_color(s))
            self.color_buttons[sign] = button
            palette_row.addWidget(button)
        palette_row.addStretch()
        right.addLayout(palette_row)
        self.viewport = OrbitalViewport()
        right.addWidget(self.viewport, 1)
        panes.addWidget(scene)
        panes.setChildrenCollapsible(False)
        panes.setSizes([340, 780])
        panes.setStretchFactor(1, 1)
        layout.addWidget(panes, 1)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        prefs = read_preferences("orbital-surface", {"positive": PHASE_COLORS[1], "negative": PHASE_COLORS[-1],
                                                    "quality": "smooth"})
        option = self.quality.findData(prefs["quality"])
        self.quality.setCurrentIndex(option if option >= 0 else self.quality.findData("smooth"))
        self.colors = {s: QColor(prefs[key]).name() if QColor.isValidColorName(prefs[key]) else PHASE_COLORS[s]
                       for s, key in ((1, "positive"), (-1, "negative"))}
        self._show_colors()
        self.spin.currentIndexChanged.connect(self._fill_table)
        self.table.currentCellChanged.connect(self._select_row)
        self.level.valueChanged.connect(self._request_surface)
        self.quality.currentIndexChanged.connect(self._quality_changed)
        self.palette_choice.currentIndexChanged.connect(self._set_palette)

    def _show_colors(self):
        pair = (self.colors[1], self.colors[-1])
        with QSignalBlocker(self.palette_choice):
            self.palette_choice.setCurrentIndex(next((i for i, (_, colors) in enumerate(_PALETTES) if colors == pair), -1))
        for sign, button in self.color_buttons.items():
            swatch = QPixmap(16, 16)
            swatch.fill(QColor(self.colors[sign]))
            button.setIcon(QIcon(swatch))
            button.setToolTip(self.colors[sign].upper())
        self.viewport.set_phase_colors(self.colors)

    def _save_preferences(self):
        try:
            write_preferences("orbital-surface", {"positive": self.colors[1], "negative": self.colors[-1],
                                                  "quality": self.quality.currentData()})
        except OSError as exc:
            self.status.setText(diagnostic_text(exc))

    def _set_palette(self, index):
        if index >= 0:
            self.colors = dict(zip((1, -1), _PALETTES[index][1]))
            self._show_colors()
            self._save_preferences()

    def _choose_color(self, sign):
        color = QColorDialog.getColor(QColor(self.colors[sign]), self, self.color_buttons[sign].text())
        if color.isValid():
            self.colors[sign] = color.name()
            self._show_colors()
            self._save_preferences()

    def _quality_changed(self):
        self._request_surface()
        self._save_preferences()

    def _stop_request(self):
        self._timer.stop()
        if self._cancel:
            self._cancel.set()
        if self.future:
            self.future.cancel()
        self.future = self._cancel = self._requested = None

    def shutdown(self):
        self._stop_request()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def set_source(self, source, wave=None, project=None):
        self._stop_request()
        self.source, self.wave = source, wave
        self._rows = []
        with QSignalBlocker(self.table), QSignalBlocker(self.spin):
            self.table.setRowCount(0)
            self.spin.clear()
        self.viewport.set_surface(None)
        self.viewport.set_molecule(None)
        self.status.clear()
        self.title.setText(Path(source.path_hint).name if source else "")
        self.title.setToolTip(source.path_hint if source else "")
        if source and wave is None:
            self.status.setText(tr("Reading linked orbital data…"))
            self._cancel = Event()
            self.future = self._pool.submit(read_linked_orbitals, source, project, self._cancel)
            self._timer.start()
        self.availability_changed.emit(wave is not None, self.status.text())

    def finish_loading(self):
        if self.wave is None and self.future is not None:
            self._finish(wait=True)

    def activate(self):
        if self.wave is None or self.future is not None:
            return
        if self._rows:
            self._request_surface()
            return
        self.viewport.set_molecule(self.wave.molecule)
        self.viewport.rotate_view("x", 20.)
        self.viewport.rotate_view("y", -25.)
        is_cube = isinstance(self.wave, CubeData)
        self.spin.setVisible(not is_cube)
        self.spin_label.setVisible(not is_cube)
        self.level_unit.setVisible(not is_cube)
        self.grid_info.setVisible(is_cube)
        self.color_buttons[1].setText(tr("Positive surface") if is_cube else tr("Positive phase"))
        self.color_buttons[-1].setText(tr("Negative surface") if is_cube else tr("Negative phase"))
        if is_cube:
            self.viewport.set_grid_center(self.wave.grid)
            dims = " × ".join(map(str, self.wave.grid.shape))
            self.grid_info.setText(tr("Grid · {dimensions}", dimensions=dims))
            self.grid_info.setToolTip("\n".join(self.wave.comments))
            self.table.setAccessibleName(tr("Cube fields"))
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels([tr("Cube field")])
            self.level_label.setText(tr("Isovalue"))
        else:
            self.table.setAccessibleName(tr("Molecular orbitals"))
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels([tr("Orbital"), tr("Energy (Ha)"), tr("Occ."), tr("Sym.")])
            self.table.horizontalHeaderItem(0).setToolTip(tr("ORCA orbital numbers start at zero within each spin."))
            self.level_label.setText(tr("Isovalue |ψ|"))
            with QSignalBlocker(self.level):
                self.level.setDecimals(3)
                self.level.setRange(.001, 10.)
                self.level.setSingleStep(.005)
                self.level.setValue(.05)
            self._frontiers = self.wave.frontiers()
            occupied = [i for i, label in self._frontiers.items() if label == "HOMO"]
            default = (max(occupied, key=lambda i: self.wave.orbitals[i].energy) if occupied
                       else min(range(len(self.wave.orbitals)), key=lambda i: self.wave.orbitals[i].energy))
            with QSignalBlocker(self.spin):
                self.spin.clear()
                for spin in sorted({mo.spin for mo in self.wave.orbitals}):
                    self.spin.addItem(tr("Alpha") if spin == "Alpha" else tr("Beta"), spin)
                self.spin.setCurrentIndex(self.spin.findData(self.wave.orbitals[default].spin))
        self._fill_table()

    def _fill_table(self):
        if self.wave is None:
            return
        if isinstance(self.wave, CubeData):
            self._rows = list(range(len(self.wave.fields)))
            cells = [(str(field.identifier),) for field in self.wave.fields]
            default = 0
        else:
            self._rows = [i for i, mo in enumerate(self.wave.orbitals) if mo.spin == self.spin.currentData()]
            cells = []
            for index in self._rows:
                mo = self.wave.orbitals[index]
                name = f"{mo.number}  {self._frontiers.get(index, '')}".strip()
                cells.append((name, f"{mo.energy:.6f}", f"{mo.occupation:g}", mo.symmetry))
            default = next((r for r, i in enumerate(self._rows) if self._frontiers.get(i) == "HOMO"),
                           next((r for r, i in enumerate(self._rows) if self._frontiers.get(i) == "LUMO"), 0))
        with QSignalBlocker(self.table):
            self.table.setRowCount(len(cells))
            for row, values in enumerate(cells):
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(value))
            self.table.setCurrentCell(default, 0)
        self._select_row()

    def _select_row(self):
        row = self.table.currentRow()
        if isinstance(self.wave, CubeData) and 0 <= row < len(self._rows):
            field = self.wave.fields[self._rows[row]]
            level = field.initial_isovalue()
            digits = min(323, max(3, 3-math.floor(math.log10(level))))
            with QSignalBlocker(self.level):
                self.level.setDecimals(digits)
                self.level.setRange(10.**-digits, max(level, abs(field.minimum), abs(field.maximum)))
                self.level.setSingleStep(max(10.**-digits, level/10))
                self.level.setValue(level)
        self._request_surface()

    def _request_surface(self):
        row = self.table.currentRow()
        if self.wave is None or not 0 <= row < len(self._rows):
            return
        index, level, quality = self._rows[row], self.level.value(), self.quality.currentData()
        key = (index, level, quality)
        if key == self._requested:
            return
        self._stop_request()
        self._requested = key
        self.viewport.set_surface(None)
        self.status.setText(tr("Calculating isosurface…"))
        self._cancel = Event()
        builder = make_cube_surface if isinstance(self.wave, CubeData) else make_orbital_surface
        self.future = self._pool.submit(builder, self.wave, index, level, self._cancel, quality=quality)
        self._timer.start()

    def _finish(self, *, wait=False):
        if self.future is None or (not wait and not self.future.done()):
            return
        self._timer.stop()
        future, self.future = self.future, None
        try:
            result = future.result()
        except (ValueError, OSError, ArithmeticError, CancelledError) as exc:
            self.status.setText(diagnostic_text(exc))
            self._requested = None
            if self.wave is None:
                self.availability_changed.emit(False, self.status.text())
            return
        if isinstance(result, (MoldenOrbitals, CubeData)):
            self.wave = result
            self.status.clear()
            self.availability_changed.emit(True, "")
        else:
            self.viewport.set_surface(result)
            if result.clipped:
                self.status.setText(tr("The surface reaches the edge of the sampled grid."))
            elif not result.faces:
                self.status.setText(tr("No surface at this isovalue."))
            else:
                self.status.clear()

    def finish_for_capture(self):
        self.finish_loading()
        self.activate()
        while self.future is not None:
            self._finish(wait=True)
        if self.viewport.surface is None:
            raise ValueError(self.status.text() or tr("Open a Molden wavefunction or a Cube file."))

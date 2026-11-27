"""Browse signed isosurfaces from a Molden wavefunction or a Gaussian Cube."""

from concurrent.futures import CancelledError, ThreadPoolExecutor
import math
from pathlib import Path
from threading import Event

from PySide6.QtCore import QPoint, QRect, QSignalBlocker, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QDoubleSpinBox, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from orcaview.application.structure_import import read_linked_orbitals
from orcaview.gui.orbital_composition import CubeOrbitalAnalysis, OrbitalAnalysis, OrbitalDecomposition
from orcaview.gui.orbital_viewport import OrbitalViewport, PHASE_COLORS
from orcaview.i18n import diagnostic_text, tr
from orcaview.io.cube import CubeData
from orcaview.io.molden_orbitals import MoldenOrbitals
from orcaview.orca.orbital_files import ORBITAL_SET_LABELS
from orcaview.preferences import read_preferences, write_preferences
from orcaview.results.orbital_surface import SURFACE_QUALITIES, make_cube_surface, make_orbital_surface


_PALETTES = {
    "Blue / orange": (PHASE_COLORS[1], PHASE_COLORS[-1]),
    "Red / blue": ("#cf4547", "#386dc4"),
    "Green / purple": ("#2c926b", "#8855b5"),
    "Teal / gold": ("#11898b", "#cf942f"),
    "Cyan / magenta": ("#1695a8", "#bf438a"),
    "Indigo / lime": ("#514fa1", "#91b93b"),
    "Navy / coral": ("#304d79", "#de7869"),
    "Violet / amber": ("#8254ac", "#dfa426"),
    "Charcoal / silver": ("#454b56", "#aeb9c4"),
}


def _phase_swatch(positive, negative):
    swatch = QPixmap(26, 14)
    swatch.fill(Qt.GlobalColor.transparent)
    with QPainter(swatch) as painter:
        painter.fillRect(0, 1, 12, 12, QColor(positive))
        painter.fillRect(14, 1, 12, 12, QColor(negative))
    return QIcon(swatch)


class _OrbitalCombo(QComboBox):
    def __init__(self, label):
        super().__init__()
        self.setAccessibleName(label)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.setMinimumContentsLength(6)
        # Use list rows so the macOS menu checkmark does not consume their text area.
        self.setStyleSheet("""
            QComboBox { combobox-popup: 0; }
            QAbstractItemView { border: 1px solid #DDD5CB; }
            QAbstractItemView::item { padding: 3px 8px; }
        """)

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
        self._source_wave = self._natural = self._engine = None
        self._deriving = False
        self._surfaces = {}
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
        set_row = QHBoxLayout()
        self.representation = QComboBox()
        self.representation.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.representation_label = _label(tr("Orbital set"), self.representation, set_row)
        set_row.setStretch(1, 1)
        side.addLayout(set_row)
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
        self.quality = _OrbitalCombo(tr("Surface quality"))
        for key, preset in SURFACE_QUALITIES.items():
            self.quality.addItem(tr(preset.label), key)
        _label(tr("Surface quality"), self.quality, controls)
        controls.addStretch()
        right.addLayout(controls)
        palette_row = QHBoxLayout()
        self.palette_choice = _OrbitalCombo(tr("Colors"))
        self.palette_choice.setIconSize(QSize(26, 14))
        for name, pair in _PALETTES.items():
            self.palette_choice.addItem(_phase_swatch(*pair), tr(name), name)
        self.palette_choice.addItem(tr("Custom"), "custom")
        _label(tr("Colors"), self.palette_choice, palette_row)
        self.color_buttons = {}
        for sign, label in ((1, "Positive phase"), (-1, "Negative phase")):
            button = QPushButton(tr(label))
            button.clicked.connect(lambda checked=False, s=sign: self._choose_color(s))
            self.color_buttons[sign] = button
            palette_row.addWidget(button)
        palette_row.addStretch()
        right.addLayout(palette_row)
        surface_panes = QSplitter(Qt.Orientation.Horizontal)
        self.viewport = OrbitalViewport()
        results_pane = QWidget()
        surface_panes.addWidget(self.viewport)
        surface_panes.addWidget(results_pane)
        surface_panes.setChildrenCollapsible(False)
        surface_panes.setStretchFactor(0, 1)
        surface_panes.setSizes([520, 260])
        self.decomposition = OrbitalDecomposition(results_pane)
        side.addWidget(self.decomposition)
        right.addWidget(surface_panes, 1)
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
                                                    "quality": "standard", "palette": "",
                                                    "customPositive": "", "customNegative": ""})
        option = self.quality.findData(prefs["quality"])
        self.quality.setCurrentIndex(option if option >= 0 else self.quality.findData("standard"))
        self.colors = {s: QColor(prefs[key]).name() if QColor.isValidColorName(prefs[key]) else PHASE_COLORS[s]
                       for s, key in ((1, "positive"), (-1, "negative"))}
        pair = (self.colors[1], self.colors[-1])
        # Older preferences contain only the active pair.
        active = next((name for name, colors in _PALETTES.items() if colors == pair), "custom")
        if prefs["palette"] == "custom":
            active = "custom"
        self.palette_choice.setCurrentIndex(self.palette_choice.findData(active))
        saved_pair = (prefs["customPositive"], prefs["customNegative"])
        self._custom_colors = None
        if active == "custom":
            self._custom_colors = pair
        elif all(QColor.isValidColorName(color) for color in saved_pair):
            self._custom_colors = tuple(QColor(color).name() for color in saved_pair)
        self._show_colors()
        self.representation.currentIndexChanged.connect(self._change_representation)
        self.spin.currentIndexChanged.connect(self._fill_table)
        self.table.currentCellChanged.connect(self._select_row)
        self.level.valueChanged.connect(self._request_surface)
        self.quality.currentIndexChanged.connect(self._quality_changed)
        self.palette_choice.currentIndexChanged.connect(self._set_palette)

    def _show_colors(self):
        custom = self._custom_colors or (self.colors[1], self.colors[-1])
        self.palette_choice.setItemIcon(self.palette_choice.findData("custom"), _phase_swatch(*custom))
        for sign, button in self.color_buttons.items():
            swatch = QPixmap(16, 16)
            swatch.fill(QColor(self.colors[sign]))
            button.setIcon(QIcon(swatch))
            button.setToolTip(self.colors[sign].upper())
        self.viewport.set_phase_colors(self.colors)

    def _save_preferences(self):
        positive, negative = self._custom_colors or ("", "")
        try:
            write_preferences("orbital-surface", {"positive": self.colors[1], "negative": self.colors[-1],
                                                  "palette": self.palette_choice.currentData(),
                                                  "customPositive": positive, "customNegative": negative,
                                                  "quality": self.quality.currentData()})
        except OSError as exc:
            self.status.setText(diagnostic_text(exc))

    def _set_palette(self, index):
        if index < 0:
            return
        name = self.palette_choice.itemData(index)
        if name == "custom":
            pair = self._custom_colors or (self.colors[1], self.colors[-1])
            self._custom_colors = pair
        else:
            pair = _PALETTES[name]
        self.colors = dict(zip((1, -1), pair))
        self._show_colors()
        self._save_preferences()

    def _choose_color(self, sign):
        color = QColorDialog.getColor(QColor(self.colors[sign]), self, self.color_buttons[sign].text())
        if color.isValid():
            self.colors[sign] = color.name()
            self._custom_colors = (self.colors[1], self.colors[-1])
            with QSignalBlocker(self.palette_choice):
                self.palette_choice.setCurrentIndex(self.palette_choice.findData("custom"))
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
        self._deriving = False

    def shutdown(self):
        self._stop_request()
        self._surfaces.clear()
        self.decomposition.shutdown()
        self.viewport.release_renderer()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def set_source(self, source, wave=None, project=None):
        self._stop_request()
        self._surfaces.clear()
        self.source, self.wave = source, wave
        self._source_wave = self._natural = self._engine = None
        self.decomposition.button.setChecked(False)
        self.decomposition.set_orbital(None, None)
        with QSignalBlocker(self.representation):
            self.representation.clear()
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
        self.representation.setVisible(not is_cube)
        self.representation_label.setVisible(not is_cube)
        self.spin.setVisible(not is_cube)
        self.spin_label.setVisible(not is_cube)
        self.level_unit.setVisible(not is_cube)
        self.grid_info.setVisible(is_cube)
        self.color_buttons[1].setText(tr("Positive surface") if is_cube else tr("Positive phase"))
        self.color_buttons[-1].setText(tr("Negative surface") if is_cube else tr("Negative phase"))
        if is_cube:
            self._engine = CubeOrbitalAnalysis(self.wave) if CubeOrbitalAnalysis and self.wave.molecule.atoms else None
            self.viewport.set_grid_center(self.wave.grid)
            dims = " × ".join(map(str, self.wave.grid.shape))
            self.grid_info.setText(tr("Grid · {dimensions}", dimensions=dims))
            self.grid_info.setToolTip("\n".join(self.wave.comments))
            self.table.setAccessibleName(tr("Cube fields"))
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels([tr("Cube field")])
            self.level_label.setText(tr("Isovalue"))
        else:
            self._source_wave = self.wave
            self._engine = OrbitalAnalysis(self.wave) if OrbitalAnalysis is not None else None
            self.level_label.setText(tr("Isovalue |ψ|"))
            with QSignalBlocker(self.level):
                self.level.setDecimals(3)
                self.level.setRange(.001, 10.)
                self.level.setSingleStep(.005)
                self.level.setValue(.05)
            with QSignalBlocker(self.representation):
                self.representation.clear()
                kind = self.wave.kind
                self.representation.addItem(tr(ORBITAL_SET_LABELS[kind]), "file")
                if self._engine and self.wave.complete_density and kind not in ("uno", "unso", "natural"):
                    label = "Natural orbitals (QRO density)" if kind == "qro" else "Natural orbitals (total density)"
                    self.representation.addItem(tr(label), "natural")
                    if kind in ("qro", "uco", "localized"):
                        self.representation.setCurrentIndex(1)
            self._change_representation()
            return
        self._fill_table()

    def _change_representation(self):
        if self._source_wave is None:
            return
        self._stop_request()
        self._surfaces.clear()
        self._rows = []
        with QSignalBlocker(self.table):
            self.table.setRowCount(0)
        self.decomposition.set_orbital(None, None)
        self.viewport.set_surface(None)
        self.representation.setToolTip(self.representation.currentText())
        if self.representation.currentData() == "natural":
            if self._source_wave.kind == "qro":
                self.representation.setToolTip(tr("These occupations describe the QRO density. Open the UNO file for the original unrestricted density."))
            if self._natural is None:
                self.status.setText(tr("Calculating natural orbitals…"))
                self._cancel = Event()
                self._deriving = True
                self.spin.setEnabled(False)
                self.future = self._pool.submit(self._engine.natural_orbitals, self._cancel)
                self._timer.start()
                return
            self.wave = self._natural
        else:
            self.wave = self._source_wave
        self._configure_orbitals()

    def _configure_orbitals(self):
        kind = self.wave.kind
        self.spin.setEnabled(True)
        self.table.setAccessibleName(tr(ORBITAL_SET_LABELS[kind]))
        occupancy = {"unso": "Spin occupation", "uno": "Natural occupation", "natural": "Natural occupation"}
        columns = ["Orbital", "Energy (Ha)", "Occ.", "Sym."] if kind in ("mo", "qro") else [
            "Orbital", occupancy.get(kind, "Occ."), "Sym."]
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels([tr(t) for t in columns])
        self.table.horizontalHeaderItem(0).setToolTip(tr("ORCA orbital numbers start at zero within each spin."))
        self._frontiers = self.wave.frontiers()
        spins = sorted({mo.spin for mo in self.wave.orbitals})
        self.spin.setVisible(len(spins) > 1 or kind == "mo")
        self.spin_label.setVisible(not self.spin.isHidden())
        occupied = [self.wave.orbitals[i] for i, label in self._frontiers.items() if label == "HOMO"]
        default_spin = max(occupied, key=lambda mo: mo.energy).spin if occupied else spins[0]
        with QSignalBlocker(self.spin):
            self.spin.clear()
            for spin in spins:
                self.spin.addItem(tr("Alpha") if spin == "Alpha" else tr("Beta"), spin)
            self.spin.setCurrentIndex(self.spin.findData(default_spin))
        self._fill_table()

    def _fill_table(self):
        if self.wave is None or self._deriving:
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
                if self.wave.kind in ("mo", "qro"):
                    cells.append((name, f"{mo.energy:.6f}", f"{mo.occupation:g}", mo.symmetry))
                else:
                    cells.append((name, f"{mo.occupation:.8g}", mo.symmetry))
            default = next((r for r, i in enumerate(self._rows) if self._frontiers.get(i) == "HOMO"),
                           next((r for r, i in enumerate(self._rows) if self._frontiers.get(i) == "LUMO"), 0))
            if self.wave.kind == "unso":
                default = max(range(len(cells)), key=lambda r: abs(self.wave.orbitals[self._rows[r]].occupation))
            elif self.wave.kind in ("natural", "uno"):
                # Highlight the most fractionally occupied spatial orbital. Break closed-shell ties at the frontier.
                default = min(range(len(cells)), key=lambda r: (abs(self.wave.orbitals[self._rows[r]].occupation-1),
                              -self.wave.orbitals[self._rows[r]].occupation, -r))
            elif self.wave.kind in ("uco", "qro", "localized"):
                default = max((r for r,i in enumerate(self._rows) if self.wave.orbitals[i].occupation > .5), default=0)
        with QSignalBlocker(self.table):
            self.table.setRowCount(len(cells))
            for row, values in enumerate(cells):
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(value))
            self.table.setCurrentCell(default, 0)
        self._select_row()

    def _select_row(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self._rows):
            self.decomposition.set_orbital(None, None)
            return
        if isinstance(self.wave, CubeData):
            field = self.wave.fields[self._rows[row]]
            mo = field
            level = field.initial_isovalue()
            digits = min(323, max(3, 3-math.floor(math.log10(level))))
            with QSignalBlocker(self.level):
                self.level.setDecimals(digits)
                self.level.setRange(10.**-digits, max(level, abs(field.minimum), abs(field.maximum)))
                self.level.setSingleStep(max(10.**-digits, level/10))
                self.level.setValue(level)
        else:
            mo = self.wave.orbitals[self._rows[row]]
        self.decomposition.set_orbital(self._engine, mo)
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
        if key in self._surfaces:
            surface = self._surfaces.pop(key)
            self._surfaces[key] = surface
            self._show_surface(surface)
            return
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
        deriving, self._deriving = self._deriving, False
        try:
            result = future.result()
        except (ValueError, OSError, ArithmeticError, RuntimeError, MemoryError, CancelledError) as exc:
            if deriving:
                self.representation.setCurrentIndex(0)
                self.representation.setToolTip(diagnostic_text(exc))
                self.representation.setItemData(1, diagnostic_text(exc), Qt.ItemDataRole.ToolTipRole)
                self.status.setText(diagnostic_text(exc))
                return
            self.status.setText(diagnostic_text(exc))
            self._requested = None
            if self.wave is None:
                self.availability_changed.emit(False, self.status.text())
            return
        if deriving:
            self.wave = self._natural = result
            self._configure_orbitals()
        elif isinstance(result, (MoldenOrbitals, CubeData)):
            self.wave = result
            self.status.clear()
            self.availability_changed.emit(True, "")
        else:
            # Keep recent quality and orbital switches instant, bounded even for big Cube grids.
            self._surfaces[self._requested] = result
            while (len(self._surfaces) > 4 or
                   sum(len(m.vertices)+len(m.faces) for m in self._surfaces.values()) > 150_000):
                self._surfaces.pop(next(iter(self._surfaces)))
            self._show_surface(result)

    def _show_surface(self, surface):
        self.viewport.set_surface(surface)
        if surface.clipped:
            self.status.setText(tr("The surface reaches the edge of the sampled grid."))
        elif not surface.faces:
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

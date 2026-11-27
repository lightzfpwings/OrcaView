"""Show the selected orbital's atom and angular-momentum contributions in the sidebar."""

from concurrent.futures import CancelledError, ThreadPoolExecutor
from threading import Event

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from orcaview.i18n import diagnostic_text, tr
from orcaview.io.cube import CubeField

try:
    from orcaview.results.orbital_analysis import METHODS, SPACE_METHODS, CubeOrbitalAnalysis, OrbitalAnalysis
except ModuleNotFoundError as exc:
    if exc.name != "numpy":
        raise
    METHODS, SPACE_METHODS, CubeOrbitalAnalysis, OrbitalAnalysis = {}, (), None, None


class OrbitalDecomposition(QWidget):
    def __init__(self):
        super().__init__()
        self.engine = self.mo = self.result = self.future = self._cancel = None
        self._ao_group = "atom"
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orcaview-composition")
        self._timer = QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self.finish)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton(tr("Orbital decomposition"))
        self.button.setCheckable(True)
        self.button.setEnabled(False)
        self.button.setToolTip(tr("Select an orbital to view its contributions."))
        layout.addWidget(self.button)
        self.details = QWidget()
        inner = QVBoxLayout(self.details)
        inner.setContentsMargins(0, 0, 0, 0)
        self.amplitude = QCheckBox(tr("This Cube field is an orbital amplitude"))
        self.amplitude.setToolTip(tr("Integrate the square of this field within the Cube grid."))
        self.amplitude.hide()
        inner.addWidget(self.amplitude)
        form = QFormLayout()
        self.method = QComboBox()
        self.method.setAccessibleName(tr("Method"))
        for key, label in METHODS.items():
            self.method.addItem(tr(label), key)
        form.addRow(tr("Method"), self.method)
        self.group = QComboBox()
        self.group.setAccessibleName(tr("Group by"))
        for key, label in (("atom", "Atom"), ("angular", "Angular momentum (s, p, d, f…)"),
                           ("both", "Atom and angular momentum")):
            self.group.addItem(tr(label), key)
        form.addRow(tr("Group by"), self.group)
        inner.addLayout(form)
        self.table = QTableWidget()
        self.table.setAccessibleName(tr("Orbital contributions"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(65)
        inner.addWidget(self.table)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        inner.addWidget(self.status)
        layout.addWidget(self.details)
        self.details.hide()
        self.button.toggled.connect(self._toggle)
        self.amplitude.toggled.connect(self._start)
        self.method.currentIndexChanged.connect(self._update_method)
        self.group.currentIndexChanged.connect(self._group_changed)

    def _stop(self):
        self._timer.stop()
        if self._cancel is not None:
            self._cancel.set()
        if self.future is not None:
            self.future.cancel()
        self.future = self._cancel = self.result = None
        self.table.setRowCount(0)
        self.status.clear()

    def shutdown(self):
        self._stop()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def set_orbital(self, engine, mo):
        if engine is self.engine and mo is self.mo:
            return
        self.engine, self.mo = engine, mo
        enabled = engine is not None and mo is not None
        is_cube = isinstance(mo, CubeField)
        with QSignalBlocker(self.amplitude):
            self.amplitude.setChecked(False)
            self.amplitude.setVisible(is_cube)
        self.button.setEnabled(enabled)
        self.button.setToolTip("" if enabled else tr("Select an orbital to view its contributions."))
        if enabled:
            with QSignalBlocker(self.method):
                for row in range(self.method.count()):
                    key = self.method.itemData(row)
                    item = self.method.model().item(row)
                    if is_cube:
                        available = key in SPACE_METHODS
                        reason = "This method requires atomic orbital coefficients."
                    else:
                        available = key not in ("nao", "bickelhaupt") or engine.source.complete_density
                        reason = "This method needs the complete electron-density orbital set."
                    item.setEnabled(available)
                    item.setToolTip("" if available else tr(reason))
                if not self.method.model().item(self.method.currentIndex()).isEnabled():
                    self.method.setCurrentIndex(self.method.findData("becke") if is_cube else 0)
        self._update_method()

    def _toggle(self, visible):
        self.details.setVisible(visible)
        self._start()

    def _update_method(self):
        real_space = self.method.currentData() in SPACE_METHODS
        with QSignalBlocker(self.group):
            self.group.setCurrentIndex(self.group.findData("atom" if real_space else self._ao_group))
        self.group.setEnabled(not real_space)
        self.group.setToolTip(tr("Real-space methods partition the orbital density by atom.") if real_space else "")
        self._start()

    def _group_changed(self):
        if self.group.isEnabled():
            self._ao_group = self.group.currentData()
        self._display()

    def _start(self):
        self._stop()
        if self.button.isChecked() and self.mo is not None and self.engine is not None:
            if isinstance(self.mo, CubeField) and not self.amplitude.isChecked():
                self.status.setText(tr("Select orbital amplitude for a molecular-orbital Cube field."))
                return
            self.status.setText(tr("Calculating orbital contributions…"))
            self._cancel = Event()
            self.future = self._pool.submit(self.engine.composition, self.mo, self.method.currentData(), self._cancel)
            self._timer.start()

    def finish(self, *, wait=False):
        if self.future is None or (not wait and not self.future.done()):
            return
        future, self.future = self.future, None
        self._timer.stop()
        try:
            self.result = future.result()
        except (ValueError, ArithmeticError, RuntimeError, OSError, MemoryError, CancelledError) as exc:
            self.status.setText(diagnostic_text(exc))
            return
        self._display()

    def _display(self):
        if self.result is None:
            return
        values = self.result.percentages
        group = self.group.currentData()
        atoms = self.engine.source.molecule.atoms
        shells = "spdfgh"
        if group == "atom":
            headings = [tr("Atom")]
            rows = [(f"{i} {a.element}", value) for i, (a, value) in enumerate(zip(atoms, values.sum(axis=1)))]
        elif group == "angular":
            headings = [tr("Shell")]
            rows = [(shells[l], values[:, l].sum()) for l in sorted(set(self.engine.angular))]
        else:
            headings = [tr("Atom"), tr("Shell")]
            keys = sorted(set(zip(self.engine.atoms, self.engine.angular)))
            rows = [(f"{i} {atoms[i].element}", shells[l], values[i,l]) for i,l in keys]
        self.table.setColumnCount(len(headings)+1)
        self.table.setHorizontalHeaderLabels([*headings, tr("Contribution (%)")])
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, text in enumerate((*row[:-1], f"{row[-1]:.3f}")):
                self.table.setItem(i, j, QTableWidgetItem(text))
        total = f"{values.sum():.2f}"
        if isinstance(self.mo, CubeField):
            self.status.setText(tr("Field {number} · Total within grid {total}%", number=self.mo.identifier, total=total))
        else:
            self.status.setText(tr("Orbital {number} · Total {total}%", number=self.mo.number, total=total))

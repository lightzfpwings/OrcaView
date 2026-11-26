"""Inspect printed optimization-cycle energies without changing the molecular geometry."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
    QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from orcaview.gui.result_display import report_text
from orcaview.gui.result_table import enable_table_copy
from orcaview.gui.spectrum_plot import axis_ticks
from orcaview.i18n import tr


class _EnergyPlot(QWidget):
    selected = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(325, 210)
        self.setAccessibleName(tr("Optimization energy curve"))
        self.points = ()
        self.relative = False
        self.row = -1
        self.locations = []

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._draw(painter)
        finally:
            painter.end()

    def _draw(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)
        self.locations = []
        if not self.points:
            return
        energies = [p.energy for p in self.points]
        if self.relative:
            energies = [(v - energies[0]) * 1000 for v in energies]
        low, high = min(energies), max(energies)
        pad = (high - low) * .1 if high > low else max(abs(high) * 1e-9, 1.e-6)
        low, high = low - pad, high + pad
        ticks = axis_ticks(low, high, 5)
        spacing = ticks[1] - ticks[0] if len(ticks) > 1 else high - low
        decimals = min(14, max(0, 1 - math.floor(math.log10(spacing))))
        labels = [f"{v:.{decimals}f}" for v in ticks]
        fm = painter.fontMetrics()
        left = max(fm.horizontalAdvance(label) for label in labels) + 17
        area = QRectF(left, 33, self.width() - left - 36, self.height() - 86)
        center = Qt.AlignmentFlag.AlignCenter
        ink = QColor("#3b3438")
        axis = QColor("#9d969a")
        trace = QColor("#754258")
        painter.setPen(ink)
        caption = tr("Energy relative to first point (mEh)") if self.relative else tr("Energy (Eh)")
        painter.drawText(QRectF(10, 2, self.width() - 20, 26),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, caption)
        for value, label in zip(ticks, labels):
            y = area.bottom() - (value - low) / (high - low) * area.height()
            painter.setPen(QColor("#e6e1e3"))
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.setPen(ink)
            painter.drawText(QRectF(0, y - 13, left - 8, 26),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
        painter.setPen(axis)
        painter.drawLine(area.topLeft(), area.bottomLeft())
        painter.drawLine(area.bottomLeft(), area.bottomRight())
        # Give the stationary-point evaluation a distinct position and label.
        # All other x coordinates are the actual cycle numbers in the file.
        last_step = next(p.step for p in reversed(self.points) if p.step is not None)
        steps = [p.step if p.step is not None else last_step + 1 for p in self.points]
        span = steps[-1] - steps[0]
        for step, value in zip(steps, energies):
            x = area.left() + ((step - steps[0]) / span if span else .5) * area.width()
            y = area.bottom() - (value - low) / (high - low) * area.height()
            self.locations.append(QPointF(x, y))

        next_label = area.left() - 50
        for i, (point, here) in enumerate(zip(self.points, self.locations)):
            final = point.step is None
            if i and (final or steps[i] - steps[i-1] <= 1):
                style = Qt.PenStyle.DashLine if final else Qt.PenStyle.SolidLine
                painter.setPen(QPen(trace, 1.8, style))
                painter.drawLine(self.locations[i-1], here)
            if i == len(steps) - 1 or (here.x() >= next_label and self.locations[-1].x() - here.x() > 42):
                label = tr("Final") if final else str(point.step)
                width = fm.horizontalAdvance(label) + 8
                painter.setPen(ink)
                painter.drawText(QRectF(here.x() - width / 2, area.bottom() + 3, width, 22), center, label)
                next_label = here.x() + max(width, 37)
        # Draw markers after the lines so that they remain visible at flat energies.
        for point, here in zip(self.points, self.locations):
            painter.setPen(QPen(trace, 1.4))
            painter.setBrush(Qt.GlobalColor.white)
            if point.step is None:
                painter.drawPolygon(QPolygonF([here + QPointF(dx, dy) for dx, dy in
                                                ((0, -5), (5, 0), (0, 5), (-5, 0))]))
            else:
                painter.drawEllipse(here, 3.5, 3.5)
        if 0 <= self.row < len(self.locations):
            painter.setPen(QPen(QColor("#236e83"), 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.locations[self.row], 7, 7)
        painter.setPen(ink)
        painter.drawText(QRectF(area.left(), area.bottom() + 25, area.width(), 25), center, tr("Optimization step"))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.locations:
            distances = [(pos - event.position()).manhattanLength() for pos in self.locations]
            closest = distances.index(min(distances))
            if distances[closest] < 15:
                self.selected.emit(closest)
                return
        super().mousePressEvent(event)


class OptimizationCurveDialog(QDialog):
    def __init__(self, runs, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Optimization energy curve"))
        self.resize(755, 550)
        self.runs = runs
        layout = QVBoxLayout(self)
        options = QHBoxLayout()
        self.run_choice = QComboBox()
        self.run_choice.setAccessibleName(tr("Optimization run"))
        for i, run in enumerate(runs, 1):
            label = tr("Optimization run {value}", value=i)
            if run.job:
                label += " · " + report_text(run.job)
            self.run_choice.addItem(label)
        self.run_choice.setVisible(len(runs) > 1)
        options.addWidget(self.run_choice)
        options.addStretch(1)
        self.units = QComboBox()
        self.units.setAccessibleName(tr("Energy scale"))
        self.units.addItems([tr("Energy (Eh)"), tr("Energy relative to first point (mEh)")])
        options.addWidget(self.units)
        layout.addLayout(options)
        self.plot = _EnergyPlot()
        layout.addWidget(self.plot, 3)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels((tr("Optimization step"), tr("Energy (Eh)"),
                                              tr("ΔE from first (mEh)"), tr("Source line number")))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        enable_table_copy(self.table)
        layout.addWidget(self.table, 2)
        self.warning = QLabel(tr("Wavefunction not fully converged"))
        layout.addWidget(self.warning)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.plot.selected.connect(self.table.selectRow)
        self.table.currentCellChanged.connect(self._select_point)
        self.units.currentIndexChanged.connect(self._set_scale)
        self.run_choice.currentIndexChanged.connect(self._set_run)
        self._set_run(self.run_choice.currentIndex())

    def _set_scale(self, index):
        self.plot.relative = bool(index)
        self.plot.update()

    def _set_run(self, index):
        points = self.runs[index].points if index >= 0 else ()
        self.plot.points = points
        self.table.setRowCount(len(points))
        for i, point in enumerate(points):
            step = tr("Final") if point.step is None else str(point.step)
            if point.scf_warning:
                step += " *"
            relative = (point.energy - points[0].energy) * 1000
            for col, value in enumerate((step, f"{point.energy:.15g}", f"{relative:.10g}", str(point.line))):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, col, item)
        self.table.selectRow(len(points) - 1)
        self._select_point(self.table.currentRow())

    def _select_point(self, row):
        self.plot.row = row
        self.warning.setVisible(0 <= row < len(self.plot.points) and self.plot.points[row].scf_warning)
        self.plot.update()

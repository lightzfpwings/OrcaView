"""Signed isotropic J values by nucleus pair, shared by preview, dialog and image exports."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from orcaview.gui.spectrum_plot import axis_ticks, choose_spectrum_image
from orcaview.gui.spectrum_preview_export import capture_chart
from orcaview.i18n import tr


def draw_pairs(painter, area, pairs, *, grid=False, compact=False):
    """Draw every finite pair in table order. Thin categorical labels when space is limited."""
    if not pairs or area.width() <= 0 or area.height() <= 0:
        return
    unit = max(abs(value) for _, _, value in pairs) or 1.
    low = min(0., min(v for _, _, v in pairs) / unit)
    high = max(0., max(v for _, _, v in pairs) / unit)
    if high == low:
        low, high = -1., 1.
    span = high - low
    lo, hi = low - .12 * span, high + .12 * span

    def y_at(fraction):
        return area.bottom() - (fraction - lo) / (hi - lo) * area.height()

    center = y_at(0)
    if not compact:
        bottom, top = lo * unit, hi * unit
        ticks = axis_ticks(bottom if math.isfinite(bottom) else low * unit,
                          top if math.isfinite(top) else high * unit, 5)
        for tick in ticks:
            y = y_at(tick / unit)
            if grid and tick:
                painter.setPen(QPen(QColor("#e8e2e3"), 1))
                painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.setPen(QColor("#655e61"))
            painter.drawText(QRectF(area.left() - 67, y - 10, 59, 20),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{tick:.5g}")
    painter.setPen(QPen(QColor("#9a9396"), 1))
    painter.drawLine(QPointF(area.left(), center), QPointF(area.right(), center))
    spacing = area.width() / len(pairs)
    width = min(38., .55 * spacing)
    labels = [f"{left} – {right}" for left, right, _ in pairs] if not compact else []
    if labels:
        metrics = painter.fontMetrics()
        label_width = max(metrics.horizontalAdvance(label) for label in labels) + 10
        step = max(1, math.ceil(label_width / spacing))
    for i, (_, _, value) in enumerate(pairs):
        x = area.left() + (i + .5) * spacing
        y = y_at(value / unit)
        color = QColor("#39736d" if value < 0 else "#904359")
        if value:
            painter.fillRect(QRectF(x - width / 2, min(y, center), width, abs(y - center)), color)
        else:
            painter.setPen(QPen(color, 1.5))
            painter.drawLine(QPointF(x - width / 2, y), QPointF(x + width / 2, y))
        if labels and i % step == 0:
            painter.setPen(QColor("#4e484c"))
            cell = QRectF(x - label_width / 2, area.bottom() + 5, label_width, 22)
            painter.drawText(cell, Qt.AlignmentFlag.AlignCenter, labels[i])
            if spacing >= 62 and value:
                painter.drawText(QRectF(x - spacing / 2, y - 20 if value > 0 else y + 1, spacing, 18),
                                 Qt.AlignmentFlag.AlignCenter, f"{value:.6g}")


class CouplingFigure(QWidget):
    def __init__(self, title, pairs):
        super().__init__()
        self.title, self.pairs = title, pairs
        self.grid = True
        self.setMinimumSize(300, 240)

    def draw(self, painter, bounds, *, grid=None, background=True):
        if background:
            painter.fillRect(bounds, Qt.GlobalColor.white)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self.font()
        font.setPixelSize(17)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#352e33"))
        painter.drawText(bounds.adjusted(12, 7, -12, -bounds.height() + 51), Qt.AlignmentFlag.AlignCenter, self.title)
        font.setBold(False)
        font.setPixelSize(12)
        painter.setFont(font)
        area = bounds.adjusted(78, 79, -40, -74)
        painter.drawText(QPointF(area.left(), area.top() - 12), tr("Isotropic J (Hz)"))
        draw_pairs(painter, area, self.pairs, grid=self.grid if grid is None else grid)
        painter.drawText(bounds.adjusted(30, bounds.height() - 40, -30, -5), Qt.AlignmentFlag.AlignCenter,
                         tr("Nucleus pair (ORCA indices)"))

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self.draw(painter, QRectF(self.rect()))
        finally:
            painter.end()

    def capture(self, grid=None, size=None):
        return capture_chart(self.draw, grid, size)

    def export_image(self, parent):
        choose_spectrum_image(parent, self.title, self.capture, self.grid)


class CouplingPlotDialog(QDialog):
    def __init__(self, title, pairs, parent):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 480)
        self.figure = CouplingFigure(title, pairs)
        layout = QVBoxLayout(self)
        layout.addWidget(self.figure, 1)
        actions = QHBoxLayout()
        layout.addLayout(actions)
        grid = QCheckBox(tr("Grid lines"))
        grid.setChecked(True)
        grid.toggled.connect(self.set_grid)
        actions.addWidget(grid)
        actions.addStretch()
        export = QPushButton(tr("Export image…"))
        export.clicked.connect(lambda: self.figure.export_image(self))
        actions.addWidget(export)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        actions.addWidget(close)

    def set_grid(self, enabled):
        self.figure.grid = enabled
        self.figure.update()

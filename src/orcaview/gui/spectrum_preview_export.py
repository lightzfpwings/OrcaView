"""Capture exportable spectroscopy plots and numerical previews as vector drawings."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from orcaview.gui.result_display import report_text
from orcaview.gui.structure_export import capture_drawing, save_structure_image
from orcaview.i18n import tr


def capture_spectrum_figure(figure, grid=None, size=None):
    """Freeze the current profile and styling with an optional export-only grid override."""
    if figure.error or figure.profile is None:
        raise ValueError(figure.error or tr("No plottable values"))
    return capture_chart(figure.draw, grid, size)


def capture_chart(draw, grid=None, size=None):
    if size is None:
        size = QSize(900, 550)
    bounds = QRectF(0, 0, size.width(), size.height())
    return capture_drawing(size, lambda painter: draw(painter, bounds, grid=grid, background=False))


def save_spectrum_png(filename, figure):
    """Write the standard 2× spectrum figure for callers without an export dialog."""
    snapshot = figure.capture()
    save_structure_image(snapshot, filename, "png", 1800, 1100, scale=2)


def _draw_mode_positions(painter, area, positions, x_unit, grid):
    left, right, y = area.left(), area.right(), area.center().y()
    low, high = min(positions), max(positions)
    # Large finite inputs can overflow when subtracting the range endpoints.
    divisor = 2 if not math.isfinite(high - low) else 1
    start, stop = low / divisor, high / divisor
    ticks = (0, .25, .5, .75, 1) if start != stop else (.5,)
    if grid:
        painter.setPen(QPen(QColor("#e8e2e3"), 1))
        for fraction in ticks:
            x = left + fraction * area.width()
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
    painter.setPen(QPen(QColor("#a79da1"), 1))
    painter.drawLine(QPointF(left, y), QPointF(right, y))
    painter.setPen(QPen(QColor("#904359"), 1.6))
    for frequency in positions:
        fraction = (frequency / divisor - start) / (stop - start) if start != stop else .5
        x = left + fraction * (right - left)
        painter.drawLine(QPointF(x, y - 24), QPointF(x, y + 24))
    painter.setPen(QColor("#6d6467"))
    for fraction in ticks:
        value = (1 - fraction) * low + fraction * high if start != stop else low
        x = left + fraction * (right - left)
        painter.drawText(QRectF(x - 65, area.bottom() + 8, 130, 26), Qt.AlignmentFlag.AlignCenter, f"{value:.5g}")
    painter.setPen(QColor("#352e33"))
    painter.drawText(QRectF(left, area.bottom() + 51, right - left, 26), Qt.AlignmentFlag.AlignCenter,
                     f"{tr('Wavenumber')} ({x_unit})")


def capture_preview(table, samples, y_caption, x_unit, font, grid=None, size=None):
    """Freeze the standalone vibrational mode positions displayed in the sidebar."""
    positions = [x for x, _ in samples]
    if not positions:
        raise ValueError(tr("No plottable values"))
    if size is None:
        size = QSize(900, 550)
    width, height = size.width(), size.height()
    left, content_width = 82, width - 164

    def draw(painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        face = QFont(font)
        face.setPixelSize(22)
        face.setBold(True)
        painter.setFont(face)
        painter.setPen(QColor("#352e33"))
        painter.drawText(QRectF(35, 20, width - 70, 80), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         report_text(table.title))
        face.setBold(False)
        face.setPixelSize(18)
        painter.setFont(face)
        painter.setPen(QColor("#6d6467"))
        painter.drawText(QRectF(left, height * .2, content_width, 48), Qt.AlignmentFlag.AlignVCenter, y_caption)
        area = QRectF(left, height * .39, content_width, height * .24)
        _draw_mode_positions(painter, area, positions, x_unit, grid)

    return capture_drawing(size, draw)

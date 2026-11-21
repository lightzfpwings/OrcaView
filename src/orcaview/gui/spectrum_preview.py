"""Compact, unbroadened previews of the values printed in an ORCA spectrum."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from orcaview.gui import typography
from orcaview.i18n import tr
from orcaview.gui.result_display import report_text

from orcaview.orca.log_spectra import SpectrumTable


_INK = QColor("#372F2D")
_MUTED = QColor("#70635F")
_BORDER = QColor("#DDD5CB")
_POSITIVE = QColor("#904359")
_NEGATIVE = QColor("#39736D")
_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_CENTER = Qt.AlignmentFlag.AlignCenter

# The IR intensity column differs between historical and current printed layouts.
_AXES = {
    "ir": ("波数", ("红外强度", "T²（km/mol）"), "强度 / km·mol⁻¹", "cm⁻¹", True),
    "raman": ("波数", ("拉曼活性",), "拉曼活性 / Å⁴·amu⁻¹", "cm⁻¹", False),
    "uvvis": ("波长", ("振子强度",), "振子强度", "nm", False),
    "cd": ("波长", ("旋光强度",), "旋光强度 / 10⁻⁴⁰ cgs", "nm", False),
    "vibrations": ("波数", (), "模式位置", "cm⁻¹", False),
}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _format(value, digits=6):
    return format(value, f".{digits}g") if value else "0"


def _column(columns, prefixes):
    return next((i for i, name in enumerate(columns) if name.startswith(prefixes)), None)


def _fraction(value, low, high):
    if high == low:
        return 0.5
    span = high - low
    if math.isinf(span):
        return (value / 2 - low / 2) / (high / 2 - low / 2)
    return (value - low) / span


class SpectrumPreview(QWidget):
    """Show the selected table's actual lines or isotropic NMR values in the sidebar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("spectrumPreview")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(102)
        self._table = None
        self._samples = ()
        self._values = ()
        self._y_caption = ""
        self._x_unit = ""
        self._decreasing = False
        self.hide()

    def sizeHint(self):
        return QSize(200, 102)

    def set_spectrum(self, table: SpectrumTable | None):
        self._table = table
        self._samples = ()
        self._values = ()
        self._y_caption = ""
        self._x_unit = ""
        self._decreasing = False
        if table is None:
            self.setAccessibleName("")
            self.setAccessibleDescription("")
            self.setToolTip("")
            self.hide()
            return

        detail = []
        if table.kind in _AXES:
            x_label, y_labels, self._y_caption, self._x_unit, self._decreasing = _AXES[table.kind]
            self._y_caption = tr(self._y_caption)
            x = _column(table.columns, x_label)
            y = _column(table.columns, y_labels)
            if x is not None and (y is not None or not y_labels):
                self._samples = tuple(
                    (row[x], row[y] if y is not None else None) for row in table.rows
                    if _number(row[x]) and (y is None or _number(row[y]))
                )
                for abscissa, strength in self._samples[:3]:
                    value = f"{_format(abscissa)} {self._x_unit}"
                    if strength is not None:
                        value += f"   {_format(strength)}"
                    detail.append(value)
        elif table.kind == "nmr":
            j = _column(table.columns, "各向同性 J")
            value_index = j if j is not None else _column(table.columns, "各向同性屏蔽")
            if value_index is not None:
                unit = "Hz" if j is not None else "ppm"
                self._y_caption = tr("各向同性 J / {unit}", unit=unit) if j is not None else tr("各向同性屏蔽 / {unit}", unit=unit)
                rows = []
                for row in table.rows[:3]:
                    nucleus = f"{row[0]} – {row[1]}" if j is not None else f"{row[0]} {row[1]}"
                    value = f"{_format(row[value_index])} {unit}" if _number(row[value_index]) else "—"
                    rows.append((nucleus, value))
                    detail.append(f"{nucleus}   {value}")
                self._values = tuple(rows)
        self.setAccessibleName(report_text(table.title))
        description = "\n".join([self._y_caption, *detail]).strip()
        self.setAccessibleDescription(description)
        self.setToolTip("\n".join(filter(None, (self.accessibleName(), description))))
        self.show()
        self.update()

    def paintEvent(self, _event):
        if self._table is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(_BORDER, 1))
        painter.setBrush(QColor("#FFFDF9"))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        width = max(0, self.width() - 16)
        font = self.font()
        font.setPixelSize(12)
        font.setBold(not typography.WINDOWS)
        painter.setFont(font)
        painter.setPen(_INK)
        title = painter.fontMetrics().elidedText(self.accessibleName(), Qt.TextElideMode.ElideMiddle, width)
        painter.drawText(QRectF(8, 3, width, 18), _LEFT, title)
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(_MUTED)
        caption = painter.fontMetrics().elidedText(self._y_caption, Qt.TextElideMode.ElideRight, width)
        painter.drawText(QRectF(8, 22, width, 16), _LEFT, caption)
        if self._values:
            for i, (nucleus, value) in enumerate(self._values):
                rect = QRectF(8, 40 + 18 * i, width, 18)
                value_width = painter.fontMetrics().horizontalAdvance(value)
                label = painter.fontMetrics().elidedText(nucleus, Qt.TextElideMode.ElideRight, max(0, width - value_width - 8))
                painter.setPen(_INK)
                painter.drawText(rect, _LEFT, label)
                painter.setPen(_POSITIVE)
                painter.drawText(rect, _RIGHT, value)
        elif self._samples:
            self._draw_spectrum(painter)
        else:
            painter.drawText(QRectF(8, 43, width, 35), _CENTER, tr("无可绘制的数值"))

    def _draw_spectrum(self, painter):
        positions_only = self._table.kind == "vibrations"
        xmin = min(x for x, _ in self._samples)
        xmax = max(x for x, _ in self._samples)
        if positions_only:
            ymin = ymax = 0
            left = 12.0
        else:
            ymin = min(0, min(y for _, y in self._samples))
            ymax = max(0, max(y for _, y in self._samples))
            label_width = max(painter.fontMetrics().horizontalAdvance(_format(v, 3)) for v in (ymin, ymax))
            left = min(self.width() * 0.36, label_width + 12)
        right = max(left, self.width() - 12.0)
        top, bottom = 46.0, self.height() - 25.0
        baseline = bottom - (bottom - top) * _fraction(0, ymin, ymax)
        painter.setPen(QPen(_BORDER, 1))
        painter.drawLine(QPointF(left, baseline), QPointF(right, baseline))
        if not positions_only:
            painter.drawLine(QPointF(left, top), QPointF(left, bottom))
            ticks = [(ymax, top), (ymin, bottom)] if ymin != ymax else [(0, baseline)]
            if ymin < 0 < ymax and min(bottom - baseline, baseline - top) >= 12:
                ticks.append((0, baseline))
            painter.setPen(_MUTED)
            for value, y in ticks:
                painter.drawText(QRectF(2, y - 8, left - 6, 16), _RIGHT, _format(value, 3))
        for x, y in self._samples:
            fraction = _fraction(x, xmin, xmax)
            if self._decreasing:
                fraction = 1 - fraction
            px = left + fraction * (right - left)
            color = _NEGATIVE if y is not None and y < 0 else _POSITIVE
            painter.setPen(QPen(color, 1.6))
            if positions_only:
                painter.drawLine(QPointF(px, baseline - 4), QPointF(px, baseline + 4))
            elif y == 0:
                painter.setBrush(color)
                painter.drawEllipse(QPointF(px, baseline), 1.8, 1.8)
            else:
                tip = bottom - (bottom - top) * _fraction(y, ymin, ymax)
                painter.drawLine(QPointF(px, baseline), QPointF(px, tip))

        # Put the unit between ascending/descending endpoints, or next to a single position.
        painter.setPen(_MUTED)
        axis = QRectF(8, self.height() - 20, max(0, self.width() - 16), 16)
        if xmin == xmax:
            painter.drawText(axis, _CENTER, f"{_format(xmin)} {self._x_unit}")
            return
        first, last = (xmax, xmin) if self._decreasing else (xmin, xmax)
        start, end = _format(first), _format(last)
        metrics = painter.fontMetrics()
        if metrics.horizontalAdvance(start + "  " + self._x_unit + "  " + end) > axis.width():
            start, end = _format(first, 3), _format(last, 3)
        if metrics.horizontalAdvance(start + "  " + self._x_unit + "  " + end) > axis.width():
            direction = "←" if self._decreasing else "→"
            painter.drawText(axis, _CENTER, f"{direction} {self._x_unit}")
            return
        painter.drawText(axis, _LEFT, start)
        painter.drawText(axis, _RIGHT, end)
        middle = axis.adjusted(metrics.horizontalAdvance(start) + 3, 0, -metrics.horizontalAdvance(end) - 3, 0)
        painter.drawText(middle, _CENTER, self._x_unit)

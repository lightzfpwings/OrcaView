"""Live sidebar spectra and the entry point to their detailed plot settings."""

from __future__ import annotations

import math
import unicodedata

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QSizePolicy, QVBoxLayout, QWidget

from orcaview.gui import typography
from orcaview.gui.result_display import report_text
from orcaview.gui.spectrum_plot import PlotProfile, PlotStyle, ProfileSampler, SpectrumPlotDialog, draw_traces
from orcaview.i18n import tr
from orcaview.orca.log_spectra import SpectrumTable
from orcaview.results.broadening import stick_spectrum


_INK = QColor("#372F2D")
_MUTED = QColor("#70635F")
_BORDER = QColor("#DDD5CB")
_POSITIVE = QColor("#904359")
_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_CENTER = Qt.AlignmentFlag.AlignCenter


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _format(value, digits=6):
    return format(value, f".{digits}g") if value else "0"


class SpectrumPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("spectrumPreview")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 104, 0, 0)
        layout.setSpacing(0)
        self.plot_button = QPushButton(tr("Plot settings…"))
        self.plot_button.setObjectName("openSpectrumPlot")
        self.plot_button.clicked.connect(self.open_plot)
        layout.addWidget(self.plot_button)
        self._sampler = ProfileSampler(self)
        self._sampler.ready.connect(self._profile_ready)
        self._table = self._profile = self._style = self._dialog = None
        self._samples = self._values = ()
        self._y_caption = self._x_unit = self._error = ""
        self.hide()

    def sizeHint(self):
        return QSize(200, 104 + self.plot_button.sizeHint().height() if self._profile else 102)

    def set_spectrum(self, table: SpectrumTable | None):
        if table is self._table and table is not None:
            return
        reopen = self._dialog is not None and self._dialog.isVisible()
        if self._dialog is not None:
            self._dialog.close()
            self._dialog.deleteLater()
            self._dialog = None
        self._sampler.cancel()
        self._table, self._profile, self._style = table, None, None
        self._samples = self._values = ()
        self._y_caption = self._x_unit = self._error = ""
        self.plot_button.hide()
        if table is None:
            self.setAccessibleName("")
            self.setAccessibleDescription("")
            self.setToolTip("")
            self.hide()
            return

        spectrum = stick_spectrum(table)
        if spectrum is not None:
            try:
                self._profile = PlotProfile.setup(spectrum, "gaussian", spectrum.default_fwhm, .5)
            except (ValueError, OverflowError) as error:
                self._error = tr(str(error))
            else:
                self._style = PlotStyle(spectrum.reversed_axis)
                self._samples = spectrum.peaks
                self._x_unit, self._y_caption = spectrum.unit, tr(spectrum.y_label)
                self.plot_button.show()
                self._error = tr("Calculating spectrum…")
                self._sampler.request(self._profile)
        elif table.kind == "vibrations":
            self._samples = tuple((row[1], None) for row in table.rows if len(row) >= 2 and _number(row[1]))
            self._x_unit, self._y_caption = "cm⁻¹", tr("Mode positions")
        elif table.kind == "nmr" and len(table.columns) >= 3:
            coupling = "Hz" in table.columns[2]
            self._x_unit = "Hz" if coupling else "ppm"
            label = unicodedata.normalize("NFKC", report_text(table.columns[2])).split("(")[0].strip()
            self._y_caption = f"{label} / {self._x_unit}"
            rows = []
            for row in table.rows[:3]:
                if len(row) < 3:
                    continue
                nucleus = f"{row[0]} – {row[1]}" if coupling else f"{row[0]} {row[1]}"
                value = f"{_format(row[2])} {self._x_unit}" if _number(row[2]) else "—"
                rows.append((nucleus, value))
            self._values = tuple(rows)
        self.setAccessibleName(report_text(table.title))
        self._describe()
        self.setFixedHeight(self.sizeHint().height())
        self.show()
        self.update()
        if reopen and self._profile:
            self.open_plot()

    def _describe(self):
        detail = [f"{name}   {value}" for name, value in self._values]
        for x, y in self._samples[:3]:
            detail.append(f"{_format(x)} {self._x_unit}" + (f"   {_format(y)}" if y is not None else ""))
        description = "\n".join(filter(None, (self._y_caption, *detail, self._error)))
        self.setAccessibleDescription(description)
        self.setToolTip("\n".join(filter(None, (self.accessibleName(), description))))

    def open_plot(self):
        if self._profile is None:
            return
        if self._dialog is None:
            self._dialog = SpectrumPlotDialog(self._table, self._profile, self._style, self._sampler, self)
            self._dialog.set_profile(self._profile, self._error)
            self._dialog.changed.connect(self._plot_changed)
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    def _profile_ready(self, profile, error):
        self._profile, self._error = profile, error
        self._samples, self._x_unit = profile.source.peaks, profile.source.unit
        self._y_caption = tr("Relative height") if self._style.normalized else tr(profile.source.y_label)
        self._describe()
        if self._dialog is not None:
            self._dialog.set_profile(profile, error)
        self.update()

    def _plot_changed(self, profile, style):
        self._profile, self._style = profile, style
        self._x_unit, self._samples = profile.source.unit, profile.source.peaks
        self._y_caption = tr("Relative height") if style.normalized else tr(profile.source.y_label)
        self._describe()
        self.update()

    def paintEvent(self, event):
        if self._table is None:
            return
        painter = QPainter(self)
        try:
            self._draw(painter)
        finally:
            painter.end()

    def _draw(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(_BORDER, 1))
        painter.setBrush(QColor("#FFFDF9"))
        painter.drawRoundedRect(QRectF(.5, .5, self.width() - 1, 101), 5, 5)
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
            return
        if not self._samples:
            painter.drawText(QRectF(8, 43, width, 35), _CENTER, self._error or tr("No plottable values"))
            return
        if self._profile:
            xmin, xmax = self._profile.limits
            rect = QRectF(10, 46, max(0, self.width() - 20), 31)
            draw_traces(painter, rect, self._profile, self._style, compact=True)
            if self._style.reverse:
                xmin, xmax = xmax, xmin
        else:
            xmin = min(x for x, _ in self._samples)
            xmax = max(x for x, _ in self._samples)
            painter.setPen(QPen(_BORDER, 1))
            painter.drawLine(QPointF(10, 63), QPointF(self.width() - 10, 63))
            painter.setPen(QPen(_POSITIVE, 1.6))
            for x, _ in self._samples:
                t = .5 if xmin == xmax else (x - xmin) / (xmax - xmin)
                px = 10 + t * (self.width() - 20)
                painter.drawLine(QPointF(px, 59), QPointF(px, 67))
        axis = QRectF(8, 82, width, 16)
        painter.setPen(_MUTED)
        if xmin == xmax:
            painter.drawText(axis, _CENTER, f"{_format(xmin)} {self._x_unit}")
            return
        start, end = _format(xmin, 4), _format(xmax, 4)
        metrics = painter.fontMetrics()
        if metrics.horizontalAdvance(start + "   " + self._x_unit + "   " + end) > width:
            painter.drawText(axis, _CENTER, ("← " if xmin > xmax else "→ ") + self._x_unit)
            return
        painter.drawText(axis, _LEFT, start)
        painter.drawText(axis, _RIGHT, end)
        painter.drawText(axis.adjusted(metrics.horizontalAdvance(start) + 3, 0, -metrics.horizontalAdvance(end) - 3, 0),
                         _CENTER, self._x_unit)

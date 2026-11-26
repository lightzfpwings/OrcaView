"""Live sidebar spectra and the entry point to their detailed plot settings."""

from __future__ import annotations

from functools import partial
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QSizePolicy, QVBoxLayout, QWidget

from orcaview.gui import typography
from orcaview.gui.nmr_couplings import CouplingFigure, CouplingPlotDialog, draw_pairs
from orcaview.gui.result_display import report_text
from orcaview.gui.spectrum_plot import (
    PlotProfile, PlotStyle, ProfileSampler, SpectrumFigure, SpectrumPlotDialog,
    choose_spectrum_image, draw_traces, plot_title,
)
from orcaview.gui.spectrum_preview_export import capture_preview
from orcaview.i18n import tr
from orcaview.orca.log_spectra import SpectrumTable
from orcaview.results.nmr import ShieldingSpectrum, coupling_pairs, default_shape, plot_source


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
        layout.setSpacing(2)
        self.plot_button = QPushButton(tr("Plot settings…"))
        self.plot_button.setObjectName("openSpectrumPlot")
        self.plot_button.clicked.connect(self.open_plot)
        layout.addWidget(self.plot_button)
        self.export_image_button = QPushButton(tr("Export image…"))
        self.export_image_button.setObjectName("exportSpectrumImage")
        self.export_image_button.clicked.connect(self.export_image)
        layout.addWidget(self.export_image_button)
        self._sampler = ProfileSampler(self)
        self._sampler.ready.connect(self._profile_ready)
        self._table = self._profile = self._style = self._dialog = None
        self._samples = self._pairs = ()
        self._y_caption = self._x_unit = self._error = ""
        self.hide()

    def sizeHint(self):
        return QSize(200, max(102, self.layout().sizeHint().height()))

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
        self._samples = self._pairs = ()
        self._y_caption = self._x_unit = self._error = ""
        self.plot_button.hide()
        self.export_image_button.hide()
        self.export_image_button.setEnabled(False)
        if table is None:
            self.setAccessibleName("")
            self.setAccessibleDescription("")
            self.setToolTip("")
            self.hide()
            return

        self.setAccessibleName(report_text(table.title))
        spectrum = plot_source(table)
        if spectrum is not None:
            try:
                self._profile = PlotProfile.setup(spectrum, default_shape(spectrum), spectrum.default_fwhm, .5)
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
        elif table.kind == "nmr":
            self._pairs = coupling_pairs(table)
            if self._pairs:
                self._y_caption = tr("Isotropic J (Hz)")
                self.plot_button.show()
        self.export_image_button.setVisible(bool(self._profile or self._samples or self._pairs))
        self.export_image_button.setEnabled(not self._error and bool(self._samples or self._pairs))
        self._describe()
        self.setFixedHeight(self.sizeHint().height())
        self.show()
        self.update()
        if reopen and (self._profile or self._pairs):
            self.open_plot()

    def _describe(self):
        detail = [f"{a} – {b}   {_format(value)} Hz" for a, b, value in self._pairs[:3]]
        for x, y in self._samples[:3]:
            detail.append(f"{_format(x)} {self._x_unit}" + (f"   {_format(y)}" if y is not None else ""))
        if self._profile and isinstance(self._profile.source, ShieldingSpectrum):
            detail.append(f"{tr('Source table')} · {tr('Isotropic shielding')} / ppm")
            for row in self._table.rows[:3]:
                if len(row) >= 3 and _number(row[2]):
                    detail.append(f"{row[0]} {row[1]}   {_format(row[2])} ppm")
        description = "\n".join(filter(None, (self._y_caption, *detail, self._error)))
        self.setAccessibleDescription(description)
        self.setToolTip("\n".join(filter(None, (self.accessibleName(), description))))

    def open_plot(self):
        if self._profile is None and not self._pairs:
            return
        if self._dialog is None:
            if self._pairs:
                self._dialog = CouplingPlotDialog(self.accessibleName(), self._pairs, self)
            else:
                self._dialog = SpectrumPlotDialog(self._table, self._profile, self._style, self._sampler, self)
                self._dialog.set_profile(self._profile, self._error)
                self._dialog.changed.connect(self._plot_changed)
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    def _profile_ready(self, profile, error):
        if self._dialog is not None:
            self._dialog.set_profile(profile, error)
        else:
            self._plot_changed(profile, self._style, error)

    def _plot_changed(self, profile, style, error):
        self._profile, self._style, self._error = profile, style, error
        self._x_unit, self._samples = profile.source.unit, profile.source.peaks
        self._y_caption = tr("Relative height") if style.normalized else tr(profile.source.y_label)
        if isinstance(profile.source, ShieldingSpectrum):
            self.setAccessibleName(plot_title(report_text(self._table.title), profile.source))
            self._y_caption = f"{tr(profile.source.x_label)} (ppm) · {self._y_caption}"
        self.export_image_button.setEnabled(not error)
        self._describe()
        self.update()

    def export_image(self):
        if self._table is None or not self.export_image_button.isEnabled():
            return
        if self._pairs:
            figure = self._dialog.figure if self._dialog else CouplingFigure(self.accessibleName(), self._pairs)
            figure.export_image(self)
            return
        if self._profile is None:
            capture = partial(capture_preview, self._table, self._samples,
                              self._y_caption, self._x_unit, self.font())
            choose_spectrum_image(self, self.accessibleName(), capture, False)
            return
        if self._dialog is None:
            figure = SpectrumFigure()
            figure.setFont(self.font())
            figure.title = report_text(self._table.title)
            figure.profile, figure.style = self._profile, self._style
        else:
            figure = self._dialog.figure
        figure.export_image(self)

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
        if self._pairs:
            draw_pairs(painter, QRectF(10, 40, max(0, self.width() - 20), 37), self._pairs, compact=True)
            painter.setPen(_MUTED)
            painter.drawText(QRectF(6, 81, width + 4, 17), _CENTER,
                             tr("Nucleus pairs ({count})", count=len(self._pairs)))
            return
        if not self._samples or self._error:
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

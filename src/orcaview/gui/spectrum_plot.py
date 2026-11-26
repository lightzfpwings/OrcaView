"""Adjust and export the line profile of a printed stick spectrum."""

from __future__ import annotations

from functools import partial
import math

from PySide6.QtCore import QIODevice, QObject, QPointF, QRectF, QRunnable, QSaveFile, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from orcaview.gui.file_dialogs import suggested_file
from orcaview.gui.result_display import report_text
from orcaview.gui.spectrum_image_dialog import SpectrumImageDialog
from orcaview.gui.spectrum_preview_export import capture_spectrum_figure, save_spectrum_png
from orcaview.i18n import tr
from orcaview.results.broadening import stick_spectrum
from orcaview.results.spectrum_profile import PlotProfile, PlotStyle, spectrum_csv


_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_CENTER = Qt.AlignmentFlag.AlignCenter
_INK = QColor("#352e33")
_MUTED = QColor("#6d6467")
_AXIS = QColor("#a79da1")
_GRID = QColor("#e8e2e3")
_POSITIVE = "#904359"
_NEGATIVE = "#39736d"
_SHAPES = (("Gaussian", "gaussian"), ("Lorentzian", "lorentzian"), ("Pseudo-Voigt", "pseudo-voigt"))


def _fmt(value, precision=5):
    return f"{value:.{precision}g}" if value else "0"


class _Completion(QObject):
    done = Signal(object, object, str)


class _SampleJob(QRunnable):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.completion = _Completion()

    def run(self):
        p = self.settings
        try:
            profile = p.sampled()
        except (ValueError, ArithmeticError) as exc:
            self.completion.done.emit(self, p, str(exc))
        else:
            self.completion.done.emit(self, profile, "")


class ProfileSampler(QObject):
    """Coalesce changes to expensive plots and ignore superseded calculations."""

    ready = Signal(object, str)

    def __init__(self, parent):
        super().__init__(parent)
        self.running = self.latest = None

    def cancel(self):
        self.latest = None

    def request(self, settings):
        self.latest = job = _SampleJob(settings)
        job.completion.done.connect(self._finished)
        if len(settings.source.peaks) < 128:
            job.run()
        elif self.running is None:
            self.running = job
            QThreadPool.globalInstance().start(job)

    @Slot(object, object, str)
    def _finished(self, job, profile, error):
        if self.running is job:
            self.running = None
        if self.latest is job:
            self.latest = None
            self.ready.emit(profile, tr(error) if error else "")
        elif self.running is None and self.latest is not None:
            self.running = self.latest
            QThreadPool.globalInstance().start(self.running)


def _pen(color, width):
    return QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _axis_ticks(low, high, count):
    target = high / count - low / count
    if target <= 0 or not math.isfinite(target):
        return [low, high]
    magnitude = 10.0 ** math.floor(math.log10(target))
    if not magnitude:
        return [low, high]
    multiplier = min((1, 2, 2.5, 5, 10), key=lambda m: abs(m - target / magnitude))
    step = multiplier * magnitude
    if not math.isfinite(step):
        return [low, high]
    start = math.ceil(low / step)
    stop = math.floor(high / step)
    ticks = [i * step for i in range(start, stop + 1)]
    return ticks or [low, high]


def draw_traces(painter, rect, profile, style, *, compact=False, grid=None):
    """Draw the same sampled envelope and source sticks on every output device."""
    xmin, xmax = profile.limits
    scale = profile.scale(style)
    sticks = [(x, y) for x, y in profile.source.peaks if xmin <= x <= xmax]
    ymin = ymax = 0.0
    for samples in (sticks if style.layers != "curve" else (), profile.curve if style.layers != "sticks" else ()):
        for _, y in samples:
            ymin = min(y, ymin)
            ymax = max(y, ymax)
    if ymin == ymax:
        ymax = 1.0
    if not compact:
        extent = ymax - ymin
        if ymin < 0:
            ymin -= .06 * extent
        if ymax > 0:
            ymax += .06 * extent

    def px(x):
        t = (x - xmin) / (xmax - xmin)
        return rect.left() + (1 - t if style.reverse else t) * rect.width()

    def py(y):
        return rect.bottom() - (y - ymin) / (ymax - ymin) * rect.height()

    baseline = py(0)
    painter.save()
    painter.setClipRect(rect.adjusted(-2, -2, 2, 2), Qt.ClipOperation.IntersectClip)
    show_grid = style.grid if grid is None else grid
    if show_grid and not compact:
        painter.setPen(_pen(_GRID, .8))
        for value in _axis_ticks(ymin / scale, ymax / scale, 4):
            y = py(value * scale)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        for value in _axis_ticks(xmin, xmax, 5 if rect.width() > 400 else 3):
            x = px(value)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
    painter.setPen(_pen(_AXIS, 1))
    painter.drawLine(QPointF(rect.left(), baseline), QPointF(rect.right(), baseline))
    if style.layers != "curve":
        for x, y in sticks:
            color = _NEGATIVE if y < 0 else _POSITIVE
            painter.setPen(_pen(color, 1.55 if compact else 1.15))
            if y:
                painter.drawLine(QPointF(px(x), baseline), QPointF(px(x), py(y)))
            else:
                painter.setBrush(QColor(color))
                painter.drawEllipse(QPointF(px(x), baseline), 1.55, 1.55)
    if style.layers != "sticks" and profile.curve:
        path = QPainterPath()
        x0, y0 = profile.curve[0]
        path.moveTo(px(x0), py(y0))
        for x, y in profile.curve[1:]:
            path.lineTo(px(x), py(y))
        painter.setPen(_pen(style.color, style.stroke_width * (.65 if compact else 1.0)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    painter.restore()
    return ymin / scale, ymax / scale


def _shape_label(shape):
    return tr(next(label for label, key in _SHAPES if key == shape))


class SpectrumFigure(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(280, 260)
        self.setObjectName("spectrumFigure")
        self.profile = self.style = None
        self.title = self.error = ""

    def export_image(self, parent):
        choose_spectrum_image(parent, self.title, partial(capture_spectrum_figure, self), self.style.grid)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self.draw(painter, QRectF(self.rect()))
        finally:
            painter.end()

    def draw(self, painter, bounds, *, grid=None, background=True):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if background:
            painter.fillRect(bounds, Qt.GlobalColor.white)
        if self.error or not self.profile:
            painter.setPen(_MUTED)
            painter.drawText(bounds.adjusted(14, 0, -14, 0), _CENTER | Qt.TextFlag.TextWordWrap, self.error)
            return
        profile, style = self.profile, self.style
        left, right = bounds.left() + 70, bounds.right() - 30
        rect = QRectF(left, bounds.top() + 100, right - left, bounds.height() - 185)
        font = self.font()
        font.setPixelSize(17)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(_INK)
        title_box = bounds.adjusted(20, 8, -20, -bounds.height() + 54)
        painter.drawText(title_box, _CENTER | Qt.TextFlag.TextWordWrap, self.title)
        font.setPixelSize(12)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(_MUTED)
        y_label = tr("Relative height") if style.normalized else tr(profile.source.y_label)
        painter.drawText(QRectF(left, rect.top() - 25, rect.width(), 19), _LEFT, y_label)
        ymin, ymax = draw_traces(painter, rect, profile, style, grid=grid)
        painter.setPen(_pen(_AXIS, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.drawLine(rect.topLeft(), rect.bottomLeft())
        for value in _axis_ticks(ymin, ymax, 4):
            fraction = (value - ymin) / (ymax - ymin)
            y = rect.bottom() - fraction * rect.height()
            painter.setPen(_MUTED)
            painter.drawText(QRectF(bounds.left(), y - 10, left - bounds.left() - 8, 20), _RIGHT,
                             _fmt(value, 4))
        xmin, xmax = profile.limits
        for value in _axis_ticks(xmin, xmax, 5 if rect.width() > 400 else 3):
            fraction = (value - xmin) / (xmax - xmin)
            if style.reverse:
                fraction = 1 - fraction
            x = rect.left() + fraction * rect.width()
            painter.drawText(QRectF(x - 42, rect.bottom() + 5, 84, 20), _CENTER, _fmt(value, 5))
        axis_caption = f"{tr(profile.source.x_label)} ({profile.source.unit})"
        painter.setPen(_INK)
        painter.drawText(QRectF(left, rect.bottom() + 30, rect.width(), 20), _CENTER, axis_caption)
        y = bounds.bottom() - 15
        labels = []
        if style.layers != "curve":
            labels.append((tr("Printed sticks"), None))
        if style.layers != "sticks":
            text = f"{_shape_label(profile.shape)}  ·  {tr('FWHM')} {_fmt(profile.fwhm)} {profile.source.unit}"
            if profile.shape == "pseudo-voigt":
                text += f"  ·  {tr('Lorentzian fraction')} {_fmt(100 * profile.mix)}%"
            labels.append((text, style.color))
        metrics = painter.fontMetrics()
        total = sum(20 + metrics.horizontalAdvance(label) for label, _ in labels) + 16 * (len(labels) - 1)
        x = max(bounds.left() + 8, bounds.center().x() - total / 2)
        for label, color in labels:
            if color is None:
                positive = any(value >= 0 for _, value in profile.source.peaks)
                negative = any(value < 0 for _, value in profile.source.peaks)
                if positive:
                    painter.setPen(_pen(_POSITIVE, 1.5))
                    painter.drawLine(QPointF(x + 5, y + 3), QPointF(x + 5, y - 5))
                if negative:
                    painter.setPen(_pen(_NEGATIVE, 1.5))
                    painter.drawLine(QPointF(x + 10, y - 2), QPointF(x + 10, y + 5))
            else:
                painter.setPen(_pen(color, style.stroke_width))
                painter.drawLine(QPointF(x, y), QPointF(x + 13, y))
            width = metrics.horizontalAdvance(label)
            painter.setPen(_MUTED)
            painter.drawText(QRectF(x + 20, y - 9, width + 2, 18), _LEFT, label)
            x += width + 36


class _PlotSpinBox(QDoubleSpinBox):
    def textFromValue(self, value):
        text = super().textFromValue(value)
        decimal = self.locale().decimalPoint()
        return text.rstrip("0").removesuffix(decimal) if decimal in text else text


def _spin(low, high, decimals, step, value):
    control = _PlotSpinBox()
    control.setMinimumWidth(76)
    control.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    control.setDecimals(decimals)
    control.setRange(low, high)
    control.setSingleStep(step)
    control.setValue(value)
    control.setKeyboardTracking(False)
    return control


class SpectrumPlotDialog(QDialog):
    changed = Signal(object, object, str)

    def __init__(self, table, profile, style, sampler, parent):
        super().__init__(parent)
        self.setObjectName("spectrumPlotDialog")
        self.setWindowTitle(tr("Spectrum plot"))
        available = self.screen().availableGeometry()
        self.resize(min(970, available.width() - 30), min(620, available.height() - 70))
        self.table = table
        self.sampler = sampler
        self.figure = SpectrumFigure()
        self.figure.title = report_text(table.title)
        self.figure.profile = profile
        self.figure.style = style
        self._loading = True
        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        layout.addLayout(body, 1)
        body.addWidget(self.figure, 1)
        panel = QWidget()
        settings = QVBoxLayout(panel)
        settings.setContentsMargins(2, 2, 6, 2)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setFixedWidth(265)
        body.addWidget(scroll)
        def group(title):
            box = QGroupBox(tr(title))
            form = QFormLayout(box)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            settings.addWidget(box)
            return form

        form = group("Line profile")
        self.shape = QComboBox()
        for label, key in _SHAPES:
            self.shape.addItem(tr(label), key)
        self.shape.setCurrentIndex(self.shape.findData(profile.shape))
        form.addRow(tr("Shape"), self.shape)
        self.width = _spin(.000001, 1e9, 6, 1, profile.fwhm)
        self.width.setToolTip(tr("Each printed strength sets its isolated peak height. FWHM uses the selected axis unit."))
        form.addRow(tr("FWHM"), self.width)
        self.mix = _spin(0, 100, 0, 5, 100 * profile.mix)
        self.mix.setSuffix("%")
        form.addRow(tr("Lorentzian fraction"), self.mix)
        self.sampling = QComboBox()
        for count in (401, 801, 1201, 2401, 4801):
            self.sampling.addItem(str(count), count)
        self.sampling.setCurrentIndex(self.sampling.findData(profile.points))
        form.addRow(tr("Base samples"), self.sampling)
        self.normalize = QCheckBox(tr("Normalize curve height"))
        self.normalize.setChecked(style.normalized)
        self.normalize.setToolTip(tr("Scale both traces by the largest absolute curve value in the displayed range."))
        form.addRow(self.normalize)

        form = group("Horizontal axis")
        self.unit = QComboBox()
        self.unit.addItems(profile.source.units)
        self.unit.setCurrentText(profile.source.unit)
        self.unit.setEnabled(self.unit.count() > 1)
        form.addRow(tr("Unit"), self.unit)
        self.auto_range = QCheckBox(tr("Automatic range"))
        self.auto_range.setChecked(True)
        form.addRow(self.auto_range)
        self.xmin = _spin(-1e15, 1e15, 6, 1, profile.limits[0])
        self.xmax = _spin(-1e15, 1e15, 6, 1, profile.limits[1])
        form.addRow(tr("Minimum"), self.xmin)
        form.addRow(tr("Maximum"), self.xmax)
        self.reverse = QCheckBox(tr("Reverse axis"))
        self.reverse.setChecked(style.reverse)
        form.addRow(self.reverse)

        form = group("Appearance")
        self.layers = QComboBox()
        for label, key in (("Curve and sticks", "both"), ("Curve only", "curve"), ("Sticks only", "sticks")):
            self.layers.addItem(tr(label), key)
        form.addRow(tr("Traces"), self.layers)
        self.grid = QCheckBox(tr("Grid lines"))
        self.grid.setChecked(style.grid)
        form.addRow(self.grid)
        self.color_button = QPushButton()
        self.color_button.setAutoDefault(False)
        self.color_button.setAccessibleName(tr("Curve color"))
        form.addRow(tr("Curve color"), self.color_button)
        self.stroke_width = _spin(.5, 6.0, 1, .5, style.stroke_width)
        self.stroke_width.setSuffix(" px")
        form.addRow(tr("Curve width"), self.stroke_width)
        settings.addStretch()
        actions = QHBoxLayout()
        layout.addLayout(actions)
        self.reset_button = QPushButton(tr("Reset settings"))
        self.reset_button.clicked.connect(self.reset)
        actions.addWidget(self.reset_button)
        actions.addStretch()
        self.export_button = QPushButton(tr("Export…"))
        export_menu = QMenu(self.export_button)
        for label, kind in (("Export image…", "image"), ("Sampled curve (CSV)…", "curve"),
                            ("Printed sticks (CSV)…", "sticks")):
            action = export_menu.addAction(tr(label))
            action.triggered.connect(lambda checked=False, mode=kind: self.choose_export(mode))
        self.export_button.setMenu(export_menu)
        actions.addWidget(self.export_button)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        actions.addWidget(close)

        for signal in (self.shape.currentIndexChanged, self.width.valueChanged, self.mix.valueChanged, self.sampling.currentIndexChanged,
                       self.auto_range.toggled, self.xmin.valueChanged, self.xmax.valueChanged):
            signal.connect(self.update_profile)
        for signal in (self.normalize.toggled, self.grid.toggled, self.reverse.toggled,
                       self.layers.currentIndexChanged, self.stroke_width.valueChanged):
            signal.connect(self.update_style)
        self.unit.currentTextChanged.connect(self.change_unit)
        self.color_button.clicked.connect(self.choose_color)
        self._set_unit_controls(profile.source)
        self._loading = False
        self._update_enabled()
        self.update_style()

    def _set_unit_controls(self, source):
        for control in (self.xmin, self.xmax, self.width):
            control.setSingleStep(source.default_fwhm / 10)
        self.width.setSuffix(" " + source.unit)

    def _update_enabled(self):
        self.mix.setEnabled(self.shape.currentData() == "pseudo-voigt")
        self.xmin.setEnabled(not self.auto_range.isChecked())
        self.xmax.setEnabled(not self.auto_range.isChecked())
        curve_visible = self.layers.currentData() != "sticks"
        self.color_button.setEnabled(curve_visible)
        self.stroke_width.setEnabled(curve_visible)

    def _paint(self):
        self.figure.update()
        self.export_button.setEnabled(not self.figure.error)
        self.changed.emit(self.figure.profile, self.figure.style, self.figure.error)

    def update_style(self):
        if self._loading:
            return
        style = self.figure.style
        style.layers = self.layers.currentData()
        style.grid = self.grid.isChecked()
        style.reverse = self.reverse.isChecked()
        style.normalized = self.normalize.isChecked()
        style.stroke_width = self.stroke_width.value()
        self.color_button.setText(style.color.upper())
        swatch = QPixmap(14, 14)
        swatch.fill(QColor(style.color))
        self.color_button.setIcon(QIcon(swatch))
        self._update_enabled()
        self._paint()

    def update_profile(self):
        if self._loading:
            return
        self._update_enabled()
        source = stick_spectrum(self.table, unit=self.unit.currentText())
        self.figure.error = ""
        try:
            if self.auto_range.isChecked():
                limits = None
            else:
                limits = self.xmin.value(), self.xmax.value()
                if limits[0] >= limits[1]:
                    raise ValueError(tr("The maximum must be greater than the minimum."))
            settings = PlotProfile.setup(source, self.shape.currentData(), self.width.value(), self.mix.value() / 100,
                                         limits, self.sampling.currentData())
        except (ValueError, ArithmeticError) as error:
            self.sampler.cancel()
            self.set_profile(self.figure.profile, tr(str(error)))
            return
        if self.auto_range.isChecked():
            self._loading = True
            self.xmin.setValue(settings.limits[0])
            self.xmax.setValue(settings.limits[1])
            self._loading = False
        self.set_profile(settings, tr("Calculating spectrum…"))
        self.sampler.request(settings)

    def set_profile(self, profile, error):
        self.figure.profile = profile
        self.figure.error = error
        self._paint()

    def change_unit(self, unit):
        if self._loading:
            return
        source = stick_spectrum(self.table, unit=unit)
        self._loading = True
        self._set_unit_controls(source)
        self.width.setValue(source.default_fwhm)
        self.auto_range.setChecked(True)
        self._loading = False
        self.update_profile()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.figure.style.color), self, tr("Curve color"))
        if color.isValid():
            self.figure.style.color = color.name()
            self.update_style()

    def reset(self):
        source = stick_spectrum(self.table)
        self._loading = True
        self.unit.setCurrentText(source.unit)
        self._set_unit_controls(source)
        self.shape.setCurrentIndex(0)
        self.width.setValue(source.default_fwhm)
        self.mix.setValue(50)
        self.sampling.setCurrentIndex(self.sampling.findData(1201))
        self.normalize.setChecked(False)
        self.auto_range.setChecked(True)
        self.reverse.setChecked(source.reversed_axis)
        self.layers.setCurrentIndex(0)
        self.grid.setChecked(True)
        self.figure.style.color = PlotStyle.color
        self.stroke_width.setValue(PlotStyle.stroke_width)
        self._loading = False
        self.update_profile()
        self.update_style()

    def choose_export(self, kind):
        if kind in ("image", "png"):
            self.figure.export_image(self)
            return
        name = suggested_file(self, f"{self.table.kind}-{kind}", ".csv")
        target, _ = QFileDialog.getSaveFileName(self, tr("Export spectrum"), name, "CSV (*.csv)")
        if target:
            try:
                self.save_export(target, kind)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, tr("Export spectrum"), str(error))

    def save_export(self, filename, kind):
        save_spectrum_figure(self.figure, filename, kind)


def choose_spectrum_image(parent, title, capture, grid):
    dialog = SpectrumImageDialog(title, capture, grid, parent)
    try:
        dialog.exec()
    finally:
        dialog.deleteLater()


def save_spectrum_figure(figure, filename, kind):
    """Write the desktop figure using a paint device without showing a window."""
    if figure.error:
        raise ValueError(figure.error)
    if kind == "png":
        save_spectrum_png(filename, figure)
        return
    profile, style = figure.profile, figure.style
    output = QSaveFile(str(filename))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(output.errorString())
    curve = None if kind == "sticks" else profile.curve
    data = spectrum_csv(profile.source, curve, scale=profile.scale(style),
                        normalized=style.normalized).encode("utf-8")
    success = output.write(data) == len(data)
    if not success or not output.commit():
        output.cancelWriting()
        raise OSError(output.errorString())

"""Preview and export the molecule shown in the current workspace."""

from pathlib import Path
import re

from PySide6.QtCore import QRectF, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractSpinBox, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from orcaview.gui.structure_export import (
    MAX_CANVAS_DIMENSION, MAX_EXPORT_SCALE, capture_structure, paint_structure_canvas, save_structure_image,
    validate_structure_size,
)
from orcaview.i18n import diagnostic_text, tr


_FORMATS = {"png": ("PNG", "*.png"), "jpg": ("JPEG", "*.jpg *.jpeg"),
            "bmp": ("BMP", "*.bmp"), "pdf": ("PDF", "*.pdf")}


class _CanvasPreview(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setMinimumSize(240, 175)
        self.setAccessibleName(tr("Image preview"))
        self.snapshot = None
        self.canvas = (1, 1)
        self.scale = 1
        self.transparent = False

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor("#eae6e1"))
            if self.snapshot is None or min(self.canvas) <= 0:
                return
            width, height = self.canvas
            factor = min((self.width() - 22) / width, (self.height() - 22) / height)
            area = QRectF((self.width() - width * factor) / 2, (self.height() - height * factor) / 2,
                          width * factor, height * factor)
            painter.fillRect(area, Qt.GlobalColor.white)
            painter.setClipRect(area)
            if self.transparent:
                for row, y in enumerate(range(int(area.top()), int(area.bottom()) + 1, 8)):
                    for x in range(int(area.left()) + 8 * (row % 2), int(area.right()) + 1, 16):
                        painter.fillRect(x, y, 8, 8, QColor("#e2e4e6"))
            painter.translate(area.topLeft())
            painter.scale(factor, factor)
            paint_structure_canvas(painter, self.snapshot, width, height, scale=self.scale)
            painter.resetTransform()
            painter.setClipping(False)
            painter.setPen(QPen(QColor("#bbb4ac"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(area)
        finally:
            painter.end()


class StructureImageDialog(QDialog):
    def __init__(self, views, name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Export structure image"))
        self.setObjectName("structureImageDialog")
        self.resize(460, 460)
        self.output_path = None
        self._snapshots = [capture_structure(view) for _, view in views]
        self._name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "molecule"
        self._transparent_preference = False
        layout = QVBoxLayout(self)
        self.preview = _CanvasPreview(self)
        layout.addWidget(self.preview, 1)
        self.dimensions = QLabel()
        self.dimensions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.dimensions)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        self.source = QComboBox()
        self.source.setObjectName("structureImageSource")
        self.source.addItems([label for label, _ in views])
        form.addRow(tr("Structure view"), self.source)
        form.setRowVisible(self.source, len(views) > 1)
        self.format_choice = QComboBox()
        self.format_choice.setObjectName("structureImageFormat")
        for key, (label, _) in _FORMATS.items():
            self.format_choice.addItem(label, key)
        form.addRow(tr("File format"), self.format_choice)
        self.scale_box = QComboBox()
        self.scale_box.setObjectName("structureImageScale")
        self.scale_box.setAccessibleName(tr("Resolution scale"))
        self.scale_box.setToolTip(tr("At 4×, a 400 × 400 view is drawn at 1600 × 1600 pixels."))
        for scale in range(1, MAX_EXPORT_SCALE + 1):
            self.scale_box.addItem(f"{scale}×", scale)
        self.scale_box.setCurrentIndex(self.scale_box.findData(2))
        self._previous_scale = self.scale_box.currentData()
        form.addRow(tr("Resolution scale"), self.scale_box)
        self.transparent = QCheckBox(tr("Transparent background"))
        self.transparent.setObjectName("structureImageTransparent")
        form.addRow(self.transparent)
        self.background_note = QLabel(tr("JPEG and BMP use a white background."))
        form.addRow(self.background_note)
        self.advanced = QToolButton()
        self.advanced.setText(tr("Advanced options"))
        self.advanced.setCheckable(True)
        self.advanced.setAutoRaise(True)
        self.advanced.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced.setObjectName("structureImageAdvanced")
        form.addRow(self.advanced)
        self.size_fields = QWidget()
        row = QHBoxLayout(self.size_fields)
        row.setContentsMargins(0, 0, 0, 0)
        self.width_box, self.height_box = QSpinBox(), QSpinBox()
        for box, label, obj_name in ((self.width_box, tr("Width"), "structureImageWidth"),
                                     (self.height_box, tr("Height"), "structureImageHeight")):
            box.setObjectName(obj_name)
            box.setRange(1, MAX_CANVAS_DIMENSION)
            box.setSuffix(" px")
            box.setKeyboardTracking(False)
            box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            box.setAccessibleName(label)
            row.addWidget(QLabel(label))
            row.addWidget(box, 1)
        form.addRow(self.size_fields)
        self.hint = QLabel(tr("A larger canvas adds margins. A smaller canvas crops the view around its center."))
        self.hint.setWordWrap(True)
        form.addRow(self.hint)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #944a25")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        self.save_button = QPushButton(tr("Export…"))
        self.save_button.setObjectName("structureImageSave")
        buttons.addButton(self.save_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self.save_button.setDefault(True)
        buttons.accepted.connect(self._choose_file)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.source.currentIndexChanged.connect(self._source_changed)
        self.format_choice.currentIndexChanged.connect(self._format_changed)
        self.scale_box.currentIndexChanged.connect(self._scale_changed)
        self.transparent.toggled.connect(self._background_changed)
        self.advanced.toggled.connect(self._refresh)
        self.width_box.valueChanged.connect(self._refresh)
        self.height_box.valueChanged.connect(self._refresh)
        self._source_changed()
        self._format_changed()

    def _source_changed(self):
        self.snapshot = self._snapshots[self.source.currentIndex()]
        if not self.advanced.isChecked():
            self._set_canvas_fields(*self._scaled_size())
        self._refresh()

    def _scaled_size(self):
        size = self.snapshot.size()
        scale = self.scale_box.currentData()
        return size.width() * scale, size.height() * scale

    def _set_canvas_fields(self, width, height):
        for box, value in ((self.width_box, width), (self.height_box, height)):
            with QSignalBlocker(box):
                # A large scale or existing crop can put a computed dimension
                # outside the export limits. Show that value and its diagnostic.
                box.setRange(min(1, value), max(MAX_CANVAS_DIMENSION, value))
                box.setValue(value)

    def _scale_changed(self):
        size = self.snapshot.size()
        scale = self.scale_box.currentData()
        difference = scale - self._previous_scale
        self._previous_scale = scale
        self._set_canvas_fields(self.width_box.value() + difference * size.width(),
                                self.height_box.value() + difference * size.height())
        self._refresh()

    def _format_changed(self):
        alpha = self.format_choice.currentData() in ("png", "pdf")
        self.transparent.setEnabled(alpha)
        self.transparent.setChecked(alpha and self._transparent_preference)
        self.background_note.setVisible(not alpha)
        self._refresh()

    def _background_changed(self, enabled):
        if self.transparent.isEnabled():
            self._transparent_preference = enabled
        self._refresh()

    def _refresh(self):
        custom = self.advanced.isChecked()
        self.advanced.setArrowType(Qt.ArrowType.DownArrow if custom else Qt.ArrowType.RightArrow)
        self.size_fields.setVisible(custom)
        self.hint.setVisible(custom)
        width, height = (self.width_box.value(), self.height_box.value()) if custom else self._scaled_size()
        self.preview.snapshot = self.snapshot
        self.preview.canvas = width, height
        self.preview.scale = self.scale_box.currentData()
        self.preview.transparent = self.transparent.isChecked()
        self.preview.update()
        self.dimensions.setText(f"{width} × {height} px")
        try:
            validate_structure_size(width, height, self.format_choice.currentData())
        except ValueError as exc:
            self.error.setText(diagnostic_text(exc))
        else:
            self.error.clear()
        self.error.setVisible(bool(self.error.text()))
        self.save_button.setEnabled(not self.error.text())

    def _choose_file(self):
        fmt = self.format_choice.currentData()
        label, patterns = _FORMATS[fmt]
        dialog = QFileDialog(self, tr("Save structure image"))
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setNameFilter(f"{label} ({patterns})")
        dialog.setDefaultSuffix(fmt)
        dialog.selectFile(f"{self._name}.{fmt}")
        if not dialog.exec():
            return
        path = Path(dialog.selectedFiles()[0])
        if "*" + path.suffix.lower() not in patterns.split():
            QMessageBox.warning(self, self.windowTitle(), tr("Use a filename ending in {extensions}.", extensions=patterns))
            return
        try:
            save_structure_image(self.snapshot, path, fmt, *self.preview.canvas,
                                 transparent=self.preview.transparent, scale=self.preview.scale)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, self.windowTitle(), diagnostic_text(exc))
            return
        self.output_path = path
        self.accept()

"""Capture vector drawings and export centered, scaled image canvases."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os

from PySide6.QtCore import QBuffer, QIODevice, QMarginsF, QPointF, QRectF, QSaveFile, QSize, QSizeF, Qt
from PySide6.QtGui import QFont, QImage, QImageWriter, QPageSize, QPainter, QPdfWriter, QPicture


MAX_CANVAS_DIMENSION = 16_384
MAX_RASTER_PIXELS = 32_000_000
MAX_EXPORT_SCALE = 8
_DPI = 96
_POINTS_PER_PIXEL = 72 / _DPI


def _format_name(image_format):
    name = image_format.upper() if isinstance(image_format, str) else ""
    if name == "JPEG":
        return "JPG"
    if name not in ("PNG", "JPG", "BMP", "PDF"):
        raise ValueError("Choose PNG, JPG, BMP or PDF.")
    return name


def _validate_scale(scale):
    if type(scale) is not int or not 1 <= scale <= MAX_EXPORT_SCALE:
        raise ValueError(f"Image scale must be a whole number from 1 to {MAX_EXPORT_SCALE}.")


def validate_structure_size(width, height, image_format, *, scale=1):
    """Raise ValueError for an unsupported format, dimension or raster allocation."""
    name = _format_name(image_format)
    _validate_scale(scale)
    if any(type(n) is not int or not 1 <= n <= MAX_CANVAS_DIMENSION for n in (width, height)):
        raise ValueError(f"Width and height must be whole numbers from 1 to {MAX_CANVAS_DIMENSION}.")
    if name != "PDF" and width * height > MAX_RASTER_PIXELS:
        raise ValueError(f"Raster exports can contain at most {MAX_RASTER_PIXELS:,} pixels.")


@dataclass(frozen=True)
class _DrawingSnapshot:
    _width: int
    _height: int
    _picture: QPicture

    def size(self):
        return QSize(self._width, self._height)

    def paint_structure(self, painter):
        # QPicture replays at destination DPI. The viewport geometry is already
        # expressed in logical pixels, including its labels and pen widths.
        device = painter.device()
        painter.save()
        try:
            painter.scale(self._picture.logicalDpiX() / device.logicalDpiX(),
                          self._picture.logicalDpiY() / device.logicalDpiY())
            painter.drawPicture(QPointF(), self._picture)
        finally:
            painter.restore()


def capture_drawing(size, draw):
    """Record a vector drawing in its source's logical pixel coordinates."""
    if size.isEmpty():
        raise ValueError("The source viewport is empty.")
    picture = QPicture()
    painter = QPainter(picture)
    try:
        draw(painter)
    finally:
        painter.end()
    return _DrawingSnapshot(size.width(), size.height(), picture)


def capture_structure(view):
    """Freeze a viewport's current vector drawing and size without retaining the widget."""
    if isinstance(view, _DrawingSnapshot):
        return view

    def draw(painter):
        if hasattr(view, "font"):
            font = QFont(view.font())
            if font.pointSizeF() > 0 and hasattr(view, "logicalDpiY"):
                font.setPointSizeF(font.pointSizeF() * view.logicalDpiY() / painter.device().logicalDpiY())
            painter.setFont(font)
        view.paint_structure(painter)

    return capture_drawing(view.size(), draw)


def paint_structure_canvas(painter, view, width, height, *, scale=1):
    """Draw the scaled viewport centered in the final pixel canvas on the caller's background."""
    _validate_scale(scale)
    source = view.size()
    painter.save()
    try:
        painter.setClipRect(QRectF(0, 0, width, height), Qt.ClipOperation.IntersectClip)
        # Integer offsets keep the original raster samples intact for odd
        # padding too. The spare pixel of positive padding goes right/bottom.
        painter.translate((width - scale * source.width()) // 2, (height - scale * source.height()) // 2)
        painter.scale(scale, scale)
        painter.setClipRect(QRectF(0, 0, source.width(), source.height()), Qt.ClipOperation.IntersectClip)
        view.paint_structure(painter)
    finally:
        painter.restore()


def _paint(device, snapshot, width, height, *, scale, white, offset_y=0.0):
    painter = QPainter()
    if not painter.begin(device):
        raise OSError("Could not initialize the drawing.")
    try:
        painter.translate(0, offset_y)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        if white:
            painter.fillRect(QRectF(0, 0, width, height), Qt.GlobalColor.white)
        paint_structure_canvas(painter, snapshot, width, height, scale=scale)
    finally:
        painter.end()


def _write_pdf(output, snapshot, width, height, transparent, scale):
    # Qt 6.8 rounds custom pages to whole PDF points. Draw on the containing
    # whole-point page with the same bottom-left origin as the final MediaBox.
    points_per_pixel = _POINTS_PER_PIXEL / scale
    points = (width * _POINTS_PER_PIXEL / scale, height * _POINTS_PER_PIXEL / scale)
    extent = tuple(math.ceil(n) for n in points)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.ReadWrite)
    pdf = QPdfWriter(buffer)
    pdf.setResolution(_DPI * scale)
    page = QPageSize(QSizeF(*extent), QPageSize.Unit.Point, "Figure", QPageSize.SizeMatchPolicy.ExactMatch)
    if not pdf.setPageSize(page) or not pdf.setPageMargins(QMarginsF()):
        raise OSError("Could not set the PDF page size.")
    _paint(pdf, snapshot, width, height, scale=scale, white=not transparent,
           offset_y=(extent[1] - points[1]) / points_per_pixel)
    data = buffer.data()
    if extent != points:
        # Only patch Qt's own single page dictionary. Keep the exact byte length
        # of both boxes, hence the content lengths and all cross-reference offsets.
        start = data.indexOf(b"/Type /Page\n")
        end = data.indexOf(b"\n>>\nendobj", start) if start >= 0 else -1
        if end < 0:
            raise OSError("Could not finalize the PDF page size.")
        entries = bytes(data.mid(start, end - start))
        # A 7× page can have recurring decimal dimensions. Round toward the
        # inside at PDF's six decimal places so rasterizers taking the ceiling
        # at the requested print density do not invent a last pixel row/column.
        page_points = tuple((n * 750_000 // scale) / 1_000_000 for n in (width, height))
        for key in (b"/MediaBox", b"/TrimBox"):
            original = key + b" [0 0 %.6f %.6f]" % extent
            exact = key + b" [0 0 %.6f %.6f]" % page_points
            if entries.count(original) != 1 or len(exact) > len(original):
                raise OSError("Could not finalize the PDF page size.")
            entries = entries.replace(original, exact.ljust(len(original)))
        data.replace(start, end - start, entries)
    if output.write(data) != data.size():
        raise OSError(output.errorString())


def save_structure_image(view, filename, image_format, width, height, transparent=False, *, scale=1):
    """Atomically write PNG, JPG/JPEG, 24-bit BMP or vector PDF. Return None on success.

    Width and height are final pixels at 96 × scale per inch. Scale enlarges
    the vector drawing before centering, padding or cropping. PNG and PDF
    support transparency. JPG and BMP use a white background. Invalid options raise
    ValueError, filesystem/encoding failures raise OSError, and exceptions
    raised by the supplied structure painter propagate to the caller.
    """
    validate_structure_size(width, height, image_format, scale=scale)
    name = _format_name(image_format)
    snapshot = capture_structure(view)
    output = QSaveFile(os.fspath(filename))
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(output.errorString())
    try:
        if name == "PDF":
            _write_pdf(output, snapshot, width, height, transparent, scale)
        else:
            alpha = transparent and name == "PNG"
            pixel_format = QImage.Format.Format_ARGB32_Premultiplied if alpha else QImage.Format.Format_RGB32
            image = QImage(width, height, pixel_format)
            if image.isNull():
                raise OSError("Could not allocate the image.")
            if alpha:
                image.fill(Qt.GlobalColor.transparent)
            dots_per_meter = round(_DPI * scale / .0254)
            image.setDotsPerMeterX(dots_per_meter)
            image.setDotsPerMeterY(dots_per_meter)
            _paint(image, snapshot, width, height, scale=scale, white=not alpha)
            writer = QImageWriter(output, name.encode("ascii"))
            if name == "JPG":
                writer.setQuality(95)
            if not writer.write(image):
                raise OSError(writer.errorString())
        if not output.commit():
            raise OSError(output.errorString())
    except BaseException:
        if output.isOpen():
            output.cancelWriting()
            # commit() after cancellation discards the temporary file immediately,
            # including when a caller retains the exception and its traceback.
            output.commit()
        raise

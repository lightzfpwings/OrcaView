"""Painted controls for the structure views."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def hydrogen_cursor():
    """Use the centre of the plus as the hotspot; outline the glyph over atoms."""
    pixmap = QPixmap(64, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    glyph = QPainterPath()
    for x1, y1, x2, y2 in ((2, 10, 12, 10), (7, 5, 7, 15), (16, 3, 16, 17),
                           (25, 3, 25, 17), (16, 10, 25, 10)):
        glyph.moveTo(x1, y1)
        glyph.lineTo(x2, y2)
    for color, width in (("#FFFDF9", 4.5), ("#623449", 2.2)):
        painter.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(glyph)
    painter.end()
    return QCursor(pixmap, 7, 10)


def rotation_icon(axis, sign):
    # Draw at three times the logical size for crisp high-DPI toolbar icons.
    pixmap = QPixmap(72, 72)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setWindow(0, 0, 24, 24)
    painter.translate(12, 12)
    painter.setPen(QPen(QColor("#493E3A"), 1.8, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    arrow = QPainterPath()
    if axis == "z":
        # Seen from +z, a positive roll is counterclockwise.
        if sign > 0:
            painter.scale(-1, 1)
        circle = QRectF(-7.5, -7.5, 15, 15)
        arrow.arcMoveTo(circle, -45)
        arrow.arcTo(circle, -45, -315)
        arrow.moveTo(4, -3.5)
        arrow.lineTo(7.5, 0)
        arrow.lineTo(11, -3.5)
    else:
        if axis == "x":
            painter.rotate(90 * sign)
        elif sign < 0:
            painter.scale(-1, 1)
        arrow.moveTo(-9, 5)
        arrow.quadTo(-4, -2, 3, -2)
        arrow.lineTo(9, -2)
        arrow.moveTo(4.5, -6.5)
        arrow.lineTo(9, -2)
        arrow.lineTo(4.5, 2.5)
    painter.drawPath(arrow)
    painter.end()
    return QIcon(pixmap)

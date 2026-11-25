"""Bond symbols shared by the sketch, the projected molecule and the tool palette."""

from collections import deque
import math

from PySide6.QtCore import QPointF, QSizeF, Qt
from PySide6.QtGui import (QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF)


def aromatic_ring_paths(bonds):
    """Find a shortest enclosing ring for each explicitly delocalized edge."""
    aromatic = [bond for bond in bonds if bond.style == "aromatic"]
    if not aromatic:
        return {}
    neighbors = {}
    for bond in bonds:
        neighbors.setdefault(bond.a, []).append(bond.b)
        neighbors.setdefault(bond.b, []).append(bond.a)
    paths = {}
    for bond in aromatic:
        first, last = bond.a, bond.b
        parent = {first: None}
        pending = deque([first])
        while pending and last not in parent:
            i = pending.popleft()
            for j in neighbors[i]:
                if j not in parent and (i, j) != (first, last):
                    parent[j] = i
                    pending.append(j)
        if last in parent:
            i = parent[last]
            path = []
            while i != first:
                path.append(i)
                i = parent[i]
            paths[bond] = path
    return paths


def ring_center(indices, points):
    if not indices:
        return None
    return sum((points[i] for i in indices), QPointF()) / len(indices)


def _inset(clearance, unit):
    # Atom text uses rectangular masks in 2D; projected spheres supply a radius.
    if isinstance(clearance, QSizeF):
        return 1 / max(abs(unit.x()) / clearance.width(), abs(unit.y()) / clearance.height())
    return clearance


def draw_bond(painter, start, end, order, style, ink, width, spacing, *,
              clearance=(0., 0.), interior=None, shaded=False, end_ink=None):
    vector = end - start
    length = math.hypot(vector.x(), vector.y())
    if length < .01:
        return
    unit = vector / length
    normal = QPointF(-unit.y(), unit.x())
    # Symbol endpoints remain visible just outside atom labels or spheres.
    if style != "plain":
        first, last = (_inset(value, unit) for value in clearance)
        start = start + unit * first
        length -= first + last
        if length < 1:
            return
    painter.save()
    painter.translate(start)
    painter.rotate(math.degrees(math.atan2(unit.y(), unit.x())))
    if end_ink is not None and end_ink != ink:
        halves = QLinearGradient(0, 0, length, 0)
        halves.setColorAt(0.4999, ink)
        halves.setColorAt(0.5001, end_ink)
        ink = QBrush(halves)

    def pen(y=0., weight=width):
        brush = QBrush(ink)
        if shaded:
            half = weight / 2
            if normal.x() * -.36 + normal.y() * -.52 < 0:
                half = -half
            gradient = QLinearGradient(0, y + half, 0, y - half)
            gradient.setColorAt(0, QColor("#9BA7A9"))
            gradient.setColorAt(.38, QColor("#909DA0"))
            gradient.setColorAt(1, QColor("#6B777A"))
            brush = QBrush(gradient)
        return QPen(brush, weight, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin)

    painter.setPen(pen())
    span = min(length * .28, max(3.5, spacing * 1.35))
    if style in ("wedge", "hollow_wedge"):
        triangle = QPolygonF([QPointF(), QPointF(length, -span), QPointF(length, span)])
        painter.setPen(pen(weight=min(width, span / 2)))
        painter.setBrush(ink if style == "wedge" else Qt.BrushStyle.NoBrush)
        painter.drawPolygon(triangle)
    elif style in ("hashed", "hashed_wedge"):
        count = max(3, min(2048, round(length / max(4., width * 2))))
        painter.setPen(pen(weight=min(width, length / count * .43)))
        for i in range(count):
            fraction = i / (count - 1)
            height = span if style == "hashed" else max(.3, span * fraction)
            x = length * fraction
            painter.drawLine(QPointF(x, -height), QPointF(x, height))
    elif style in ("wavy", "wavy_wedge"):
        path = QPainterPath(QPointF())
        count = max(4, min(2048, round(length / max(4., width * 2))))
        for i in range(count):
            amplitude = (span * (i + .5) / count if style == "wavy_wedge" else span * .74)
            sign = 1 if i % 2 == 0 else -1
            path.quadTo(QPointF(length * (i + .5) / count, sign * amplitude * 2),
                        QPointF(length * (i + 1) / count, 0))
        painter.setPen(pen(weight=min(width, span / 2)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    elif style == "coordinate_arrow":
        depth = min(length * .38, span * 2)
        painter.setPen(pen(weight=min(width, span / 1.5)))
        painter.drawLine(QPointF(), QPointF(length, 0))
        painter.drawPolyline(QPolygonF([QPointF(length-depth, -span), QPointF(length, 0),
                                        QPointF(length-depth, span)]))
    else:
        if style == "bold":
            width *= 1.7
            spacing *= 1.5
        if style == "aromatic" and interior is not None and QPointF.dotProduct(interior - start, normal) < 0:
            spacing = -spacing
        for line in range(order):
            y = spacing * (line - (order - 1) / 2)
            dashed = style in ("coordinate", "dashed") or (
                style in ("aromatic", "partial_triple") and line == order - 1)
            stroke = pen(y, width)
            if dashed:
                # At least three dashes remain visible even on short projected sticks.
                unit_length = min(max(2 * width, 3.), length / 5.)
                stroke.setCapStyle(Qt.PenCapStyle.FlatCap)
                stroke.setDashPattern([unit_length / width, .74 * unit_length / width])
            painter.setPen(stroke)
            painter.drawLine(QPointF(0, y), QPointF(length, -y if style == "crossed" else y))
    painter.restore()


def bond_icon(order, style):
    pixmap = QPixmap(84, 54)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setWindow(0, 0, 28, 18)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_bond(painter, QPointF(2, 9), QPointF(26, 9), order, style, QColor("#493E3A"), 1.5, 3.4)
    painter.end()
    return QIcon(pixmap)

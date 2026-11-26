"""Depth-colored backbone strokes and local, transparent gaps at crossings."""

from collections import defaultdict
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainterPath, QPainterPathStroker, QPen


def _outline(path, width):
    stroker = QPainterPathStroker()
    stroker.setWidth(width)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return stroker.createStroke(path)


def _mix(a, b, t):
    return QColor.fromRgbF(*(x + (y - x) * t for x, y in zip(a.getRgbF()[:3], b.getRgbF()[:3])))


def _ink_color(base, t):
    pale = _mix(base, QColor("#e5efed"), .48)
    deep = _mix(base, QColor("#153543"), .18)
    return _mix(pale, deep, t)


class _Stroke:
    def __init__(self, segment, points, t, ta, tb, base):
        self.a, self.b, self.path, self.depth = segment.a, segment.b, segment.path, segment.depth
        self.width = 3.7 + 3.1 * t
        self.color = _ink_color(base, t)
        self.gap = QPainterPath()
        self.points = points
        self.dot = self.path.isEmpty()
        bounds = QRectF(points[0], points[0]) if self.dot else self.path.boundingRect()
        self.box = bounds.adjusted(-8., -8., 8., 8.)
        self.shape = self._shape(self.width) if self.dot else None
        self.brush = QBrush(self.color)
        if points[0] != points[-1] and abs(tb - ta) > .001:
            gradient = QLinearGradient(points[0], points[-1])
            gradient.setColorAt(0., _ink_color(base, ta))
            gradient.setColorAt(1., _ink_color(base, tb))
            self.brush = QBrush(gradient)
        self.pen = QPen(self.brush, self.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin)

    def _shape(self, width):
        if self.dot:
            mark = QPainterPath()
            mark.addEllipse(self.points[0], width / 2, width / 2)
            return mark
        return _outline(self.path, width)

    def hit_distance(self, point):
        if not self.box.contains(point) or (self.shape is not None and self.gap.contains(point)):
            return math.inf
        if self.dot:
            return math.hypot(point.x() - self.points[0].x(), point.y() - self.points[0].y())
        best = math.inf
        for a, b in zip(self.points, self.points[1:]):
            vx, vy = b.x() - a.x(), b.y() - a.y()
            dx, dy = point.x() - a.x(), point.y() - a.y()
            length2 = vx * vx + vy * vy
            t = max(0., min(1., (dx * vx + dy * vy) / length2)) if length2 else 0.
            best = min(best, math.hypot(dx - t * vx, dy - t * vy))
        return best

    def paint(self, painter, highlighted=False):
        if highlighted:
            halo = self._shape(self.width + 5.)
            if self.shape is not None:
                halo = halo.subtracted(self.gap)
            painter.fillPath(halo, QColor("#94d9d1"))
        if self.shape is not None:
            painter.fillPath(self.shape, self.brush)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(self.pen)
            painter.drawPath(self.path)


def _crossing(first, second):
    """Locate an actual crossing of the rendered centerlines, skipping tangencies."""
    for a, b in zip(first.points, first.points[1:]):
        vx, vy = b.x() - a.x(), b.y() - a.y()
        for p, q in zip(second.points, second.points[1:]):
            wx, wy = q.x() - p.x(), q.y() - p.y()
            det = vx * wy - vy * wx
            if abs(det) <= max(1e-9, .12 * math.hypot(vx, vy) * math.hypot(wx, wy)):
                continue
            dx, dy = p.x() - a.x(), p.y() - a.y()
            u = (dx * wy - dy * wx) / det
            v = (dx * vy - dy * vx) / det
            if -1e-8 <= u <= 1.00000001 and -1e-8 <= v <= 1.00000001:
                return QPointF(a.x() + u * vx, a.y() + u * vy)
    return None


def _near_edges(i, strands, locations, radius):
    chain, pos = locations[i]
    indices, periodic = strands[chain]
    if periodic:
        return {indices[j % len(indices)] for j in range(pos - radius, pos + radius + 1)}
    return indices[max(0, pos-radius):pos+radius+1]


def prepare_ink(segments, chain_colors, paths):
    """Cache vector strokes in back-to-front paint order, with matching pointer geometry."""
    if not segments:
        return ()
    levels = sorted(s.depth for s in segments)
    trim = len(levels) // 32
    low, high = levels[trim], levels[-1-trim]

    def tone(depth):
        if high - low < 1e-8:
            return .65
        t = max(0., min(1., (depth-low) / (high-low)))
        return t*t*(3.-2.*t)

    node_levels = defaultdict(list)
    for s in segments:
        node_levels[s.a].append(s.depth)
        node_levels[s.b].append(s.depth)
    node_tones = {i: tone(sum(z) / len(z)) for i, z in node_levels.items()}
    strokes = []
    for s in segments:
        polygons = s.path.toSubpathPolygons()
        points = list(polygons[0]) if polygons else [s.path.currentPosition()] * 2
        strokes.append(_Stroke(s, points, tone(s.depth), node_tones[s.a], node_tones[s.b], chain_colors[s.a]))

    row = {tuple(sorted((s.a, s.b))): i for i, s in enumerate(strokes)}
    strands, locations = [], {}
    for chain, atoms in enumerate(paths):
        indices = [row[tuple(sorted((a, b)))] for a, b in zip(atoms, atoms[1:])]
        strands.append((indices, atoms[0] == atoms[-1]))
        locations.update((i, (chain, pos)) for pos, i in enumerate(indices))

    bounds = strokes[0].box
    for s in strokes[1:]:
        bounds = bounds.united(s.box)
    cell = max(30., bounds.width() / 128., bounds.height() / 128.)
    grid = defaultdict(list)
    order = sorted(range(len(strokes)), key=lambda i: strokes[i].depth)
    for i in order:
        front = strokes[i]
        box = front.box
        cells = [(x, y) for x in range(math.floor(box.left()/cell), math.floor(box.right()/cell) + 1)
                 for y in range(math.floor(box.top()/cell), math.floor(box.bottom()/cell) + 1)]
        candidates = {j for key in cells for j in grid[key]}
        near_front = set(_near_edges(i, strands, locations, 5))
        for j in candidates.difference(near_front):
            back = strokes[j]
            if ({front.a, front.b}.intersection((back.a, back.b)) or not box.intersects(back.box)):
                continue
            cross = _crossing(front, back)
            if cross is None:
                continue
            # Stroke a short stretch of the foreground centerline and restrict
            # the knockout to this crossing. Unpainted paper stays transparent
            # in PNG/PDF, even when the canvas uses a different background.
            circle = QPainterPath()
            radius = front.width * 1.8
            circle.addEllipse(cross, radius, radius)
            local = circle.boundingRect()
            front_path = QPainterPath()
            for k in near_front:
                if local.intersects(strokes[k].box):
                    front_path.addPath(strokes[k].path)
            gap = _outline(front_path, front.width + 3.8).intersected(circle)
            for k in _near_edges(j, strands, locations, 4):
                if k not in near_front and local.intersects(strokes[k].box):
                    strokes[k].gap = strokes[k].gap.united(gap)
        for key in cells:
            grid[key].append(i)
    for s in strokes:
        if not s.gap.isEmpty():
            s.shape = s._shape(s.width).subtracted(s.gap)
    return tuple(strokes[i] for i in order)

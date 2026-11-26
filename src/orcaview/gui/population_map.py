"""Map frame-bound atomic results onto a molecular projection and its color key."""

from dataclasses import dataclass
import math
import re
from typing import Optional

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPen, QRegion

from orcaview.gui.result_display import POPULATION_NAMES, dataset_name, report_text
from orcaview.i18n import tr


PALETTES = {
    "RWB": ("#b2182b", "#ffffff", "#2166ac"),
    "BWR": ("#2166ac", "#ffffff", "#b2182b"),
    "Rainbow": ("#62319b", "#3267bd", "#18a9af", "#76be49", "#ffdf4c", "#d53731"),
    "Black–white": ("#000000", "#ffffff"),
}
MISSING_COLOR = QColor("#9a9a9a")


def _nearest_open_box(x, y, width, height, margin, occupied):
    """Find space for a crowded label, skipping entire runs of blocked positions."""
    bounds = margin.toRect()
    target_x, target_y = round(x - width / 2), round(y - height / 2)
    first_x, last_x = bounds.left(), bounds.right() - width + 1
    best_box, best_distance = None, math.inf
    rows = range(bounds.top(), bounds.bottom() - height + 2)
    for top in sorted(rows, key=lambda row: abs(row - target_y)):
        dy2 = (top - target_y) ** 2
        if dy2 >= best_distance:
            break
        for direction in (-1, 1):
            left = max(first_x, min(target_x, last_x))
            while first_x <= left <= last_x:
                distance = (left - target_x) ** 2 + dy2
                if distance >= best_distance:
                    break
                rect = QRect(left, top, width, height)
                hit = occupied.intersected(rect).boundingRect()
                if hit.isEmpty():
                    best_box, best_distance = QRectF(rect), distance
                    break
                left = hit.left() - width if direction < 0 else hit.right() + 1
    return best_box


def _label_box(x, y, radius, width, height, margin, bonds, spheres, used):
    """Choose a nearby badge position in the current screen projection."""
    fallback = None
    best_rank = None
    for extra in (0, height * .6, height * 1.4, height * 2.5):
        gap = radius + 4 + extra
        diagonal = gap / math.sqrt(2)
        offsets = ((gap, -height / 2), (-gap - width, -height / 2),
                   (-width / 2, -gap - height), (-width / 2, gap),
                   (diagonal, -diagonal - height), (-diagonal - width, -diagonal - height),
                   (diagonal, diagonal), (-diagonal - width, diagonal))
        for dx, dy in offsets:
            left = max(margin.left(), min(x + dx, margin.right() - width))
            top = max(margin.top(), min(y + dy, margin.bottom() - height))
            box = QRectF(left, top, width, height)
            rect = box.toAlignedRect()
            rank = (bonds.intersects(rect), used.intersects(rect), spheres.intersects(rect))
            if not any(rank):
                return box
            if best_rank is None or rank < best_rank:
                fallback, best_rank = box, rank
    if best_rank[0]:
        # A crowded projection can cover every nearby candidate with a bond.
        for occupied in (bonds | spheres | used, bonds | used, bonds):
            clear = _nearest_open_box(x, y, width, height, margin, occupied)
            if clear is not None:
                return clear
    return fallback


@dataclass(frozen=True)
class PopulationStyle:
    colors: tuple = PALETTES["RWB"]
    range_mode: str = "data"
    lower: float = -1.0
    upper: float = 1.0
    reverse: bool = False
    digits: int = 3
    labels: bool = True
    color_atoms: bool = False
    legend: bool = True
    midpoint: Optional[float] = None

    def __post_init__(self):
        if not 2 <= len(self.colors) <= 8 or any(not re.fullmatch("#[0-9a-fA-F]{6}", c) for c in self.colors):
            raise ValueError("Invalid color stops")
        if self.range_mode not in ("data", "symmetric", "manual"):
            raise ValueError("Invalid scale range")
        if not all(type(v) in (int, float) and math.isfinite(v) for v in (self.lower, self.upper)) or self.lower >= self.upper:
            raise ValueError("The lower limit must be smaller than the upper limit.")
        if type(self.digits) is not int or not 0 <= self.digits <= 8:
            raise ValueError("Invalid population precision")
        if self.midpoint is not None and (self.range_mode != "manual" or type(self.midpoint) not in (int, float)
                                          or not self.lower < self.midpoint < self.upper):
            raise ValueError("The midpoint must lie between the manual limits.")
        if any(type(v) is not bool for v in (self.reverse, self.labels, self.color_atoms, self.legend)):
            raise ValueError("Invalid display setting")

    def bounds(self, values):
        if self.range_mode == "manual":
            return self.lower, self.upper
        low, high = min(values), max(values)
        if self.range_mode == "symmetric":
            high = max(abs(low), abs(high))
            return -high, high
        return low, high


def _ink(stops, position):
    offset = max(0., min(1., position)) * (len(stops) - 1)
    i = min(int(offset), len(stops) - 2)
    left, right = stops[i], stops[i + 1]
    return QColor.fromRgb(*(round(a + (b - a) * (offset - i)) for a, b in zip(left.getRgb()[:3], right.getRgb()[:3])))


def population_name(data):
    context = dict(data.provenance.parameters).get("population_series")
    name = dataset_name(data)
    return tr("{label} ({suffix})", label=name, suffix=report_text(context)) if context else name


def available_populations(datasets, geometry):
    return tuple(d for d in datasets if d.geometry == geometry and d.kind in POPULATION_NAMES
                 and len(d.axes) == 1 and d.axes[0].kind == "atom" and d.values is not None
                 and any(v is not None for v in d.values))


def _number(value, digits):
    return format(round(value, digits) or 0., f".{digits}f").replace("-", "−")


def _fraction(value, low, high):
    span = high - low
    return (value - low) / span if math.isfinite(span) else (value / 2 - low / 2) / (high / 2 - low / 2)


class PopulationMap:
    def __init__(self, data, snapshot, style):
        data.validate_geometry(snapshot)
        by_id = dict(zip(data.axes[0].ids, data.values))
        self.values = tuple(by_id.get(atom_id) for atom_id in snapshot.atom_ids)
        self.style = style
        self.name = population_name(data)
        self.unit = data.unit
        self.low, self.high = style.bounds([value for value in self.values if value is not None])
        colors = style.colors[::-1] if style.reverse else style.colors
        self.stops = tuple(QColor(color) for color in colors)
        self.colors = tuple(MISSING_COLOR if v is None else self.color(v) for v in self.values)
        self.labels = tuple("—" if v is None else _number(v, style.digits) for v in self.values)
        self.missing = None in self.values

    def color(self, value):
        if self.high == self.low:
            return _ink(self.stops, 0.5)
        value = min(self.high, max(self.low, value))
        midpoint = self.style.midpoint
        if midpoint is None:
            fraction = _fraction(value, self.low, self.high)
        elif value <= midpoint:
            fraction = .5 * _fraction(value, self.low, midpoint)
        else:
            fraction = .5 + .5 * _fraction(value, midpoint, self.high)
        return _ink(self.stops, fraction)

    def draw_key(self, painter, area):
        """Paint the same data limits and stops used to color the atoms."""
        metrics = painter.fontMetrics()
        row = metrics.height()
        painter.setPen(QColor("#393432"))
        title = self.name if self.unit == "1" else f"{self.name} ({self.unit})"
        if self.missing:
            title += ("   × " if self.style.color_atoms else "   — ") + tr("No data")
        width = min(area.width(), max(150, metrics.horizontalAdvance(title) + 16))
        left, bottom = area.left(), area.bottom()
        height = row + 8 + (row + 15 if self.style.color_atoms else 0)
        rect = QRectF(left, bottom - height, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 225))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor("#393432"))
        title = metrics.elidedText(title, Qt.TextElideMode.ElideRight, max(1, int(width) - 12))
        painter.drawText(QPointF(left + 6, rect.top() + metrics.ascent() + 3), title)
        if not self.style.color_atoms:
            return rect
        bar = QRectF(left + 6, rect.top() + row + 4, width - 12, 9)
        gradient = QLinearGradient(bar.topLeft(), bar.topRight())
        mid = self.style.midpoint
        center = .5 if mid is None else _fraction(mid, self.low, self.high)
        for i, color in enumerate(self.stops):
            t = i / (len(self.stops) - 1)
            position = 2 * t * center if t <= .5 else center + (2*t-1) * (1-center)
            gradient.setColorAt(position, color)
        if mid is not None:
            gradient.setColorAt(center, _ink(self.stops, .5))
        painter.setPen(QPen(QColor("#89827d"), .8))
        painter.setBrush(self.color(self.low) if self.low == self.high else gradient)
        painter.drawRect(bar)
        painter.setPen(QColor("#393432"))
        ticks = QRectF(bar.left(), bar.bottom() + 1, bar.width(), row)
        if self.low == self.high:
            painter.drawText(ticks, Qt.AlignmentFlag.AlignCenter, f"{self.low:.6g}")
        else:
            # Use extra digits when the endpoints would otherwise have the same label.
            digits = 5 if f"{self.low:.5g}" != f"{self.high:.5g}" else 12
            for end, align in ((self.low, Qt.AlignmentFlag.AlignLeft), (self.high, Qt.AlignmentFlag.AlignRight)):
                painter.drawText(ticks, align | Qt.AlignmentFlag.AlignVCenter, format(end, f".{digits}g"))
            if mid is None and self.low < 0 and self.low == -self.high:
                mid = 0.
            if mid is not None:
                tick = f"{mid:.5g}"
                x = ticks.left() + ticks.width() * center - metrics.horizontalAdvance(tick) / 2
                if (x > ticks.left() + metrics.horizontalAdvance(format(self.low, f".{digits}g")) + 3 and
                        x + metrics.horizontalAdvance(tick) < ticks.right() - metrics.horizontalAdvance(format(self.high, f".{digits}g")) - 3):
                    painter.drawText(QPointF(x, ticks.top() + metrics.ascent()), tick)
        return rect

    def draw_annotations(self, painter, view, projected, element_labels, selected, bond_region):
        painter.save()
        try:
            margin = QRectF(view.rect()).adjusted(3, 3, -3, -3)
            used = QRegion()
            if self.style.legend:
                key = self.draw_key(painter, QRectF(8, 5, max(55, view.width() - 76), view.height() - 13))
                used |= QRegion(key.toAlignedRect())
            if not self.style.labels:
                return
            spheres = QRegion()
            for x, y, _, r in projected:
                r += 2  # Reserve the sphere rim and its antialiased edge.
                spheres |= QRegion(QRectF(x-r, y-r, 2*r, 2*r).toAlignedRect(), QRegion.RegionType.Ellipse)
            metrics = painter.fontMetrics()
            for i in sorted(range(len(projected)), key=lambda index: projected[index][2], reverse=True):
                x, y, _, r = projected[i]
                if not margin.contains(x, y):
                    continue
                text = self.labels[i]
                if element_labels or i in selected:
                    text = f"{view.molecule.atoms[i].element}{i+1}  {text}"
                width, height = metrics.horizontalAdvance(text) + 8, metrics.height() + 2
                box = _label_box(x, y, r, width, height, margin, bond_region, spheres, used)
                used |= QRegion(box.toAlignedRect().adjusted(-1, -1, 1, 1))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 255, 255, 222))
                painter.drawRoundedRect(box, 3, 3)
                painter.setPen(QColor("#292526"))
                painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        finally:
            painter.restore()

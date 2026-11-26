"""Pointer targets in the sketch and the projected design view."""

import math

from PySide6.QtCore import QEvent, QPointF, QRectF
from PySide6.QtWidgets import QWidget


def polymer_wheel_zoom(zoom, event):
    """Scale a polymer view from 0.3× to 8×, including high-resolution touchpad input."""
    pixels = event.pixelDelta()
    steps = event.angleDelta().y() / 120. if pixels.isNull() else pixels.y() / 40.
    # Forty notches cover the entire range; bound the exponent for coalesced events.
    return min(8., max(.3, zoom * 1.12 ** max(-40., min(40., steps))))


def distance_to_segment(point, start, end):
    vector = end - start
    length2 = QPointF.dotProduct(vector, vector)
    if not length2:
        return math.inf, 0., 0.
    fraction = max(0., min(1., QPointF.dotProduct(point - start, vector) / length2))
    offset = point - (start + vector * fraction)
    return math.hypot(offset.x(), offset.y()), fraction, math.sqrt(length2)


class MoleculeEditView(QWidget):
    """A hover target contains zero, one (atom), or two (bond) atom indices."""

    def __init__(self, parent=None, *, mouse_tracking=True):
        super().__init__(parent)
        self.setMouseTracking(mouse_tracking)
        self._hover_point = None
        self._hover_target = ()

    def _track_hover(self, point):
        self._hover_point = point if point is not None and QRectF(self.rect()).contains(point) else None
        previous = self._hover_target
        if self._refresh_hover() != previous:
            self.update()

    def _refresh_hover(self):
        # Re-pick during painting as well: zooms and resizes can move the molecule
        # underneath a stationary pointer.
        self._hover_target = self._target_at(self._hover_point) if self._hover_point is not None else ()
        return self._hover_target

    def event(self, event):
        if event.type() in (QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.FocusOut,
                            QEvent.Type.WindowDeactivate) and getattr(self, "_hover_point", None) is not None:
            self._track_hover(None)
        return super().event(event)

"""Manage the draggable sidebars and their transition between workspaces."""

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QObject, QTimer, Qt, QVariantAnimation
from PySide6.QtWidgets import QStyle


_DEFAULT_SIDE_SHARE = 0.25
_RESULTS_SIDE_SHARE = 0.125


class WorkspaceColumns(QObject):
    def __init__(self, window, left, right):
        super().__init__(window)
        self.window, self.left, self.right = window, left, right
        self._shares = (_DEFAULT_SIDE_SHARE, _DEFAULT_SIDE_SHARE)
        self._structure_shares = self._shares
        self._start_shares = self._shares
        self._showing_results = False
        self._inspector_minimum = right.widget().minimumWidth()
        self._window_width = window.width()
        self._applying = False
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(240)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.valueChanged.connect(self.apply)
        self._animation.finished.connect(self._finish_transition)
        # Dock resize events arrive separately. Read the final splitter positions
        # after Qt has laid out both docks and the central page.
        self._remember = QTimer(self)
        self._remember.setSingleShot(True)
        self._remember.timeout.connect(self._remember_widths)
        for widget in (window, left, right):
            widget.installEventFilter(self)
        self.apply()

    def _docked_sides(self):
        areas = (Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea)
        return [(i, dock) for i, (dock, area) in enumerate(zip((self.left, self.right), areas))
                if not dock.isHidden() and not dock.isFloating() and self.window.dockWidgetArea(dock) == area]

    def _animating(self):
        return self._animation.state() == QAbstractAnimation.State.Running

    def set_results(self, showing_results):
        if self._showing_results == showing_results:
            return
        sides = self._docked_sides()
        if not self._animating():
            self._remember_widths()
        self._animation.stop()
        self._remember.stop()
        self._start_shares = self._measured_shares(sides)
        if showing_results:
            self._structure_shares = self._shares
            self._shares = (_RESULTS_SIDE_SHARE, _RESULTS_SIDE_SHARE)
        else:
            self._shares = self._structure_shares
        self._showing_results = showing_results
        # Keep the narrower minimum throughout the return animation, too.
        self.right.widget().setMinimumWidth(0)
        if sides and self.window.isVisible():
            self._animation.start()
        else:
            self._finish_transition()

    def _finish_transition(self):
        self.right.widget().setMinimumWidth(0 if self._showing_results else self._inspector_minimum)
        self.apply()

    def eventFilter(self, watched, event):
        if (watched is self.window and event.type() == QEvent.Type.MouseButtonDblClick
                and event.button() == Qt.MouseButton.LeftButton):
            side = self._separator_at(event.position().toPoint())
            if side is not None:
                self._reset_side(side)
                event.accept()
                return True
        elif event.type() == QEvent.Type.Resize:
            if watched is self.window:
                if event.size().width() != event.oldSize().width():
                    self.apply()
            elif not self._applying and not self._animating() and self.window.width() == self._window_width:
                self._remember.start(0)
        return False

    def _separator_at(self, pos):
        middle = self.window.centralWidget().geometry()
        if not middle.top() <= pos.y() <= middle.bottom():
            return None
        x = pos.x()
        hit = self.window.childAt(pos)
        if hit is not None:
            # macOS gives its one-pixel separator a wider native mouse target.
            if hit.parentWidget() is not self.window or hit.cursor().shape() != Qt.CursorShape.SplitHCursor:
                return None
            x = hit.geometry().center().x()
        for index, dock in self._docked_sides():
            bounds = dock.geometry()
            if bounds.top() <= pos.y() <= bounds.bottom():
                if bounds.right() < x < middle.left() or middle.right() < x < bounds.left():
                    return index
        return None

    def _reset_side(self, side):
        default = _RESULTS_SIDE_SHARE if self._showing_results else _DEFAULT_SIDE_SHARE
        if self._animating():
            # Reset this edge immediately while the opposite edge keeps moving.
            start = list(self._start_shares)
            start[side] = default
            self._start_shares = tuple(start)
        else:
            self._remember_widths()
        shares = list(self._shares)
        shares[side] = default
        # Keep the other edge where the user put it, up to the central
        # viewport's minimum width when the opposite dock is unusually wide.
        sides = self._docked_sides()
        available = self._available_width(sides)
        center = self.window.centralWidget()
        room = available - round(available * default) - max(
            center.minimumWidth(), center.minimumSizeHint().width())
        if len(sides) == 2 and round(available * shares[1 - side]) > room:
            shares[1 - side] = max(0, room) / available
        self._shares = tuple(shares)
        self.apply()

    def _available_width(self, sides):
        separator = self.window.style().pixelMetric(QStyle.PixelMetric.PM_DockWidgetSeparatorExtent,
                                                     None, self.window)
        return max(1, self.window.contentsRect().width() - len(sides) * separator)

    def _measured_shares(self, sides):
        available = self._available_width(sides)
        shares = list(self._shares)
        for index, dock in sides:
            shares[index] = dock.width() / available
        return tuple(shares)

    def _remember_widths(self):
        if self._animating() or self.window.width() != self._window_width:
            return
        sides = self._docked_sides()
        available = self._available_width(sides)
        used = self.window.centralWidget().width() + sum(dock.width() for _, dock in sides)
        # Ignore rounding and the transient geometry while switching workspaces.
        if abs(used - available) <= 2 and any(
                abs(dock.width() - self._shares[i] * available) > 1 for i, dock in sides):
            self._shares = self._measured_shares(sides)

    def apply(self):
        self._remember.stop()
        self._window_width = self.window.width()
        sides = self._docked_sides()
        if not sides:
            return
        available = self._available_width(sides)
        progress = self._animation.currentValue() if self._animating() else 1.0
        shares = [start + (target - start) * progress
                  for start, target in zip(self._start_shares, self._shares)]
        widths = [round(shares[i] * available) for i, _ in sides]
        self._applying = True
        try:
            self.window.resizeDocks([dock for _, dock in sides], widths, Qt.Orientation.Horizontal)
            self.window.layout().activate()
        finally:
            self._applying = False

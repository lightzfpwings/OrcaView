"""Fade the outgoing layout over the live workspace when entering or leaving Design."""

from PySide6.QtCore import QEasingCurve, QEvent, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QStyle, QTabBar, QTabWidget, QWidget


class WorkspaceTabs(QTabWidget):
    about_to_switch = Signal(object, object)

    def __init__(self):
        super().__init__()
        bar = QTabBar()
        # Connect before QTabWidget attaches its own currentChanged handler.
        # The old page and its docks are then still visible for the capture.
        bar.currentChanged.connect(self._changing)
        self.setTabBar(bar)

    def _changing(self, index):
        self.about_to_switch.emit(self.currentWidget(), self.widget(index))


class WorkspaceTransition(QWidget):
    def __init__(self, window, tabs, design, docks):
        super().__init__(window)
        self.tabs, self.design, self.docks = tabs, design, docks
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()
        self._image = None
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(210)
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.valueChanged.connect(lambda _: self.update())
        self._animation.finished.connect(self._clear)
        tabs.about_to_switch.connect(self._switching)
        window.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Hide):
            self._clear()
        return False

    def _switching(self, outgoing, destination):
        window = self.parentWidget()
        if (not window.isVisible() or outgoing is None or outgoing is destination
                or self.design not in (outgoing, destination)
                or not window.style().styleHint(QStyle.StyleHint.SH_Widget_Animate)):
            self._clear()
            return
        area = self.tabs.geometry()
        for dock in self.docks:
            if dock.isVisible() and not dock.isFloating():
                area = area.united(dock.geometry())
        # A quick reversal captures the partially faded overlay as it appears now.
        image = window.grab(area)
        self._animation.stop()
        self._image = image
        self.setGeometry(area)
        self.show()
        self.raise_()
        self._animation.start()

    def _clear(self):
        self._animation.stop()
        self.hide()
        self._image = None

    def paintEvent(self, event):
        if self._image is not None:
            painter = QPainter(self)
            painter.setOpacity(float(self._animation.currentValue()))
            painter.drawPixmap(0, 0, self._image)

"""Align the input/output tab strip with the docked workspace columns."""

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTabBar


class InputPreview(QPlainTextEdit):
    editingFinished = Signal()
    revertRequested = Signal()

    def __init__(self):
        super().__init__()
        self.pending = False
        self.base_ref = None
        self.setTabChangesFocus(True)
        self.textChanged.connect(self._edited)

    def _edited(self):
        self.pending = not self.isReadOnly()

    def display(self, text, base_ref, *, editable=True):
        self.pending = False
        self.base_ref = base_ref
        self.setReadOnly(not editable)
        if self.toPlainText() != text:
            cursor = self.textCursor()
            line, column = cursor.blockNumber(), cursor.positionInBlock()
            scroll = self.verticalScrollBar().value()
            with QSignalBlocker(self):
                self.setPlainText(text)
                block = self.document().findBlockByNumber(min(line, self.blockCount() - 1))
                cursor = self.textCursor()
                cursor.setPosition(block.position() + min(column, block.length() - 1))
                self.setTextCursor(cursor)
                self.verticalScrollBar().setValue(scroll)
        self.document().setModified(False)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.pending and not QApplication.activePopupWidget() and not QApplication.mouseButtons():
            self.editingFinished.emit()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self.pending and event.reason() != Qt.FocusReason.PopupFocusReason:
            self.editingFinished.emit()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.pending and not self.rect().contains(self.mapFromGlobal(event.globalPosition().toPoint())):
            self.editingFinished.emit()

    def keyPressEvent(self, event):
        if self.pending and event.key() == Qt.Key.Key_Escape:
            self.revertRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class PreviewTabBar(QTabBar):
    def __init__(self, parent, workspace, left_dock, right_dock):
        super().__init__(parent)
        self.setObjectName("previewTabBar")
        self.setDrawBase(False)
        self._workspace = workspace
        self._left_dock = left_dock
        self._right_dock = right_dock
        self._widths = ()
        # Measure after QMainWindow has positioned every dock in this layout pass.
        self._align = QTimer(self)
        self._align.setSingleShot(True)
        self._align.timeout.connect(self._align_tabs)
        for widget in (self, parent, workspace, left_dock, right_dock):
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show, QEvent.Type.Hide):
            self._align.start(0)
        return super().eventFilter(watched, event)

    def _align_tabs(self):
        if not self.isVisible() or self.count() != 3:
            return
        # The tab widget may initially place its native bar at the natural
        # text width; size the strip from the entire available panel.
        width = self.parentWidget().contentsRect().width()
        first, second = round(width / 3), round(2 * width / 3)
        if (self.window() is self._workspace.window()
                and self._left_dock.isVisible() and not self._left_dock.isFloating()
                and self._right_dock.isVisible() and not self._right_dock.isFloating()):
            left = self.mapFromGlobal(self._workspace.mapToGlobal(QPoint(0, 0))).x()
            right = self.mapFromGlobal(self._right_dock.mapToGlobal(QPoint(0, 0))).x()
            if 0 < left < right < width:
                first, second = left, right
        widths = (first, second - first, width - second)
        if any(w < self.minimumTabSizeHint(i).width() for i, w in enumerate(widths)):
            widths = ()  # A narrow floating dock can use Qt's scroll buttons.
        if widths != self._widths:
            self._widths = widths
            # QTabBar caches style-derived tab sizes even when the bar's own
            # geometry stays fixed (for example while a sidebar is dragged).
            QCoreApplication.sendEvent(self, QEvent(QEvent.Type.StyleChange))

    def tabSizeHint(self, index):
        hint = super().tabSizeHint(index)
        if 0 <= index < len(self._widths):
            hint.setWidth(self._widths[index])
        return hint

    def minimumTabSizeHint(self, index):
        # Keep the native text size as the minimum, independent of dock widths.
        return super().tabSizeHint(index)

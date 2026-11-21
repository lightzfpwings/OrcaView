"""A compact periodic table for selecting the element used by the design tools."""

from PySide6.QtCore import QPoint, QRectF, Qt, QEvent
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHeaderView, QLabel, QLineEdit, QStyle,
    QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from orcaview.core.elements import ATOMIC_NUMBERS
from orcaview.i18n import tr


def _table_position(number):
    """Return zero-based period/group indices, with the f block on two extra rows."""
    if number <= 2:
        return 0, 0 if number == 1 else 17
    if number <= 18:
        row, column = divmod(number - 3, 8)
        return row + 1, column if column < 2 else column + 10
    if number <= 54:
        row, column = divmod(number - 19, 18)
        return row + 3, column
    row, column = divmod(number - 55, 32)
    if 2 <= column <= 16:
        return row + 7, column
    return row + 5, column if column < 2 else column - 14


class _ElementDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        number = index.data(Qt.ItemDataRole.UserRole)
        if number is None:
            super().paint(painter, option, index)
            return
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tile = QRectF(option.rect).adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor("#904359" if selected else "#E0D9D1")))
        painter.setBrush(QColor("#904359" if selected else "#FFFDF9"))
        painter.drawRoundedRect(tile, 3, 3)
        font = option.font
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(QColor("white" if selected else "#70635F"))
        painter.drawText(tile.adjusted(3, 1, -1, 0), Qt.AlignmentFlag.AlignTop, str(number))
        font.setBold(True)
        font.setPixelSize(14)
        painter.setFont(font)
        painter.setPen(QColor("white" if selected else "#372F2D"))
        painter.drawText(tile.adjusted(0, 6, 0, 0), Qt.AlignmentFlag.AlignCenter, index.data())
        painter.restore()


class _ElementPopup(QFrame):
    def __init__(self, combo):
        super().__init__(combo, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.combo = combo
        self.setObjectName("elementPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        self.setStyleSheet("""
            QFrame#elementPopup { background: #FAF7F2; border: 1px solid #CFC4B9; }
            QTableWidget { background: #FAF7F2; border: none; }
            QHeaderView::section, QTableCornerButton::section {
                background: #FAF7F2; border: none; color: #70635F; font-size: 10px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        layout.addWidget(QLabel(tr("元素周期表")))
        self.search = QLineEdit()
        self.search.setObjectName("elementSearch")
        self.search.setAccessibleName(tr("元素符号或原子序数"))
        self.search.setPlaceholderText(tr("元素符号或原子序数"))
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.table = QTableWidget(9, 18)
        self.table.setObjectName("periodicTable")
        self.table.setAccessibleName(tr("元素周期表"))
        self.table.setItemDelegate(_ElementDelegate(self.table))
        self.table.setShowGrid(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setHorizontalHeaderLabels([str(i) for i in range(1, 19)])
        self.table.setVerticalHeaderLabels(["1", "2", "3", "4", "5", "6", "7", "6*", "7**"])
        for header, size, tip in ((self.table.horizontalHeader(), 35, tr("族")),
                                  (self.table.verticalHeader(), 33, tr("周期"))):
            header.setToolTip(tip)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            header.setMinimumSectionSize(size)
            header.setDefaultSectionSize(size)
        self.cells = {}
        for symbol, number in ATOMIC_NUMBERS.items():
            item = QTableWidgetItem(symbol)
            item.setData(Qt.ItemDataRole.UserRole, number)
            item.setToolTip(f"{number} · {symbol}")
            self.table.setItem(*_table_position(number), item)
            self.cells[symbol] = item
        for row, text in ((5, "*"), (6, "**")):
            item = QTableWidgetItem(text)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item)
        layout.addWidget(self.table, 1)
        self.search.textChanged.connect(self._search)
        self.search.returnPressed.connect(lambda: self._choose(self.table.currentItem()))
        self.table.itemClicked.connect(self._choose)
        self.table.installEventFilter(self)
        self.search.installEventFilter(self)

    def open_at_combo(self):
        self.search.clear()
        self.table.setCurrentItem(self.cells[self.combo.currentText()])
        self.layout().activate()
        self.ensurePolished()
        # Keep all cells visible when possible. On a smaller display Qt supplies
        # scrollbars, and symbol/number search still reaches the last element.
        size = self.layout().sizeHint()
        size.setWidth(self.table.horizontalHeader().length() + self.table.verticalHeader().width() + 20)
        size.setHeight(size.height() - self.table.sizeHint().height() + self.table.verticalHeader().length()
                       + self.table.horizontalHeader().height() + 4)
        bounds = self.combo.screen().availableGeometry()
        self.resize(size.boundedTo(bounds.size()))
        below = self.combo.mapToGlobal(QPoint(0, self.combo.height()))
        above = self.combo.mapToGlobal(QPoint(0, 0)).y() - self.height()
        y = below.y() if below.y() + self.height() <= bounds.bottom() + 1 else above
        self.move(max(bounds.left(), min(below.x(), bounds.right() + 1 - self.width())),
                  max(bounds.top(), min(y, bounds.bottom() + 1 - self.height())))
        self.show()
        self.search.setFocus()

    def _search(self, text):
        query = text.strip().casefold()
        found = self.cells.get(self.combo.currentText()) if not query else None
        for symbol, number in ATOMIC_NUMBERS.items():
            if symbol.casefold() == query or str(number) == query:
                found = self.cells[symbol]
                break
            if query and found is None and symbol.casefold().startswith(query):
                found = self.cells[symbol]
        self.table.setCurrentItem(found)
        if found is not None:
            self.table.scrollToItem(found)

    def _choose(self, item):
        if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
            return
        index = self.combo.findText(item.text())
        self.combo.setCurrentIndex(index)
        self.combo.hidePopup()
        self.combo.activated.emit(index)
        self.combo.textActivated.emit(item.text())

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.combo.hidePopup()
                return True
            if obj is self.search and key == Qt.Key.Key_Down:
                self.table.setFocus()
                return True
            if obj is self.table and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self._choose(self.table.currentItem())
                return True
            steps = {Qt.Key.Key_Left: (0, -1), Qt.Key.Key_Right: (0, 1),
                     Qt.Key.Key_Up: (-1, 0), Qt.Key.Key_Down: (1, 0)}
            if obj is self.table and key in steps:
                row, col = self.table.currentRow(), self.table.currentColumn()
                dy, dx = steps[key]
                row, col = row + dy, col + dx
                while 0 <= row < self.table.rowCount() and 0 <= col < self.table.columnCount():
                    item = self.table.item(row, col)
                    if item and item.data(Qt.ItemDataRole.UserRole) is not None:
                        self.table.setCurrentItem(item)
                        break
                    row, col = row + dy, col + dx
                return True
        return super().eventFilter(obj, event)


class ElementPicker(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.addItems(list(ATOMIC_NUMBERS))
        self.setCurrentText("C")
        self._popup = None

    def showPopup(self):
        if self._popup is None:
            self._popup = _ElementPopup(self)
        self._popup.open_at_combo()

    def hidePopup(self):
        if self._popup is not None:
            self._popup.hide()
        super().hidePopup()

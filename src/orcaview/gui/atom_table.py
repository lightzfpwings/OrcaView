"""Column layout for the read-only Cartesian coordinate table."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QStyledItemDelegate, QTableWidget

from orcaview.gui.typography import fixed_font
from orcaview.i18n import tr


class _CoordinateDelegate(QStyledItemDelegate):
    field_length = len("-0.000000")

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # Center a common numeric field. Figure spaces reserve the sign and
        # integer places without adding padding to the actual cell value.
        option.text = option.text.rjust(self.field_length, "\u2007")
        option.displayAlignment = Qt.AlignmentFlag.AlignCenter


class AtomCoordinateTable(QTableWidget):
    def __init__(self):
        super().__init__(0, 6)
        self.setObjectName("foundationAtoms")
        self.setHorizontalHeaderLabels((tr("序号"), tr("元素"), tr("结果"), "X", "Y", "Z"))
        self.horizontalHeaderItem(0).setToolTip(tr("当前几何快照的原子序号，从 1 开始"))
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setMinimumWidth(230)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(37)
        header = self.horizontalHeader()
        header.setSectionsClickable(False)
        header.setSortIndicatorShown(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.coordinate_font = fixed_font()
        self._coordinates = _CoordinateDelegate(self)
        for column in (3, 4, 5):
            self.setItemDelegateForColumn(column, self._coordinates)

    def fit_columns(self, longest_coordinate):
        self._coordinates.field_length = max(len("-0.000000"), longest_coordinate)
        if not self.isColumnHidden(2):
            self.resizeColumnToContents(2)
        self._size_columns()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._size_columns()

    def _size_columns(self):
        # Split any spare width 3:3:4:4:4. Below the natural text width,
        # retain complete numbers and let the viewport scroll horizontally.
        available = self.viewport().width() - self.columnWidth(2)
        metrics = QFontMetrics(self.coordinate_font)
        margin = 18  # cell padding, native focus margins and grid line
        coordinate_minimum = metrics.horizontalAdvance("0" * self._coordinates.field_length) + margin
        # Let the two short identity columns give up spare padding first.
        # Keep room for both header labels as well as multi-digit atom indices.
        identity_text = (self.horizontalHeaderItem(0).text(), self.horizontalHeaderItem(1).text(),
                         str(self.rowCount()))
        identity_minimum = max(self.fontMetrics().horizontalAdvance(label) for label in identity_text) + margin
        identity_width = max(identity_minimum, min(available // 6, (available - 3 * coordinate_minimum) // 2))
        coordinate_width = max(coordinate_minimum, (available - 2 * identity_width) // 3)
        for column in (0, 1):
            self.setColumnWidth(column, identity_width)
        for column in (3, 4, 5):
            self.setColumnWidth(column, coordinate_width)

"""Read-only result cells and tab-separated clipboard export."""

import csv
from io import StringIO

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHeaderView, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem,
)

from orcaview.i18n import tr


def _copy_table(table, *, entire=False):
    model = table.model()
    selection = None
    if entire:
        rows = range(model.rowCount())
        columns = range(model.columnCount())
    else:
        selection = {(i.row(), i.column()) for i in table.selectionModel().selectedIndexes()
                     if not table.isColumnHidden(i.column()) and not table.isRowHidden(i.row())}
        if not selection:
            return
        rows = sorted({row for row, _ in selection})
        left, right = min(col for _, col in selection), max(col for _, col in selection)
        columns = range(left, right + 1)
    columns = [col for col in columns if not table.isColumnHidden(col)]
    if not rows or not columns:
        return
    output = StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    if entire:
        writer.writerow(model.headerData(col, Qt.Orientation.Horizontal) for col in columns)
    for row in rows:
        if not table.isRowHidden(row):
            writer.writerow(model.index(row, col).data() if selection is None or (row, col) in selection
                            else "" for col in columns)
    QApplication.clipboard().setText(output.getvalue().removesuffix("\n"))


def enable_table_copy(table):
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
    selected = QAction(tr("Copy selection"), table)
    selected.setShortcuts(QKeySequence.StandardKey.Copy)
    selected.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
    selected.triggered.connect(lambda: _copy_table(table))
    entire = QAction(tr("Copy entire table (with headers)"), table)
    entire.triggered.connect(lambda: _copy_table(table, entire=True))
    table.addActions([selected, entire])


class _CompactResultCell(QStyledItemDelegate):
    """Keep the summary compact while copying the model's original precision."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        width = option.rect.width() or self.parent().columnWidth(index.column())
        available = width - 12  # horizontal item padding and focus margins
        if available <= 0 or option.fontMetrics.horizontalAdvance(option.text) <= available:
            return
        number, _, unit = option.text.partition(" ")
        try:
            value = float(number)
        except ValueError:
            return
        if option.fontMetrics.horizontalAdvance(number) > available:
            for digits in range(15, 0, -1):
                number = format(value, f".{digits}g")
                if option.fontMetrics.horizontalAdvance(number) <= available:
                    break
        option.text = "\n".join(part for part in (number, unit) if part)


class CalculationResultTable(QTableWidget):
    def __init__(self):
        super().__init__(0, 4)
        self.setObjectName("resultDatasets")
        self.setAccessibleName(tr("Calculation results"))
        self.setHorizontalHeaderLabels((tr("Name"), tr("Result"), tr("Name"), tr("Result")))
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setWordWrap(True)
        self.verticalHeader().hide()
        self.verticalHeader().setMinimumSectionSize(28)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header = self.horizontalHeader()
        header.setSectionsClickable(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setMinimumSectionSize(1)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for column in (1, 3):
            self.setItemDelegateForColumn(column, _CompactResultCell(self))
        enable_table_copy(self)

    def name_item(self, cell):
        """Both cells of a result resolve to its name; the unused pair does not."""
        if cell is None or not cell.flags() & Qt.ItemFlag.ItemIsEnabled:
            return None
        return self.item(cell.row(), cell.column() - cell.column() % 2)

    def add_result(self, name, value, *, tooltip=""):
        row = self.rowCount() - 1
        if row >= 0 and not self.item(row, 2).flags() & Qt.ItemFlag.ItemIsEnabled:
            first = 2
        else:
            row += 1
            first = 0
            self.insertRow(row)
            for column in (2, 3):
                empty = QTableWidgetItem()
                empty.setFlags(Qt.ItemFlag.NoItemFlags)
                self.setItem(row, column, empty)
        for column, text in enumerate((name, value), first):
            cell = QTableWidgetItem(str(text))
            cell.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            cell.setToolTip(tooltip)
            cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, column, cell)
        return self.item(row, first)


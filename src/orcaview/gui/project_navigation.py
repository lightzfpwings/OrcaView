"""Project navigation with a flush text column and native disclosure controls."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QTextLayout, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QTreeWidget, QTreeWidgetItem,
)
from orcaview.i18n import tr


class WrappingTreeLabel(QStyledItemDelegate):
    """Wrap a flat text column to its available width, keeping the model text intact."""

    def __init__(self, tree):
        super().__init__(tree)
        tree.header().sectionResized.connect(lambda *_: tree.scheduleDelayedItemsLayout())

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        tree = self.parent()
        width = tree.columnWidth(0)
        if not option.text or width <= 0:
            return
        # The same native text rectangle is used when Qt asks for the row
        # height and when it paints. Account for the theme's item padding.
        measure = QStyleOptionViewItem(option)
        measure.rect = QRect(0, 0, width, option.fontMetrics.height() * 2)
        style = tree.style()
        area = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, measure, tree)
        margin = style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, measure, tree) + 1
        available = max(1, area.width() - 2 * margin)
        text = option.text.replace("\n", "\u2028")
        if "\u2028" not in text and option.fontMetrics.horizontalAdvance(text) <= available:
            return

        # Native item delegates only wrap at words. Ask the text engine for
        # grapheme-safe line ends within a long filename, then let the native
        # delegate paint the resulting lines, including focus and selection.
        layout = QTextLayout(text, option.font)
        wrapping = QTextOption()
        wrapping.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(wrapping)
        encoded = text.encode("utf-16-le")
        lines = []
        layout.beginLayout()
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(available)
            start = line.textStart() * 2
            end = start + line.textLength() * 2
            lines.append(encoded[start:end].decode("utf-16-le").rstrip("\u2028"))
        layout.endLayout()
        option.text = "\u2028".join(lines)


class ProjectNavigationTree(QTreeWidget):
    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setColumnCount(2)
        # The trailing column holds Qt's native branch arrow. All names
        # start at the same position in the first column, at every depth.
        self.setTreePosition(1)
        self.setIndentation(16)
        header = self.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(1)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, self.indentation())
        self.setItemDelegateForColumn(0, WrappingTreeLabel(self))
        self.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def set_structure(self, name):
        self.clear()
        root = QTreeWidgetItem(self, [tr("当前项目")])
        root.setToolTip(0, root.text(0))
        for text in (tr("结构  ·  {name}", name=name), tr("计算设置  ·  ORCA"), tr("输入预览")):
            child = QTreeWidgetItem(root, [text])
            child.setToolTip(0, text)
        root.setExpanded(True)

"""Shared columns for the calculation inspector and its expandable input blocks."""

import re

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QFrame, QGridLayout, QLabel, QScrollArea, QSizePolicy,
    QStylePainter, QWidget,
)


def wrap_parameter_text(text):
    """Allow a displayed ORCA identifier to wrap at its natural word boundaries."""
    return re.sub(r"(?<=[._])(?=[A-Za-z])|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
                  "\u200b", text)


class InspectorLabel(QLabel):
    """Wrap a sidebar caption, including a translated word wider than the dock."""

    def __init__(self, text="", *, reserve_text=None):
        super().__init__(text)
        # Validation reserves the height of its success caption for all diagnostics.
        self.reserve_text = reserve_text
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        policy = self.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        self.setSizePolicy(policy)

    def _measure(self, text, width):
        area = QRect(0, 0, max(1, width), 0)
        metrics = self.fontMetrics()
        wrap = Qt.TextFlag.TextWordWrap
        bounds = metrics.boundingRect(area, wrap, text)
        if bounds.width() > area.width():
            wrap = Qt.TextFlag.TextWrapAnywhere
            bounds = metrics.boundingRect(area, wrap, text)
        return wrap, bounds.height()

    def heightForWidth(self, width):
        margins = self.contentsMargins()
        _, height = self._measure(self.reserve_text or self.text(), width - margins.left() - margins.right())
        return margins.top() + height + margins.bottom()

    def sizeHint(self):
        return QSize(0, self.heightForWidth(self.width()))

    def minimumSizeHint(self):
        margins = self.contentsMargins()
        return QSize(0, self.fontMetrics().height() + margins.top() + margins.bottom())

    def paintEvent(self, event):
        QFrame.paintEvent(self, event)
        painter = QStylePainter(self)
        rect = self.contentsRect()
        text = self.text()
        wrap, height = self._measure(text, rect.width())
        if self.reserve_text and height > rect.height():
            # Use the reserved lines for the diagnostic, keeping its full text in the tooltip.
            low, high = 0, len(text)
            while low < high:
                end = (low + high + 1) // 2
                _, height = self._measure(text[:end].rstrip() + "…", rect.width())
                if height <= rect.height():
                    low = end
                else:
                    high = end - 1
            text = text[:low].rstrip() + "…"
            wrap, _ = self._measure(text, rect.width())
        flags = int(self.alignment()) | wrap.value
        painter.drawItemText(rect, flags, self.palette(), self.isEnabled(), text, self.foregroundRole())


class InspectorScrollArea(QScrollArea):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        panel = self.widget()
        if panel is not None:
            # Retain space for the editors and the disclosure button in the 1/8 sidebar.
            inset = max(6, min(16, (self.width() - 128) // 10))
            panel.layout().setContentsMargins(inset, 18, inset, 14)


class InspectorForm(QWidget):
    """A two-column settings form that stacks whole rows in a narrow dock."""

    def __init__(self, *, spacing=8):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(spacing)
        self.grid.setColumnStretch(1, 1)
        self._rows = []
        self._labels = {}
        self._stacked = False

    def addRow(self, label, field=None):
        # A lone widget (e.g. method help) spans the form. A field with a None
        # label (e.g. Restore defaults) follows the editor column.
        spanning = field is None
        if spanning:
            field, label = label, None
        if isinstance(label, str):
            label = QLabel(label)
        if label is not None:
            label.setBuddy(field)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        if not spanning:
            field.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        if isinstance(field, (QComboBox, QAbstractSpinBox)):
            field.installEventFilter(self)
        field.setAttribute(Qt.WidgetAttribute.WA_LayoutUsesWidgetRect)
        self._labels[field] = label
        self._rows.append((label, field, spanning))
        self._place_row(len(self._rows) - 1)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def labelForField(self, field):
        return self._labels[field]

    def setRowVisible(self, field, visible):
        label = self._labels[field]
        if label is not None:
            label.setVisible(visible)
        field.setVisible(visible)

    def isRowVisible(self, field):
        return not field.isHidden()

    def _place_row(self, index):
        label, field, spanning = self._rows[index]
        row = 2 * index
        if spanning:
            self.grid.addWidget(field, row, 0, 1, 2)
            return
        if label is not None:
            self.grid.addWidget(label, row, 0, 1, 2 if self._stacked else 1)
        if self._stacked:
            self.grid.addWidget(field, row + 1, 0, 1, 2)
        else:
            self.grid.addWidget(field, row, 1, Qt.AlignmentFlag.AlignVCenter)

    def resizeEvent(self, event):
        width = event.size().width()
        em = max(1, self.fontMetrics().height())
        # Independent blocks receive the same available width. Their contents
        # and disclosure state have no influence on the position of a column.
        stacked = width < 19 * em
        self.grid.setColumnMinimumWidth(0, 0 if stacked else min(round(width * 0.43), 14 * em))
        if self._stacked != stacked:
            self._stacked = stacked
            for i, (label, field, _) in enumerate(self._rows):
                if label is not None:
                    self.grid.removeWidget(label)
                self.grid.removeWidget(field)
                self._place_row(i)
        super().resizeEvent(event)

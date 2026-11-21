"""A checkable drawing tool with the element picker's native dropdown indicator."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QPushButton, QSizePolicy, QStyle, QStyleOptionButton,
                               QStyleOptionComboBox, QStylePainter)


class ToolbarMenuButton(QPushButton):
    def __init__(self, element_picker):
        super().__init__()
        self._element_picker = element_picker
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return self._element_picker.sizeHint()

    def _combo_option(self):
        combo = QStyleOptionComboBox()
        self._element_picker.initStyleOption(combo)
        combo.initFrom(self)
        return combo

    def _subcontrol_rect(self, option, part):
        style = self._element_picker.style()
        return style.subControlRect(QStyle.ComplexControl.CC_ComboBox, option, part, self._element_picker)

    def arrow_rect(self):
        rect = self._subcontrol_rect(self._combo_option(), QStyle.SubControl.SC_ComboBoxArrow)
        # Native bezel metrics can include half of a compact button in the arrow.
        # Keep its centre available for the primary tool even without a stylesheet.
        width = min(rect.width(), max(1, self.width() // 3))
        if self.layoutDirection() == Qt.LayoutDirection.LeftToRight:
            rect.setLeft(rect.right() - width + 1)
        else:
            rect.setWidth(width)
        return rect

    def paintEvent(self, event):
        painter = QStylePainter(self)
        face = QStyleOptionButton()
        self.initStyleOption(face)
        face.features &= ~QStyleOptionButton.ButtonFeature.HasMenu
        face.icon = QIcon()
        painter.drawControl(QStyle.ControlElement.CE_PushButton, face)

        # Ask the neighbouring element picker for its platform's disclosure and layout.
        combo = self._combo_option()
        style = self._element_picker.style()
        painter.save()
        painter.setClipRect(self._subcontrol_rect(combo, QStyle.SubControl.SC_ComboBoxArrow))
        style.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, combo, painter, self._element_picker)
        painter.restore()
        field = self._subcontrol_rect(combo, QStyle.SubControl.SC_ComboBoxEditField)
        bounds = QRect(field.topLeft(), self.iconSize())
        bounds.moveCenter(field.center())
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        self.icon().paint(painter, bounds, Qt.AlignmentFlag.AlignCenter, mode)

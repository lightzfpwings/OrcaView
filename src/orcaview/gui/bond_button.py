"""Split controls for choosing a bond family and its drawing variant."""

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QMenu

from orcaview.gui.bond_drawing import bond_icon
from orcaview.gui.toolbar_menu_button import ToolbarMenuButton
from orcaview.i18n import tr


def _choices(order):
    if order == 1:
        return (
            ("plain", tr("Single bond")), ("coordinate", tr("Coordinate bond (dashed)")),
            ("coordinate_arrow", tr("Coordinate bond (arrow)")), ("wedge", tr("Solid wedge")),
            ("hashed_wedge", tr("Hashed wedge")), ("hollow_wedge", tr("Hollow wedge")),
            ("wavy", tr("Wavy bond")), ("wavy_wedge", tr("Wavy wedge")),
            ("hashed", tr("Hashed bond")), ("bold", tr("Bold single bond")),
        )
    if order == 2:
        return (
            ("plain", tr("Double bond")), ("aromatic", tr("Aromatic bond (solid and dashed, 1.5)")),
            ("crossed", tr("Crossed double bond (unspecified configuration)")), ("bold", tr("Bold double bond")),
            ("dashed", tr("Dashed double bond")),
        )
    return (("plain", tr("Triple bond")), ("partial_triple", tr("Partial triple bond (two solid, one dashed, 2.5)")))


class BondButton(ToolbarMenuButton):
    activated = Signal(int, str)

    def __init__(self, order, element_picker):
        super().__init__(element_picker)
        self.order = order
        self.setObjectName(f"designBond{order}")
        self.setIconSize(QSize(24, 16))
        self.options_menu = QMenu(self)
        self.options_menu.setObjectName(f"designBond{order}Menu")
        self._choices = QActionGroup(self)
        for style, label in _choices(order):
            action = self.options_menu.addAction(bond_icon(order, style), label)
            action.setIconVisibleInMenu(True)
            action.setData(style)
            action.setCheckable(True)
            self._choices.addAction(action)
            if style == "plain":
                action.setChecked(True)
                self._use_appearance(action)
        self.options_menu.triggered.connect(self._choose)
        self.clicked.connect(self._activate)

    def _use_appearance(self, action):
        self.setIcon(action.icon())
        self.setToolTip(action.text())
        self.setAccessibleName(action.text())

    def _choose(self, action):
        self._use_appearance(action)
        self.setChecked(True)
        self._activate()

    def _activate(self):
        self.activated.emit(self.order, self._choices.checkedAction().data())

    def _open(self):
        self.options_menu.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        self.options_menu.popup(self.mapToGlobal(QPoint(0, self.height())))
        self.options_menu.setActiveAction(self._choices.checkedAction())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.arrow_rect().contains(event.position().toPoint()):
            self._open()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Down:
            self._open()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)

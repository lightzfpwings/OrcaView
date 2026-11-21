"""Icon-only ring menu in the molecular drawing toolbar."""

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

from orcaview.gui.toolbar_menu_button import ToolbarMenuButton


def _benzene_icon():
    pixmap = QPixmap(72, 72)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setWindow(0, 0, 24, 24)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#493E3A"), 1.65, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in
                        ((12, 2), (20.7, 7), (20.7, 17), (12, 22), (3.3, 17), (3.3, 7))]))
    for start, end in (((12.3, 5.6), (17.6, 8.7)), ((17.6, 15.3), (12.3, 18.4)),
                       ((6.3, 15.1), (6.3, 8.9))):
        painter.drawLine(QPointF(*start), QPointF(*end))
    painter.end()
    return QIcon(pixmap)


class RingTemplateButton(ToolbarMenuButton):
    def __init__(self, element_picker):
        super().__init__(element_picker)
        self.setIcon(_benzene_icon())
        self.setIconSize(QSize(18, 18))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.showMenu()
            event.accept()
            return
        super().keyPressEvent(event)

"""轻量投影视口，验证选择、旋转和缩放；将来可替换为 VTK 适配器。"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QWidget

from orcaview.i18n import tr

from orcaview.core.elements import ELEMENT_COLORS
from orcaview.core.geometry import infer_bonds
from orcaview.core.point_group import geometric_symmetry
from orcaview.core.symmetry import DEFAULT_TOLERANCE


# Schematic sphere sizes in Å, chosen for the ball-and-stick view.
_BALL_RADII = {"H": 0.19, "C": 0.32, "N": 0.33, "O": 0.34}
_CANVAS = QColor("#FFFDFA")
_ACCENT = QColor("#904359")
_MUTED = QColor("#70635F")
_INPUT_FRAME = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))
_AZIMUTH_COS = math.cos(math.radians(30))
_AZIMUTH_SIN = math.sin(math.radians(30))


def _principal_frame(direction):
    """Rows of a right-handed basis, expressed in the input coordinate system."""
    if direction is None:
        return _INPUT_FRAME
    # Keep the input x direction as far as the new z direction allows.
    reference = _INPUT_FRAME[0] if abs(direction[0]) < 0.95 else _INPUT_FRAME[1]
    component = sum(a * b for a, b in zip(reference, direction))
    projected = tuple(a - component * b for a, b in zip(reference, direction))
    length = math.hypot(*projected)
    x = tuple(value / length for value in projected)
    a, b, c = direction
    y = (b * x[2] - c * x[1], c * x[0] - a * x[2], a * x[1] - b * x[0])
    return x, y, direction


class MoleculeViewport(QWidget):
    selection_changed = Signal(list)

    def __init__(self, parent=None, *, result_view=False):
        super().__init__(parent)
        self._result_view = result_view
        self.molecule = None
        self._frame = _INPUT_FRAME
        self._point_group_label = ""
        self.symmetry_label = ""
        self.principal_axis = None
        self.selected = []
        self.labels = False
        self.yaw, self.pitch, self.zoom = 0.32, -0.40, 1.0
        self._projected = []
        self._press = self._last = None
        self._dragged = False
        self.setMinimumSize(360, 300)
        self.setMouseTracking(True)

    def set_molecule(self, molecule):
        self.molecule = molecule
        self.bonds = molecule.bonds or infer_bonds(molecule)
        group, self.principal_axis = geometric_symmetry(molecule)
        self._frame = _principal_frame(self.principal_axis.direction)
        if self.principal_axis.direction is None:
            alignment = tr("沿用输入坐标轴")
        else:
            order = "∞" if math.isinf(self.principal_axis.order) else str(self.principal_axis.order)
            alignment = tr("C{order} 主轴 ∥ z", order=order)
        self._point_group_label = tr("几何点群 {group}", group=group)
        self.symmetry_label = f"{self._point_group_label}  ·  {alignment}"
        self.setAccessibleDescription(self.symmetry_label)
        self.setToolTip(self.symmetry_label + "\n" + tr("几何匹配容差 {tolerance:g} Å。原子表及 ORCA 输入使用原始坐标。", tolerance=DEFAULT_TOLERANCE))
        self.selected = []
        # Pending clicks belong to the previous frame until paintEvent projects the new atoms.
        self._projected = []
        self._press = self._last = None
        self._dragged = False
        self.fit()
        self.selection_changed.emit([])

    def fit(self):
        if self.principal_axis and self.principal_axis.direction is not None:
            # A side view keeps the atoms of a linear molecule individually visible.
            self.yaw = 0.0
            self.pitch = math.radians(-75 if math.isinf(self.principal_axis.order) else -35)
        else:
            self.yaw, self.pitch = 0.32, -0.40
        self.zoom = 1.0
        self.update()

    def transform(self, x, y, z):
        local = tuple(a * x + b * y + c * z for a, b, c in self._frame)
        return self.camera_transform(*local)

    def camera_transform(self, x, y, z):
        # The axis triad is already in the local frame. Apply only the camera to it.
        if self.principal_axis and self.principal_axis.direction is not None:
            x, y = x * _AZIMUTH_COS - y * _AZIMUTH_SIN, x * _AZIMUTH_SIN + y * _AZIMUTH_COS
        x, z = x * math.cos(self.yaw) + z * math.sin(self.yaw), -x * math.sin(self.yaw) + z * math.cos(self.yaw)
        y, z = y * math.cos(self.pitch) - z * math.sin(self.pitch), y * math.sin(self.pitch) + z * math.cos(self.pitch)
        return x, y, z

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), _CANVAS)
        if self.molecule is None:
            return
        atoms = self.molecule.atoms
        center = tuple(sum(getattr(a, key) for a in atoms) / len(atoms) for key in ("x", "y", "z"))
        radius = max(math.sqrt(sum((getattr(a, key) - c) ** 2 for key, c in zip(("x", "y", "z"), center))) for a in atoms)
        scale = min(self.width(), self.height()) * 0.32 / max(radius, 1.2) * self.zoom
        self._projected = []
        for atom in atoms:
            x, y, z = self.transform(atom.x - center[0], atom.y - center[1], atom.z - center[2])
            size = max(1.5, _BALL_RADII.get(atom.element, 0.32) * scale)
            self._projected.append((self.width() / 2 + x * scale, self.height() / 2 - y * scale, z, size))
        for bond in self.bonds:
            a, b = self._projected[bond.a], self._projected[bond.b]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 0.01:
                continue
            radius = max(0.7, (0.062 if "H" in (atoms[bond.a].element, atoms[bond.b].element) else 0.083) * scale)
            # Shade across the stick, with a consistent light direction on rotation.
            nx, ny = dy / length, -dx / length
            if nx * -0.36 + ny * -0.52 < 0:
                nx, ny = -nx, -ny
            shade = QLinearGradient(a[0] + nx * radius, a[1] + ny * radius,
                                    a[0] - nx * radius, a[1] - ny * radius)
            shade.setColorAt(0, QColor("#9BA7A9"))
            shade.setColorAt(0.38, QColor("#909DA0"))
            shade.setColorAt(1, QColor("#6B777A"))
            painter.setPen(QPen(QBrush(shade), 2 * radius, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
        for index in sorted(range(len(atoms)), key=lambda i: self._projected[i][2]):
            x, y, z, size = self._projected[index]
            color = QColor(ELEMENT_COLORS.get(atoms[index].element, "#aa88bb"))
            gradient = QRadialGradient(QPointF(x - size * 0.28, y - size * 0.36), size * 1.47)
            gradient.setColorAt(0, color.lighter(110))
            gradient.setColorAt(0.42, color)
            gradient.setColorAt(0.78, color.darker(114))
            gradient.setColorAt(1, color.darker(140))
            painter.setBrush(gradient)
            painter.setPen(QPen(color.darker(128), 0.8))
            painter.drawEllipse(QPointF(x, y), size, size)
            if self.labels and index not in self.selected:
                painter.setPen(_MUTED)
                painter.drawText(QPointF(x + size + 5, y - size - 2), "{}{}".format(atoms[index].element, index + 1))
        # Table selection may address an atom behind another in this projection.
        if self.selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_ACCENT, 2))
            for index in self.selected:
                x, y, _, radius = self._projected[index]
                painter.drawEllipse(QPointF(x, y), radius + 4, radius + 4)
                label = f"{atoms[index].element}{index + 1}"
                metrics = painter.fontMetrics()
                label_x = min(x + radius + 7, self.width() - metrics.horizontalAdvance(label) - 4)
                label_y = max(y - radius * 0.7, metrics.ascent() + 4)
                bounds = metrics.boundingRect(label).translated(round(label_x), round(label_y))
                painter.fillRect(bounds.adjusted(-2, -1, 2, 1), _CANVAS)
                painter.drawText(QPointF(label_x, label_y), label)
            names = "、".join(f"{atoms[index].element}{index + 1}" for index in self.selected)
            selection_text = tr("已选  ") + names
            painter.setPen(_ACCENT)
            painter.drawText(self.width() - 18 - painter.fontMetrics().horizontalAdvance(selection_text),
                             26, selection_text)
        painter.setPen(_MUTED)
        if self._result_view:
            painter.drawText(18, 26, tr("哑光球棍"))
            painter.drawText(18, 47, self._point_group_label)
        else:
            painter.drawText(18, 26, tr("几何  /  Å     ·     哑光球棍"))
            painter.drawText(18, 47, self.symmetry_label)
        self._draw_axes(painter)

    def _draw_axes(self, painter):
        # 轴标随相机旋转，避免固定标签误导空间方向。
        origin = QPointF(self.width() - 48, self.height() - 52)
        axes = zip(_INPUT_FRAME, "xyz", ("#AC534C", "#397E60", "#386FA7"))
        directions = [(self.camera_transform(*vector), label, QColor(color)) for vector, label, color in axes]
        end_on = None
        for (x, y, z), label, color in sorted(directions, key=lambda axis: axis[0][2]):
            offset = QPointF(33 * x, -33 * y)
            end = origin + offset
            painter.setPen(QPen(color, 2))
            if not self._result_view:
                painter.drawLine(origin, end)
                painter.drawText(end + QPointF(3, -3), label)
                continue
            length = math.hypot(offset.x(), offset.y())
            if length < 5:
                # Positive axis nearly normal to the screen. Draw its end-on
                # symbol last so the other two shafts cannot hide its center.
                end_on = (z, label, color)
                continue
            direction = offset / length
            painter.drawLine(origin, end)
            head_length = min(7.0, length * 0.8)
            base = end - direction * head_length
            wing = QPointF(-direction.y(), direction.x()) * (head_length * 0.5)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(QPolygonF([end, base + wing, base - wing]))
            self._draw_axis_label(painter, end + direction * 8, label, color)
        if end_on is not None:
            z, label, color = end_on
            painter.setPen(QPen(color, 1.4))
            painter.setBrush(_CANVAS)
            painter.drawEllipse(origin, 4, 4)
            if z > 0:
                painter.setBrush(color)
                painter.drawEllipse(origin, 1, 1)
            else:
                for slope in (-1, 1):
                    diagonal = QPointF(2, slope * 2)
                    painter.drawLine(origin - diagonal, origin + diagonal)
            # The other two axes are nearly orthogonal. Put the label in the
            # opposite quadrant, outside both shafts.
            free = QPointF(-sum(v[0] for v, name, _ in directions if name != label),
                           sum(v[1] for v, name, _ in directions if name != label))
            self._draw_axis_label(painter, origin + free * 10, label, color)

    @staticmethod
    def _draw_axis_label(painter, center, label, color):
        painter.setPen(color)
        painter.drawText(QRectF(center.x() - 6, center.y() - 10, 12, 20),
                         Qt.AlignmentFlag.AlignCenter, label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = self._last = event.position()
            self._dragged = False

    def mouseMoveEvent(self, event):
        if self._last is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.position() - self._last
            if (event.position() - self._press).manhattanLength() > 4:
                self._dragged = True
            if self._dragged:
                self.yaw += delta.x() * 0.012
                self.pitch += delta.y() * 0.012
                self.update()
            self._last = event.position()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._dragged and self._press is not None:
            candidates = []
            for i, (x, y, z, radius) in enumerate(self._projected):
                distance = math.hypot(x - event.position().x(), y - event.position().y())
                if distance <= radius + 5:
                    candidates.append((z, i))
            if candidates:
                index = max(candidates)[1]
                if index in self.selected:
                    self.selected.remove(index)
                else:
                    self.selected = (self.selected + [index])[-2:]
            else:
                self.selected = []
            self.selection_changed.emit(list(self.selected))
            self.update()
        self._last = self._press = None

    def mouseDoubleClickEvent(self, event):
        self.fit()

    def wheelEvent(self, event):
        self.zoom = min(4.0, max(0.3, self.zoom * (1.12 if event.angleDelta().y() > 0 else 1 / 1.12)))
        self.update()


"""轻量投影视口，验证选择、旋转和缩放；将来可替换为 VTK 适配器。"""

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QWidget

from orcaview.gui.bond_drawing import aromatic_ring_paths, draw_bond, ring_center
from orcaview.i18n import tr

from orcaview.core.elements import ELEMENT_COLORS
from orcaview.core.geometry import display_bonds
from orcaview.core.point_group import geometric_symmetry
from orcaview.core.symmetry import DEFAULT_TOLERANCE


# Schematic sphere sizes in Å, chosen for the ball-and-stick view.
_BALL_RADII = {"H": 0.19, "C": 0.32, "N": 0.33, "O": 0.34}
_CANVAS = QColor("#FFFDFA")
_ACCENT = QColor("#904359")
_STICK = QColor("#829093")
_MUTED = QColor("#70635F")
_INPUT_FRAME = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


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
    atom_targeted = Signal(int)

    def __init__(self, parent=None, *, result_view=False, design_selection=False):
        super().__init__(parent)
        self._result_view = result_view
        self.design_selection = design_selection
        self.atom_targeting = False
        self._box_select = False
        self.molecule = None
        self._frame = _INPUT_FRAME
        self._point_group_label = ""
        self.symmetry_label = ""
        self.principal_axis = None
        self.selected = []
        self.labels = False
        self._projected = []
        self.setMinimumSize(360, 300)
        self.setMouseTracking(True)
        self.fit()

    def set_molecule(self, molecule, *, keep_view=False):
        keep_view = keep_view and self.molecule is not None and bool(self.molecule.atoms)
        self.molecule = molecule
        self.selected = []
        # Previously projected atoms must not be pickable after changing geometry.
        self._projected = []
        if molecule is None or not molecule.atoms:
            self.bonds = ()
            self._aromatic_paths = {}
            self.principal_axis = None
            self._frame = _INPUT_FRAME
            self._point_group_label = self.symmetry_label = ""
            self.setAccessibleDescription("")
            self.setToolTip("")
            self.fit()
            self.selection_changed.emit([])
            return
        self.bonds = display_bonds(molecule)
        self._aromatic_paths = aromatic_ring_paths(self.bonds)
        group, self.principal_axis = geometric_symmetry(molecule)
        frame = _principal_frame(self.principal_axis.direction)
        if keep_view:
            # Express the old screen orientation in the new principal-axis basis.
            self._camera = tuple(zip(*(self.transform(*axis) for axis in frame)))
            self.yaw = self.pitch = 0.
        self._frame = frame
        if self.principal_axis.direction is None:
            alignment = tr("沿用输入坐标轴")
        else:
            order = "∞" if math.isinf(self.principal_axis.order) else str(self.principal_axis.order)
            alignment = tr("C{order} 主轴 ∥ z", order=order)
        self._point_group_label = tr("几何点群 {group}", group=group)
        self.symmetry_label = f"{self._point_group_label}  ·  {alignment}"
        self.setAccessibleDescription(self.symmetry_label)
        self.setToolTip(self.symmetry_label + "\n" + tr("几何匹配容差 {tolerance:g} Å。原子表及 ORCA 输入使用原始坐标。", tolerance=DEFAULT_TOLERANCE))
        if keep_view:
            self._end_gesture()
            self.update()
        else:
            self.fit()
        self.selection_changed.emit([])

    def fit(self):
        # Look from local +z at the origin. Screen y is inverted at projection.
        self._camera = _INPUT_FRAME
        self.yaw = self.pitch = 0.0
        self.zoom = 1.0
        self._pan = QPointF()
        self._end_gesture()
        self.update()

    def transform(self, x, y, z):
        local = tuple(a * x + b * y + c * z for a, b, c in self._frame)
        return self.camera_transform(*local)

    def camera_transform(self, x, y, z):
        # The axis triad is already in the local frame. Apply only the camera to it.
        x, y, z = (a * x + b * y + c * z for a, b, c in self._camera)
        x, z = x * math.cos(self.yaw) + z * math.sin(self.yaw), -x * math.sin(self.yaw) + z * math.cos(self.yaw)
        y, z = y * math.cos(self.pitch) - z * math.sin(self.pitch), y * math.sin(self.pitch) + z * math.cos(self.pitch)
        return x, y, z

    def _commit_orbit(self):
        # The next gesture starts in screen coordinates from the displayed orientation.
        if self.yaw or self.pitch:
            self._camera = tuple(zip(*(self.camera_transform(*axis) for axis in _INPUT_FRAME)))
            self.yaw = self.pitch = 0.0

    def rotate_view(self, axis, degrees):
        """Rotate the displayed molecule about a screen axis, using right-handed degrees."""
        if self._box_select:
            self._end_gesture()
        first, second = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}[axis]
        angle = math.radians(degrees)
        cosine, sine = math.cos(angle), math.sin(angle)
        self._commit_orbit()
        # Left-multiply by the screen-axis rotation: just two matrix rows change.
        rows = list(self._camera)
        a, b = rows[first], rows[second]
        rows[first] = tuple(cosine * u - sine * v for u, v in zip(a, b))
        rows[second] = tuple(sine * u + cosine * v for u, v in zip(a, b))
        self._camera = tuple(rows)
        self.update()

    def _project_atoms(self, fixed_target=None):
        atoms = self.molecule.atoms
        center = tuple(sum(getattr(a, key) for a in atoms) / len(atoms) for key in ("x", "y", "z"))
        radius = max(math.sqrt(sum((getattr(a, key) - c) ** 2 for key, c in zip(("x", "y", "z"), center))) for a in atoms)
        scale = min(self.width(), self.height()) * 0.32 / max(radius, 1.2) * self.zoom
        if fixed_target is not None:
            # Adding a peripheral H changes the centre and extent. Keep the
            # clicked nucleus under the cursor for the next click.
            index, screen_x, screen_y = fixed_target
            atom = atoms[index]
            x, y, _ = self.transform(atom.x - center[0], atom.y - center[1], atom.z - center[2])
            self._pan = QPointF(screen_x - self.width() / 2 - x * scale, screen_y - self.height() / 2 + y * scale)
        origin_x = self.width() / 2 + self._pan.x()
        origin_y = self.height() / 2 + self._pan.y()
        self._projected = []
        for atom in atoms:
            x, y, z = self.transform(atom.x - center[0], atom.y - center[1], atom.z - center[2])
            size = max(1.5, _BALL_RADII.get(atom.element, 0.32) * scale)
            self._projected.append((origin_x + x * scale, origin_y - y * scale, z, size))
        return scale

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), _CANVAS)
        if self.molecule is None or not self.molecule.atoms:
            return
        atoms = self.molecule.atoms
        scale = self._project_atoms()
        points = [QPointF(x, y) for x, y, z, radius in self._projected]
        for bond in self.bonds:
            radius = max(0.7, (0.062 if "H" in (atoms[bond.a].element, atoms[bond.b].element) else 0.083) * scale)
            stick = radius if bond.order == 1 else max(.6, radius * .52)
            draw_bond(painter, points[bond.a], points[bond.b], bond.order, bond.style, _STICK,
                      2 * stick, 3.1 * stick, shaded=True,
                      clearance=(self._projected[bond.a][3] + 1, self._projected[bond.b][3] + 1),
                      interior=ring_center(self._aromatic_paths.get(bond), points))
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
            group_selection = self.design_selection and len(self.selected) > 2
            metrics = painter.fontMetrics()
            for position, index in enumerate(self.selected):
                x, y, _, radius = self._projected[index]
                painter.drawEllipse(QPointF(x, y), radius + 4, radius + 4)
                if group_selection and not self.labels:
                    continue
                label = f"{atoms[index].element}{index + 1}"
                width = metrics.horizontalAdvance(label)
                label_x = x + radius + 7
                label_y = y - radius - metrics.descent() - 5
                if len(self.selected) == 2:
                    # Put the labels outside the measured span, even on short bonds.
                    other_x, other_y = self._projected[self.selected[1 - position]][:2]
                    if other_x > x:
                        label_x = x - radius - 7 - width
                    if other_y < y - 1:
                        label_y = y + radius + metrics.ascent() + 5
                label_x = max(4, min(label_x, self.width() - width - 4))
                label_y = max(metrics.ascent() + 4, min(label_y, self.height() - metrics.descent() - 4))
                bounds = metrics.boundingRect(label).translated(round(label_x), round(label_y))
                painter.fillRect(bounds.adjusted(-2, -1, 2, 1), _CANVAS)
                painter.drawText(QPointF(label_x, label_y), label)
            if group_selection:
                selection_text = tr("已选 {count} 个原子", count=len(self.selected))
            else:
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
        if self._box_select and self._dragged:
            painter.setPen(QPen(_ACCENT, 1, Qt.PenStyle.DashLine))
            fill = QColor(_ACCENT)
            fill.setAlpha(30)
            painter.setBrush(fill)
            painter.drawRect(QRectF(self._press, self._last).normalized())

    def _draw_axes(self, painter):
        # 轴标随相机旋转，避免固定标签误导空间方向。
        origin = QPointF(self.width() - 48, self.height() - 52)
        axes = zip(_INPUT_FRAME, "xyz", ("#AC534C", "#397E60", "#386FA7"))
        directions = [(self.camera_transform(*vector), label, QColor(color)) for vector, label, color in axes]
        end_on = None
        for (x, y, z), label, color in sorted(directions, key=lambda axis: axis[0][2]):
            offset = QPointF(33 * x, -33 * y)
            end = origin + offset
            length = math.hypot(offset.x(), offset.y())
            if length < 5:
                # Positive axis nearly normal to the screen. Draw its end-on
                # symbol last so the other two shafts cannot hide its center.
                end_on = (z, label, color)
                continue
            direction = offset / length
            head_length = min(8.0, length * 0.8)
            base = end - direction * head_length
            wing = QPointF(-direction.y(), direction.x()) * (head_length * 0.5)
            painter.setPen(QPen(color, 2))
            painter.drawLine(origin, base)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(QPolygonF([end, base + wing, base - wing]))
            self._draw_axis_label(painter, end + direction * 8, label, color)
        if end_on is not None:
            z, label, color = end_on
            painter.setPen(QPen(color, 1.4))
            painter.setBrush(_CANVAS)
            painter.drawEllipse(origin, 5, 5)
            if z > 0:
                painter.setBrush(color)
                painter.drawEllipse(origin, 1.5, 1.5)
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
        if self._button is None and event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self._button = event.button()
            self._press = self._last = event.position()
            self._dragged = False
            self._box_select = (self.design_selection and not self.atom_targeting and self._button == Qt.MouseButton.LeftButton
                                and bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            if self._box_select:
                self.setFocus(Qt.FocusReason.MouseFocusReason)

    def mouseMoveEvent(self, event):
        if self._button is not None and event.buttons() & self._button:
            self._drag_to(event.position())

    def _drag_to(self, position):
        if position == self._last:
            return
        displacement = position - self._press
        if not self._dragged:
            if displacement.manhattanLength() <= 4:
                return
            self._dragged = True
            if self._button == Qt.MouseButton.LeftButton and not self._box_select:
                self._commit_orbit()
        if self._button == Qt.MouseButton.RightButton:
            self._pan += position - self._last
        elif not self._box_select:
            self.yaw = displacement.x() * 0.012
            self.pitch = displacement.y() * 0.012
        self._last = position
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != self._button:
            return
        self._drag_to(event.position())
        if self._box_select and self._dragged:
            bounds = QRectF(self._press, event.position()).normalized()
            selected = set(self.selected)
            self.selected.extend(i for i, (x, y, _, _) in enumerate(self._projected)
                                 if i not in selected and bounds.contains(x, y))
        elif self._button == Qt.MouseButton.LeftButton and not self._dragged:
            hits = [(z, i) for i, (x, y, z, radius) in enumerate(self._projected)
                    if math.hypot(x - event.position().x(), y - event.position().y()) <= radius + 5]
            target = max(hits)[1] if hits else None
            if self.atom_targeting:
                self._end_gesture()
                if target is not None:
                    fixed = self.mapToGlobal(QPointF(*self._projected[target][:2]))
                    previous = self.molecule
                    self.atom_targeted.emit(target)
                    if self.molecule is not previous:
                        point = self.mapFromGlobal(fixed)
                        self._project_atoms((target, point.x(), point.y()))
                        self.update()
                return
            self._pick_atom(target)
        else:
            self._end_gesture()
            return
        self._end_gesture()
        self.selection_changed.emit(list(self.selected))
        self.update()

    def _pick_atom(self, index):
        if index is None:
            if not self._box_select:
                self.selected = []
            return
        if self.design_selection and not self._box_select and len(self.selected) > 2:
            self.selected = [index]
        elif index in self.selected:
            self.selected.remove(index)
        elif self._box_select:
            self.selected.append(index)
        else:
            self.selected = (self.selected + [index])[-2:]

    def _end_gesture(self):
        self._button = self._last = self._press = None
        self._dragged = self._box_select = False

    def event(self, event):
        if event.type() in (QEvent.Type.UngrabMouse, QEvent.Type.FocusOut, QEvent.Type.Hide,
                            QEvent.Type.WindowDeactivate, QEvent.Type.Resize) and getattr(self, "_box_select", False):
            self._end_gesture()
            self.update()
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._box_select:
            self._end_gesture()
            self.update()
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        if self._box_select:
            event.accept()
            return
        self.zoom = min(4.0, max(0.3, self.zoom * (1.12 if event.angleDelta().y() > 0 else 1 / 1.12)))
        self.update()


"""Lightweight projection viewport for selection, rotation and zoom. A VTK adapter may be used in the future."""

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QWidget

from orcaview.appearance import AppearanceSettings, MODEL_LABELS
from orcaview.core.elements import ELEMENT_COLORS, VDW_RADII
from orcaview.core.geometry import DEFAULT_BOND_DISTANCE_FACTOR, display_bonds
from orcaview.core.point_group import geometric_symmetry
from orcaview.core.symmetry import DEFAULT_TOLERANCE
from orcaview.gui.bond_drawing import aromatic_ring_paths, draw_bond, ring_center
from orcaview.i18n import tr


# Schematic sphere sizes in Å, chosen for the ball-and-stick view.
_BALL_RADII = {"H": 0.19, "C": 0.32, "N": 0.33, "O": 0.34}
_CANVAS = QColor("#FFFDFA")
_ACCENT = QColor("#904359")
_STICK = QColor("#829093")
_MUTED = QColor("#70635F")
_FALLBACK_ATOM = QColor("#aa88bb")
_STICK_RADIUS = 0.13
_INPUT_FRAME = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


def _atom_colors(settings, overrides):
    colors = {symbol: QColor(value) for symbol, value in {**ELEMENT_COLORS, **overrides}.items()}
    if settings.model in ("stick", "wireframe"):
        # A narrow white hydrogen stroke disappears on the pale canvas. Keep its hue
        # and dim only light inks; shaded sphere models already supply a dark rim.
        for symbol, color in colors.items():
            luma = .2126 * color.red() + .7152 * color.green() + .0722 * color.blue()
            if luma > 145:
                colors[symbol] = color.darker(round(100 * luma / 145))
    return colors


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


def _in_frame(rows, x, y, z):
    return tuple(a * x + b * y + c * z for a, b, c in rows)


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
        self.bonds = ()
        self.visual_bonds = ()
        self.appearance = AppearanceSettings()
        self._colors = _atom_colors(self.appearance, {})
        self._center_distances = ()
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

    def set_appearance(self, settings, colors):
        old = self.appearance
        self.appearance = settings
        self._colors = _atom_colors(settings, colors)
        if self.has_exportable_structure():
            if old.bond_distance_factor != settings.bond_distance_factor:
                self._update_visual_bonds()
            self._update_atom_radii()
            if settings.model != old.model:
                self._update_fit_radius()
            if self._projected:
                _, self._projected = self._project_atoms()
        self.update()

    def _update_visual_bonds(self):
        factor = self.appearance.bond_distance_factor
        # The design editor still uses self.bonds for measurements and edits.
        self.visual_bonds = (self.bonds if factor == DEFAULT_BOND_DISTANCE_FACTOR
                             else display_bonds(self.molecule, factor))

    def _update_atom_radii(self):
        style = self.appearance
        elements = (atom.element for atom in self.molecule.atoms)
        self._min_atom_pixels = 1.5
        if style.model == "space-filling":
            self._atom_radii = tuple(VDW_RADII[symbol] * style.atom_scale for symbol in elements)
        elif style.model == "ball-and-stick":
            self._atom_radii = tuple(_BALL_RADII.get(symbol, .32) * style.atom_scale for symbol in elements)
        elif style.model == "stick":
            self._atom_radii = (_STICK_RADIUS * style.bond_scale,) * len(self.molecule.atoms)
        else:
            # Tiny element-colored junctions keep even isolated atoms visible in wireframe.
            self._atom_radii = (0.,) * len(self.molecule.atoms)
            self._min_atom_pixels = max(1., 1.6 * style.bond_scale)

    def _update_fit_radius(self):
        # Preserve the legacy framing while allowing large spheres to fit at any orientation.
        extent = max(d + r for d, r in zip(self._center_distances, self._atom_radii))
        self._fit_radius = max(1.2, max(self._center_distances), .75 * extent)

    def set_molecule(self, molecule, *, keep_view=False):
        keep_view = keep_view and self.molecule is not None and bool(self.molecule.atoms)
        self.molecule = molecule
        self.selected = []
        # Previously projected atoms must not be pickable after changing geometry.
        self._projected = []
        if molecule is None or not molecule.atoms:
            self.bonds = self.visual_bonds = ()
            self._aromatic_paths = {}
            self._local_positions = ()
            self._center_distances = ()
            self.principal_axis = None
            self._frame = _INPUT_FRAME
            self._point_group_label = self.symmetry_label = ""
            self.setAccessibleDescription("")
            self.setToolTip("")
            self.fit()
            self.selection_changed.emit([])
            return
        self.bonds = display_bonds(molecule)
        self._update_visual_bonds()
        self._aromatic_paths = aromatic_ring_paths(self.bonds)
        group, self.principal_axis = geometric_symmetry(molecule)
        frame = _principal_frame(self.principal_axis.direction)
        if keep_view:
            # Express the old screen orientation in the new principal-axis basis.
            self._camera = tuple(zip(*(self.transform(*axis) for axis in frame)))
            self.yaw = self.pitch = 0.
        self._frame = frame
        # Rotation, zoom and export all use the same centered molecular geometry.
        atoms = molecule.atoms
        cx, cy, cz = (sum(getattr(atom, axis) for atom in atoms) / len(atoms) for axis in "xyz")
        centered = [(atom.x - cx, atom.y - cy, atom.z - cz) for atom in atoms]
        self._center_distances = tuple(math.sqrt(sum(v ** 2 for v in point)) for point in centered)
        self._update_atom_radii()
        self._local_positions = tuple(_in_frame(frame, *point) for point in centered)
        if self.principal_axis.direction is None:
            alignment = tr("Use input coordinate axes")
        else:
            order = "∞" if math.isinf(self.principal_axis.order) else str(self.principal_axis.order)
            alignment = tr("C{order} principal axis ∥ z", order=order)
        self._point_group_label = tr("Point group {group}", group=group)
        self.symmetry_label = f"{self._point_group_label}  ·  {alignment}"
        self.setAccessibleDescription(self.symmetry_label)
        self.setToolTip(self.symmetry_label + "\n" + tr("Geometry matching tolerance: {tolerance:g} Å. The atom table and ORCA input use the original coordinates.", tolerance=DEFAULT_TOLERANCE))
        if keep_view:
            self._update_fit_radius()
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
        if self._center_distances:
            self._update_fit_radius()
        self._end_gesture()
        self.update()

    def transform(self, x, y, z):
        return self.camera_transform(*_in_frame(self._frame, x, y, z))

    def camera_transform(self, x, y, z):
        # The axis triad is already in the local frame. Apply only the camera to it.
        x, y, z = _in_frame(self._camera, x, y, z)
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
        scale = min(self.width(), self.height()) * 0.32 / self._fit_radius * self.zoom
        if fixed_target is not None:
            # Adding a peripheral H changes the centre and extent. Keep the
            # clicked nucleus under the cursor for the next click.
            index, screen_x, screen_y = fixed_target
            x, y, _ = self.camera_transform(*self._local_positions[index])
            self._pan = QPointF(screen_x - self.width() / 2 - x * scale, screen_y - self.height() / 2 + y * scale)
        origin_x = self.width() / 2 + self._pan.x()
        origin_y = self.height() / 2 + self._pan.y()
        projected = []
        for radius, point in zip(self._atom_radii, self._local_positions):
            x, y, z = self.camera_transform(*point)
            size = max(self._min_atom_pixels, radius * scale)
            projected.append((origin_x + x * scale, origin_y - y * scale, z, size))
        return scale, projected

    def has_exportable_structure(self):
        return self.molecule is not None and bool(self.molecule.atoms)

    def paint_structure(self, painter):
        """Paint the current molecular projection in widget coordinates."""
        if not self.has_exportable_structure():
            return
        scale, projected = self._project_atoms()
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBackgroundMode(Qt.BGMode.TransparentMode)
            font = self.font()
            # Keep labels in viewport pixels even when printing to a high-DPI device.
            font.setPixelSize(self.fontInfo().pixelSize())
            painter.setFont(font)
            self._draw_molecule(painter, scale, projected)
        finally:
            painter.restore()

    def _draw_molecule(self, painter, scale, projected, selection_labels=()):
        atoms = self.molecule.atoms
        colors = [self._colors.get(atom.element, _FALLBACK_ATOM) for atom in atoms]
        model = self.appearance.model
        if model != "space-filling":
            points = [QPointF(x, y) for x, y, z, radius in projected]
            draw_as_ball_and_stick = model == "ball-and-stick"
            for bond in self.visual_bonds:
                if draw_as_ball_and_stick:
                    weight = .062 if "H" in (atoms[bond.a].element, atoms[bond.b].element) else .083
                    radius = max(.7, weight * scale * self.appearance.bond_scale)
                elif model == "stick":
                    radius = max(.7, _STICK_RADIUS * scale * self.appearance.bond_scale)
                else:
                    radius = max(.5, .85 * self.appearance.bond_scale)
                stick = radius if bond.order == 1 else max(.6, radius * .52)
                draw_bond(painter, points[bond.a], points[bond.b], bond.order, bond.style,
                          _STICK if draw_as_ball_and_stick else colors[bond.a],
                          2 * stick, 3.1 * stick, shaded=draw_as_ball_and_stick,
                          end_ink=None if draw_as_ball_and_stick else colors[bond.b],
                          clearance=(projected[bond.a][3] + 1, projected[bond.b][3] + 1),
                          interior=ring_center(self._aromatic_paths.get(bond), points))
        for index in sorted(range(len(atoms)), key=lambda i: projected[i][2]):
            x, y, z, size = projected[index]
            color = colors[index]
            if model in ("stick", "wireframe"):
                painter.setBrush(color)
                painter.setPen(Qt.PenStyle.NoPen)
            else:
                gradient = QRadialGradient(QPointF(x - size * 0.28, y - size * 0.36), size * 1.47)
                gradient.setColorAt(0, color.lighter(110))
                gradient.setColorAt(0.42, color)
                gradient.setColorAt(0.78, color.darker(114))
                gradient.setColorAt(1, color.darker(140))
                painter.setBrush(gradient)
                painter.setPen(QPen(color.darker(128), 0.8))
            painter.drawEllipse(QPointF(x, y), size, size)
            if self.labels and index not in selection_labels:
                painter.setPen(_MUTED)
                painter.drawText(QPointF(x + size + 5, y - size - 2), "{}{}".format(atoms[index].element, index + 1))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), _CANVAS)
        if not self.has_exportable_structure():
            return
        atoms = self.molecule.atoms
        scale, self._projected = self._project_atoms()
        selection_labels = set(self.selected) if self.labels else ()
        self._draw_molecule(painter, scale, self._projected, selection_labels)
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
                selection_text = tr("{count} atoms selected", count=len(self.selected))
            else:
                names = ", ".join(f"{atoms[index].element}{index + 1}" for index in self.selected)
                selection_text = tr("Selected  ") + names
            painter.setPen(_ACCENT)
            painter.drawText(self.width() - 18 - painter.fontMetrics().horizontalAdvance(selection_text),
                             26, selection_text)
        painter.setPen(_MUTED)
        model = tr(MODEL_LABELS[self.appearance.model])
        if self._result_view:
            painter.drawText(18, 26, model)
            painter.drawText(18, 47, self._point_group_label)
        else:
            painter.drawText(18, 26, tr("Geometry  /  Å     ·     {model}", model=model))
            painter.drawText(18, 47, self.symmetry_label)
        self._draw_axes(painter)
        if self._box_select and self._dragged:
            painter.setPen(QPen(_ACCENT, 1, Qt.PenStyle.DashLine))
            fill = QColor(_ACCENT)
            fill.setAlpha(30)
            painter.setBrush(fill)
            painter.drawRect(QRectF(self._press, self._last).normalized())

    def _draw_axes(self, painter):
        # Rotate axis labels with the camera to keep orientations unambiguous.
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
                        _, self._projected = self._project_atoms((target, point.x(), point.y()))
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


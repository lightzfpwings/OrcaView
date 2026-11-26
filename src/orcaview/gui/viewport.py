"""Lightweight projection viewport for selection, rotation and zoom. A VTK adapter may be used in the future."""

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QRadialGradient, QRegion
from PySide6.QtWidgets import QApplication

from orcaview.appearance import AppearanceSettings, MODEL_LABELS
from orcaview.core.elements import ELEMENT_COLORS, VDW_RADII
from orcaview.core.geometry import DEFAULT_BOND_DISTANCE_FACTOR, connected_component, display_bonds
from orcaview.core.point_group import geometric_symmetry
from orcaview.core.symmetry import DEFAULT_TOLERANCE, rotation_axis_angle
from orcaview.gui.bond_drawing import aromatic_ring_paths, bond_half_width, draw_bond, ring_center
from orcaview.gui.design_picking import MoleculeEditView, distance_to_segment
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


def _orbit(x, y, z, yaw, pitch):
    x, z = x * math.cos(yaw) + z * math.sin(yaw), -x * math.sin(yaw) + z * math.cos(yaw)
    y, z = y * math.cos(pitch) - z * math.sin(pitch), y * math.sin(pitch) + z * math.cos(pitch)
    return x, y, z


_ORBIT_RADIANS_PER_PIXEL = .012


class MoleculeViewport(MoleculeEditView):
    selection_changed = Signal(list)
    atom_targeted = Signal(int)
    bond_targeted = Signal(int, int)
    space_targeted = Signal(float, float, float)
    fragment_moved = Signal(int, float, float, float)
    fragment_rotated = Signal(int, object, float)
    delete_requested = Signal()

    def __init__(self, parent=None, *, result_view=False, design_selection=False):
        super().__init__(parent, mouse_tracking=design_selection)
        self._result_view = result_view
        self.design_selection = design_selection
        self._design_tool = "select"
        if design_selection:
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._box_select = False
        self.molecule = None
        self.bonds = ()
        self.visual_bonds = ()
        self._editable_bonds = ()
        self.appearance = AppearanceSettings()
        self._colors = _atom_colors(self.appearance, {})
        self.population_map = None
        self._center_distances = ()
        self._center = (0., 0., 0.)
        self._fit_radius = 1.2
        self._frame = _INPUT_FRAME
        self._point_group_label = ""
        self.symmetry_label = ""
        self.principal_axis = None
        self.selected = []
        self.labels = False
        self._projected = []
        self.setMinimumSize(360, 300)
        self.fit()

    def set_design_tool(self, mode):
        self._design_tool = mode
        self._end_gesture()
        self._track_hover(None)
        self.update()

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
        if self.design_selection:
            # A custom distance cutoff can show extra guides outside the editor's topology.
            topology = set(self.bonds)
            self._editable_bonds = tuple(b for b in self.visual_bonds if b in topology)

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

    def set_molecule(self, molecule, *, keep_view=False, keep_projection=False):
        keep_view = keep_view and self.molecule is not None and bool(self.molecule.atoms)
        old_center = self._center
        self.molecule = molecule
        self.population_map = None
        self._track_hover(None)
        self.selected = []
        # Previously projected atoms must not be pickable after changing geometry.
        self._projected = []
        if molecule is None or not molecule.atoms:
            self.bonds = self.visual_bonds = self._editable_bonds = ()
            self._aromatic_paths = {}
            self._local_positions = ()
            self._center_distances = ()
            self._center = (0., 0., 0.)
            self._fit_radius = 1.2
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
        self._center = (cx, cy, cz)
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
            if keep_projection:
                # The new centroid is the pivot for subsequent rotations. Offset
                # its shift on screen so only the translated fragment moves.
                x, y, _ = self.transform(*(new - old for new, old in zip(self._center, old_center)))
                self._pan += QPointF(x, -y) * self._projection_scale()
            else:
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
        return _orbit(*_in_frame(self._camera, x, y, z), self.yaw, self.pitch)

    def _commit_orbit(self):
        # The next gesture starts in screen coordinates from the displayed orientation.
        if self.yaw or self.pitch:
            self._camera = tuple(zip(*(self.camera_transform(*axis) for axis in _INPUT_FRAME)))
            self.yaw = self.pitch = 0.0

    def rotate_view(self, axis, degrees):
        """Rotate the displayed molecule about a screen axis, using right-handed degrees."""
        if self._box_select or self._fragment_rows is not None:
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

    def _projection_scale(self):
        return min(self.width(), self.height()) * 0.32 / self._fit_radius * self.zoom

    def _project_atoms(self, fixed_target=None, *, positions=None):
        if positions is None:
            positions = self._local_positions
        scale = self._projection_scale()
        if fixed_target is not None:
            # Adding a peripheral H changes the centre and extent. Keep the
            # clicked nucleus under the cursor for the next click.
            index, screen_x, screen_y = fixed_target
            x, y, _ = self.camera_transform(*positions[index])
            self._pan = QPointF(screen_x - self.width() / 2 - x * scale, screen_y - self.height() / 2 + y * scale)
        origin_x = self.width() / 2 + self._pan.x()
        origin_y = self.height() / 2 + self._pan.y()
        projected = []
        for radius, point in zip(self._atom_radii, positions):
            x, y, z = self.camera_transform(*point)
            size = max(self._min_atom_pixels, radius * scale)
            projected.append((origin_x + x * scale, origin_y - y * scale, z, size))
        return scale, projected

    def _world_at(self, point):
        # An empty-space click lies in the screen plane of the last selected atom,
        # or through the molecular centre when there is no selection.
        scale = self._projection_scale()
        x = (point.x() - self.width() / 2 - self._pan.x()) / scale
        y = (self.height() / 2 + self._pan.y() - point.y()) / scale
        z = self._projected[self.selected[-1]][2] if self.selected else 0.
        return tuple(center + sum(a * b for a, b in zip(self.transform(*axis), (x, y, z)))
                     for center, axis in zip(self._center, _INPUT_FRAME))

    def has_exportable_structure(self):
        return self.molecule is not None and bool(self.molecule.atoms)

    def paint_structure(self, painter, *, positions=None):
        """Paint the current molecular projection in widget coordinates."""
        if not self.has_exportable_structure():
            return
        scale, projected = self._project_atoms(positions=positions)
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

    def _stick_half_width(self, bond, scale):
        model = self.appearance.model
        if model == "ball-and-stick":
            atoms = self.molecule.atoms
            weight = .062 if "H" in (atoms[bond.a].element, atoms[bond.b].element) else .083
            radius = max(.7, weight * scale * self.appearance.bond_scale)
        elif model == "stick":
            radius = max(.7, _STICK_RADIUS * scale * self.appearance.bond_scale)
        else:
            radius = max(.5, .85 * self.appearance.bond_scale)
        return radius if bond.order == 1 else max(.6, radius * .52)

    def _target_at(self, point, *, fragment=False):
        front = None
        px, py = point.x(), point.y()
        for i, (x, y, z, radius) in enumerate(self._projected):
            distance2 = (x - px) ** 2 + (y - py) ** 2
            if distance2 <= (radius + 5) ** 2:
                # A nearby sphere's picking margin must not mask a visible atom.
                hit = (self.design_selection and distance2 <= radius ** 2, z, i)
                if front is None or hit > front:
                    front = hit
        if front is not None:
            return (front[2],)
        if self.design_selection and self._button is None:
            modifiers = QApplication.keyboardModifiers()
            fragment = fragment or bool(modifiers & Qt.KeyboardModifier.AltModifier)
            if not fragment and modifiers & Qt.KeyboardModifier.ShiftModifier:
                return ()
        if (not self.design_selection or not (fragment or self._design_tool in ("select", "bond")) or self._box_select
                or self.appearance.model == "space-filling" or not self._projected):
            return ()
        scale = self._projection_scale()
        best = None
        for bond in self._editable_bonds:
            if fragment and not bond.is_covalent:
                continue
            x1, y1, z1, _ = self._projected[bond.a]
            x2, y2, z2, _ = self._projected[bond.b]
            miss, fraction, length = distance_to_segment(point, QPointF(x1, y1), QPointF(x2, y2))
            stick = self._stick_half_width(bond, scale)
            half_width = bond_half_width(bond.order, bond.style, 2 * stick, 3.1 * stick, length, fraction)
            if miss <= half_width + 5:
                hit = (miss, -(z1 + fraction * (z2 - z1)), bond.a, bond.b)
                if best is None or hit < best:
                    best = hit
        return best[2:] if best else ()

    def _draw_molecule(self, painter, scale, projected, selection_labels=(), hover=()):
        atoms = self.molecule.atoms
        population = self.population_map
        colored = population is not None and population.style.color_atoms
        numeric_labels = population is not None and population.style.labels
        colors = population.colors if colored else [self._colors.get(atom.element, _FALLBACK_ATOM) for atom in atoms]
        model = self.appearance.model
        bond_region = QRegion() if numeric_labels else None
        if model != "space-filling":
            points = [QPointF(x, y) for x, y, z, radius in projected]
            draw_as_ball_and_stick = model == "ball-and-stick"
            for bond in self.visual_bonds:
                stick = self._stick_half_width(bond, scale)
                start, end = points[bond.a], points[bond.b]
                highlighted = hover == (bond.a, bond.b)
                if numeric_labels or highlighted:
                    span = end - start
                    length = math.hypot(span.x(), span.y())
                    width = 2 * bond_half_width(bond.order, bond.style, 2 * stick, 3.1 * stick, length)
                    if numeric_labels and length >= .01:
                        # Include rounded caps, antialiased edges and any hover outline.
                        pad = width / 2 + (7 if highlighted else 2)
                        along = span * (pad / length)
                        across = QPointF(-along.y(), along.x())
                        hull = QPolygonF([start - along + across, end + along + across,
                                          end + along - across, start - along - across])
                        bond_region |= QRegion(hull.toPolygon())
                if highlighted:
                    for extra, color in ((10, QColor(46, 161, 203, 75)), (5, QColor("#368FB2"))):
                        painter.setPen(QPen(color, width + extra, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                        painter.drawLine(start, end)
                draw_bond(painter, start, end, bond.order, bond.style,
                          _STICK if draw_as_ball_and_stick else colors[bond.a],
                          2 * stick, 3.1 * stick, shaded=draw_as_ball_and_stick,
                          end_ink=None if draw_as_ball_and_stick else colors[bond.b],
                          clearance=(projected[bond.a][3] + 1, projected[bond.b][3] + 1),
                          interior=ring_center(self._aromatic_paths.get(bond), points))
        for index in sorted(range(len(atoms)), key=lambda i: projected[i][2]):
            x, y, z, size = projected[index]
            color = colors[index]
            if hover == (index,):
                outer = size + 8
                halo = QRadialGradient(QPointF(x, y), outer)
                halo.setColorAt(size / outer, QColor("#277FAB"))
                halo.setColorAt((size + 3) / outer, QColor(52, 165, 215, 185))
                halo.setColorAt(1, QColor(52, 165, 215, 0))
                painter.setBrush(halo)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(x, y), outer, outer)
            if model in ("stick", "wireframe"):
                painter.setBrush(color)
                painter.setPen(QPen(_MUTED, .7) if colored and color.lightness() > 215 else Qt.PenStyle.NoPen)
            else:
                gradient = QRadialGradient(QPointF(x - size * 0.28, y - size * 0.36), size * 1.47)
                gradient.setColorAt(0, color.lighter(110))
                gradient.setColorAt(0.42, color)
                gradient.setColorAt(0.78, color.darker(114))
                gradient.setColorAt(1, color.darker(140))
                painter.setBrush(gradient)
                painter.setPen(QPen(color.darker(128), 0.8))
            painter.drawEllipse(QPointF(x, y), size, size)
            if colored and population.values[index] is None:
                mark = min(5., max(2., size * .55))
                painter.setPen(QPen(QColor("#333333"), 1.5))
                painter.drawLine(QPointF(x-mark, y-mark), QPointF(x+mark, y+mark))
                painter.drawLine(QPointF(x-mark, y+mark), QPointF(x+mark, y-mark))
            if self.labels and not numeric_labels and index not in selection_labels:
                painter.setPen(_MUTED)
                painter.drawText(QPointF(x + size + 5, y - size - 2), "{}{}".format(atoms[index].element, index + 1))
        if population is not None:
            population.draw_annotations(painter, self, projected, self.labels, selection_labels, bond_region)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), _CANVAS)
        if not self.has_exportable_structure():
            return
        atoms = self.molecule.atoms
        scale, self._projected = self._project_atoms()
        if self._fragment_rows and self._dragged:
            delta = self._last - self._press
            if self._button == Qt.MouseButton.LeftButton:
                cx, cy, cz, _ = (sum(values) / len(self._fragment_rows)
                                 for values in zip(*(self._projected[i] for i in self._fragment_rows)))
                yaw, pitch = delta.x() * _ORBIT_RADIANS_PER_PIXEL, delta.y() * _ORBIT_RADIANS_PER_PIXEL
                for i in self._fragment_rows:
                    x, y, z, radius = self._projected[i]
                    rx, ry, rz = _orbit((x - cx) / scale, (cy - y) / scale, z - cz, yaw, pitch)
                    self._projected[i] = (cx + rx * scale, cy - ry * scale, cz + rz, radius)
            else:
                for i in self._fragment_rows:
                    x, y, z, radius = self._projected[i]
                    self._projected[i] = (x + delta.x(), y + delta.y(), z, radius)
        numeric_labels = self.population_map is not None and self.population_map.style.labels
        selection_labels = set(self.selected) if self.labels or numeric_labels else ()
        self._draw_molecule(painter, scale, self._projected, selection_labels, self._refresh_hover())
        # Table selection may address an atom behind another in this projection.
        if self.selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_ACCENT, 2))
            group_selection = self.design_selection and len(self.selected) > 2
            metrics = painter.fontMetrics()
            for position, index in enumerate(self.selected):
                x, y, _, radius = self._projected[index]
                painter.drawEllipse(QPointF(x, y), radius + 4, radius + 4)
                if numeric_labels or (group_selection and not self.labels):
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
            if self.design_selection:
                self.setFocus(Qt.FocusReason.MouseFocusReason)
                self._track_hover(None)
            self._button = event.button()
            self._press = self._last = event.position()
            self._dragged = False
            if self.design_selection:
                if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                    self._fragment_rows = frozenset()
                    if self.has_exportable_structure():
                        _, self._projected = self._project_atoms()
                        target = self.selected[-1:] or self._target_at(self._press, fragment=True)
                        if target:
                            self._fragment_anchor = target[0]
                            self._fragment_rows = connected_component(self.bonds, self._fragment_anchor)
                elif self._button == Qt.MouseButton.LeftButton:
                    self._box_select = (self._design_tool != "hydrogen"
                                        and bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))

    def mouseMoveEvent(self, event):
        if self._button is not None and event.buttons() & self._button:
            self._drag_to(event.position())
        elif self.design_selection and self._button is None and not event.buttons():
            self._track_hover(event.position())

    def _drag_to(self, position):
        if position == self._last:
            return
        displacement = position - self._press
        orbit = self._button == Qt.MouseButton.LeftButton and not self._box_select and self._fragment_rows is None
        if not self._dragged:
            threshold = QApplication.startDragDistance() if self._fragment_rows is not None else 5
            if displacement.manhattanLength() < threshold:
                return
            self._dragged = True
            if orbit:
                self._commit_orbit()
        if self._button == Qt.MouseButton.RightButton and self._fragment_rows is None:
            self._pan += position - self._last
        elif orbit:
            self.yaw = displacement.x() * _ORBIT_RADIANS_PER_PIXEL
            self.pitch = displacement.y() * _ORBIT_RADIANS_PER_PIXEL
        self._last = position
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != self._button:
            return
        self._drag_to(event.position())
        if self._fragment_rows is not None:
            delta = event.position() - self._press
            anchor = self._fragment_anchor
            rows, button = self._fragment_rows, self._button
            changed = bool(rows and self._dragged and not delta.isNull())
            self._end_gesture()
            if changed and button == Qt.MouseButton.LeftButton and len(rows) > 1:
                yaw, pitch = delta.x() * _ORBIT_RADIANS_PER_PIXEL, delta.y() * _ORBIT_RADIANS_PER_PIXEL
                rotation = tuple(zip(*(_orbit(*axis, yaw, pitch) for axis in _INPUT_FRAME)))
                screen_axis, angle = rotation_axis_angle(rotation)
                if screen_axis is not None:
                    world_axis = tuple(sum(a * b for a, b in zip(self.transform(*axis), screen_axis))
                                       for axis in _INPUT_FRAME)
                    self.fragment_rotated.emit(anchor, world_axis, math.degrees(angle))
            elif changed and button == Qt.MouseButton.RightButton:
                # The inverse of the orthographic camera rotation is its
                # transpose. The depth component of a screen-plane drag is zero.
                scale = self._projection_scale()
                axes = (self.transform(*axis) for axis in _INPUT_FRAME)
                xyz = tuple((x * delta.x() - y * delta.y()) / scale for x, y, _ in axes)
                self.fragment_moved.emit(anchor, *xyz)
        elif self._box_select and self._dragged:
            bounds = QRectF(self._press, event.position()).normalized()
            selected = set(self.selected)
            self.selected.extend(i for i, (x, y, _, _) in enumerate(self._projected)
                                 if i not in selected and bounds.contains(x, y))
            self._end_gesture()
            self.selection_changed.emit(list(self.selected))
        elif self._button == Qt.MouseButton.LeftButton and not self._dragged:
            self._click_point(event.position())
        else:
            self._end_gesture()
        if self.design_selection:
            self._track_hover(self.mapFromGlobal(event.globalPosition()))
        self.update()

    def _click_point(self, point):
        if self.has_exportable_structure():
            _, self._projected = self._project_atoms()
        target = self._target_at(point)
        additive = self._box_select
        tool = "select" if additive else self._design_tool
        self._end_gesture()
        if tool == "select":
            if len(target) == 2:
                self.selected = list(target)
            else:
                self._pick_atom(target[0] if target else None, additive)
            self.selection_changed.emit(list(self.selected))
        elif len(target) == 2:
            self.bond_targeted.emit(*target)
        elif target:
            index, = target
            fixed = self.mapToGlobal(QPointF(*self._projected[index][:2])) if tool == "hydrogen" else None
            previous = self.molecule
            self.atom_targeted.emit(index)
            if fixed is not None and self.molecule is not previous:
                pos = self.mapFromGlobal(fixed)
                _, self._projected = self._project_atoms((index, pos.x(), pos.y()))
        elif tool in ("atom", "ring", "bond"):
            self.space_targeted.emit(*self._world_at(point))

    def _pick_atom(self, index, additive):
        if index is None:
            if not additive:
                self.selected = []
            return
        if self.design_selection and not additive and len(self.selected) > 2:
            self.selected = [index]
        elif index in self.selected:
            self.selected.remove(index)
        elif additive:
            self.selected.append(index)
        else:
            self.selected = (self.selected + [index])[-2:]

    def _end_gesture(self):
        self._button = self._last = self._press = None
        self._dragged = self._box_select = False
        self._fragment_anchor = self._fragment_rows = None

    def event(self, event):
        if (event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
                and event.key() in (Qt.Key.Key_Shift, Qt.Key.Key_Alt) and self._hover_point is not None):
            self.update()
        if getattr(self, "_button", None) is not None and (
                event.type() in (QEvent.Type.UngrabMouse, QEvent.Type.FocusOut, QEvent.Type.Hide,
                                 QEvent.Type.WindowDeactivate) or event.type() == QEvent.Type.Resize
                and (self._box_select or self._fragment_rows is not None)):
            self._end_gesture()
            self.update()
        return super().event(event)

    def keyPressEvent(self, event):
        if self.design_selection and event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._end_gesture()
            self.delete_requested.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape and (self._box_select or self._fragment_rows is not None):
            self._end_gesture()
            self.update()
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        if self._box_select or self._fragment_rows is not None:
            event.accept()
            return
        self.zoom = min(4.0, max(0.3, self.zoom * (1.12 if event.angleDelta().y() > 0 else 1 / 1.12)))
        self.update()


class NormalModeViewport(MoleculeViewport):
    """Draw a displacement around a fixed geometry using the equilibrium camera frame."""

    def __init__(self, parent=None):
        super().__init__(parent, result_view=True)
        self._equilibrium_positions = ()
        self._mode_directions = ()

    def set_equilibrium(self, molecule):
        self.set_molecule(molecule)
        self._equilibrium_positions = self._local_positions
        self._mode_directions = ()
        self._point_group_label = tr("Equilibrium geometry · {symmetry}", symmetry=self._point_group_label)

    def set_mode(self, displacements):
        if len(displacements) != len(self._equilibrium_positions):
            raise ValueError("Normal-mode vectors must match the equilibrium atoms.")
        largest = max((math.hypot(*v) for v in displacements), default=0.)
        # The printed Cartesian vectors already include atomic-mass factors.
        # Scale the entire vector by one constant to preserve relative atomic motion.
        self._mode_directions = tuple(_in_frame(self._frame, *(v / largest for v in row))
                                      for row in displacements) if largest else ()
        self.set_displacement(0.)

    def set_displacement(self, distance):
        """Set the signed displacement of the most mobile atom in angstroms."""
        self._local_positions = self._positions_at(distance)
        self.update()

    def paint_displacement(self, painter, distance):
        """Paint one animation frame in the current camera without changing the live pose."""
        self.paint_structure(painter, positions=self._positions_at(distance))

    def _positions_at(self, distance):
        if not distance or not self._mode_directions:
            return self._equilibrium_positions
        return tuple((x + distance * dx, y + distance * dy, z + distance * dz)
                     for (x, y, z), (dx, dy, dz) in zip(self._equilibrium_positions, self._mode_directions))

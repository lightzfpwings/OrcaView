"""Interactive molecular drawing in the active sketch's XY coordinates."""

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QApplication

from orcaview.core.geometry import connected_component, display_bonds
from orcaview.core.models import COORDINATE_STYLES
from orcaview.core.polymer_backbone import topology_roles, validate_backbone_links, validate_polymer_roles
from orcaview.gui.backbone_ink import prepare_ink
from orcaview.gui.backbone_trace import chain_paths, project_trace
from orcaview.gui.bond_drawing import aromatic_ring_paths, bond_half_width, draw_bond, ring_center
from orcaview.gui.design_picking import MoleculeEditView, distance_to_segment, polymer_wheel_zoom
from orcaview.i18n import tr


_PAPER = QColor("#FFFDF9")
_LABEL_COLORS = {"O": "#B84138", "N": "#3265A7", "S": "#856224", "Cl": "#237B54",
                 "F": "#237B54", "Br": "#8F5141", "I": "#79559B", "P": "#AA5729"}
_CHAIN_COLORS = ("#17767D", "#A04A69", "#456AB0", "#A26628")


def _components(indices, neighbors):
    remaining = set(indices)
    for start in sorted(remaining):
        if start not in remaining:
            continue
        remaining.remove(start)
        component = [start]
        for index in component:
            for other in neighbors[index]:
                if other in remaining:
                    remaining.remove(other)
                    component.append(other)
        yield component


def _chain_colors(roles, bonds, links):
    if "B" not in roles:
        return {}
    if links is None:
        links = ((b.a, b.b) for b in bonds if b.is_covalent and b.style not in COORDINATE_STYLES)
    neighbors = [[] for _ in roles]
    for a, b in links:
        neighbors[a].append(b)
        neighbors[b].append(a)
    sites = (i for i, role in enumerate(roles) if role == "B")
    colors = {}
    for strand, component in enumerate(_components(sites, neighbors)):
        color = QColor(_CHAIN_COLORS[strand % len(_CHAIN_COLORS)])
        colors.update((i, color) for i in component)
    return colors


class DesignCanvas(MoleculeEditView):
    atom_clicked = Signal(int)
    atom_shift_clicked = Signal(int)
    box_selected = Signal(list, bool)
    space_clicked = Signal(float, float, float)
    atom_moved = Signal(int, float, float, float)
    fragment_moved = Signal(int, float, float)
    fragment_rotated = Signal(int, float)
    bond_clicked = Signal(int, int)
    bond_to_space = Signal(int, float, float, float)
    delete_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("designCanvas")
        self.setAccessibleName(tr("Molecular sketch"))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(210, 220)
        self.molecule = None
        self.polymer_roles = ""
        self.polymer_zoom = False
        self.zoom = 1.
        self.backbone_links = None
        self.selected = []
        self._label_colors = _LABEL_COLORS
        self.tool = "select"
        self.bond_order = 1
        self.bond_style = "plain"
        self._center = (0., 0.)
        self._extent = (1., 1.)
        self._projection_key = None
        self.cancel_gesture()

    def set_element_colors(self, overrides):
        self._label_colors = {**_LABEL_COLORS, **overrides}
        self.update()

    def cancel_gesture(self):
        self._start = self._pressed = self._drag = self._bond_tip = None
        self._fragment = self._button = self._rotation_center = None
        self._box = None
        self._can_box = self._append_box = False
        self._track_hover(None)
        self.update()

    def set_molecule(self, molecule, *, fit=False, independent_sketch=False, polymer_roles="", backbone_links=None):
        self.molecule = molecule
        self._projection_key = None
        roles = polymer_roles or topology_roles(molecule)
        self._full_bonds = display_bonds(molecule)
        count = len(molecule.atoms)
        links = None if backbone_links is None else tuple(sorted({tuple(sorted(pair)) for pair in backbone_links}))
        validate_polymer_roles(roles, count)
        validate_backbone_links(links, roles)
        self._chain_colors = _chain_colors(roles, self._full_bonds, links)
        self.polymer_roles = roles
        self.backbone_links = links
        polymer = "B" in roles or "S" in roles
        if self.polymer_zoom and not polymer:
            fit = True
        self.polymer_zoom = polymer
        if not polymer:
            self._visible_indices = range(count)
            self._ordinary_bonds = self._full_bonds
            self._trace_bonds = {}
        else:
            self._visible_indices = [i for i, role in enumerate(roles) if role != "S"]
            self._ordinary_bonds = tuple(b for b in self._full_bonds if roles[b.a] == roles[b.b] == ".")
            self._trace_bonds = {tuple(sorted((b.a, b.b))): (b.a, b.b) for b in self._full_bonds
                                 if roles[b.a] == roles[b.b] == "B" and b.is_covalent and b.style not in COORDINATE_STYLES}
        if links is not None:
            # A source's schematic link can be drawn even when it is not an editable bond.
            traced = set(links)
            self._trace_bonds = {edge: pair for edge, pair in self._trace_bonds.items() if edge in traced}
        self._strands = chain_paths(self._trace_bonds if links is None else links)
        self._trace_nodes = {i for strand in self._strands for i in strand}
        self._independent_sketch = independent_sketch
        self._phosphates = {i for i in self._chain_colors if molecule.atoms[i].element == "P"}
        self._depths = tuple(0. if independent_sketch else atom.z for atom in molecule.atoms) if self._strands else ()
        # A detached drawing has no depth. Keep its paint and hit-test order
        # stable when a 3D optimization moves atoms through the page plane.
        self._paint_order = list(self._visible_indices)
        if not independent_sketch:
            self._paint_order.sort(key=lambda i: molecule.atoms[i].z)
        self._aromatic_paths = aromatic_ring_paths(self._ordinary_bonds)
        self.cancel_gesture()
        if fit:
            self.fit()
        self.update()

    def fit(self):
        self.zoom = 1.
        if self.molecule is not None and self._visible_indices:
            coords = tuple(zip(*((self.molecule.atoms[i].x, self.molecule.atoms[i].y) for i in self._visible_indices)))
            self._center = tuple((min(values) + max(values)) / 2 for values in coords)
            self._extent = tuple(max(1., max(values) - min(values)) for values in coords)
        else:
            self._center = (0., 0.)
            self._extent = (1., 1.)
        self.update()

    def _scale(self):
        # Thumbnail exports can be smaller than the sketch editor's margins.
        w, h = self.width(), self.height()
        return self.zoom * min(72., (w - min(68., .4 * w)) / self._extent[0],
                               (h - min(80., .4 * h)) / self._extent[1])

    def wheelEvent(self, event):
        if not self.polymer_zoom:
            super().wheelEvent(event)
            return
        event.accept()
        if self._start is not None:
            return
        zoom = polymer_wheel_zoom(self.zoom, event)
        if zoom != self.zoom:
            previous = self._scale()
            self.zoom = zoom
            delta = 1. / previous - 1. / self._scale()
            point = event.position()
            self._center = (self._center[0] + (point.x() - self.width() / 2) * delta,
                            self._center[1] - (point.y() - self.height() / 2) * delta)
            self.update()

    def _atom_positions(self):
        scale = self._scale()
        key = (self.width(), self.height(), self._center, scale)
        if key != self._projection_key:
            cx, cy = self._center
            w, h = self.width() / 2, self.height() / 2
            self._raw_positions = tuple(QPointF(w + (atom.x - cx) * scale, h - (atom.y - cy) * scale)
                                        for atom in self.molecule.atoms)
            self._positions, self._ink = self._trace_projection(self._raw_positions)
            # At a crossover an occluded node on the rear strand is not a pick target.
            self._node_paint_rank = {}
            for rank, line in enumerate(self._ink):
                for i in (line.a, line.b):
                    if line.hit_distance(self._positions[i]) <= 1:
                        self._node_paint_rank[i] = rank
            # Switch only when many atoms compete for the same label-sized cells.
            # Backbone lines have no permanent labels. Only ordinary atoms
            # contribute to the decision to compact the remaining labels.
            ordinary = [self._positions[i] for i in self._visible_indices if i not in self._chain_colors]
            self._compact = (len(ordinary) >= 64 and scale < 32 and
                             len({(int(p.x() // 24), int(p.y() // 24)) for p in ordinary})
                             < .75 * len(ordinary))
            self._projection_key = key
        return self._positions

    def _trace_projection(self, raw):
        if not self._strands:
            return raw, ()
        points, segments = project_trace(self._strands, raw, self._depths, independent_sketch=self._independent_sketch,
                                         phosphate_sites=self._phosphates)
        return points, prepare_ink(segments, self._chain_colors, self._strands)

    def atom_position(self, index):
        return QPointF(self._atom_positions()[index])

    def _xyz(self, point, anchor):
        atoms = self.molecule.atoms
        z = atoms[anchor].z if anchor is not None else sum(a.z for a in atoms) / max(1, len(atoms))
        return (self._center[0] + (point.x() - self.width() / 2) / self._scale(),
                self._center[1] - (point.y() - self.height() / 2) / self._scale(), z)

    def _offset_xyz(self, anchor, delta):
        atom = self.molecule.atoms[anchor]
        scale = self._scale()
        return atom.x + delta.x() / scale, atom.y - delta.y() / scale, atom.z

    def _hit_atom(self, point):
        positions = self._atom_positions()
        closest, best = None, math.inf
        for i in reversed(self._paint_order):
            hit_radius = 4 if self._compact or i in self._chain_colors else 15
            offset = positions[i] - point
            distance2 = QPointF.dotProduct(offset, offset)
            if distance2 <= hit_radius ** 2 and distance2 < best:
                if i in self._trace_nodes:
                    rank = self._node_paint_rank.get(i)
                    # Collinear overlaps have no crossing gap. Check visible ink
                    # above this node too, so the foreground remains selectable.
                    if rank is None or any(self._ink[k].hit_distance(positions[i]) < self._ink[k].width / 2
                                           for k in range(rank + 1, len(self._ink))):
                        continue
                closest, best = i, distance2
        return closest

    def _target_at(self, point, *, fragment=False):
        if self.molecule is None:
            return ()
        atom = self._hit_atom(point)
        if self._start is not None and self._pressed is not None and self.tool == "bond":
            return (atom,) if atom is not None and atom != self._pressed else ()
        if atom is not None:
            return (atom,)
        if not fragment and self.tool not in ("select", "bond"):
            return ()
        best = None
        positions = self._atom_positions()
        stroke, spacing = (1., 2.) if self._compact else (1.8, 4.2)
        # Front-to-back picking matches the visible ink at an overlap.
        for line in reversed(self._ink):
            pair = self._trace_bonds.get(tuple(sorted((line.a, line.b))))
            if pair is not None:
                distance = line.hit_distance(point)
                if distance <= .5 * line.width + 2.5 and (best is None or distance < best[0] - .25):
                    best = (distance, *pair)
        for bond in self._ordinary_bonds:
            if fragment and not bond.is_covalent:
                continue
            distance, fraction, length = distance_to_segment(point, positions[bond.a], positions[bond.b])
            half_width = bond_half_width(bond.order, bond.style, stroke, spacing, length, fraction)
            hit_radius = half_width + 2.5 if self._compact else max(7., half_width + 4.)
            if distance <= hit_radius and (best is None or distance < best[0]):
                best = (distance, bond.a, bond.b)
        return best[1:] if best else ()

    def mousePressEvent(self, event):
        if self._start is not None:
            return
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if self.molecule is not None and (event.button() == Qt.MouseButton.LeftButton
                                          or alt and event.button() == Qt.MouseButton.RightButton):
            self.setFocus()
            self._track_hover(None)
            self._button = event.button()
            self._press_tool = self.tool
            self._start = event.position()
            self._press_target = self._target_at(self._start, fragment=alt)
            if alt:
                self._press_target = self.selected[-1:] or self._press_target
                self._fragment = (connected_component(self._full_bonds, self._press_target[0])
                                  if self._press_target else frozenset())
                if self._button == Qt.MouseButton.LeftButton and self._fragment:
                    self._rotation_center = (sum((self._raw_positions[i] for i in self._fragment), QPointF())
                                             / len(self._fragment))
            self._pressed = self._press_target[0] if len(self._press_target) == 1 else None
            self._can_box = not alt and self.tool == "select" and not self._press_target
            self._append_box = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._start is None:
            if not event.buttons():
                self._track_hover(event.position())
            return
        if not event.buttons() & self._button or self.tool != self._press_tool:
            self.cancel_gesture()
            return
        delta = event.position() - self._start
        if (delta.manhattanLength() < QApplication.startDragDistance()
                and self._drag is None and self._bond_tip is None and self._box is None):
            return
        if self._fragment is not None:
            if self._fragment:
                self._drag = delta
        elif self._can_box:
            self._box = QRectF(self._start, event.position()).normalized()
        elif self._pressed is not None and self.tool == "select":
            self._drag = delta
        elif self._pressed is not None and self.tool == "bond":
            self._track_hover(event.position())
            if self.bond_order:
                self._bond_tip = event.position()
        self.update()

    def _rotation_degrees(self, delta):
        start = self._start - self._rotation_center
        if math.hypot(start.x(), start.y()) < 8:
            # At the pivot there is no initial radial direction.
            return .7 * (delta.x() - delta.y())
        end = start + delta
        cross = start.y() * end.x() - start.x() * end.y()
        return math.degrees(math.atan2(cross, QPointF.dotProduct(start, end)))

    def mouseReleaseEvent(self, event):
        if self._start is None or event.button() != self._button:
            return
        start, index, fragment = self._start, self._pressed, self._fragment
        delta = event.position() - start
        moved = delta.manhattanLength() >= QApplication.startDragDistance()
        degrees = self._rotation_degrees(delta) if self._rotation_center is not None else None
        box_select = self._can_box and (moved or self._box is not None)
        append = self._append_box or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.cancel_gesture()
        if self.tool != self._press_tool:
            return
        if fragment is not None:
            if moved and fragment:
                if degrees is None:
                    scale = self._scale()
                    self.fragment_moved.emit(self._press_target[0], delta.x() / scale, -delta.y() / scale)
                elif len(fragment) > 1 and abs(degrees) > 1e-10:
                    self.fragment_rotated.emit(self._press_target[0], degrees)
        elif box_select:
            rect = QRectF(start, event.position()).normalized()
            positions = self._atom_positions()
            indices = [i for i in self._visible_indices if rect.contains(positions[i])]
            self.box_selected.emit(indices, append)
        elif moved:
            if self.tool == "select" and index is not None:
                self.atom_moved.emit(index, *self._offset_xyz(index, delta))
            elif self.tool == "bond" and index is not None:
                other = self._hit_atom(event.position())
                if other is not None and other != index:
                    self.bond_clicked.emit(index, other)
                elif other is None and self.bond_order:
                    pos = self._offset_xyz(index, event.position() - self.atom_position(index))
                    self.bond_to_space.emit(index, *pos)
        elif index is not None and self.tool == "select" and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.atom_shift_clicked.emit(index)
        elif index is not None:
            fixed = self.mapToGlobal(self.atom_position(index)) if self.tool == "hydrogen" else None
            self.atom_clicked.emit(index)
            if fixed is not None:
                # Showing or clearing a diagnostic resizes the sketch. Keep
                # the target at its old screen point for successive H clicks.
                delta = self.atom_position(index) - self.mapFromGlobal(fixed)
                scale = self._scale()
                self._center = (self._center[0] + delta.x() / scale, self._center[1] - delta.y() / scale)
                self.update()
        elif len(self._press_target) == 2:
            self.bond_clicked.emit(*self._press_target)
        else:
            anchor = self.selected[-1] if self.selected else None
            self.space_clicked.emit(*self._xyz(event.position(), anchor))
        self._track_hover(self.mapFromGlobal(event.globalPosition()))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._start is not None:
            self.cancel_gesture()
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_requested.emit()
        else:
            super().keyPressEvent(event)

    def event(self, event):
        if event.type() in (QEvent.Type.UngrabMouse, QEvent.Type.FocusOut, QEvent.Type.Hide,
                            QEvent.Type.WindowDeactivate) and getattr(self, "_start", None) is not None:
            self.cancel_gesture()
        return super().event(event)

    def has_exportable_structure(self):
        return self.molecule is not None and bool(self._visible_indices)

    def paint_structure(self, painter):
        """Paint the committed sketch in widget coordinates on any background."""
        if not self.has_exportable_structure():
            return
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBackgroundMode(Qt.BGMode.TransparentMode)
            self._draw_molecule(painter, interactive=False)
        finally:
            painter.restore()

    def _draw_molecule(self, painter, *, interactive):
        ink = QColor("#3E4141")
        positions = self._atom_positions()
        ink_lines = self._ink
        if interactive and self._drag is not None:
            raw = list(self._raw_positions)
            if self._rotation_center is not None:
                transform = QTransform().rotate(-self._rotation_degrees(self._drag))
                for index in self._fragment:
                    offset = raw[index] - self._rotation_center
                    raw[index] = self._rotation_center + transform.map(offset)
            else:
                for index in self._fragment or (self._pressed,):
                    raw[index] = raw[index] + self._drag
            positions, ink_lines = self._trace_projection(raw)
        font = self.font()
        font.setPixelSize(17)
        font.setBold(True)
        painter.setFont(font)
        hover = self._refresh_hover() if interactive else ()
        selected_indices = set(self.selected) if interactive else set()
        label_indices = self._paint_order
        stroke, spacing = (1., 2.) if self._compact else (1.8, 4.2)
        if self._compact or self._chain_colors:
            focus = selected_indices.copy() if len(selected_indices) <= 2 else set()
            if len(hover) == 1:
                focus.add(hover[0])
            label_indices = [i for i in self._paint_order
                             if i in focus or (not self._compact and i not in self._chain_colors)]
        boxes, masks = {}, {}
        metrics = painter.fontMetrics()
        for i in label_indices:
            width = max(23, metrics.horizontalAdvance(self.molecule.atoms[i].element) + 7)
            p = positions[i]
            boxes[i] = QRectF(p.x() - width / 2, p.y() - 12, width, 24)
            masks[i] = QSizeF(width / 2 + 1, 13)
        dot_radius = max(1.1, min(2.8, .19 * self._scale()))
        painter.save()
        if not interactive and (self._ordinary_bonds or ink_lines) and boxes:
            # Cut the underlying bond layer away, including any unrelated bond
            # crossing a label. The holes retain the caller's actual background.
            labels = QPainterPath()
            labels.setFillRule(Qt.FillRule.WindingFill)
            for box in boxes.values():
                labels.addRoundedRect(box, 6, 6)
            visible = QPainterPath()
            visible.addRect(QRectF(self.rect()))
            painter.setClipPath(visible.subtracted(labels), Qt.ClipOperation.IntersectClip)
        for line in ink_lines:
            line.paint(painter, highlighted=hover in ((line.a, line.b), (line.b, line.a)))
        for bond in self._ordinary_bonds:
            if hover == (bond.a, bond.b):
                span = positions[bond.b] - positions[bond.a]
                width = bond_half_width(bond.order, bond.style, stroke, spacing, math.hypot(span.x(), span.y()))
                painter.setPen(QPen(QColor("#A2DCD7"), 2 * width + 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(positions[bond.a], positions[bond.b])
            draw_bond(painter, positions[bond.a], positions[bond.b], bond.order, bond.style, ink, stroke, spacing,
                      clearance=(masks.get(bond.a, dot_radius), masks.get(bond.b, dot_radius)),
                      interior=ring_center(self._aromatic_paths.get(bond), positions))
        painter.restore()
        if interactive and self._bond_tip is not None:
            draw_bond(painter, positions[self._pressed], self._bond_tip, self.bond_order, self.bond_style,
                      QColor("#9F5970"), 1.6, 4.2, clearance=(masks.get(self._pressed, dot_radius), 0))
        if self._compact or self._chain_colors:
            # Keep atoms and bonds visible beneath the focused element labels.
            colors = {"C": "#4C5353", "H": "#9BA2A2", **self._label_colors}
            for i in self._paint_order:
                if not self._compact and i not in self._chain_colors:
                    continue
                element = self.molecule.atoms[i].element
                selected = i in selected_indices
                if i in self._trace_nodes and not selected:
                    continue
                painter.setPen(QPen(QColor("#9F5970"), 1.5) if selected else Qt.PenStyle.NoPen)
                if i in self._chain_colors:
                    painter.setBrush(self._chain_colors[i])
                    radius = 2.3
                else:
                    painter.setBrush(QColor(colors.get(element, "#394445")))
                    radius = dot_radius * (.65 if element == "H" else 1.)
                radius += int(selected)
                painter.drawEllipse(positions[i], radius, radius)
        for i in label_indices:
            el = self.molecule.atoms[i].element
            box = boxes[i]
            if interactive:
                selected = i in selected_indices
                background = _PAPER
                if hover == (i,):
                    background = QColor("#D8F1EC")
                    painter.setPen(QPen(QColor("#157D7B"), 1.7))
                    painter.setBrush(background)
                    painter.drawRoundedRect(box.adjusted(-3, -3, 3, 3), 8, 8)
                painter.setPen(QPen(QColor("#9F5970"), 1.5) if selected else Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#F6E7EC") if selected else background)
                painter.drawRoundedRect(box, 6, 6)
            painter.setPen(QColor(self._label_colors.get(el, "#394445")))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, el)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), _PAPER)
        if self.molecule is None:
            return
        self._draw_molecule(painter, interactive=True)
        if self._box is not None:
            painter.setPen(QPen(QColor("#904359"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(144, 67, 89, 30))
            painter.drawRect(self._box)

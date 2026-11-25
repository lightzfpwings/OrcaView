"""Interactive molecular drawing in the active sketch's XY coordinates."""

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

from orcaview.core.geometry import display_bonds
from orcaview.gui.bond_drawing import aromatic_ring_paths, bond_half_width, draw_bond, ring_center
from orcaview.gui.design_picking import MoleculeEditView, distance_to_segment
from orcaview.i18n import tr


_PAPER = QColor("#FFFDF9")
_LABEL_COLORS = {"O": "#B84138", "N": "#3265A7", "S": "#856224", "Cl": "#237B54",
                 "F": "#237B54", "Br": "#8F5141", "I": "#79559B", "P": "#AA5729"}


class DesignCanvas(MoleculeEditView):
    atom_clicked = Signal(int)
    atom_shift_clicked = Signal(int)
    box_selected = Signal(list, bool)
    space_clicked = Signal(float, float, float)
    atom_moved = Signal(int, float, float, float)
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
        self._box = None
        self._can_box = self._append_box = False
        self._track_hover(None)
        self.update()

    def set_molecule(self, molecule, *, fit=False, independent_sketch=False):
        self.molecule = molecule
        self._projection_key = None
        # A detached drawing has no depth. Keep its paint and hit-test order
        # stable when a 3D optimization moves atoms through the page plane.
        self._paint_order = list(range(len(molecule.atoms)))
        if not independent_sketch:
            self._paint_order.sort(key=lambda i: molecule.atoms[i].z)
        self._bonds = display_bonds(molecule)
        self._aromatic_paths = aromatic_ring_paths(self._bonds)
        self.cancel_gesture()
        if fit:
            self.fit()
        self.update()

    def fit(self):
        if self.molecule is not None and self.molecule.atoms:
            coords = tuple(zip(*((atom.x, atom.y) for atom in self.molecule.atoms)))
            self._center = tuple((min(values) + max(values)) / 2 for values in coords)
            self._extent = tuple(max(1., max(values) - min(values)) for values in coords)
        else:
            self._center = (0., 0.)
            self._extent = (1., 1.)
        self.update()

    def _scale(self):
        # Thumbnail exports can be smaller than the sketch editor's margins.
        w, h = self.width(), self.height()
        return min(72., (w - min(68., .4 * w)) / self._extent[0],
                   (h - min(80., .4 * h)) / self._extent[1])

    def _atom_positions(self):
        scale = self._scale()
        key = (self.width(), self.height(), self._center, scale)
        if key != self._projection_key:
            cx, cy = self._center
            w, h = self.width() / 2, self.height() / 2
            self._positions = tuple(QPointF(w + (atom.x - cx) * scale, h - (atom.y - cy) * scale)
                                    for atom in self.molecule.atoms)
            self._projection_key = key
        return self._positions

    def atom_position(self, index):
        return QPointF(self._atom_positions()[index])

    def _xyz(self, point, anchor):
        atoms = self.molecule.atoms
        z = atoms[anchor].z if anchor is not None else sum(a.z for a in atoms) / max(1, len(atoms))
        return (self._center[0] + (point.x() - self.width() / 2) / self._scale(),
                self._center[1] - (point.y() - self.height() / 2) / self._scale(), z)

    def _hit_atom(self, point):
        positions = self._atom_positions()
        closest, best = None, math.inf
        for i in reversed(self._paint_order):
            offset = positions[i] - point
            distance2 = QPointF.dotProduct(offset, offset)
            if distance2 <= 15 ** 2 and distance2 < best:
                closest, best = i, distance2
        return closest

    def _target_at(self, point):
        if self.molecule is None:
            return ()
        atom = self._hit_atom(point)
        if self._start is not None and self._pressed is not None and self.tool == "bond":
            return (atom,) if atom is not None and atom != self._pressed else ()
        if atom is not None:
            return (atom,)
        if self.tool not in ("select", "bond"):
            return ()
        best = None
        positions = self._atom_positions()
        for bond in self._bonds:
            distance, fraction, length = distance_to_segment(point, positions[bond.a], positions[bond.b])
            half_width = bond_half_width(bond.order, bond.style, 1.8, 4.2, length, fraction)
            if distance <= max(7., half_width + 4.) and (best is None or distance < best[0]):
                best = (distance, bond.a, bond.b)
        return best[1:] if best else ()

    def mousePressEvent(self, event):
        self.cancel_gesture()
        if event.button() == Qt.MouseButton.LeftButton and self.molecule is not None:
            self.setFocus()
            self._press_tool = self.tool
            self._start = event.position()
            self._press_target = self._target_at(self._start)
            self._pressed = self._press_target[0] if len(self._press_target) == 1 else None
            self._can_box = self.tool == "select" and not self._press_target
            self._append_box = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._start is None:
            if not event.buttons():
                self._track_hover(event.position())
            return
        if not event.buttons() & Qt.MouseButton.LeftButton or self.tool != self._press_tool:
            self.cancel_gesture()
            return
        delta = event.position() - self._start
        if (delta.manhattanLength() < QApplication.startDragDistance()
                and self._drag is None and self._bond_tip is None and self._box is None):
            return
        if self._can_box:
            self._box = QRectF(self._start, event.position()).normalized()
        elif self._pressed is not None and self.tool == "select":
            self._drag = self.atom_position(self._pressed) + delta
        elif self._pressed is not None and self.tool == "bond":
            self._track_hover(event.position())
            if self.bond_order:
                self._bond_tip = event.position()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        start, index = self._start, self._pressed
        delta = event.position() - start
        moved = delta.manhattanLength() >= QApplication.startDragDistance()
        box_select = self._can_box and (moved or self._box is not None)
        append = self._append_box or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.cancel_gesture()
        if self.tool != self._press_tool:
            return
        if box_select:
            rect = QRectF(start, event.position()).normalized()
            indices = [i for i in range(len(self.molecule.atoms)) if rect.contains(self.atom_position(i))]
            self.box_selected.emit(indices, append)
        elif moved:
            if self.tool == "select" and index is not None:
                self.atom_moved.emit(index, *self._xyz(self.atom_position(index) + delta, index))
            elif self.tool == "bond" and index is not None:
                other = self._hit_atom(event.position())
                if other is not None and other != index:
                    self.bond_clicked.emit(index, other)
                elif other is None and self.bond_order:
                    self.bond_to_space.emit(index, *self._xyz(event.position(), index))
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
        return self.molecule is not None and bool(self.molecule.atoms)

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
        if interactive and self._drag is not None:
            positions = list(positions)
            positions[self._pressed] = self._drag
        font = self.font()
        font.setPixelSize(17)
        font.setBold(True)
        painter.setFont(font)
        widths = [max(23, painter.fontMetrics().horizontalAdvance(atom.element) + 7)
                  for atom in self.molecule.atoms]
        masks = [QSizeF(w / 2 + 1, 13) for w in widths]
        boxes = [QRectF(p.x() - w / 2, p.y() - 12, w, 24) for p, w in zip(positions, widths)]
        hover = self._refresh_hover() if interactive else ()
        painter.save()
        if not interactive and self._bonds:
            # Cut the underlying bond layer away, including any unrelated bond
            # crossing a label. The holes retain the caller's actual background.
            labels = QPainterPath()
            labels.setFillRule(Qt.FillRule.WindingFill)
            for box in boxes:
                labels.addRoundedRect(box, 6, 6)
            visible = QPainterPath()
            visible.addRect(QRectF(self.rect()))
            painter.setClipPath(visible.subtracted(labels), Qt.ClipOperation.IntersectClip)
        for bond in self._bonds:
            if hover == (bond.a, bond.b):
                span = positions[bond.b] - positions[bond.a]
                width = bond_half_width(bond.order, bond.style, 1.8, 4.2, math.hypot(span.x(), span.y()))
                painter.setPen(QPen(QColor("#A2DCD7"), 2 * width + 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(positions[bond.a], positions[bond.b])
            draw_bond(painter, positions[bond.a], positions[bond.b], bond.order, bond.style, ink, 1.8, 4.2,
                      clearance=(masks[bond.a], masks[bond.b]),
                      interior=ring_center(self._aromatic_paths.get(bond), positions))
        painter.restore()
        if interactive and self._bond_tip is not None:
            draw_bond(painter, positions[self._pressed], self._bond_tip, self.bond_order, self.bond_style,
                      QColor("#9F5970"), 1.6, 4.2, clearance=(masks[self._pressed], 0))
        selected_indices = set(self.selected)
        for i in self._paint_order:
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

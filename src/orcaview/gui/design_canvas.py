"""Interactive molecular drawing in the active sketch's XY coordinates."""

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from orcaview.core.geometry import display_bonds
from orcaview.gui.bond_drawing import aromatic_ring_paths, draw_bond, ring_center
from orcaview.i18n import tr


class DesignCanvas(QWidget):
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
        self.setAccessibleName(tr("分子草图"))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(210, 220)
        self.molecule = None
        self.selected = []
        self.tool = "select"
        self.bond_order = 1
        self.bond_style = "plain"
        self._center = (0., 0.)
        self._extent = (1., 1.)
        self.cancel_gesture()

    def cancel_gesture(self):
        self._start = self._pressed = self._drag = self._bond_tip = None
        self._box = None
        self._can_box = self._append_box = False
        self.update()

    def set_molecule(self, molecule, *, fit=False, independent_sketch=False):
        self.molecule = molecule
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
        return min(72., (self.width() - 68) / self._extent[0],
                   (self.height() - 80) / self._extent[1])

    def atom_position(self, index):
        atom = self.molecule.atoms[index]
        return QPointF(self.width() / 2 + (atom.x - self._center[0]) * self._scale(),
                       self.height() / 2 - (atom.y - self._center[1]) * self._scale())

    def _xyz(self, point, anchor):
        atoms = self.molecule.atoms
        z = atoms[anchor].z if anchor is not None else sum(a.z for a in atoms) / max(1, len(atoms))
        return (self._center[0] + (point.x() - self.width() / 2) / self._scale(),
                self._center[1] - (point.y() - self.height() / 2) / self._scale(), z)

    def _hit_atom(self, point):
        hits = []
        for layer, i in enumerate(self._paint_order):
            offset = self.atom_position(i) - point
            hits.append((math.hypot(offset.x(), offset.y()), -layer, i))
        distance, _, index = min(hits, default=(math.inf, 0, None))
        return index if distance <= 15 else None

    def _hit_bond(self, point):
        best = None
        for bond in self._bonds:
            a, b = self.atom_position(bond.a), self.atom_position(bond.b)
            vector = b - a
            length2 = QPointF.dotProduct(vector, vector)
            if length2 == 0:
                continue
            fraction = max(0., min(1., QPointF.dotProduct(point - a, vector) / length2))
            miss = point - (a + vector * fraction)
            distance = math.hypot(miss.x(), miss.y())
            if distance <= 7 and (best is None or distance < best[0]):
                best = (distance, bond.a, bond.b)
        return best

    def mousePressEvent(self, event):
        self.cancel_gesture()
        if event.button() == Qt.MouseButton.LeftButton and self.molecule is not None:
            self.setFocus()
            self._press_tool = self.tool
            self._start = event.position()
            self._pressed = self._hit_atom(self._start)
            self._can_box = (self.tool == "select" and self._pressed is None
                             and self._hit_bond(self._start) is None)
            self._append_box = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._start is None:
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
        elif self._pressed is not None and self.tool == "bond" and self.bond_order:
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
            return
        if moved:
            if self.tool == "select" and index is not None:
                self.atom_moved.emit(index, *self._xyz(self.atom_position(index) + delta, index))
            elif self.tool == "bond" and index is not None:
                other = self._hit_atom(event.position())
                if other is not None and other != index:
                    self.bond_clicked.emit(index, other)
                elif other is None and self.bond_order:
                    self.bond_to_space.emit(index, *self._xyz(event.position(), index))
            return
        if index is not None and self.tool == "select" and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
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
        elif self.tool in ("select", "bond") and (hit := self._hit_bond(event.position())) is not None:
            self.bond_clicked.emit(hit[1], hit[2])
        else:
            anchor = self.selected[-1] if self.selected else None
            self.space_clicked.emit(*self._xyz(event.position(), anchor))

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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paper = QColor("#FFFDF9")
        painter.fillRect(self.rect(), paper)
        if self.molecule is None:
            return
        ink = QColor("#3E4141")
        positions = [self.atom_position(i) for i in range(len(self.molecule.atoms))]
        if self._drag is not None:
            positions[self._pressed] = self._drag
        font = painter.font()
        font.setPixelSize(17)
        font.setBold(True)
        painter.setFont(font)
        widths = [max(23, painter.fontMetrics().horizontalAdvance(atom.element) + 7)
                  for atom in self.molecule.atoms]
        masks = [QSizeF(w / 2 + 1, 13) for w in widths]
        for bond in self._bonds:
            draw_bond(painter, positions[bond.a], positions[bond.b], bond.order, bond.style, ink, 1.8, 4.2,
                      clearance=(masks[bond.a], masks[bond.b]),
                      interior=ring_center(self._aromatic_paths.get(bond), positions))
        if self._bond_tip is not None:
            draw_bond(painter, positions[self._pressed], self._bond_tip, self.bond_order, self.bond_style,
                      QColor("#9F5970"), 1.6, 4.2, clearance=(masks[self._pressed], 0))
        colors = {"O": "#B84138", "N": "#3265A7", "S": "#856224", "Cl": "#237B54",
                  "F": "#237B54", "Br": "#8F5141", "I": "#79559B", "P": "#AA5729"}
        selected_indices = set(self.selected)
        for i in self._paint_order:
            el = self.molecule.atoms[i].element
            p = positions[i]
            width = widths[i]
            box = QRectF(p.x() - width / 2, p.y() - 12, width, 24)
            selected = i in selected_indices
            painter.setPen(QPen(QColor("#9F5970"), 1.5) if selected else Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#F6E7EC") if selected else paper)
            painter.drawRoundedRect(box, 6, 6)
            painter.setPen(QColor(colors.get(el, "#394445")))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, el)
        if self._box is not None:
            painter.setPen(QPen(QColor("#904359"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(144, 67, 89, 30))
            painter.drawRect(self._box)

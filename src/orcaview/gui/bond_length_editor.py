"""Measure selected atom pairs and adjust the length of acyclic bonds."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from orcaview.core.geometry import display_bonds
from orcaview.editing import CoordinateDefinition, SetBondLength, measure
from orcaview.editing.coordinates import bond_moving_atoms
from orcaview.i18n import diagnostic_text, tr


class BondLengthEditor(QWidget):
    apply_requested = Signal(object)
    swap_requested = Signal()

    def __init__(self):
        super().__init__()
        self.coordinate = None
        self.moving_atoms = ()
        self._initial_value = 0.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.summary = QLabel()
        self.summary.setObjectName("designBondDistance")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.details = QLabel()
        self.details.setObjectName("designBondSide")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.controls = QWidget()
        row = QHBoxLayout(self.controls)
        row.setContentsMargins(0, 0, 0, 0)
        self.target = QDoubleSpinBox()
        self.target.setObjectName("designTargetLength")
        self.target.setDecimals(6)
        self.target.setRange(0.000001, 1e12)
        self.target.setSingleStep(.01)
        self.target.setSuffix(" Å")
        self.target.setAccessibleName(tr("目标键长"))
        row.addWidget(QLabel(tr("目标键长")))
        row.addWidget(self.target, 1)
        self.swap = QPushButton("⇄")
        self.swap.setObjectName("designSwapBondEnds")
        self.swap.setToolTip(tr("交换固定端和移动端"))
        self.swap.setAccessibleName(self.swap.toolTip())
        self.swap.clicked.connect(self.swap_requested)
        row.addWidget(self.swap)
        self.apply = QPushButton(tr("应用"))
        self.apply.setObjectName("designApplyBondLength")
        self.apply.clicked.connect(self._apply)
        self.target.valueChanged.connect(self._target_changed)
        row.addWidget(self.apply)
        layout.addWidget(self.controls)

    def set_selection(self, snapshot, indices):
        self.coordinate = None
        self.moving_atoms = ()
        self.controls.hide()
        self.details.hide()
        if len(indices) != 2:
            self.summary.setText(tr("键长：点选一条键，或按住 Shift 依次选择两个原子。"))
            return
        labels = [f"{snapshot.molecule.atoms[i].element}{i + 1}" for i in indices]
        definition = CoordinateDefinition(snapshot.ref, "distance", tuple(snapshot.atom_ids[i] for i in indices))
        self.summary.setText("–".join(labels))
        try:
            distance = measure(snapshot, definition)
            self.summary.setText(tr("{first}–{second} 距离  {distance:.6f} Å",
                                    first=labels[0], second=labels[1], distance=distance))
            self.details.show()
            self.moving_atoms = bond_moving_atoms(snapshot, definition, display_bonds(snapshot.molecule))
        except ValueError as exc:
            self.details.setText(diagnostic_text(exc))
            self.details.show()
            return
        if distance == 0:
            self.details.setText(tr("端点重合，无法沿键轴移动。"))
            return
        self.coordinate = definition
        self.details.setText(tr("固定 {fixed}，移动 {moving} 一侧的 {count} 个原子。",
                                fixed=labels[0], moving=labels[1], count=len(self.moving_atoms)))
        self.target.setValue(distance)
        self._initial_value = self.target.value()
        self.apply.setEnabled(False)
        self.controls.show()

    def _target_changed(self, value):
        self.apply.setEnabled(self.coordinate is not None and value != self._initial_value)

    def _apply(self):
        if self.coordinate is not None and self.apply.isEnabled():
            self.apply_requested.emit(SetBondLength(self.coordinate, self.target.value(),
                                                   self.moving_atoms, self.coordinate.atom_ids[:1]))

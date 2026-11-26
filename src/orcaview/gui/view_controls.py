"""Shared camera controls for molecular structures and vibrational motion."""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QPushButton, QWidget

from orcaview.gui.view_icons import rotation_icon
from orcaview.i18n import tr


DEFAULT_ROTATION_STEP = 15.


class ViewControls(QWidget):
    def __init__(self, current_view):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        reset = QPushButton(tr("Reset view"))
        reset.setObjectName("resetView")
        reset.setAutoDefault(False)
        reset.clicked.connect(lambda: current_view().fit())
        layout.addWidget(reset)
        layout.addWidget(self._rotation_controls(current_view))

    def _rotation_controls(self, current_view):
        controls = QWidget()
        controls.setObjectName("rotationControls")
        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.rotation_angle = QDoubleSpinBox()
        self.rotation_angle.setObjectName("rotationAngle")
        self.rotation_angle.setRange(0, 360)
        self.rotation_angle.setDecimals(2)
        self.rotation_angle.setValue(DEFAULT_ROTATION_STEP)
        self.rotation_angle.setSuffix("°")
        self.rotation_angle.setAccessibleName(tr("Rotation angle"))
        self.rotation_angle.setToolTip(tr("Angle per click of a rotation button"))
        for name, label, hint, axis, sign in (
            ("rotateLeft", tr("Left"), tr("Turn left about the view’s y-axis"), "y", -1),
            ("rotateRight", tr("Right"), tr("Turn right about the view’s y-axis"), "y", 1),
            ("rotateForward", tr("Forward"), tr("Tilt the top edge toward you about the view’s x-axis"), "x", 1),
            ("rotateBackward", tr("Back"), tr("Tilt the top edge away from you about the view’s x-axis"), "x", -1),
            ("rotateUp", tr("Up ↺"), tr("Rotate counterclockwise about the view’s z-axis to raise the right edge"), "z", 1),
            ("rotateDown", tr("Down ↻"), tr("Rotate clockwise about the view’s z-axis to lower the right edge"), "z", -1),
        ):
            if name in ("rotateForward", "rotateUp"):
                layout.addSpacing(4)
            button = QPushButton()
            button.setObjectName(name)
            button.setAutoDefault(False)
            button.setIcon(rotation_icon(axis, sign))
            button.setIconSize(QSize(20, 20))
            button.setAccessibleName(label)
            button.setToolTip(hint)
            button.clicked.connect(
                lambda checked=False, axis=axis, sign=sign:
                current_view().rotate_view(axis, sign * self.rotation_angle.value())
            )
            layout.addWidget(button)
        layout.addSpacing(5)
        layout.addWidget(self.rotation_angle)
        return controls

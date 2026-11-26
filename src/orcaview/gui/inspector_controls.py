"""Windows subcontrols for the calculation inspector."""

from pathlib import Path

from PySide6.QtCore import QDir

from orcaview.gui import typography


def apply_inspector_control_style(panel):
    if not typography.WINDOWS:
        return
    # A Qt search path keeps QSS URLs valid even inside a Unicode install path.
    QDir.setSearchPaths("orcaviewInspector", [str(Path(__file__).with_name("assets"))])
    panel.setStyleSheet("""
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button, QComboBox::drop-down {
            subcontrol-origin: padding;
            width: 22px;
            background: transparent;
            border: none;
        }
        QAbstractSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 3px; }
        QAbstractSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 3px; }
        QComboBox::drop-down {
            subcontrol-position: center right;
            border-top-right-radius: 3px; border-bottom-right-radius: 3px;
        }
        QAbstractSpinBox::up-arrow {
            image: url(orcaviewInspector:step-up.svg);
            width: 10px; height: 6px;
        }
        QAbstractSpinBox::down-arrow, QComboBox::down-arrow {
            image: url(orcaviewInspector:step-down.svg);
            width: 10px; height: 6px;
        }
        QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover,
        QComboBox::drop-down:hover { background: #F2E4E6; }
        QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed,
        QComboBox::drop-down:pressed { background: #E5CDD2; }
    """)

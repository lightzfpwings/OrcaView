"""Foldable editors for the input blocks supported by the current calculation."""

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QLabel, QLineEdit, QPushButton, QSizePolicy, QStyle, QStyleOptionToolButton,
    QStylePainter, QToolButton, QVBoxLayout, QWidget,
)

from orcaview.i18n import tr
from orcaview.core.block_options import BlockOverride, available_options, parse_option_value
from orcaview.gui.inspector_form import InspectorForm, wrap_parameter_text


class _Disclosure(QToolButton):
    def __init__(self, text):
        super().__init__()
        self.setText(text)
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setArrowType(Qt.ArrowType.RightArrow)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.toggled.connect(lambda expanded: self.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow))

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, event):
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        shortage = self.sizeHint().width() - self.width()
        if shortage > 0:
            metrics = option.fontMetrics
            width = max(0, metrics.horizontalAdvance(option.text) - shortage)
            option.text = metrics.elidedText(option.text, Qt.TextElideMode.ElideRight, width)
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, option)


def _caption(title, count):
    return f"{title} ({count})" if count else title


def _block_label(name):
    return "%" + name.replace(".", " → ")


def _input_field(option, text, on_edit):
    if option.kind in ("choice", "bool"):
        control = QComboBox()
        control.addItem(tr("ORCA default"), "")
        if option.kind == "bool":
            control.addItem(tr("On (true)"), "true")
            control.addItem(tr("Off (false)"), "false")
        else:
            for value in option.choices:
                control.addItem(value, value)
        control.setCurrentIndex(max(0, control.findData(text)))
        control.currentIndexChanged.connect(lambda: on_edit(control.currentData()))
    else:
        control = QLineEdit(text)
        control.setClearButtonEnabled(True)
        control.setPlaceholderText(tr("ORCA default"))
        control.textChanged.connect(on_edit)
    control.setMinimumWidth(86)
    control.setAccessibleName(f"%{option.block} {option.key} · {tr(option.label)}")
    control.setToolTip(tr(option.hint or option.label))
    return control


class _BlockGroup(QWidget):
    def __init__(self, name, options, panel):
        super().__init__()
        self.name = name
        self.options = options
        self.panel = panel
        self.fields = {}
        self.body = None
        self.toggle = _Disclosure(_block_label(name))
        self.group_layout = QVBoxLayout(self)
        self.group_layout.setContentsMargins(0, 0, 0, 0)
        self.group_layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.toggle.toggled.connect(self._expand)
        self.update_count()

    def _expand(self, expanded):
        if expanded:
            self.panel.expanded_blocks.add(self.name)
            if self.body is None:
                self._build_fields()
        else:
            self.panel.expanded_blocks.discard(self.name)
        if self.body is not None:
            self.body.setVisible(expanded)

    def _build_fields(self):
        self.body = InspectorForm()
        for option in self.options:
            key = (self.name, option.key)
            field = _input_field(option, self.panel.drafts.get(key, ""),
                                 lambda text, key=key: self.panel.edit(key, text))
            self.fields[option.key] = field
            label = QLabel(f"{wrap_parameter_text(option.key)}\n{tr(option.label)}")
            label.setAccessibleName(f"{option.key} · {tr(option.label)}")
            label.setToolTip(f"{option.key} · {tr(option.hint or option.label)}")
            self.body.addRow(label, field)
        self.reset = QPushButton(tr("Reset this block"))
        self.reset.setAccessibleName(tr("Restore {block} defaults", block=_block_label(self.name)))
        self.reset.setToolTip(self.reset.accessibleName())
        self.reset.clicked.connect(lambda: self.panel.reset_block(self.name))
        self.body.addRow(None, self.reset)
        self.group_layout.addWidget(self.body)
        self.update_count()

    def update_count(self):
        count = sum(block == self.name for block, _ in self.panel.drafts)
        self.toggle.setText(_caption(_block_label(self.name), count))
        if self.body is not None:
            self.reset.setEnabled(bool(count))


class BlockOptionsPanel(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.toggle = _Disclosure(tr("Advanced input blocks"))
        self.body = QWidget()
        self.body.hide()
        self.groups_layout = QVBoxLayout(self.body)
        self.groups_layout.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.body)
        self.toggle.toggled.connect(self._expand)
        self.options = {}
        self.groups = {}
        self.expanded_blocks = set()
        self.drafts = {}

    def load(self, spec, *, keep_expanded=False):
        if not keep_expanded:
            self.toggle.setChecked(False)
            self.expanded_blocks.clear()
        self.drafts = {(item.block, item.key): str(item.value).lower() if type(item.value) is bool else str(item.value)
                       for item in spec.block_options}
        self.set_context(spec, force=True)

    def set_context(self, spec, *, force=False):
        options = {(option.block, option.key): option for option in available_options(spec)}
        if not force and options == self.options:
            return ()
        removed = []
        for key, draft in list(self.drafts.items()):
            previous = None if force else self.options.get(key)
            if key not in options or (previous is not None and options[key] != previous
                                      and self._no_longer_valid(previous, options[key], draft)):
                del self.drafts[key]
                removed.append(key)
        self.options = options
        self.toggle.setVisible(bool(options))
        self.expanded_blocks.intersection_update(block for block, _ in options)
        self._rebuild_groups()
        self._update_caption()
        return tuple(removed)

    @staticmethod
    def _no_longer_valid(previous, option, draft):
        try:
            parse_option_value(previous, draft)
        except ValueError:
            return False  # Keep unfinished edits available for correction.
        try:
            parse_option_value(option, draft)
        except ValueError:
            return True
        return False

    def overrides(self):
        items = []
        for key, text in self.drafts.items():
            value = parse_option_value(self.options[key], text)
            items.append(BlockOverride(*key, value))
        return tuple(items)

    def _expand(self, expanded):
        if expanded and not self.groups:
            self._rebuild_groups()
        self.body.setVisible(expanded)

    def _rebuild_groups(self):
        for group in self.groups.values():
            self.groups_layout.removeWidget(group)
            group.hide()
            group.deleteLater()
        self.groups.clear()
        if not self.toggle.isChecked():
            return
        by_block = {}
        for option in self.options.values():
            by_block.setdefault(option.block, []).append(option)
        for name, options in by_block.items():
            group = _BlockGroup(name, options, self)
            self.groups[name] = group
            self.groups_layout.addWidget(group)
            group.toggle.setChecked(name in self.expanded_blocks)

    def _update_caption(self):
        self.toggle.setText(_caption(tr("Advanced input blocks"), len(self.drafts)))

    def edit(self, key, text):
        if text:
            self.drafts[key] = text
        else:
            self.drafts.pop(key, None)
        self.groups[key[0]].update_count()
        self._update_caption()
        self.changed.emit()

    def reset_block(self, name):
        group = self.groups[name]
        for key, field in group.fields.items():
            self.drafts.pop((name, key), None)
            with QSignalBlocker(field):
                if isinstance(field, QComboBox):
                    field.setCurrentIndex(0)
                else:
                    field.clear()
        group.update_count()
        self._update_caption()
        self.changed.emit()

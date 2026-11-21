"""Molecular sketch and Cartesian editor for the active document."""

from PySide6.QtCore import QEvent, QSignalBlocker, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QMenu,
                               QPushButton, QSizePolicy, QSplitter, QVBoxLayout, QWidget)

from orcaview.core.models import Atom
from orcaview.core.snapshots import SelectionContext
from orcaview.editing import (AddAtoms, AddHydrogen, AttachAtom, DeleteAtoms, EditorService, GeometryEditCommand, MoveAtom,
                              InsertRing, ReplaceElement, SetBond)
from orcaview.editing.diagnostics import design_diagnostics
from orcaview.gui import typography
from orcaview.gui.bond_button import BondButton
from orcaview.gui.design_canvas import DesignCanvas
from orcaview.gui.bond_length_editor import BondLengthEditor
from orcaview.gui.element_picker import ElementPicker
from orcaview.gui.ring_button import RingTemplateButton
from orcaview.gui.structure_job import StructureJob
from orcaview.gui.view_icons import hydrogen_cursor
from orcaview.gui.viewport import MoleculeViewport
from orcaview.i18n import diagnostic_text, tr


class DesignPanel(QWidget):
    geometry_changed = Signal()
    new_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("designPanel")
        self.setStyleSheet(typography.stylesheet("""
            QWidget#designPanel { background: #FAF7F2; }
            QWidget#designPanel QPushButton:checked { color: #7C354F; background: #F1E3E8; border-color: #AE7F8E; }
            QWidget#designPanel QLabel#designSection { color: #433B37; font-weight: $section_weight; }
            QWidget#designPanel QLabel#designHint { color: #70635F; }
            QWidget#designPanel QLabel#designProblems { color: #944A25; }
            QWidget#designPanel QSplitter::handle { background: #DDD5CB; }
        """))
        self.editor = None
        self._structure_job = None
        self._bond_start = None
        self._order = 1
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        tool_row = QWidget()
        tool_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        toolbar = QHBoxLayout(tool_row)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(4)
        layout.addWidget(tool_row)
        self.canvas = DesignCanvas()
        self._tools = QButtonGroup(self)

        def tool(name, label, hint, mode, order=1):
            button = QPushButton(label)
            button.setObjectName(name)
            button.setCheckable(True)
            button.setToolTip(hint)
            button.setAccessibleName(hint)
            self._tools.addButton(button)
            button.clicked.connect(lambda: self._set_tool(mode, order))
            toolbar.addWidget(button)
            return button

        self.select_tool = tool("designSelect", tr("选择"), tr("选择或移动原子"), "select")
        self.select_tool.setChecked(True)
        self.atom_tool = tool("designAtom", tr("原子"), tr("添加或替换原子"), "atom")
        self.element = ElementPicker()
        self.element.setObjectName("designElement")
        self.element.setAccessibleName(tr("绘制元素"))
        self.element.activated.connect(self._element_picked)
        toolbar.addWidget(self.element)
        toolbar.addSpacing(6)
        for order in (1, 2, 3):
            button = BondButton(order, self.element)
            self._tools.addButton(button)
            button.activated.connect(self._activate_bond)
            toolbar.addWidget(button)
        tool("designBond0", "⊘", tr("断开化学键"), "bond", 0)
        self.ring_tool = RingTemplateButton(self.element)
        self.ring_tool.setObjectName("designRing")
        self.ring_tool.setAccessibleName(tr("环模板"))
        self._tools.addButton(self.ring_tool)
        toolbar.addWidget(self.ring_tool)
        self.ring_menu = QMenu(self.ring_tool)
        self.ring_tool.setMenu(self.ring_menu)
        self._ring_size, self._benzene = 6, False
        templates = QActionGroup(self.ring_menu)
        for size, benzene in [(i, False) for i in range(3, 9)] + [(6, True)]:
            label = tr("苯环") if benzene else tr("{size} 元碳环", size=size)
            action = self.ring_menu.addAction(label)
            action.setData((size, benzene))
            templates.addAction(action)
            action.setCheckable(True)
            if (size, benzene) == (self._ring_size, self._benzene):
                action.setChecked(True)
                self.ring_tool.setToolTip(f"{tr('环模板')} · {label}")
        self.ring_menu.triggered.connect(self._choose_ring)
        self.hydrogens = tool("designAddHydrogens", "+H", tr("单击后点原子逐个加氢，双击补全整个结构。"), "hydrogen")
        self.hydrogens.installEventFilter(self)
        self._hydrogen_cursor = hydrogen_cursor()
        self._leave_hydrogens = QAction(self)
        self._leave_hydrogens.setShortcut(Qt.Key.Key_Escape)
        self._leave_hydrogens.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._leave_hydrogens.triggered.connect(self.select_tool.click)
        self.addAction(self._leave_hydrogens)
        toolbar.addStretch()
        self.undo_button = self._button(toolbar, "designUndo", tr("撤销"), lambda: self._history(True))
        self.redo_button = self._button(toolbar, "designRedo", tr("重做"), lambda: self._history(False))
        self.delete_button = self._button(toolbar, "designDelete", tr("删除原子"), self._delete)
        self._button(toolbar, "designNew", tr("新建分子"), self.new_requested.emit)
        # Let the tallest translated label determine the row height, including the element picker.
        for i in range(toolbar.count()):
            widget = toolbar.itemAt(i).widget()
            if widget is not None:
                widget.setAttribute(Qt.WidgetAttribute.WA_LayoutUsesWidgetRect)
                widget.setSizePolicy(widget.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.MinimumExpanding)
        for key, button in ((QKeySequence.StandardKey.Undo, self.undo_button),
                            (QKeySequence.StandardKey.Redo, self.redo_button)):
            action = QAction(self)
            action.setShortcuts(QKeySequence.keyBindings(key))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(button.click)
            self.addAction(action)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("designSplitter")
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        sketch = QWidget()
        sketch_layout = QVBoxLayout(sketch)
        sketch_layout.setContentsMargins(0, 0, 4, 0)
        sketch_header = QHBoxLayout()
        sketch_layout.addLayout(sketch_header)
        sketch_header.addWidget(self._section(tr("分子草图")))
        sketch_header.addStretch()
        self.clean_2d = self._button(sketch_header, "designClean2D", tr("整理 2D"),
                                     lambda: self._start_structure_job("2D"))
        self.clean_2d.setToolTip(tr("将当前结构排入 XY 平面，规整键长、键角和环。可撤销。"))
        self._button(sketch_header, "designFit", tr("居中"), self.canvas.fit)
        sketch_layout.addWidget(self.canvas, 1)
        splitter.addWidget(sketch)

        preview = QWidget()
        right = QVBoxLayout(preview)
        right.setContentsMargins(4, 0, 0, 0)
        preview_header = QHBoxLayout()
        right.addLayout(preview_header)
        preview_header.addWidget(self._section(tr("三维预览")))
        preview_header.addStretch()
        self.optimize_3d = self._button(preview_header, "designOptimize3D", tr("优化 3D"),
                                         lambda: self._start_structure_job("3D"))
        self.optimize_3d.setToolTip(tr("用 Open Babel 力场预优化当前构象。可撤销。"))
        self.viewport = MoleculeViewport(design_selection=True)
        self.viewport.setObjectName("designViewport")
        self.viewport.setMinimumSize(200, 180)
        right.addWidget(self.viewport, 1)
        atom_row = QHBoxLayout()
        right.addLayout(atom_row)
        atom_row.addWidget(self._section(tr("原子坐标 / Å")))
        self.atom_choice = QComboBox()
        self.atom_choice.setObjectName("designAtomChoice")
        self.atom_choice.setAccessibleName(tr("选择原子"))
        self.atom_choice.setPlaceholderText(tr("选择原子"))
        self.atom_choice.activated.connect(lambda i: self._select([i]))
        atom_row.addWidget(self.atom_choice, 1)
        coords = QHBoxLayout()
        right.addLayout(coords)
        self.coordinates = []
        for axis in "XYZ":
            field = QDoubleSpinBox()
            field.setObjectName("design" + axis)
            field.setAccessibleName(axis + " (Å)")
            field.setRange(-1e12, 1e12)
            field.setDecimals(8)
            field.setSingleStep(0.1)
            field.setMinimumWidth(0)
            field.setSizePolicy(field.sizePolicy().Policy.Ignored, field.sizePolicy().Policy.Fixed)
            coords.addWidget(QLabel(axis))
            coords.addWidget(field, 1)
            self.coordinates.append(field)
        self.apply_button = self._button(coords, "designApplyPosition", tr("应用"), self._apply_coordinates)
        self.bond_length = BondLengthEditor()
        right.addWidget(self.bond_length)
        self.bond_length.apply_requested.connect(self._execute)
        self.bond_length.swap_requested.connect(lambda: self._select(self.canvas.selected[::-1]))
        splitter.addWidget(preview)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        # Equal weights above both pane minima also work before this tab is shown.
        splitter.setSizes([1000, 1000])
        self._divider = splitter.handle(1)
        self._divider.setToolTip(tr("双击恢复两栏等宽"))
        self._divider.installEventFilter(self)

        self.problems = QLabel()
        self.problems.setObjectName("designProblems")
        self.problems.setWordWrap(True)
        self.problems.hide()
        layout.addWidget(self.problems)
        self.status = QLabel()
        self.status.setObjectName("designHint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.canvas.atom_clicked.connect(self._atom_clicked)
        self.canvas.atom_shift_clicked.connect(self._shift_select)
        self.canvas.box_selected.connect(self._box_select)
        self.canvas.space_clicked.connect(self._space_clicked)
        self.canvas.bond_clicked.connect(self._bond_clicked)
        self.canvas.bond_to_space.connect(self._extend_bond)
        self.canvas.atom_moved.connect(self._move)
        self.canvas.delete_requested.connect(self._delete)
        self.viewport.selection_changed.connect(self._select)
        self.viewport.atom_targeted.connect(self._atom_clicked)
        self._set_tool("select")
        self._sync_selection()

    def eventFilter(self, watched, event):
        if (watched is self.hydrogens and event.type() == QEvent.Type.MouseButtonDblClick
                and event.button() == Qt.MouseButton.LeftButton):
            self.hydrogens.setChecked(True)
            self._set_tool("hydrogen")
            self._start_structure_job("H")
            event.accept()
            return True
        if (event.type() == QEvent.Type.MouseButtonDblClick and watched is self._divider
                and event.button() == Qt.MouseButton.LeftButton):
            splitter = watched.splitter()
            width = splitter.contentsRect().width()
            splitter.setSizes([width, width])
            event.accept()
            return True
        return super().eventFilter(watched, event)

    @staticmethod
    def _section(title):
        label = QLabel(title)
        label.setObjectName("designSection")
        return label

    @staticmethod
    def _button(layout, name, label, slot):
        button = QPushButton(label)
        button.setObjectName(name)
        button.clicked.connect(slot)
        layout.addWidget(button)
        return button

    def set_document(self, document):
        if self.editor is not None and self.editor.document is document:
            if self.editor.expected == document.head.ref:
                return
            self.editor.reset_to_head()
            self._refresh()
        else:
            self._structure_job = None
            self.editor = EditorService(document)
            self._refresh(fit=True)

    def use_result_geometry(self, source_ref):
        result = self.editor.use_result_geometry(source_ref)
        if result is not None:
            self._edited()
            self.canvas.fit()

    def discard_pending_job(self):
        self._structure_job = None

    def _start_structure_job(self, mode):
        if self._structure_job is not None or self.editor is None:
            return
        self.set_document(self.editor.document)
        base = self.editor.document.head
        if not base.atom_ids:
            return
        job = StructureJob(base, mode)
        self._structure_job = job
        job.completion.finished.connect(self._finish_structure_job)
        self._sync_selection()
        self.status.setText(tr("正在补氢…") if mode == "H" else tr("正在优化结构…"))
        QThreadPool.globalInstance().start(job)

    @Slot(object, object, str)
    def _finish_structure_job(self, job, command, error):
        if job is not self._structure_job:
            return
        self._structure_job = None
        self.set_document(self.editor.document)
        self._sync_selection()
        if job.snapshot.ref != self.editor.document.head.ref:
            self.status.setText(tr("结构已更改，请重新执行此操作。"))
            return
        if command is None:
            self.status.setText(diagnostic_text(error))
            return
        result = self._commit(command)
        if result is None:
            return
        self.canvas.fit()
        if job.mode == "H":
            self.status.setText(tr("已补加 {count} 个氢原子。", count=len(command.operation.attachments)))
        elif job.mode == "2D":
            self.status.setText(tr("已整理二维结构。"))
        else:
            self.status.setText(tr("已用 {method} 预优化三维结构。", method=command.operation.method))

    def _element_picked(self):
        if self.canvas.tool != "bond" or self._order == 0:
            self.atom_tool.click()

    def _activate_bond(self, order, style):
        self._set_tool("bond", order, style)

    def _set_tool(self, mode, order=1, style="plain"):
        self.canvas.cancel_gesture()
        self.canvas.tool = mode
        self.canvas.bond_order = order
        self.canvas.bond_style = style
        self._order = order
        self._bond_start = None
        targeting = mode == "hydrogen"
        self._leave_hydrogens.setEnabled(targeting)
        self.viewport.atom_targeting = targeting
        if targeting:
            self.canvas.setCursor(self._hydrogen_cursor)
            self.viewport.setCursor(self._hydrogen_cursor)
        else:
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor if mode == "select" else Qt.CursorShape.CrossCursor)
            self.viewport.unsetCursor()
        self._show_hint()

    def _choose_ring(self, action):
        self._ring_size, self._benzene = action.data()
        self.ring_tool.setToolTip(f"{tr('环模板')} · {action.text()}")
        self.ring_tool.setChecked(True)
        self._set_tool("ring")

    def _show_hint(self):
        if self.canvas.molecule is not None and not self.canvas.molecule.atoms:
            text = tr("选择原子工具或环模板，在空白处开始绘制。")
        elif self.canvas.tool == "select":
            text = tr("在二维空白处拖动可框选，拖动原子可移动。按住 Shift 拖动可在任一视图追加框选。")
        elif self.canvas.tool == "atom":
            text = tr("点击空白处添加原子，点击已有原子替换元素。")
        elif self.canvas.tool == "hydrogen":
            text = tr("点击二维或三维视图中的原子添加一个氢。可连续点击；按 Esc 退出。")
        elif self.canvas.tool == "ring":
            text = tr("点击起始碳原子建环，点击其他原子接出环，或点击空白处放置独立环。")
        elif self._bond_start is not None:
            text = tr("点击第二个原子。")
        elif self._order:
            text = tr("点击两个原子连键。从原子拖到空白处可延伸分子。")
        else:
            text = tr("依次点击两个原子，或直接点击已有的键。")
        self.status.setText(text)

    def _refresh(self, *, fit=False):
        head = self.editor.document.head
        self._bond_start = None
        self.canvas.set_molecule(head.molecule, fit=fit)
        if not head.atom_ids and self.canvas.tool == "hydrogen":
            self.select_tool.click()
        with QSignalBlocker(self.viewport):
            self.viewport.set_molecule(head.molecule, keep_view=not fit)
        with QSignalBlocker(self.atom_choice):
            self.atom_choice.clear()
            self.atom_choice.addItems([f"{atom.element}{i}" for i, atom in enumerate(head.molecule.atoms, 1)])
        problems = [diagnostic_text(issue) for issue in design_diagnostics(head.molecule)]
        shown = "\n".join(problems[:2])
        self.problems.setText(shown + (" …" if len(problems) > 2 else ""))
        self.problems.setToolTip("\n".join(problems))
        self.problems.setVisible(bool(problems))
        self._sync_selection()
        self._show_hint()

    def _select(self, indices):
        if self.editor is None:
            return
        head = self.editor.document.head
        ids = tuple(head.atom_ids[i] for i in indices)
        self.editor.set_selection(SelectionContext(head.ref, ids))
        self._sync_selection()

    def _sync_selection(self):
        selected = []
        head = None
        if self.editor is not None:
            head = self.editor.document.head
            selected = list(self.editor.selection.indices(head))
        self.canvas.selected = selected
        self.viewport.selected = selected.copy()
        self.canvas.update()
        self.viewport.update()
        self.atom_choice.setCurrentIndex(selected[0] if len(selected) == 1 else -1)
        has_atoms = self.atom_choice.count() > 0
        self.atom_choice.setEnabled(has_atoms)
        if len(selected) == 1:
            atom = head.molecule.atoms[selected[0]]
            for field, value in zip(self.coordinates, (atom.x, atom.y, atom.z)):
                field.setValue(value)
            self._displayed_xyz = tuple(field.value() for field in self.coordinates)
        else:
            for field in self.coordinates:
                field.clear()
        for field in [*self.coordinates, self.apply_button]:
            field.setEnabled(len(selected) == 1)
        self.delete_button.setEnabled(bool(selected))
        self.undo_button.setEnabled(self.editor is not None and self.editor.can_undo)
        self.redo_button.setEnabled(self.editor is not None and self.editor.can_redo)
        ready = head is not None and self._structure_job is None
        self.hydrogens.setEnabled(has_atoms)
        self.clean_2d.setEnabled(ready and len(head.atom_ids) > 1)
        self.optimize_3d.setEnabled(ready and len(head.atom_ids) > 1)
        self.bond_length.set_selection(head, selected)

    def _shift_select(self, index):
        selected = self.canvas.selected
        if index in selected:
            self._select([i for i in selected if i != index])
        else:
            self._select(selected + [index])

    def _box_select(self, indices, additive):
        if additive:
            indices = list(dict.fromkeys([*self.canvas.selected, *indices]))
        self._select(indices)

    def _execute(self, operation):
        return self._commit(GeometryEditCommand(self.editor.expected, operation))

    def _commit(self, command):
        try:
            result = self.editor.commit(self.editor.preview(command))
        except ValueError as exc:
            self.status.setText(diagnostic_text(exc))
            return
        self._edited()
        return result

    def _edited(self):
        self._refresh()
        self.geometry_changed.emit()

    def _history(self, undo):
        was_empty = not self.editor.document.head.atom_ids
        try:
            if undo:
                self.editor.undo()
            else:
                self.editor.redo()
        except ValueError as exc:
            self.status.setText(diagnostic_text(exc))
            return
        self._edited()
        if was_empty:
            self.canvas.fit()

    def _space_clicked(self, x, y, z):
        if self.canvas.tool == "ring":
            self._insert_ring(center=(x, y, z))
        elif self.canvas.tool == "atom":
            result = self._execute(AddAtoms((Atom(self.element.currentText(), x, y, z),)))
            if result is not None:
                self._select([len(result.snapshot.atom_ids) - 1])
        else:
            self._bond_start = None
            self._select([])
            self._show_hint()

    def _atom_clicked(self, index):
        head = self.editor.document.head
        atom_id = head.atom_ids[index]
        if self.canvas.tool == "ring":
            self._insert_ring(anchor_id=atom_id)
            return
        if self.canvas.tool == "bond" and self._bond_start is not None and self._bond_start != atom_id:
            self._bond_clicked(head.index_of(self._bond_start), index)
            return
        self._select([index])
        if self.canvas.tool == "hydrogen":
            self._execute(AddHydrogen(atom_id))
            self.layout().activate()
        elif self.canvas.tool == "atom":
            element = self.element.currentText()
            if head.molecule.atoms[index].element != element:
                self._execute(ReplaceElement(atom_id, element))
        elif self.canvas.tool == "bond":
            self._bond_start = atom_id
            self._show_hint()

    def _bond_clicked(self, first, second):
        head = self.editor.document.head
        self._bond_start = None
        self._select([first, second])
        if self.canvas.tool == "bond":
            self._execute(SetBond(head.atom_ids[first], head.atom_ids[second], self._order, self.canvas.bond_style))

    def _extend_bond(self, index, x, y, z):
        head = self.editor.document.head
        atom = Atom(self.element.currentText(), x, y, z)
        self._select([index])
        result = self._execute(AttachAtom(head.atom_ids[index], atom, self._order, self.canvas.bond_style))
        if result is not None:
            self._select([len(result.snapshot.atom_ids) - 1])

    def _insert_ring(self, *, center=None, anchor_id=None):
        operation = InsertRing(self._ring_size, self._benzene, "XY", center, anchor_id)
        result = self._execute(operation)
        if result is not None:
            visible = self.canvas.rect().adjusted(15, 15, -15, -15)
            if any(not visible.contains(self.canvas.atom_position(i).toPoint()) for i in result.mapping.added_indices):
                self.canvas.fit()
            self._select([len(result.snapshot.atom_ids) - self._ring_size])

    def _move(self, index, x, y, z):
        self._select([index])
        self._execute(MoveAtom(self.editor.document.head.atom_ids[index], x, y, z))

    def _apply_coordinates(self):
        index = self.atom_choice.currentIndex()
        if index < 0:
            return
        atom = self.editor.document.head.molecule.atoms[index]
        xyz = []
        for axis, field, displayed in zip("xyz", self.coordinates, self._displayed_xyz):
            original = getattr(atom, axis)
            # Keep the original full precision in fields the user did not change.
            xyz.append(original if field.value() == displayed else field.value())
        self._move(index, *xyz)

    def _delete(self):
        if self.delete_button.isEnabled():
            self._execute(DeleteAtoms(self.editor.selection.atom_ids))

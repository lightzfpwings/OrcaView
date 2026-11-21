"""Browse calculation results and their corresponding molecular geometries."""

from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, QModelIndex, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QLabel, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTabWidget,
    QTableView, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from orcaview.i18n import tr

from orcaview.core.snapshots import SelectionContext
from orcaview.editing.coordinates import CoordinateDefinition, measure
from orcaview.gui import typography
from orcaview.gui.atom_table import AtomCoordinateTable
from orcaview.gui.project_navigation import WrappingTreeLabel
from orcaview.gui.result_display import (
    describe, display_file_name, geometry_name, log_filename, log_overview_status, log_property_series, log_reference_snapshot,
    dataset_name, matched_energy_lines, report_text, source_file_details,
)
from orcaview.gui.result_table import CalculationResultTable, enable_table_copy
from orcaview.gui.spectrum_preview import SpectrumPreview
from orcaview.gui.viewport import MoleculeViewport


STYLE = """
QWidget#foundationPanel { background: #FAF7F2; }
QLabel#foundationTitle { color: #372F2D; font-size: 22px; font-weight: $heading_weight; }
QLabel#sectionTitle { color: #372F2D; font-size: 14px; font-weight: $section_weight; padding: 8px 0; }
QTabBar#resultInspectorTabs::tab { padding: 8px 7px; }
QLabel#foundationDetails { color: #372F2D; padding: 10px 8px; }
QLabel#bondLength { color: #76394D; font-weight: $section_weight; padding: 8px; }
QScrollArea, QScrollArea > QWidget > QWidget { background: #FFFDF9; border: none; }
QTreeWidget { background: #FFFDF9; border: 1px solid #DDD5CB; border-radius: 6px; padding: 4px; }
QTreeWidget::item { padding: 8px 3px; }
QTreeWidget::item:selected { color: #904359; background: #F2E4E6; }
QTableView { background: #FFFDF9; alternate-background-color: #FAF7F2; gridline-color: #DDD5CB; border: 1px solid #DDD5CB; border-radius: 6px; }
QTableView#resultDatasets, QStackedWidget#resultValuesFrame, QFrame#resultInspectorFrame {
    background: #FFFDF9; border: 1px solid #B2A397; border-radius: 6px;
}
QTableView#foundationAtoms, QTableView#logValues { border: none; }
QTabWidget#resultInspector::pane { border: none; background: #FFFDF9; }
QHeaderView::section { background: #FAF7F2; padding: 7px 3px; border: none; border-bottom: 1px solid #DDD5CB; color: #70635F; }
QTableView::item { padding: 3px; }
QTableView::item:selected { background: #F2E4E6; color: #904359; }
QSplitter::handle { background: transparent; }
"""


def _label(text="", name=None):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    return label


class _LogTableModel(QAbstractTableModel):
    """Display printed spectral or property rows without building widgets per value."""

    def __init__(self, parent):
        super().__init__(parent)
        self.columns = ()
        self.rows = ()

    def set_table(self, columns, rows):
        self.beginResetModel()
        self.columns, self.rows = tuple(report_text(key) for key in columns), rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            value = self.rows[index.row()][index.column()]
            return "—" if value is None else str(value)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.columns[section]
        return super().headerData(section, orientation, role)


class FoundationPanel(QWidget):
    design_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("foundationPanel")
        self.setStyleSheet(typography.stylesheet(STYLE))
        self.document = None
        self.selected_snapshot = None
        self._dataset_id = None
        self._selected_ids = []
        self._dataset_items = {}
        self._document_view_key = None
        self._input_path = self._project_path = ""
        self._report = None
        self._log_snapshot = None
        self._standalone = False
        self._log_selection = None
        self._preview_index = 0
        self._series = ()
        self._merged_series = {}
        layout = QVBoxLayout(self)
        # Half a splitter gap at each outer edge keeps all three column
        # centers on the quarter, half, and three-quarter window positions.
        column_gap = 10
        layout.setContentsMargins(column_gap // 2, 14, column_gap // 2, 14)
        layout.setSpacing(10)
        self.title = _label(tr("结果"), "foundationTitle")
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.title)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(column_gap)
        left = QWidget()
        navigation = QVBoxLayout(left)
        navigation.setContentsMargins(0, 0, 0, 0)
        navigation.setSpacing(8)
        navigation.addWidget(_label(tr("计算结果"), "sectionTitle"))
        self.datasets = CalculationResultTable()
        self.datasets.horizontalHeader().hide()
        navigation.addWidget(self.datasets, 3)
        navigation.addWidget(_label(tr("光谱"), "sectionTitle"))
        self.spectra = QTreeWidget()
        self.spectra.setObjectName("resultSpectra")
        self.spectra.setHeaderHidden(True)
        self.spectra.setRootIsDecorated(False)
        self.spectra.setItemDelegateForColumn(0, WrappingTreeLabel(self.spectra))
        self.spectra.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.spectra.setMinimumWidth(165)
        navigation.addWidget(self.spectra, 2)
        self.spectrum_preview = SpectrumPreview()
        navigation.addWidget(self.spectrum_preview)
        splitter.addWidget(left)
        self.geometry_pane = QWidget()
        scene = QVBoxLayout(self.geometry_pane)
        scene.setContentsMargins(0, 0, 0, 0)
        self.viewport = MoleculeViewport(result_view=True)
        self.viewport.setMinimumWidth(220)
        self.viewport.setObjectName("foundationViewport")
        scene.addWidget(self.viewport, 1)
        self.design_button = QPushButton(tr("用此结构设计"))
        self.design_button.setObjectName("designResultGeometry")
        self.design_button.setToolTip(tr("将显示的几何带入设计，可撤销此次替换。"))
        self.design_button.setEnabled(False)
        self.design_button.clicked.connect(self._request_design)
        scene.addWidget(self.design_button, alignment=Qt.AlignmentFlag.AlignCenter)
        splitter.addWidget(self.geometry_pane)
        right = QWidget()
        table_layout = QVBoxLayout(right)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(navigation.spacing())
        self.table_title = _label(tr("原子坐标 / Å"), "sectionTitle")
        table_layout.addWidget(self.table_title)
        self.atoms = AtomCoordinateTable()
        self.log_table = QTableView()
        self.log_table.setObjectName("logValues")
        self.log_model = _LogTableModel(self.log_table)
        self.log_table.setModel(self.log_model)
        enable_table_copy(self.atoms)
        enable_table_copy(self.log_table)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.verticalHeader().hide()
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.tables = QStackedWidget()
        self.tables.setObjectName("resultValuesFrame")
        self.tables.setFrameShape(QFrame.Shape.StyledPanel)
        self.tables.addWidget(self.atoms)
        self.tables.addWidget(self.log_table)
        table_layout.addWidget(self.tables, 3)
        self.details = _label("", "foundationDetails")
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(0)
        self.bond_length = _label(name="bondLength")
        self.bond_length.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.bond_length.hide()
        overview_layout.addWidget(self.bond_length)
        overview_scroll = QScrollArea()
        overview_scroll.setWidgetResizable(True)
        overview_scroll.setWidget(self.details)
        overview_layout.addWidget(overview_scroll, 1)
        self.evidence = QPlainTextEdit()
        self.evidence.setReadOnly(True)
        self.inspector_tabs = QTabWidget()
        self.inspector_tabs.setObjectName("resultInspector")
        self.inspector_tabs.tabBar().setObjectName("resultInspectorTabs")
        self.inspector_tabs.addTab(overview, tr("概览"))
        self.inspector_tabs.addTab(self.evidence, tr("来源详情"))
        inspector_frame = QFrame()
        inspector_frame.setObjectName("resultInspectorFrame")
        inspector_frame.setFrameShape(QFrame.Shape.StyledPanel)
        inspector_layout = QVBoxLayout(inspector_frame)
        inspector_layout.setContentsMargins(0, 0, 0, 0)
        inspector_layout.addWidget(self.inspector_tabs)
        table_layout.addWidget(inspector_frame, 2)
        splitter.addWidget(right)
        for index in range(splitter.count()):
            splitter.setStretchFactor(index, 1)
        # Sizes act as weights on subsequent resizes and when a pane is
        # hidden. Start above each pane's minimum so Qt keeps them equal.
        column_width = max(splitter.widget(i).minimumSizeHint().width() for i in range(splitter.count()))
        splitter.setSizes([column_width] * splitter.count())
        # If a manually narrowed workspace is too small for the three panes,
        # let their content scroll while the tab and its header keep fitting.
        self.result_contents = QScrollArea()
        self.result_contents.setFrameShape(QFrame.Shape.NoFrame)
        self.result_contents.setWidgetResizable(True)
        self.result_contents.setWidget(splitter)
        layout.addWidget(self.result_contents, 1)
        self.datasets.currentItemChanged.connect(self._dataset_changed)
        self.spectra.currentItemChanged.connect(self._spectrum_changed)
        self.atoms.itemSelectionChanged.connect(self._table_selected)
        self.viewport.selection_changed.connect(self._viewport_selected)

    def set_document(self, document, *, input_path=None, project_path=None):
        snapshots, datasets = document.records()
        if self.document is not document:
            self._input_path = self._project_path = ""
            self._report = None
            self._standalone = False
            self._log_selection = None
        if input_path is not None:
            self._input_path = input_path
        if project_path is not None:
            self._project_path = project_path
        # The two record sets are append-only. Saving under a new name can
        # also change the displayed file without changing either count.
        view_key = len(snapshots), len(datasets), self._input_path, self._project_path
        if self.document is document and self._document_view_key == view_key:
            return
        self._document_view_key = view_key
        previous = self.selected_snapshot.ref if self.selected_snapshot else None
        previous_dataset = self._dataset_id
        self.document = document
        head = next(snapshot for snapshot in reversed(snapshots) if snapshot.ref.frame_id is None)
        has_atoms = bool(head.molecule.atoms)
        self.result_contents.setVisible(has_atoms)
        self.result_contents.setEnabled(has_atoms)
        if not has_atoms:
            self._clear_empty_design()
            return
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._rebuild_results(snapshots, datasets)
        if self._log_selection is not None:
            self._show_log_selection(*self._log_selection)
            return
        if self._standalone:
            self._show_empty_report()
            return
        if previous_dataset in self._dataset_items and document.dataset(previous_dataset).geometry == previous:
            self.view_dataset(previous_dataset)
        else:
            self._dataset_id = None
            self._show_snapshot(head, retain_selection=True)

    def _clear_empty_design(self):
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setText(tr("当前设计没有原子。"))
        self.title.setToolTip("")
        self._dataset_id = self.selected_snapshot = self._log_snapshot = self._log_selection = None
        self._dataset_items.clear()
        self._series_items = []
        self._merged_series.clear()
        self._series = ()
        with QSignalBlocker(self.datasets), QSignalBlocker(self.spectra), QSignalBlocker(self.atoms):
            self.datasets.setRowCount(0)
            self.spectra.clear()
            self.atoms.setRowCount(0)
        self.viewport.set_molecule(None)
        self._select_ids(())
        self.spectrum_preview.set_spectrum(None)
        self.log_model.set_table((), ())
        self.details.clear()
        self.evidence.clear()

    def refresh_document(self):
        if self.document is not None:
            self.set_document(self.document)

    def set_log_report(self, report, *, standalone=False):
        """Show the output file's own results, optionally without any molecular context."""
        if report is not self._report:
            self._preview_index = 0
        self._report = report
        self._standalone = report is not None and standalone
        self._log_selection = None
        if self.document is not None and not self.document.head.molecule.atoms:
            return
        records = self.document.records() if self.document is not None and not self._standalone else ((), ())
        self._rebuild_results(*records)
        if self._dataset_id in self._dataset_items:
            self.view_dataset(self._dataset_id)
        elif self._series:
            self.datasets.setCurrentItem(self._series_items[0])
        elif report is not None and report.spectra:
            self.spectra.setCurrentItem(self.spectra.topLevelItem(0))
        elif self._standalone:
            self._show_empty_report()
        elif self.document is not None:
            ref = self.selected_snapshot.ref if self.selected_snapshot is not None else self.document.head.ref
            self.view_geometry(ref)

    def _rebuild_results(self, snapshots, datasets):
        report = self._report
        if self._standalone:
            datasets = ()
        self.geometry_pane.setVisible(not self._standalone)
        path = report.source.path_hint if report is not None else ""
        fallback = tr("结果")
        if not self._standalone:
            path = self._project_path or self._input_path or path
            if snapshots:
                fallback = self.document.head.molecule.name
                if not path:
                    path = next((ref.path_hint for ref in snapshots[0].provenance.parents if ref.path_hint), "")
        self.title.setText(display_file_name(path, fallback))
        self.title.setToolTip(str(path or fallback))
        self._series = log_property_series(report) if report is not None else ()
        self._log_snapshot = (log_reference_snapshot(snapshots, report.source)
                              if report is not None and not self._standalone else None)
        spectra = report.spectra if report is not None else ()
        self.spectrum_preview.set_spectrum(spectra[self._preview_index] if spectra else None)
        self._series_items = []
        self._merged_series = {}
        self._dataset_items = {}
        energies = matched_energy_lines(datasets, report.source) if report is not None else {}
        contexts = {}
        for series in self._series:
            prop = series[0]
            contexts.setdefault((prop.label, prop.unit), set()).add(prop.context)
        with QSignalBlocker(self.datasets), QSignalBlocker(self.spectra):
            self.datasets.setRowCount(0)
            self.spectra.clear()
            for index, series in enumerate(self._series):
                prop = series[0]
                tooltip = "\n".join(filter(None, (f"{tr(prop.group)} · {report_text(prop.label)}  {prop.value} {prop.unit}",
                                                  report_text(prop.context), log_filename(report) + " · " + tr("第 {value} 行", value=prop.line))))
                name = report_text(prop.label)
                alternatives = contexts[(prop.label, prop.unit)] - {prop.context}
                if alternatives and prop.context:
                    qualifiers = [part for part in prop.context.split(" · ")
                                  if any(part not in other.split(" · ") for other in alternatives)]
                    name = tr("{label}（{suffix}）", label=name, suffix=report_text(" · ".join(qualifiers) or prop.context))
                item = self.datasets.add_result(name, f"{prop.value} {prop.unit}".rstrip(), tooltip=tooltip)
                self._series_items.append(item)
                energy = energies.get(prop.line)
                if energy is not None:
                    self._merged_series[energy.dataset_id] = index
                    self._dataset_items[energy.dataset_id] = item
                    item.setData(Qt.ItemDataRole.UserRole, energy.dataset_id)
                else:
                    item.setData(Qt.ItemDataRole.UserRole + 1, index)
            for data in sorted(datasets, key=lambda d: (d.kind != "energy", bool(d.shape))):
                if data.dataset_id in self._dataset_items:
                    continue
                if (report is not None and data.kind == "mulliken-charge"
                        and data.values is None and data.missing_reason
                        and data.provenance.kind == "orca-native-import"):
                    continue
                name = dataset_name(data)
                context = dict(data.provenance.parameters).get("population_series", "")
                if context:
                    name = tr("{label}（{suffix}）", label=name, suffix=report_text(context))
                if data.array_ref is not None:
                    value = tr("未加载")
                elif data.values is None or all(v is None for v in data.values):
                    value = tr("全部缺失")
                elif not data.shape:
                    value = f"{data.values[0]} {data.unit}".rstrip()
                elif len(data.axes) == 1 and data.axes[0].kind == "atom":
                    value = tr("{count} 个原子", count=data.shape[0])
                else:
                    value = tr("{count} 项", count=" × ".join(map(str, data.shape)))
                if data.missing_reason and value != tr("全部缺失"):
                    value += tr("（部分缺失）")
                tooltip = "\n".join(filter(None, (f"{name}  {value}", tr("单位  {unit}", unit=data.unit) if data.shape else "",
                                                  data.missing_reason, geometry_name(data.geometry))))
                item = self.datasets.add_result(name, value, tooltip=tooltip)
                item.setData(Qt.ItemDataRole.UserRole, data.dataset_id)
                self._dataset_items[data.dataset_id] = item
            for index, spectrum in enumerate(spectra):
                item = QTreeWidgetItem(self.spectra, [report_text(spectrum.title)])
                item.setData(0, Qt.ItemDataRole.UserRole, index)
                item.setToolTip(0, f"{report_text(spectrum.title)}\n{log_filename(report)} · " + tr("第 {value} 行", value=spectrum.source_line))
            self.datasets.horizontalHeader().setVisible(self.datasets.rowCount() > 0)

    def _show_empty_report(self):
        self._dataset_id = None
        self._select_ids(())
        self.tables.setCurrentWidget(self.log_table)
        self.table_title.setText(tr("计算结果"))
        self.log_model.set_table((), ())
        self.details.setText(log_overview_status(self._report) + "\n" + tr("日志中没有识别到可显示的计算结果。"))
        self.evidence.setPlainText(source_file_details((self._report.source,)))

    def _show_log_selection(self, kind, index):
        snapshot = self._log_snapshot
        if snapshot is not None:
            self.geometry_pane.show()
            if self.selected_snapshot is None or self.selected_snapshot.ref != snapshot.ref:
                self._show_snapshot(snapshot)
        else:
            self._select_ids(())
            self.geometry_pane.hide()
        self._dataset_id = None
        self._log_selection = kind, index
        self.design_button.setEnabled(snapshot is not None)
        if kind == "spectrum":
            data = self._report.spectra[index]
            self._preview_index = index
            self.spectrum_preview.set_spectrum(data)
            title, line = report_text(data.title), data.source_line
            self.log_model.set_table(data.columns, data.rows)
            description = title + " · " + tr("{count} 行", count=len(data.rows))
            selected, other = self.spectra, self.datasets
            item = self.spectra.topLevelItem(index)
        else:
            series = self._series[index]
            prop = series[0]
            title, line = report_text(prop.label), prop.line
            self._load_property_table(series)
            description = f"{tr(prop.group)} · {title}   {prop.value} {prop.unit}\n{report_text(prop.context)}".rstrip()
            selected, other = self.datasets, self.spectra
            item = self._series_items[index]
        with QSignalBlocker(selected), QSignalBlocker(other):
            if selected is self.spectra or self.datasets.name_item(self.datasets.currentItem()) != item:
                selected.setCurrentItem(item)
            other.clearSelection()
            other.setCurrentItem(None)
        self.tables.setCurrentWidget(self.log_table)
        self.table_title.setText(title)
        self.details.setText("\n".join((description, tr("来源文件  ") + log_filename(self._report),
                                        tr("来源行  ") + str(line), log_overview_status(self._report))))
        self.evidence.setPlainText(source_file_details((self._report.source,)))

    def _load_property_table(self, series):
        self.log_model.set_table(("数值", "单位", "计算上下文", "日志行"),
                                 tuple((p.value, p.unit, report_text(p.context), p.line) for p in series))

    def view_geometry(self, ref):
        if self._standalone or not self.result_contents.isEnabled():
            return
        snapshot = self.document.resolve(ref)
        self._dataset_id = None
        self.datasets.blockSignals(True)
        self.datasets.clearSelection()
        self.datasets.setCurrentItem(None)
        self.datasets.blockSignals(False)
        self._show_snapshot(snapshot)

    def view_dataset(self, dataset_id):
        if self._standalone or not self.result_contents.isEnabled():
            return
        data = self.document.dataset(dataset_id)
        snapshot = self.document.resolve(data.geometry)
        data.validate_geometry(snapshot)
        if dataset_id not in self._dataset_items:
            self.refresh_document()
            if dataset_id not in self._dataset_items:
                return
        self._dataset_id = dataset_id
        self.datasets.blockSignals(True)
        item = self._dataset_items[dataset_id]
        if self.datasets.name_item(self.datasets.currentItem()) != item:
            self.datasets.setCurrentItem(item)
        self.datasets.blockSignals(False)
        self._show_snapshot(snapshot, data, retain_selection=True)
        series_index = self._merged_series.get(dataset_id)
        if series_index is not None:
            series = self._series[series_index]
            line = series[0].line
            self.details.setText(self.details.text() + "\n" + tr("来源行  ") + f"{line} · {log_filename(self._report)}")
            self.evidence.setPlainText(source_file_details((self._report.source,)))
            if len(series) > 1:
                self._load_property_table(series)
                self.tables.setCurrentWidget(self.log_table)
                self.table_title.setText(report_text(series[0].label))

    def _show_snapshot(self, snapshot, data=None, *, retain_selection=False):
        self._log_selection = None
        self.geometry_pane.show()
        self.tables.setCurrentWidget(self.atoms)
        with QSignalBlocker(self.spectra):
            self.spectra.setCurrentItem(None)
        same_geometry = self.selected_snapshot == snapshot
        previous_ids = tuple(self._selected_ids) if same_geometry and retain_selection else ()
        self.selected_snapshot = snapshot
        if not same_geometry:
            self.viewport.set_molecule(snapshot.molecule)
        self._populate_atoms(snapshot, data)
        self._select_ids(previous_ids)
        artifacts = data.provenance.parents if data is not None else snapshot.provenance.parents
        details = describe(snapshot, data)
        if self._report is not None and self._report.source in artifacts:
            details += "\n" + report_text(self._report.status)
        self.details.setText(details)
        if data is None and snapshot.provenance.kind == "schema1-import" and self._input_path:
            # Legacy projects record the container alongside the original input.
            artifacts = tuple(ref for ref in artifacts if ref.format != "orcaview.schema1")
        if data is not None and data.array_ref is not None:
            artifacts += (data.array_ref,)
        self.evidence.setPlainText(source_file_details(
            artifacts, input_path=self._input_path if data is None else "", project_path=self._project_path))

    def _populate_atoms(self, snapshot, data):
        atom_axis = data is not None and len(data.shape) == 1 and data.axes[0].kind == "atom"
        ids = set(data.axes[0].ids) if atom_axis else set()
        values = dict(zip(data.axes[0].ids, data.values)) if atom_axis and data.values is not None else {}
        self.table_title.setText(tr("逐原子值 / {unit}    ·    坐标 Å", unit=data.unit) if atom_axis else tr("原子坐标 / Å"))
        self.atoms.setUpdatesEnabled(False)
        self.atoms.blockSignals(True)
        self.atoms.setRowCount(len(snapshot.atom_ids))
        self.atoms.setColumnHidden(2, not atom_axis)
        self.atoms.setHorizontalHeaderItem(2, QTableWidgetItem(tr("结果 / {unit}", unit=data.unit) if atom_axis else tr("结果")))
        longest_coordinate = 0
        for row, (atom_id, atom) in enumerate(zip(snapshot.atom_ids, snapshot.molecule.atoms)):
            value = values.get(atom_id)
            if not atom_axis:
                shown = "—"
            elif atom_id not in ids:
                shown = tr("轴外")
            elif data.array_ref is not None:
                shown = tr("未加载")
            else:
                shown = tr("缺失") if value is None else str(value)
            coordinates = (atom.x, atom.y, atom.z)
            formatted = tuple(f"{v:.6f}" for v in coordinates)
            longest_coordinate = max(longest_coordinate, *map(len, formatted))
            for column, entry in enumerate((str(row + 1), atom.element, shown, *formatted)):
                cell = QTableWidgetItem(entry)
                cell.setData(Qt.ItemDataRole.UserRole, atom_id)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setToolTip(entry)
                if column >= 3:
                    cell.setFont(self.atoms.coordinate_font)
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    cell.setToolTip(str(coordinates[column - 3]))
                self.atoms.setItem(row, column, cell)
        self.atoms.clearSelection()
        self.atoms.fit_columns(longest_coordinate)
        self.atoms.blockSignals(False)
        self.atoms.setUpdatesEnabled(True)

    def _dataset_changed(self, current, previous):
        item = self.datasets.name_item(current)
        if item is None or item == self.datasets.name_item(previous):
            return
        dataset_id = item.data(Qt.ItemDataRole.UserRole)
        if dataset_id is not None:
            self.view_dataset(dataset_id)
        else:
            index = item.data(Qt.ItemDataRole.UserRole + 1)
            if index is not None:
                self._show_log_selection("property", index)

    def _spectrum_changed(self, current, previous):
        if current is not None:
            index = current.data(0, Qt.ItemDataRole.UserRole)
            if index is not None:
                self._show_log_selection("spectrum", index)

    def _table_selected(self):
        selected = [self.atoms.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
                    for index in self.atoms.selectionModel().selectedRows()]
        ordered = [atom_id for atom_id in self._selected_ids if atom_id in selected]
        ordered += [atom_id for atom_id in selected if atom_id not in ordered]
        self._select_ids(ordered[-2:], reveal_measurement=True)

    def _viewport_selected(self, indices):
        if self.selected_snapshot is not None:
            self._select_ids([self.selected_snapshot.id_at(index) for index in indices], reveal_measurement=True)

    @property
    def selection_context(self):
        if self.selected_snapshot is None or self._standalone or (self._log_selection is not None and self._log_snapshot is None):
            return None
        return SelectionContext(self.selected_snapshot.ref, tuple(self._selected_ids))

    def _select_ids(self, atom_ids, *, reveal_measurement=False):
        self._selected_ids = list(atom_ids)
        context = self.selection_context
        self.design_button.setEnabled(context is not None)
        snapshot = self.selected_snapshot
        rows = context.indices(snapshot) if context is not None else ()
        with QSignalBlocker(self.atoms):
            self.atoms.clearSelection()
            selection = self.atoms.selectionModel()
            for row in rows:
                selection.select(self.atoms.model().index(row, 0),
                                 QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
            if rows:
                self.atoms.scrollToItem(self.atoms.item(rows[-1], 0))
        self.viewport.selected = list(rows)
        self.viewport.update()
        if len(rows) == 2:
            definition = CoordinateDefinition(snapshot.ref, "distance", context.atom_ids)
            length = measure(snapshot, definition)
            pair = "–".join(f"{snapshot.molecule.atoms[i].element}{i + 1}" for i in rows)
            self.bond_length.setText(tr("键长  {pair}  {length:.6f} Å", pair=pair, length=length))
            if reveal_measurement:
                self.inspector_tabs.setCurrentIndex(0)
        else:
            self.bond_length.clear()
        self.bond_length.setVisible(len(rows) == 2)

    def _request_design(self):
        context = self.selection_context
        if context is not None:
            self.design_requested.emit(context.geometry)

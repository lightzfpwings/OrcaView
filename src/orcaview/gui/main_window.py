"""Single-document prototype. Calculation settings must pass validation before export."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import math
from pathlib import Path
import sys
from threading import Event

from PySide6.QtCore import QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QCompleter, QDialog, QDockWidget, QFileDialog, QFrame,
    QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QSpinBox, QTabWidget, QToolBar,
    QVBoxLayout, QWidget,
)

from orcaview import __version__
from orcaview.appearance import AppearanceStore
from orcaview.gui import typography
from orcaview.i18n import diagnostic_text, tr
from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.application.structure_import import (
    OpenedStructure, PeriodicFile, PreparedMolden, open_file_filters, prepare_gbw_open, read_structure_file,
)
from orcaview.core.integrals import (
    auxiliary_options, basis_options, grid_options, integral_options, scalar_options,
)
from orcaview.core.methods import (
    ACTIVE_SPACE_METHODS, ALL_JOBS, ELECTRON_CHANNEL_METHODS, EXCITED_STATE_METHODS, METHOD_GROUPS,
    METHODS, REFERENCE_FUNCTIONAL_METHODS, RESPONSE_FUNCTIONALS, canonical_method, dispersion_options, frozen_core_options,
    pno_options, reference_options,
)
from orcaview.core.models import Atom, CalculationSpec, Molecule, SCF_CONVERGENCE
from orcaview.core.resource_defaults import detect_resources
from orcaview.core.solvation import SOLVENTS, solvation_options, uses_numerical_frequencies
from orcaview.gui.appearance_dialog import AppearanceDialog
from orcaview.gui.block_options import BlockOptionsPanel
from orcaview.gui.design_panel import DesignPanel
from orcaview.gui.file_dialogs import document_directory, set_document_directory, suggested_file
from orcaview.gui.foundation_demo import build_foundation_demo
from orcaview.gui.foundation_panel import FoundationPanel
from orcaview.gui.gbw_dialog import GbwOpenDialog
from orcaview.gui.inspector_controls import apply_inspector_control_style
from orcaview.gui.inspector_form import InspectorForm, InspectorLabel, InspectorScrollArea
from orcaview.gui.language_settings import LanguageDialog, load_interface_language
from orcaview.gui.manual import ManualDialog
from orcaview.gui.native_input import edit_native_input
from orcaview.gui.orbital_panel import OrbitalPanel
from orcaview.gui.preview_tabs import InputPreview, PreviewTabBar
from orcaview.gui.project_navigation import ProjectNavigationTree
from orcaview.gui.result_demo import build_result_demo
from orcaview.gui.result_display import display_file_name
from orcaview.gui.result_import import SummaryView, read_native_session, read_summary_view
from orcaview.gui.structure_image_dialog import StructureImageDialog
from orcaview.gui.update_dialog import UpdateDialog
from orcaview.gui.version_info import desktop_version_info
from orcaview.gui.view_controls import ViewControls
from orcaview.gui.viewport import MoleculeViewport
from orcaview.gui.workspace_columns import WorkspaceColumns
from orcaview.gui.workspace_transition import WorkspaceTabs, WorkspaceTransition
from orcaview.io.xyz import parse_xyz
from orcaview.orca.input import render_input
from orcaview.results import OrcaImportError


APP_ICON = Path(__file__).with_name("assets") / "orcaview.png"


STYLE = """
QMainWindow, QDialog, QWidget#calculationInspector, QScrollArea { background: #FAF7F2; }
QMainWindow::separator { background: #DDD5CB; width: 1px; height: 1px; }
QWidget#structureWorkspace { background: #FFFDFA; }
QWidget { color: #372F2D; font-size: 13px; selection-background-color: #904359; selection-color: white; }
QMenuBar, QMenu, QToolBar { background: #FFFDF9; }
QMenuBar { padding: 5px; border-bottom: 1px solid #DDD5CB; }
QMenu::item:selected, QMenuBar::item:selected { background: #F2E4E6; color: #904359; }
QToolBar { padding: 10px; spacing: 9px; border-bottom: 1px solid #DDD5CB; }
QPushButton { background: #FFFDF9; border: 1px solid #DDD5CB; border-radius: 5px; padding: 8px 13px; }
QWidget#rotationControls QPushButton { padding: 8px 6px; }
QPushButton:hover { background: #F2E4E6; border-color: #AB7884; }
QPushButton#primary { background: #904359; color: white; border-color: #904359; }
QPushButton#primary:hover { background: #79364B; }
QLabel#brand { font-size: 22px; font-weight: $heading_weight; color: #904359; padding-right: 20px; }
QLabel#platformBadge { color: #70635F; font-size: 12px; padding: 5px 10px; background: #FAF7F2; border-radius: 4px; }
QLabel#heading { font-size: 18px; font-weight: $section_weight; }
QLabel#muted { color: #70635F; }
/* Size native dock titles with the font that paints the Chinese glyphs. */
QDockWidget { font-weight: $section_weight; $dock_family }
QDockWidget::title { background: #FAF7F2; border-bottom: 1px solid #DDD5CB; padding: 9px; }
/* Qt sizes the title using twice the top inset. Leave the descenders and
   bottom divider room in that same row, including at fractional DPI. */
QDockWidget[sidePane="true"]::title { padding: 8px 9px 5px; }
QTreeWidget { background: #FAF7F2; border: none; padding: 10px 4px; }
QTreeWidget::item { padding: 7px 2px; }
QTreeWidget::item:selected, QTableWidget::item:selected { background: #F2E4E6; color: #904359; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { padding: 6px; background: #FFFDF9; border: 1px solid #DDD5CB; border-radius: 4px; }
QComboBox QLineEdit, QSpinBox QLineEdit, QDoubleSpinBox QLineEdit { padding: 0; border: none; }
QComboBox QAbstractItemView { background: #FFFDF9; color: #372F2D; }
QTabWidget::pane { border: 1px solid #DDD5CB; background: #FFFDF9; }
QTabWidget#workspaceTabs::pane { border: none; border-top: 1px solid #DDD5CB; }
QTabWidget#workspaceTabs::tab-bar { alignment: left; }
QTabBar::tab { background: #FAF7F2; padding: 9px 22px; color: #70635F; }
QTabBar#workspaceTabBar::tab { padding: 7px 16px $workspace_tab_bottom; }
QTabBar#workspaceTabBar::tab:disabled { color: #908d89; }
QTabBar::tab:selected { background: #FFFDF9; color: #904359; border-top: 2px solid #904359; }
QTabWidget#inputOutputTabs::pane { border: none; background: #FFFDF9; }
QTabWidget#inputOutputTabs::tab-bar { alignment: left; }
QTabBar#previewTabBar::tab {
    margin: 0; padding: 7px 10px; border: none;
    border-top: 1px solid #DDD5CB; border-bottom: 1px solid #DDD5CB; border-right: 1px solid #DDD5CB;
}
QTabBar#previewTabBar::tab:last { border-right: none; }
QTabBar#previewTabBar::tab:selected { color: #76394D; background: #F2E4E6; border-bottom-color: #904359; }
QPlainTextEdit, QTextBrowser { border: none; background: #FFFDF9; padding: 9px; color: #372F2D; }
QTableWidget { background: #FFFDF9; alternate-background-color: #FAF7F2; border: 1px solid #DDD5CB; gridline-color: #DDD5CB; }
QTableWidget::item { padding: 5px; }
$header_rule
QHeaderView::section { background: #FAF7F2; border: none; padding: 8px 5px; font-weight: $section_weight; }
QPushButton:disabled, QPushButton#primary:disabled { color: #857976; background: #EFEAE4; border-color: #DDD5CB; }
QStatusBar { background: #FAF7F2; color: #70635F; border-top: 1px solid #DDD5CB; }
QStatusBar QLabel { color: #70635F; }
"""


def demo_benzene():
    """Geometry display only. Bond orders are unknown in XYZ files."""
    lines = ["12", "Benzene · demonstration geometry"]
    for element, radius in (("C", 1.397), ("H", 2.481)):
        for i in range(6):
            angle = math.pi * i / 3
            lines.append("{} {:.8f} {:.8f} 0.0".format(element, radius * math.cos(angle), radius * math.sin(angle)))
    return parse_xyz("\n".join(lines), name="Benzene")


class MainWindow(QMainWindow):
    def __init__(self, *, appearance_store=None):
        super().__init__()
        self.appearance_store = AppearanceStore() if appearance_store is None else appearance_store
        self.resources = detect_resources()
        self.default_calculation = CalculationSpec()
        self.session = Session(molecule=demo_benzene(), calculation=replace(self.default_calculation, job_type="OPT"))
        self.dirty = False
        self._loading = True
        self._workspace_version = 0
        self._reader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orcaview-import")
        self._read_future = None
        self._after_open = None
        self._read_cancel = None
        self._update_dialog = None
        self._pending_result = None
        self._read_timer = QTimer(self)
        self._read_timer.setInterval(50)
        self._read_timer.timeout.connect(self._finish_read)
        self.resize(1440, 980)
        self.setMinimumSize(1120, 780)
        self.setStyleSheet(typography.stylesheet(STYLE))
        versions = desktop_version_info()
        self._create_actions()
        self._create_toolbar(versions.platform_name)
        self.viewport = MoleculeViewport()
        center = QWidget()
        center.setObjectName("structureWorkspace")
        layout = QVBoxLayout(center)
        layout.setContentsMargins(16, 18, 16, 12)
        self.heading = QLabel()
        self.heading.setObjectName("heading")
        self.heading.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle = QLabel(tr("Structure preview / interactive 3D prototype"))
        self.subtitle.setObjectName("muted")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.heading)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.viewport, 1)
        self.workspace_tabs = WorkspaceTabs()
        self.workspace_tabs.setObjectName("workspaceTabs")
        self.workspace_tabs.tabBar().setObjectName("workspaceTabBar")
        self.input_page = center
        self.workspace_tabs.addTab(self.input_page, tr("Input"))
        self.design_panel = DesignPanel()
        self.design_panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.workspace_tabs.addTab(self.design_panel, tr("Design"))
        self.foundation_panel = FoundationPanel()
        self.orbital_panel = OrbitalPanel(self.workspace_tabs)
        self.orbital_panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._viewports = (self.viewport, self.design_panel.viewport, self.foundation_panel.viewport,
                           self.orbital_panel.viewport)
        self._apply_appearance(self.appearance_store.load())
        # Let the splitters inside the results page adapt to each animation frame.
        self.foundation_panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.workspace_tabs.addTab(self.foundation_panel, tr("Result"))
        orbital_index = self.workspace_tabs.addTab(self.orbital_panel, "Orbitals")
        self.workspace_tabs.setTabEnabled(orbital_index, False)
        self.orbital_panel.availability_changed.connect(self._orbital_availability_changed)
        self.setCentralWidget(self.workspace_tabs)
        self._create_tree()
        self._create_inspector()
        self._create_bottom()
        self._structure_bottom_visible = True
        self._work_docks_hidden = False
        self._previous_page = self.input_page
        self.workspace_tabs.currentChanged.connect(self._workspace_changed)
        self.design_panel.geometry_changed.connect(self._design_geometry_changed)
        self.design_panel.new_requested.connect(self._new_design)
        self.foundation_panel.design_requested.connect(self._design_result)
        self.viewport.selection_changed.connect(self._selection_changed)
        for viewport in self._viewports:
            viewport.selection_changed.connect(self._update_structure_image_action)
        self.orbital_panel.viewport.surface_changed.connect(self._update_structure_image_action)
        self.workspace_tabs.currentChanged.connect(self._update_structure_image_action)
        self._create_status_bar(versions)
        self._load_controls()
        self.statusBar().showMessage(self.resource_hint.text(), 8000)
        self._update_structure_image_action()
        self.columns = WorkspaceColumns(self, self.tree_dock, self.inspector_dock)
        self.workspace_transition = WorkspaceTransition(self, self.workspace_tabs, self.design_panel,
                                                       (self.tree_dock, self.inspector_dock, self.bottom_dock))
        self.resizeDocks([self.bottom_dock], [260], Qt.Orientation.Vertical)

    def _action(self, title, slot, shortcut=None):
        action = QAction(title, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def _create_actions(self):
        menu = self.menuBar().addMenu(tr("File"))
        self.open_file_action = self._action(tr("Open file…"), self.open_file, "Ctrl+O")
        menu.addAction(self.open_file_action)
        menu.addAction(self._action(tr("Open project…"), self.open_project))
        menu.addAction(self._action(tr("Save project…"), self.save_project_dialog, "Ctrl+S"))
        self.export_action = self._action(tr("Export ORCA input…"), self.export_input)
        self.native_editor_action = self._action(tr("Edit native ORCA input…"), self.open_native_input_editor)
        self.structure_image_action = self._action(tr("Export structure image…"), self.export_structure_image)
        self.structure_image_action.setObjectName("exportStructureImage")
        menu.addActions([self.export_action, self.structure_image_action, self.native_editor_action])
        menu.aboutToShow.connect(self._update_structure_image_action)
        self.import_action = self._action(tr("Import ORCA results…"), self.import_native_output)
        self.summary_action = self._action(tr("Read ORCA output summary…"), self.open_output)
        menu.addAction(self.import_action)
        menu.addAction(self.summary_action)
        view = self.menuBar().addMenu(tr("View"))
        self.fit_action = self._action(tr("Reset view"), self._fit_active_view)
        view.addAction(self.fit_action)
        labels = QAction(tr("Show all atom labels"), self)
        labels.setCheckable(True)
        labels.toggled.connect(self._toggle_labels)
        view.addAction(labels)
        self.labels_action = labels
        self.appearance_action = self._action(tr("Molecular appearance…"), self.show_appearance_dialog)
        view.addAction(self.appearance_action)
        view.addAction(self._action(tr("Interface language…"), lambda: LanguageDialog(self).exec()))
        calculation = self.menuBar().addMenu(tr("Calculation"))
        self.find_method_action = self._action(tr("Find method…"), self.find_method, "Ctrl+K")
        calculation.addAction(self.find_method_action)
        data_menu = self.menuBar().addMenu(tr("Data"))
        data_menu.addAction(self._action(tr("Result"), lambda: self.workspace_tabs.setCurrentWidget(self.foundation_panel)))
        data_menu.addAction(self._action(tr("Load M6 synthetic charge example"), self.load_analysis_demo))
        data_menu.addAction(self._action(tr("Load M1 atomic charge example"), self.load_foundation_demo))
        help_menu = self.menuBar().addMenu(tr("Help"))
        help_menu.addAction(self._action(tr("ORCA 6.1.1 manual…"), lambda: ManualDialog(self).exec()))
        self.update_action = self._action(tr("Check for Updates…"), self.show_update_dialog)
        self.update_action.setObjectName("checkForUpdateAction")
        self.update_action.setMenuRole(QAction.MenuRole.NoRole)
        help_menu.addAction(self.update_action)
        help_menu.addAction(self._action(tr("About OrcaView"), lambda: QMessageBox.information(
            self, "OrcaView", tr("OrcaView {}\nORCA desktop pre- and postprocessor\n\nSupports XYZ, input templates, calculation logs and spectra.", __version__))))

    def show_appearance_dialog(self):
        dialog = AppearanceDialog(self.appearance, self.appearance_store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            settings = dialog.settings()
            try:
                self.appearance_store.save(settings)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, tr("Molecular appearance"),
                                    tr("Could not save molecular appearance: {error}", error=diagnostic_text(exc)))
            else:
                self._apply_appearance(settings)
        dialog.deleteLater()

    def _apply_appearance(self, settings):
        self.appearance = settings
        colors = self.appearance_store.overrides(settings.palette_id)
        for viewport in self._viewports:
            viewport.set_appearance(settings, colors)
        self.foundation_panel.set_mode_appearance(settings, colors)
        self.design_panel.canvas.set_element_colors(colors)

    def show_update_dialog(self):
        if self._update_dialog is None:
            self._update_dialog = UpdateDialog(self)
        if not self._update_dialog.isVisible():
            self._update_dialog.show()
            self._update_dialog.check()
        self._update_dialog.raise_()
        self._update_dialog.activateWindow()

    def _create_toolbar(self, platform_name):
        self.file_toolbar = toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        mark = QLabel()
        mark.setPixmap(QIcon(str(APP_ICON)).pixmap(QSize(32, 32), self.devicePixelRatioF()))
        toolbar.addWidget(mark)
        brand = QLabel("OrcaView")
        brand.setObjectName("brand")
        toolbar.addWidget(brand)
        for title, slot in [(tr("Open file"), self.open_file), (tr("Open project"), self.open_project),
                            (tr("Save project"), self.save_project_dialog)]:
            button = QPushButton(title)
            button.clicked.connect(slot)
            if slot == self.open_file:
                self.open_file_action.enabledChanged.connect(button.setEnabled)
            toolbar.addWidget(button)
        import_button = QPushButton(tr("Import results"))
        import_button.setObjectName("primary")
        import_button.setToolTip(self.import_action.text())
        import_button.clicked.connect(self.import_action.trigger)
        self.import_action.changed.connect(lambda: import_button.setEnabled(self.import_action.isEnabled()))
        toolbar.addWidget(import_button)
        self.view_toolbar = toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        controls = ViewControls(self._active_viewport)
        self.rotation_angle = controls.rotation_angle
        toolbar.addWidget(controls)
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().Policy.Expanding, spacer.sizePolicy().Policy.Preferred)
        toolbar.addWidget(spacer)
        badge = QLabel(platform_name)
        badge.setObjectName("platformBadge")
        badge.setAccessibleName(tr("Platform"))
        toolbar.addWidget(badge)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "view_toolbar"):
            # Keep both sets of controls visible when translations need more room.
            required = self.file_toolbar.sizeHint().width() + self.view_toolbar.sizeHint().width()
            needs_break = event.size().width() < required
            if needs_break and not self.toolBarBreak(self.view_toolbar):
                self.insertToolBarBreak(self.view_toolbar)
            elif not needs_break and self.toolBarBreak(self.view_toolbar):
                self.removeToolBarBreak(self.view_toolbar)

    def _create_status_bar(self, versions):
        bar = self.statusBar()
        # A permanent strip keeps both corner labels visible while Qt displays
        # temporary messages. Qt still owns their lifetime and clear/timeout.
        strip = QWidget()
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(12)
        system = QLabel(versions.system_version)
        system.setObjectName("systemVersion")
        system.setTextFormat(Qt.TextFormat.PlainText)
        system.setAccessibleName(tr("System version"))
        layout.addWidget(system)
        message = QLabel()
        message.setObjectName("statusMessage")
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        bar.messageChanged.connect(message.setText)
        layout.addWidget(message, 1)
        self.pending_result_button = QPushButton(tr("Open the loaded file"))
        self.pending_result_button.clicked.connect(self._open_pending_result)
        layout.addWidget(self.pending_result_button)
        self.pending_result_button.hide()
        self.cancel_read_button = QPushButton(tr("Cancel reading"))
        self.cancel_read_button.clicked.connect(self._cancel_read)
        layout.addWidget(self.cancel_read_button)
        self.cancel_read_button.hide()
        software = QLabel(versions.software_version)
        software.setObjectName("softwareVersion")
        software.setAccessibleName(tr("OrcaView version and supported ORCA version"))
        layout.addWidget(software)
        bar.addPermanentWidget(strip, 1)

    def _dock(self, title, widget, area):
        dock = QDockWidget(title, self)
        if area in (Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea):
            dock.setProperty("sidePane", True)
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(area, dock)
        return dock

    def _create_tree(self):
        self.tree = ProjectNavigationTree()
        self.tree_dock = self._dock(tr("Project navigation"), self.tree, Qt.DockWidgetArea.LeftDockWidgetArea)

    def _spin(self, minimum, maximum, value):
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.setValue(value)
        control.valueChanged.connect(self._settings_changed)
        return control

    def _create_inspector(self):
        panel = QWidget()
        panel.setObjectName("calculationInspector")
        apply_inspector_control_style(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 18, 16, 14)
        label = InspectorLabel(tr("Calculation settings"))
        label.setObjectName("heading")
        layout.addWidget(label)
        self.method_form = form = InspectorForm(spacing=12)
        self.method_group = QComboBox()
        for family in METHOD_GROUPS:
            self.method_group.addItem(tr(family), family)
        self.method = QComboBox()
        self.job = QComboBox()
        self.basis = QComboBox()
        self.integral_approximation = QComboBox()
        auxiliary_labels = {"aux_j": tr("Coulomb fitting AuxJ"), "aux_jk": tr("Coulomb/exchange AuxJK"),
                            "aux_c": tr("Correlation fitting AuxC"), "cabs": tr("Complementary basis CABS")}
        self.auxiliary_bases = {name: QComboBox() for name in auxiliary_labels}
        self.pno_preset = QComboBox()
        self.dispersion = QComboBox()
        self.integration_grid = QComboBox()
        self.relativity = QComboBox()
        self.wavefunction = QComboBox()
        self.frozen_core = QComboBox()
        self.solvation_model = QComboBox()
        self.solvent = QComboBox()
        self.active_electrons = self._spin(0, 2147483647, 0)
        self.active_orbitals = self._spin(0, 2147483647, 0)
        for field in (self.active_electrons, self.active_orbitals):
            field.setSpecialValueText(tr("Not set"))
        self.nroots = self._spin(1, 2147483647, 5)
        self.reference_functional = QComboBox()
        self.reference_functional.addItems(list(RESPONSE_FUNCTIONALS))
        self.reference_functional.setCurrentText("B3LYP")
        self.electron_channel = QComboBox()
        self.electron_channel.addItem(tr("Select a spin channel"), None)
        self.electron_channel.addItem("α · alpha", "alpha")
        self.electron_channel.addItem("β · beta", "beta")
        self.method_group.currentIndexChanged.connect(self._method_group_changed)
        self.method.currentTextChanged.connect(self._method_changed)
        for control in (self.basis, self.integral_approximation):
            control.currentIndexChanged.connect(self._basis_or_approximation_changed)
        self.job.currentIndexChanged.connect(self._job_changed)
        self.solvation_model.currentIndexChanged.connect(self._solvation_changed)
        self.solvent.currentIndexChanged.connect(self._settings_changed)
        for control in (self.reference_functional, self.electron_channel, self.pno_preset, self.dispersion,
                        self.integration_grid, self.relativity, self.wavefunction, self.frozen_core,
                        *self.auxiliary_bases.values()):
            control.currentIndexChanged.connect(self._settings_changed)
        self.charge = self._spin(-100, 100, 0)
        self.scf_convergence = QComboBox()
        self._fill_options(self.scf_convergence, ("Auto", *SCF_CONVERGENCE), "Auto")
        self.scf_convergence.currentIndexChanged.connect(self._settings_changed)
        self.multiplicity = self._spin(1, 101, 1)
        self.cores = self._spin(1, 256, self.default_calculation.cores)
        self.maxcore = self._spin(1, 1048576, self.default_calculation.maxcore_mb)
        for label, control in [(tr("Method family"), self.method_group), (tr("Computational method"), self.method), (tr("Orbital basis set"), self.basis),
                               (tr("Job type"), self.job)]:
            form.addRow(label, control)
        self.method_hint = QLabel(tr("Numerical frequencies require calculations at multiple displaced geometries. Cost increases with the number of atoms."))
        self.method_hint.setWordWrap(True)
        self.method_hint.setObjectName("muted")
        form.addRow(self.method_hint)
        for label, control in [(tr("Active electrons"), self.active_electrons), (tr("Active orbitals"), self.active_orbitals),
                               (tr("Reference functional"), self.reference_functional), (tr("Target roots"), self.nroots), (tr("Charge"), self.charge),
                               (tr("Spin multiplicity"), self.multiplicity), (tr("Electron spin channel"), self.electron_channel),
                               (tr("Reference wavefunction"), self.wavefunction), (tr("Scalar relativity"), self.relativity),
                               (tr("Integral approximation"), self.integral_approximation), (tr("SCF convergence preset"), self.scf_convergence),
                               (tr("Solvent model"), self.solvation_model),
                               (tr("Solvent"), self.solvent)]:
            form.addRow(label, control)
        for name, label in auxiliary_labels.items():
            form.addRow(label, self.auxiliary_bases[name])
        for label, control in [(tr("Dispersion correction"), self.dispersion), (tr("Numerical integration grid"), self.integration_grid),
                               (tr("Freeze core orbitals"), self.frozen_core), (tr("PNO accuracy"), self.pno_preset),
                               (tr("ORCA processes"), self.cores), (tr("Memory per process / MB"), self.maxcore)]:
            form.addRow(label, control)
        cores, memory = self.resources.recommend()
        self.resource_hint = InspectorLabel(tr("Startup recommendation: {cores} × {memory:,} MB per process",
                                              cores=cores, memory=memory))
        unknown = tr("Unknown")
        memory_mb = self.resources.memory_mb
        self.resource_hint.setToolTip(tr("CPU limit at startup: {cpus}\nAvailable memory at startup (MB): {memory}\n"
                                         "The recommendation targets up to 75% of detected available memory.",
                                         cpus=self.resources.cpu_limit or unknown,
                                         memory=f"{memory_mb:,}" if memory_mb is not None else unknown))
        self.memory_hint = InspectorLabel()
        self.memory_hint.setToolTip(tr("ORCA may use more memory than the configured total."))
        for hint in (self.resource_hint, self.memory_hint):
            hint.setObjectName("muted")
            form.addRow(hint)
        layout.addWidget(form)
        self.block_options = BlockOptionsPanel()
        self.block_options.changed.connect(self._settings_changed)
        layout.addWidget(self.block_options)
        self.validation = InspectorLabel(reserve_text=tr("● Geometry and electron count validated"))
        layout.addWidget(self.validation)
        self.export_button = QPushButton(tr("Export .inp"))
        self.export_button.setObjectName("primary")
        self.export_button.setStyleSheet("padding: 8px 4px;")
        self.export_button.clicked.connect(self.export_input)
        layout.addWidget(self.export_button)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        self.selection = QLabel(tr("Select an atom to view its coordinates"))
        self.selection.setWordWrap(True)
        layout.addWidget(self.selection)
        layout.addStretch()
        scroll = InspectorScrollArea()
        scroll.setMinimumWidth(240)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(panel)
        self.inspector_dock = self._dock(tr("Properties and settings"), scroll, Qt.DockWidgetArea.RightDockWidgetArea)

    def _set_family_methods(self, family, method=None):
        names = METHOD_GROUPS[family]
        with QSignalBlocker(self.method):
            self.method.clear()
            self.method.addItems(list(names))
            if method is not None:
                self.method.setCurrentText(method)
            elif "B3LYP" in names:
                self.method.setCurrentText("B3LYP")

    @staticmethod
    def _fill_options(control, choices, selected, *, optional=False):
        with QSignalBlocker(control):
            control.clear()
            if optional:
                control.addItem(tr("Automatic"), None)
            for value in choices:
                control.addItem(tr("Automatic") if value == "Auto" else value, value)
            index = control.findData(selected)
            if index >= 0:
                control.setCurrentIndex(index)

    def _set_auto_option(self, name, choices, spec):
        control = getattr(self, name)
        selected = control.currentData() if spec is None else getattr(spec, name)
        self._fill_options(control, choices, selected or "Auto")
        self.method_form.setRowVisible(control, len(choices) > 1)

    def _refresh_basis_options(self, spec=None):
        method = self.method.currentText()
        basis = self.basis.currentData()
        approximation = self.integral_approximation.currentData()
        self._set_auto_option("relativity", scalar_options(method, basis), spec)
        self._set_auto_option("integration_grid", grid_options(method, approximation), spec)
        if spec is not None:
            self._refresh_auxiliary_controls(spec)

    def _refresh_auxiliary_controls(self, spec):
        choices = auxiliary_options(spec.method, spec.basis, spec.integral_approximation, spec.block_options)
        for name, control in self.auxiliary_bases.items():
            self._fill_options(control, choices.get(name, ()), getattr(spec, name), optional=True)
            self.method_form.setRowVisible(control, name in choices)

    def _basis_or_approximation_changed(self):
        self._refresh_basis_options()
        self._settings_changed()

    def _fill_solvents(self, selected, *, custom=False):
        choices = SOLVENTS.get(self.solvation_model.currentData(), ())
        self._fill_options(self.solvent, choices, selected.lower() if selected else "water")
        if self.solvation_model.currentData() == "DDCOSMO":
            with QSignalBlocker(self.solvent):
                self.solvent.addItem(tr("Custom dielectric constant (%xtb EPSILON)"), None)
                if custom:
                    self.solvent.setCurrentIndex(self.solvent.count() - 1)
        self.method_form.setRowVisible(self.solvent, bool(choices))

    def _solvation_changed(self):
        self._fill_solvents(self.solvent.currentData())
        self._settings_changed()

    def _set_integral_options(self, spec=None):
        method = self.method.currentText()
        job = self.job.currentData()
        self._set_auto_option("wavefunction", reference_options(method, job), spec)
        models = solvation_options(method, job)
        selected = spec.solvation_model if spec else self.solvation_model.currentData()
        custom = ((spec.solvation_model == "DDCOSMO" and spec.solvent is None) if spec else
                  self.solvation_model.currentData() == "DDCOSMO" and self.solvent.currentData() is None)
        self._fill_options(self.solvation_model, models, selected)
        self.solvation_model.setItemText(0, tr("Gas phase"))
        self.method_form.setRowVisible(self.solvation_model, len(models) > 1)
        self._fill_solvents(spec.solvent if spec else self.solvent.currentData(), custom=custom)
        self._set_auto_option("integral_approximation", integral_options(method, job), spec)
        self._refresh_basis_options(spec)

    def _job_changed(self):
        previous = self.integral_approximation.currentText()
        self._set_integral_options()
        if previous != self.integral_approximation.currentText():
            self.statusBar().showMessage(tr("Integral approximation for {job} changed to {approximation}.", job=self.job.currentText(), approximation=self.integral_approximation.currentText()), 7000)
        self._settings_changed()

    def _set_method_options(self, job_type, basis, spec=None):
        method = self.method.currentText()
        preset = METHODS[method]
        self.method_form.setRowVisible(self.active_electrons, method in ACTIVE_SPACE_METHODS)
        self.method_form.setRowVisible(self.active_orbitals, method in ACTIVE_SPACE_METHODS)
        self.method_form.setRowVisible(self.nroots, method in EXCITED_STATE_METHODS)
        self.method_form.setRowVisible(self.reference_functional, method in REFERENCE_FUNCTIONAL_METHODS)
        if preset.uses_orbital_basis:
            bases = basis_options(method)
            selected_basis = basis if basis in bases else "def2-SVP"
            self._fill_options(self.basis, bases, selected_basis)
        else:
            with QSignalBlocker(self.basis):
                self.basis.clear()
                self.basis.addItem(tr("Built in / fixed by method"), basis)
        self.basis.setEnabled(preset.uses_orbital_basis)
        self._set_auto_option("frozen_core", frozen_core_options(method), spec)
        self._set_auto_option("pno_preset", pno_options(method), spec)
        self._set_auto_option("dispersion", dispersion_options(method), spec)
        job_labels = {"SP": tr("Single-point energy  ·  SP"), "OPT": tr("Geometry optimization  ·  Opt"), "FREQ": tr("Frequencies"), "OPT_FREQ": tr("Optimization + frequencies"),
                      "OPT_TS": tr("Transition state optimization · OptTS"), "IRC": tr("Intrinsic reaction coordinate · IRC")}
        with QSignalBlocker(self.job):
            self.job.clear()
            for key in preset.job_types:
                self.job.addItem(job_labels[key], key)
            if job_type in preset.job_types:
                self.job.setCurrentIndex(self.job.findData(job_type))
            self.job.setEnabled(len(preset.job_types) > 1)
        self._set_integral_options(spec)

    def _method_group_changed(self):
        self._set_family_methods(self.method_group.currentData())
        self._method_changed()

    def find_method(self):
        if not self.session.molecule.atoms:
            return
        dialog = QInputDialog(self)
        dialog.setWindowTitle(tr("Find method"))
        dialog.setLabelText(tr("Method name or alias"))
        dialog.setComboBoxItems(list(METHODS))
        dialog.setComboBoxEditable(True)
        dialog.setOkButtonText(tr("Selection"))
        dialog.setCancelButtonText(tr("Cancel"))
        combo = dialog.findChild(QComboBox)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setCurrentIndex(-1)
        completer = combo.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        dialog.resize(420, dialog.sizeHint().height())
        accepted = dialog.exec()
        query = dialog.textValue().strip()
        dialog.deleteLater()
        if not accepted:
            return
        try:
            method = canonical_method(query)
        except ValueError:
            QMessageBox.warning(self, tr("Method not found"), tr("No match for “{query}” in the method catalog.", query=query))
            return
        self.workspace_tabs.setCurrentWidget(self.input_page)
        self.inspector_dock.show()
        if method != self.method.currentText():
            family = METHODS[method].family
            with QSignalBlocker(self.method_group):
                self.method_group.setCurrentIndex(self.method_group.findData(family))
            self._set_family_methods(family, method)
            self._method_changed()
        self.inspector_dock.widget().ensureWidgetVisible(self.method)

    def _method_changed(self):
        previous_job = self.job.currentData()
        previous_basis = self.basis.currentText()
        self._set_method_options(previous_job, self.basis.currentData())
        changes = []
        if previous_job != self.job.currentData():
            changes.append(tr("Job type changed to {job}", job=self.job.currentText()))
        if previous_basis != self.basis.currentText():
            changes.append(tr("Orbital basis set changed to {basis}", basis=self.basis.currentText()))
        if changes:
            self.statusBar().showMessage(f"{self.method.currentText()} · " + ", ".join(changes), 7000)
        self._settings_changed()

    def _text_panel(self):
        panel = QPlainTextEdit()
        panel.setReadOnly(True)
        panel.setFont(typography.preview_font())
        return panel

    def _create_bottom(self):
        self.tabs = QTabWidget()
        self.tabs.setObjectName("inputOutputTabs")
        self.tabs.setTabBar(PreviewTabBar(self.tabs, self.workspace_tabs, self.tree_dock, self.inspector_dock))
        self.tabs.setDocumentMode(True)
        self.input_preview = InputPreview()
        self.input_preview.setFont(typography.preview_font())
        self.input_preview.setToolTip(tr("Edit the input here. Move the pointer outside or press Tab to apply. Escape discards the pending edit."))
        self.input_preview.editingFinished.connect(self._commit_preview_edit)
        self.input_preview.revertRequested.connect(self._revert_preview_edit)
        self.input_preview.textChanged.connect(self._preview_edited)
        # A short validation message and a full input deck share this viewport.
        self.input_preview.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.output_summary = self._text_panel()
        self.output_summary.setPlainText(tr("To view a single-job log, choose File → Read ORCA output summary.\nImport results to open single-point energies and atomic charges."))
        self.log = self._text_panel()
        self.log.setPlainText(tr("OrcaView started.\nThe example structure is for demonstration. No calculation has been run."))
        for widget, name in [(self.input_preview, tr("ORCA input preview")), (self.output_summary, tr("Results summary")), (self.log, tr("Messages and log"))]:
            self.tabs.addTab(widget, name)
        self.bottom_dock = self._dock(tr("Input and results"), self.tabs, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.bottom_dock.setObjectName("inputOutputDock")
        # The tabs label this panel. Collapse only its native dock title row.
        title_bar = QWidget(self.bottom_dock)
        title_bar.setFixedHeight(0)
        self.bottom_dock.setTitleBarWidget(title_bar)

    def _load_calculation_controls(self, *, keep_expanded=False):
        molecule, spec = self.session.molecule, self.session.calculation
        family = METHODS[spec.method].family
        with QSignalBlocker(self.method_group):
            self.method_group.setCurrentIndex(self.method_group.findData(family))
        self._set_family_methods(family, spec.method)
        self._set_method_options(spec.job_type, spec.basis, spec)
        self.active_electrons.setValue(spec.active_electrons or 0)
        self.active_orbitals.setValue(spec.active_orbitals or 0)
        self.nroots.setValue(spec.nroots or 5)
        self.reference_functional.setCurrentText(spec.reference_functional or "B3LYP")
        self.electron_channel.setCurrentIndex(max(0, self.electron_channel.findData(spec.electron_channel)))
        for control, value in [(self.charge, molecule.charge), (self.multiplicity, molecule.multiplicity),
                               (self.cores, spec.cores), (self.maxcore, spec.maxcore_mb)]:
            # Expand the controls to retain values from previously saved projects.
            control.setRange(min(control.minimum(), value), max(control.maximum(), value))
            control.setValue(value)
        self.scf_convergence.setCurrentIndex(self.scf_convergence.findData(spec.scf_convergence))
        self.block_options.load(spec, keep_expanded=keep_expanded)

    def _load_controls(self, *, project_path=None, opened_path=None):
        self._workspace_version += 1
        self._loading = True
        self.input_preview.pending = False
        self.method_form.setEnabled(True)
        self.block_options.setEnabled(True)
        self._load_calculation_controls()
        molecule = self.session.molecule
        self._refresh_input_geometry(molecule)
        self._set_structure_heading(project_path or self.session.source_path)
        if molecule.atoms:
            self.tree.set_structure(molecule.name)
        self.dirty = False
        self._loading = False
        self._update_preview()
        self.design_panel.set_document(self.session.document)
        self.foundation_panel.set_document(self.session.document, input_path=self.session.source_path,
                                           project_path=project_path)
        report_only = (self.session.log_report is not None and not molecule.atoms
                       and self.session.document.head.parent is None)
        self.foundation_panel.set_log_report(self.session.log_report, standalone=report_only,
                                             opened_path=opened_path or project_path)
        self._update_title()
        self._set_orbital_source(project_path)
        source = project_path or opened_path or self.session.source_path
        if source:
            set_document_directory(self, source)

    def _set_orbital_source(self, project_path):
        origin = self.session.document.records()[0][0].provenance
        parameters = dict(origin.parameters)
        formats = {"molecular_orbitals": "molden", "cube_fields": "gaussian-cube"}
        supported = {fmt for key, fmt in formats.items() if key in parameters}
        source = next((a for a in origin.parents if a.format in supported and a.sha256 and a.path_hint), None)
        self.orbital_panel.set_source(source, self.session.molden_orbitals or self.session.cube_grid, project_path)

    def _orbital_availability_changed(self, available, detail):
        tabs, panel = self.workspace_tabs, self.orbital_panel
        index = tabs.indexOf(panel)
        if not available and tabs.currentWidget() is panel:
            tabs.setCurrentWidget(self.input_page if self.session.molecule.atoms else self.design_panel)
        tabs.setTabEnabled(index, available)
        tabs.setTabToolTip(index, panel.title.text() if available else
                           (detail or tr("Open a Molden wavefunction or a Cube file.")))
        if available and tabs.currentWidget() is panel:
            panel.activate()
        if detail and panel.future is None:
            self.log.appendPlainText(detail)
            self.statusBar().showMessage(detail, 8000)

    def _refresh_input_geometry(self, molecule, *, keep_view=False):
        has_atoms = bool(molecule.atoms)
        previous = self.viewport.molecule
        if previous is not None and has_atoms != bool(previous.atoms):
            page = self.workspace_tabs.currentWidget()
            if not has_atoms and page is self.input_page and not self._work_docks_hidden:
                self._structure_bottom_visible = not self.bottom_dock.isHidden()
            self._set_workspace_docks(page)
        self.heading.setVisible(has_atoms)
        self.viewport.setVisible(has_atoms)
        self.inspector_dock.widget().setEnabled(has_atoms)
        self.tabs.setEnabled(has_atoms)
        self.tree.setEnabled(has_atoms)
        has_view = has_atoms or self.workspace_tabs.currentWidget() is self.orbital_panel
        self.view_toolbar.setEnabled(has_view)
        self.fit_action.setEnabled(has_view)
        for action in (self.export_action, self.native_editor_action, self.labels_action, self.find_method_action):
            action.setEnabled(has_atoms)
        self.viewport.set_molecule(molecule, keep_view=keep_view)
        if not has_atoms:
            self.tree.clear()
            self.selection.clear()
            self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.subtitle.setText(tr("The current design has no atoms."))
            return
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        counts = Counter(a.element for a in molecule.atoms)
        formula = " ".join("{}{}".format(element, counts[element] if counts[element] > 1 else "") for element in sorted(counts))
        self.subtitle.setText(tr("{}  /  {} atoms  /  Coordinates in Å", formula, len(molecule.atoms)))

    def _new_design(self):
        if not self._guard_discard():
            return
        seed = Molecule(tr("New molecule"), (Atom("C", 0., 0., 0.),), bonds_explicit=True)
        self.session = Session(molecule=seed, calculation=replace(self.default_calculation, job_type="OPT"))
        self._load_controls()
        self.workspace_tabs.setCurrentWidget(self.design_panel)
        self.dirty = True
        self._update_title()

    def _design_geometry_changed(self):
        previous = self.viewport.molecule
        molecule = self.session.molecule
        if (previous.charge, previous.multiplicity) != (molecule.charge, molecule.multiplicity):
            for control, value in ((self.charge, molecule.charge), (self.multiplicity, molecule.multiplicity)):
                with QSignalBlocker(control):
                    control.setRange(min(control.minimum(), value), max(control.maximum(), value))
                    control.setValue(value)
        if molecule.atoms and (not previous.atoms or previous.name != molecule.name):
            self.tree.set_structure(molecule.name)
            self._set_structure_heading(self._structure_path)
        if previous != molecule:
            self._refresh_input_geometry(molecule, keep_view=True)
        # An edit can make previously rejected form values valid. Preview them
        # without publishing a second revision that would invalidate this undo.
        self._settings_changed(commit_settings=False)
        if self.foundation_panel.showing_independent_log:
            self.foundation_panel.set_log_report(self.session.log_report)

    def _design_result(self, ref):
        panel = self.foundation_panel
        context = panel.selection_context
        if (self.workspace_tabs.currentWidget() is not panel or panel.document is not self.session.document
                or context is None or context.geometry != ref):
            return
        try:
            self.design_panel.set_document(self.session.document)
            self.design_panel.use_result_geometry(ref)
        except ValueError as exc:
            self._error(exc)
            return
        self.workspace_tabs.setCurrentWidget(self.design_panel)

    def _set_structure_heading(self, path):
        self._structure_path = path
        name = display_file_name(path, self.session.molecule.name)
        self.heading.setText(name)
        self.heading.setToolTip(str(path or name))

    def _settings_changed(self, *args, commit_settings=True):
        if self._loading:
            return
        self._workspace_version += 1
        self.dirty = True
        self._update_title()
        self._update_preview(commit_settings=commit_settings)
        self.foundation_panel.set_document(self.session.document)

    def _workspace_changed(self, index):
        page = self.workspace_tabs.widget(index)
        previous = self._previous_page
        self._previous_page = page
        if previous is self.input_page and not self._work_docks_hidden:
            self._structure_bottom_visible = not self.bottom_dock.isHidden()
        self._set_workspace_docks(page)
        has_view = bool(self.session.molecule.atoms) or page is self.orbital_panel
        self.view_toolbar.setEnabled(has_view)
        self.fit_action.setEnabled(has_view)
        if page is self.orbital_panel:
            page.activate()
            return
        if page is self.design_panel:
            self.design_panel.set_document(self.session.document)
            return
        showing_results = page is self.foundation_panel
        self.columns.set_results(showing_results)
        if not self.session.molecule.atoms:
            self.statusBar().clearMessage()
            if showing_results and self.foundation_panel.showing_independent_log:
                return
            if not self.isVisible():
                # Command-line startup and offscreen captures can choose an empty page explicitly.
                return
            choices = QMessageBox.StandardButton
            dialog = QMessageBox(QMessageBox.Icon.Question, tr("Empty molecule"),
                                 tr("The current design has no atoms. Return to Design to draw a molecule?"),
                                 choices.Yes | choices.No, self)
            dialog.button(choices.Yes).setText(tr("Yes"))
            dialog.button(choices.No).setText(tr("No"))
            dialog.setDefaultButton(choices.Yes)
            if dialog.exec() == choices.Yes:
                self.workspace_tabs.setCurrentWidget(self.design_panel)
            return
        if showing_results:
            self.foundation_panel.set_document(self.session.document)

    def _set_workspace_docks(self, page):
        hidden = page in (self.design_panel, self.orbital_panel) or not self.session.molecule.atoms
        self.bottom_dock.setVisible(not hidden and page is self.input_page and self._structure_bottom_visible)
        if hidden == self._work_docks_hidden:
            return
        self._work_docks_hidden = hidden
        sides = (self.tree_dock, self.inspector_dock)
        if hidden:
            self._design_side_visibility = tuple(not dock.isHidden() for dock in sides)
            for dock in sides:
                dock.hide()
        else:
            for dock, visible in zip(sides, self._design_side_visibility):
                dock.setVisible(visible)
            self.columns.apply()

    def _active_viewport(self):
        page = self.workspace_tabs.currentWidget()
        if page is self.design_panel:
            return self.design_panel.viewport
        if page is self.foundation_panel:
            return self.foundation_panel.viewport
        if page is self.orbital_panel:
            return self.orbital_panel.viewport
        return self.viewport

    def _fit_active_view(self):
        self._active_viewport().fit()

    def _structure_image_views(self):
        page = self.workspace_tabs.currentWidget()
        if page is self.foundation_panel and self.foundation_panel.geometry_pane.isHidden():
            return []
        if page is self.orbital_panel:
            surface = self.orbital_panel.viewport.surface
            if surface is None or not surface.faces:
                return []
        views = [(tr("3D view"), self._active_viewport())]
        if page is self.design_panel:
            views.insert(0, (tr("2D sketch"), self.design_panel.canvas))
        return [(name, view) for name, view in views if view.has_exportable_structure() and not view.size().isEmpty()]

    def _update_structure_image_action(self):
        self.structure_image_action.setEnabled(bool(self._structure_image_views()))

    def export_structure_image(self):
        views = self._structure_image_views()
        if views:
            molecule = self._active_viewport().molecule or self.session.molecule
            dialog = StructureImageDialog(views, molecule.name, self)
            if dialog.exec():
                self.statusBar().showMessage(tr("Structure image saved to {path}", path=dialog.output_path), 8000)
            dialog.deleteLater()

    def open_result_session(self, session, dataset_id=None, *, mark_dirty=True, project_path=None, opened_path=None,
                            message=None, timeout_ms=8000):
        """Display a validated session after its caller has handled unsaved edits."""
        document = session.document
        datasets = document.records()[1]
        if dataset_id is not None:
            selected = document.dataset(dataset_id)
        elif session.log_report is not None:
            selected = next((d for d in datasets if "orca-final-single-point-energy" in d.quality), None)
        else:
            selected = next(iter(datasets), None)
        if selected is not None:
            selected.validate_geometry(document.resolve(selected.geometry))
        self.session = session
        self._load_controls(project_path=project_path, opened_path=opened_path)
        if session.molecule.atoms or self.foundation_panel.showing_independent_log:
            self.workspace_tabs.setCurrentWidget(self.foundation_panel)
            if selected is not None:
                self.foundation_panel.view_dataset(selected.dataset_id)
            if self.foundation_panel.showing_independent_log and message is None:
                self.statusBar().clearMessage()
            else:
                self.statusBar().showMessage(message if message is not None else tr("Atoms are ordered by number. Select a row to locate its atom in the structure."), timeout_ms)
        else:
            self.workspace_tabs.setCurrentWidget(self.design_panel)
            self.statusBar().clearMessage()
        self.dirty = mark_dirty
        self._update_title()

    def load_analysis_demo(self):
        if self._guard_discard():
            session, dataset_id = build_result_demo()
            session.calculation = self.default_calculation
            self.open_result_session(session, dataset_id, message=tr("Loaded M6 synthetic charge example"))

    def load_foundation_demo(self):
        if not self._guard_discard():
            return
        session = build_foundation_demo()
        session.calculation = self.default_calculation
        charge = next(data for data in session.document.records()[1] if data.kind == "atomic_charge")
        self.open_result_session(session, charge.dataset_id, message=tr("M1 synthetic atomic charge example loaded"))
        self.log.appendPlainText(tr("Loaded M1 synthetic atomic charges with one missing value."))

    def _update_title(self):
        changed = self.dirty or self.input_preview.pending
        self.setWindowTitle("{}{} · OrcaView {}".format("* " if changed else "", self.session.molecule.name, __version__))

    def _preview_edited(self):
        if self.input_preview.pending:
            self._workspace_version += 1
            self._update_title()

    def _commit_preview_edit(self):
        editor = self.input_preview
        if not editor.pending:
            return True
        before = self.session.document.head
        selection = [before.atom_ids[i] for i in self.viewport.selected if i < len(before.atom_ids)]
        previous_spec = self.session.calculation
        try:
            self.session.apply_input_preview(editor.toPlainText(), expected=editor.base_ref)
        except ValueError as exc:
            message = tr("Input edits have not been applied. {reason} · Escape discards this edit.",
                         reason=diagnostic_text(exc))
            self.validation.setText(message)
            self.validation.setToolTip(message)
            self.validation.setStyleSheet("color: #944A25; padding: 8px 0;")
            self.statusBar().showMessage(message)
            self.export_button.setEnabled(False)
            self.method_form.setEnabled(False)
            self.block_options.setEnabled(False)
            return False
        editor.pending = False
        self.method_form.setEnabled(True)
        self.block_options.setEnabled(True)
        self.statusBar().clearMessage()
        head = self.session.document.head
        changed = previous_spec != self.session.calculation or before is not head
        if changed or not self.export_button.isEnabled():
            self._loading = True
            try:
                self._load_calculation_controls(keep_expanded=True)
                if before is not head:
                    self._refresh_input_geometry(head.molecule, keep_view=True)
                    if selection:
                        rows = {atom_id: i for i, atom_id in enumerate(head.atom_ids)}
                        self.viewport.selected = [rows[key] for key in selection if key in rows]
                        self.viewport.selection_changed.emit(self.viewport.selected)
                    self.design_panel.set_document(self.session.document)
                    self.foundation_panel.set_document(self.session.document)
            finally:
                self._loading = False
            self.dirty |= changed
        self._update_preview(commit_settings=False)
        self._update_title()
        return True

    def _revert_preview_edit(self):
        self.input_preview.pending = False
        self.method_form.setEnabled(True)
        self.block_options.setEnabled(True)
        self.statusBar().clearMessage()
        self._update_preview()
        self._update_title()

    def _update_frequency_labels(self, spec):
        numerical = uses_numerical_frequencies(spec)
        for job, label in (("FREQ", tr("Numerical frequencies  ·  NumFreq") if numerical else tr("Analytical frequencies  ·  Freq")),
                           ("OPT_FREQ", tr("Optimization + numerical frequencies") if numerical else tr("Optimization + frequencies"))):
            index = self.job.findData(job)
            if index >= 0:
                self.job.setItemText(index, label)
        self.method_form.setRowVisible(self.method_hint, numerical and spec.job_type in ("FREQ", "OPT_FREQ"))

    def _update_preview(self, *, commit_settings=True) -> str:
        """Return the validated input shown in the preview, or an empty string on failure."""
        if self.input_preview.pending:
            return self.input_preview.toPlainText() if self._commit_preview_edit() else ""
        cores, memory = self.cores.value(), self.maxcore.value()
        self.memory_hint.setText(tr("Configured total: {total:,} MB", total=cores * memory))
        if not self.session.molecule.atoms:
            self.input_preview.display("", self.session.document.head.ref, editable=False)
            self.validation.clear()
            self.validation.setToolTip("")
            self.export_button.setEnabled(False)
            return ""
        method = self.method.currentText()
        job_type = self.job.currentData()
        has_channel = method in ELECTRON_CHANNEL_METHODS and self.multiplicity.value() > 1
        self.method_form.setRowVisible(self.electron_channel, has_channel)
        if not has_channel:
            with QSignalBlocker(self.electron_channel):
                self.electron_channel.setCurrentIndex(0)
        try:
            active = method in ACTIVE_SPACE_METHODS
            excited = method in EXCITED_STATE_METHODS
            spec = CalculationSpec(
                method=method, basis=self.basis.currentData(), job_type=job_type,
                cores=self.cores.value(), maxcore_mb=self.maxcore.value(),
                scf_convergence=self.scf_convergence.currentData(), input_comments=self.session.calculation.input_comments,
                integral_approximation=self.integral_approximation.currentData() or "Auto",
                pno_preset=self.pno_preset.currentData() or "Auto",
                dispersion=self.dispersion.currentData() or "Auto",
                integration_grid=self.integration_grid.currentData() or "Auto",
                relativity=self.relativity.currentData() or "Auto",
                wavefunction=self.wavefunction.currentData() or "Auto",
                frozen_core=self.frozen_core.currentData() or "Auto",
                electron_channel=self.electron_channel.currentData(),
                solvation_model=self.solvation_model.currentData() or "Gas", solvent=self.solvent.currentData(),
                active_electrons=(self.active_electrons.value() or None) if active else None,
                active_orbitals=(self.active_orbitals.value() or None) if active else None,
                nroots=self.nroots.value() if excited else None,
                reference_functional=self.reference_functional.currentText() if method in REFERENCE_FUNCTIONAL_METHODS else None,
                block_options=tuple(item for item in self.session.calculation.block_options
                                    if self.session.calculation.method == method and item.block == "freq"
                                    and (item.block, item.key) in self.block_options.drafts),
                **{name: control.currentData() for name, control in self.auxiliary_bases.items()},
            )
            self._update_frequency_labels(spec)
            removed = self.block_options.set_context(spec)
            if removed:
                names = ", ".join(f"%{block} {key}" for block, key in removed)
                message = tr("Removed settings incompatible with this calculation: {names}", names=names)
                self.log.appendPlainText(message)
                self.statusBar().showMessage(message, 10000)
            spec = replace(spec, block_options=self.block_options.overrides())
            has_scf_preset = ("scf", "Convergence") in self.block_options.options
            self.method_form.setRowVisible(self.scf_convergence, has_scf_preset)
            if not has_scf_preset and spec.scf_convergence != "Auto":
                with QSignalBlocker(self.scf_convergence):
                    self.scf_convergence.setCurrentIndex(0)
                spec = replace(spec, scf_convergence="Auto")
            self._refresh_auxiliary_controls(spec)
            spec = replace(spec, **{name: control.currentData() for name, control in self.auxiliary_bases.items()})
            charge, multiplicity = self.charge.value(), self.multiplicity.value()
            if commit_settings:
                document = self.session.tracked_document
                previous_head = document.head if document is not None else None
                text = self.session.apply_settings(spec, charge, multiplicity)
                if document is not None and document.head is not previous_head:
                    self.design_panel.set_document(document)
                    self.foundation_panel.set_document(document)
            else:
                molecule = replace(self.session.molecule, charge=charge, multiplicity=multiplicity)
                text = render_input(molecule, spec)
            if spec.peak_maxcore_per_process != spec.maxcore_mb:
                peak = spec.peak_maxcore_per_process
                self.memory_hint.setText(tr("Highest configured module budget: {peak:,} MB per process, {total:,} MB total",
                                            peak=peak, total=peak * cores))
            self.input_preview.display(text, self.session.document.head.ref)
            self.validation.setText(self.validation.reserve_text)
            self.validation.setToolTip(self.validation.text())
            self.validation.setStyleSheet("color: #466446; padding: 8px 0;")
            self.export_button.setEnabled(True)
            return text
        except ValueError as exc:
            message = diagnostic_text(exc)
            self.input_preview.display(tr("Input cannot be exported yet:\n{}", message), self.session.document.head.ref)
            self.validation.setText("● " + " ".join(message.splitlines()))
            self.validation.setToolTip(message)
            self.validation.setStyleSheet("color: #944A25; padding: 8px 0;")
            self.export_button.setEnabled(False)
            return ""

    def _selection_changed(self, selected):
        atoms = self.session.molecule.atoms
        if not selected:
            self.selection.setText(tr("Select an atom to view its coordinates"))
            return
        lines = []
        for index in selected:
            a = atoms[index]
            lines.append("{}{}  ({:.4f}, {:.4f}, {:.4f}) Å".format(a.element, index + 1, a.x, a.y, a.z))
        self.selection.setText("\n".join(lines))

    def _toggle_labels(self, enabled):
        for viewport in self._viewports:
            viewport.labels = enabled
            viewport.update()

    def _error(self, exc):
        message = diagnostic_text(exc)
        self.log.appendPlainText(message)
        QMessageBox.warning(self, tr("Operation incomplete"), message)

    def _guard_discard(self):
        if not self.dirty and not self.input_preview.pending:
            return True
        choice = QMessageBox.question(self, tr("Unsaved settings"), tr("Save the current project first?"), QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Save:
            return self.save_project_dialog()
        return choice == QMessageBox.StandardButton.Discard

    def open_file(self):
        if not self.open_file_action.isEnabled():
            return
        filename, _ = QFileDialog.getOpenFileName(self, tr("Open file"), str(document_directory(self)), open_file_filters(tr))
        if not filename:
            return
        path = Path(filename)
        try:
            if path.name.lower().endswith(".oview.json"):
                self._open_project_path(filename)
            elif path.suffix.lower() in (".out", ".log"):
                self._start_read(path, read_native_session)
            elif path.suffix.lower() == ".gbw":
                self.open_gbw(path)
            elif path.suffix.lower() in (".cube", ".cub"):
                self._read_cancel = Event()
                self._start_read(path, read_structure_file, None, self._read_cancel)
            elif path.suffix.lower() == ".xyz" and path.stat().st_size <= 64 * 1024:
                # The native single-frame reader needs no external conversion.
                result = read_structure_file(path)
                if isinstance(result, PeriodicFile) or self._guard_discard():
                    self._display_read_result(path, result)
            else:
                self._start_read(path, read_structure_file)
        except (ValueError, OSError) as exc:
            self._error(exc)

    open_xyz = open_file

    def open_gbw(self, path, after_open=None):
        dialog = GbwOpenDialog(path, self)
        if dialog.exec():
            if dialog.choice == "existing":
                self._start_read(dialog.destination, read_structure_file, after_open=after_open)
            elif dialog.choice == "convert":
                self._read_cancel = Event()
                self._start_read(path, prepare_gbw_open, dialog.converter, dialog.expected, self._read_cancel,
                                 after_open=after_open)
                self.statusBar().showMessage(tr("Converting {path.name} to Molden…", path=path))
        dialog.deleteLater()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Open project"), str(document_directory(self)),
                                              "OrcaView (*.oview.json);;JSON (*.json)")
        self._open_project_path(path)

    def _open_project_path(self, path):
        if not path or not self._guard_discard():
            return
        try:
            session = load_project(Path(path))
            if session.log_report is not None or (session.tracked_document is not None and session.document.records()[1]):
                self.open_result_session(session, mark_dirty=False, project_path=path)
            else:
                self.session = session
                self._load_controls(project_path=path)
                self.workspace_tabs.setCurrentWidget(self.input_page if session.molecule.atoms else self.design_panel)
            self.log.appendPlainText(tr("Project loaded: {}", path))
        except (ValueError, OSError) as exc:
            self._error(exc)

    def save_project_dialog(self):
        if self.session.molecule.atoms and not self._update_preview():
            self._error(ValueError(tr("Correct the calculation settings before saving the project.")))
            return False
        suggested = suggested_file(self, self.session.molecule.name, ".oview.json")
        path, _ = QFileDialog.getSaveFileName(self, tr("Save project"), suggested, "OrcaView (*.oview.json)")
        if not path:
            return False
        try:
            save_project(self.session, Path(path))
            self._set_structure_heading(path)
            self.foundation_panel.set_document(self.session.document, project_path=path)
            self.dirty = False
            self._update_title()
            self.log.appendPlainText(tr("Project saved: {}", path))
            return True
        except (ValueError, OSError) as exc:
            self._error(exc)
            return False

    def export_input(self):
        if not self.session.molecule.atoms:
            return
        text = self._update_preview()
        if not text:
            self._error(ValueError(tr("Correct the calculation settings before exporting input.")))
            return
        suggested = suggested_file(self, self.session.molecule.name, ".inp")
        path, _ = QFileDialog.getSaveFileName(self, tr("Export ORCA input"), suggested, tr("ORCA input") + " (*.inp)")
        if path:
            try:
                Path(path).write_text(text, encoding="utf-8")
                self.log.appendPlainText(tr("ORCA input exported: {}", path))
                self.statusBar().showMessage(tr("Input exported: {}", path), 8000)
            except (ValueError, OSError) as exc:
                self._error(exc)

    def open_native_input_editor(self):
        if not self.session.molecule.atoms:
            return
        text = self._update_preview()
        edit_native_input(self, text or (self.input_preview.toPlainText() if self.input_preview.pending else ""))

    def import_native_output(self):
        if not self.import_action.isEnabled():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("Import ORCA results"), str(document_directory(self)),
                                              tr("ORCA output") + " (*.out *.log);;" + tr("All files") + " (*)")
        if path:
            self._start_read(Path(path), read_native_session)

    def _show_native_result(self, path, session):
        session.calculation = self.default_calculation
        self.open_result_session(session, opened_path=path, message=tr("Imported structure and results from {path.name}. The project can now be saved.", path=path))
        self.log.appendPlainText(tr("Imported results from {path} into a separate project.", path=path))

    def open_output(self):
        if not self.summary_action.isEnabled():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("Read single-job output"), str(document_directory(self)),
                                              tr("ORCA output") + " (*.out *.log);;" + tr("All files") + " (*)")
        if not path:
            return
        job, accepted = QInputDialog.getItem(self, tr("Output job type"), tr("Select the original job type to assess convergence"), list(ALL_JOBS), 0, False)
        if not accepted:
            return
        self._start_read(Path(path), read_summary_view, job)

    def _show_summary(self, path, result):
        if not self.session.molecule.atoms:
            if result.report.properties or result.report.spectra:
                self._show_log_only(path, result.report)
            else:
                self.workspace_tabs.setCurrentWidget(self.input_page)
            return
        self.output_summary.setPlainText(result.text)
        self.tabs.setCurrentWidget(self.output_summary)
        if result.report.properties or result.report.spectra:
            self._show_log_only(path, result.report)
        else:
            self.workspace_tabs.setCurrentWidget(self.input_page)
        self.log.appendPlainText(tr("Output summary loaded: {path}", path=path))
        self.statusBar().showMessage(tr("Read summary from {path.name}", path=path), 8000)

    def _show_log_only(self, path, report):
        self.foundation_panel.set_log_report(report, standalone=True, opened_path=path)
        self.workspace_tabs.setCurrentWidget(self.foundation_panel)
        if not self.session.molecule.atoms:
            return
        self.statusBar().showMessage(tr("Viewing separate log {path.name}. The current project is retained.", path=path), 8000)

    def _read_context(self):
        return self._workspace_version, self.session.document.records()

    def _start_read(self, path, reader, *args, after_open=None):
        self._read_origin = self._read_context()
        self._after_open = after_open
        self._read_path = path
        self.open_file_action.setEnabled(False)
        self.import_action.setEnabled(False)
        self.summary_action.setEnabled(False)
        self.cancel_read_button.setText(tr("Cancel opening"))
        self.cancel_read_button.show()
        self.statusBar().showMessage(tr("Reading {path.name}…", path=path))
        self._read_future = self._reader.submit(reader, path, *args)
        self._read_timer.start()

    def _finish_read(self):
        future = self._read_future
        if future is None or not future.done():
            return
        self._read_timer.stop()
        self._read_future = None
        path = self._read_path
        try:
            result = future.result()
            if self._read_origin != self._read_context() or QApplication.activeModalWidget() is not None:
                self._pending_result = (path, result)
                self.pending_result_button.setToolTip(str(path))
                self.pending_result_button.show()
                self.cancel_read_button.setText(tr("Discard open request"))
                self.statusBar().showMessage(tr("{path.name} is ready to open once the current operation is complete.", path=path))
            else:
                if isinstance(result, (Session, OpenedStructure, PreparedMolden)) and not self._guard_discard():
                    if isinstance(result, PreparedMolden):
                        result.folder.cleanup()
                    self._reset_reader()
                else:
                    self._display_read_result(path, result)
        except Exception as exc:
            self._reset_reader()
            if isinstance(exc, OrcaImportError):
                details = "\n".join(
                    f"{issue.code} · " + (tr("Line {issue.line} · ", issue=issue) if issue.line else "") + diagnostic_text(issue.message)
                    for issue in exc.issues
                )
            else:
                details = diagnostic_text(exc)
            self.statusBar().showMessage(tr("Could not read {path.name}", path=path), 8000)
            self._error(ValueError(f"{path.name}\n{details}"))

    def _open_pending_result(self):
        if self._pending_result is None:
            return
        path, result = self._pending_result
        if isinstance(result, (Session, OpenedStructure, PreparedMolden)) and not self._guard_discard():
            return
        self._display_read_result(path, result)

    def _display_read_result(self, path, result):
        after_open = self._after_open
        self._reset_reader()
        if isinstance(result, PreparedMolden):
            path = result.destination
            try:
                result = result.publish()
            except (ValueError, OSError) as exc:
                self._error(exc)
                return
        if isinstance(result, PeriodicFile):
            dialog = QMessageBox(QMessageBox.Icon.Question, tr("Periodic structure"),
                                 tr("{path.name} contains a periodic structure. Remove periodicity and display a finite structure?", path=path),
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
            dialog.button(QMessageBox.StandardButton.Yes).setText(tr("Yes"))
            dialog.button(QMessageBox.StandardButton.No).setText(tr("No"))
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
            if dialog.exec() == QMessageBox.StandardButton.Yes:
                reader = read_native_session if path.suffix.lower() in (".out", ".log") else read_structure_file
                self._start_read(path, reader, result, after_open=after_open)
            else:
                self.statusBar().showMessage(tr("Periodic structures are unsupported."), 8000)
                QMessageBox.information(self, tr("Periodic structure"), tr("Periodic structures are unsupported."))
        elif isinstance(result, OpenedStructure):
            self.session = result.session(self.session.calculation)
            self._load_controls(opened_path=path)
            has_field = result.orbitals or result.cube_grid
            self.workspace_tabs.setCurrentWidget(self.orbital_panel if has_field else self.input_page)
            if result.orbitals:
                message = tr("Loaded {count} molecular orbitals from {name}.",
                             count=len(result.orbitals.orbitals), name=path.name)
            elif result.cube_grid:
                message = tr("Loaded {count} Cube fields from {name}.", count=len(result.cube_grid.fields), name=path.name)
            elif result.orbital_error:
                message = tr("Geometry loaded. Molecular orbitals could not be read: {reason}",
                             reason=diagnostic_text(result.orbital_error))
            elif result.record.generated_3d:
                message = tr("Generated a 3D conformer for {path.name} with Open Babel.", path=path)
            elif result.record.removed_periodicity:
                message = tr("Removed periodicity from {path.name}. Displaying a finite structure.", path=path)
            else:
                message = tr("Loaded molecular structure from {path.name}.", path=path)
            self.log.appendPlainText(message)
            self.statusBar().showMessage(message, 8000)
            if after_open:
                after_open()
        elif isinstance(result, Session):
            self._show_native_result(path, result)
        elif isinstance(result, SummaryView):
            self._show_summary(path, result)
        else:
            self._show_log_only(path, result)

    def _reset_reader(self):
        self._read_timer.stop()
        self._after_open = None
        self._read_cancel = None
        self._read_origin = None
        self._read_future = None
        self._pending_result = None
        self.pending_result_button.hide()
        self.cancel_read_button.hide()
        self.open_file_action.setEnabled(True)
        self.import_action.setEnabled(True)
        self.summary_action.setEnabled(True)

    def _cancel_read(self):
        if self._read_cancel is not None:
            self._read_cancel.set()
        if self._read_future is not None:
            # A reader already parsing may finish independently. Its result is discarded.
            future = self._read_future
            if not future.cancel():
                future.add_done_callback(self._discard_prepared_molden)
        if self._pending_result and isinstance(self._pending_result[1], PreparedMolden):
            self._pending_result[1].folder.cleanup()
        self._reset_reader()
        self.statusBar().showMessage(tr("Opening canceled."), 8000)

    @staticmethod
    def _discard_prepared_molden(future):
        if not future.cancelled() and future.exception() is None:
            result = future.result()
            if isinstance(result, PreparedMolden):
                result.folder.cleanup()

    def closeEvent(self, event):
        if self._guard_discard():
            if self._update_dialog is not None:
                if not self._update_dialog.finish_on_exit():
                    event.ignore()
                    return
                self._update_dialog.reject()
            self.design_panel.discard_pending_job()
            self.orbital_panel.shutdown()
            self._cancel_read()
            self._reader.shutdown(wait=False, cancel_futures=True)
            event.accept()
        else:
            event.ignore()


def launch(screenshot=None, *, configure=None):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("OrcaView")
    locale = load_interface_language(app)
    app.setWindowIcon(QIcon(str(APP_ICON)))
    app.setFont(typography.interface_font(locale))
    window = MainWindow()
    if configure is not None:
        configure(window)
    if screenshot is not None:
        from PySide6.QtCore import QIODevice, QSaveFile

        # A hidden widget can be laid out and painted without mapping a desktop window.
        window.ensurePolished()
        image = window.grab()
        output = QSaveFile(str(screenshot))
        image_format = Path(screenshot).suffix.lstrip(".").upper()
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(output.errorString())
        if not image_format or not image.save(output, image_format):
            output.cancelWriting()
            raise ValueError("Could not encode the desktop screenshot using the filename extension")
        if not output.commit():
            raise OSError(output.errorString())
        return 0
    window.show()
    return app.exec()

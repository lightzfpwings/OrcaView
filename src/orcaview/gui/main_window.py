"""单文档桌面原型：科学设置通过应用层校验后才能导出。"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import math
from pathlib import Path
import sys

from PySide6.QtCore import QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QCompleter, QDockWidget, QFileDialog, QFrame,
    QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QSpinBox, QTabWidget, QToolBar,
    QVBoxLayout, QWidget,
)

from orcaview import __version__
from orcaview.i18n import diagnostic_text, tr
from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session
from orcaview.application.structure_import import OpenedStructure, PeriodicFile, open_file_filters, read_structure_file
from orcaview.core.integrals import (
    auxiliary_options, basis_options, grid_options, integral_options, scalar_options,
)
from orcaview.core.methods import (
    ACTIVE_SPACE_METHODS, ALL_JOBS, ELECTRON_CHANNEL_METHODS, EXCITED_STATE_METHODS, METHOD_GROUPS,
    METHODS, REFERENCE_FUNCTIONAL_METHODS, RESPONSE_FUNCTIONALS, canonical_method, dispersion_options, frozen_core_options,
    pno_options, reference_options,
)
from orcaview.core.models import CalculationSpec
from orcaview.core.solvation import SOLVENTS, solvation_options, uses_numerical_frequencies
from orcaview.gui.block_options import BlockOptionsPanel
from orcaview.gui.foundation_demo import build_foundation_demo
from orcaview.gui.foundation_panel import FoundationPanel
from orcaview.gui.inspector_form import InspectorForm, InspectorScrollArea, wrap_parameter_text
from orcaview.gui.language_settings import LanguageDialog, load_interface_language
from orcaview.gui.manual import ManualDialog
from orcaview.gui.native_input import edit_native_input
from orcaview.gui.preview_tabs import PreviewTabBar
from orcaview.gui.project_navigation import ProjectNavigationTree
from orcaview.gui.result_demo import build_result_demo
from orcaview.gui.result_display import display_file_name
from orcaview.gui.result_import import SummaryView, read_native_session, read_summary_view
from orcaview.gui.version_info import desktop_version_info
from orcaview.gui.viewport import MoleculeViewport
from orcaview.gui.workspace_columns import WorkspaceColumns
from orcaview.io.xyz import parse_xyz
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
QPushButton:hover { background: #F2E4E6; border-color: #AB7884; }
QPushButton#primary { background: #904359; color: white; border-color: #904359; }
QPushButton#primary:hover { background: #79364B; }
QLabel#brand { font-size: 22px; font-weight: 700; color: #904359; padding-right: 20px; }
QLabel#platformBadge { color: #70635F; font-size: 12px; padding: 5px 10px; background: #FAF7F2; border-radius: 4px; }
QLabel#heading { font-size: 18px; font-weight: 600; }
QLabel#muted { color: #70635F; }
/* Size native dock titles with the font that paints the Chinese glyphs. */
QDockWidget { font-weight: 600; font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }
QDockWidget::title { background: #FAF7F2; border-bottom: 1px solid #DDD5CB; padding: 9px; }
QDockWidget[sidePane="true"]::title { padding: 8px 9px 9px; }
QDockWidget#inputOutputDock::title { border: none; }
QTreeWidget { background: #FAF7F2; border: none; padding: 10px 4px; }
QTreeWidget::item { padding: 7px 2px; }
QTreeWidget::item:selected, QTableWidget::item:selected { background: #F2E4E6; color: #904359; }
QComboBox, QSpinBox, QLineEdit { padding: 6px; background: #FFFDF9; border: 1px solid #DDD5CB; border-radius: 4px; }
QComboBox QLineEdit, QSpinBox QLineEdit { padding: 0; border: none; }
QComboBox QAbstractItemView { background: #FFFDF9; color: #372F2D; }
QTabWidget::pane { border: 1px solid #DDD5CB; background: #FFFDF9; }
QTabWidget#workspaceTabs::pane { border: none; border-top: 1px solid #DDD5CB; }
QTabWidget#workspaceTabs::tab-bar { alignment: left; }
QTabBar::tab { background: #FAF7F2; padding: 9px 22px; color: #70635F; }
QTabBar#workspaceTabBar::tab { padding: 7px 16px 9px; }
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
QHeaderView::section { background: #FAF7F2; border: none; padding: 8px 5px; font-weight: 600; }
QPushButton:disabled, QPushButton#primary:disabled { color: #857976; background: #EFEAE4; border-color: #DDD5CB; }
QStatusBar { background: #FAF7F2; color: #70635F; border-top: 1px solid #DDD5CB; }
QStatusBar QLabel { color: #70635F; }
"""


def demo_benzene():
    """展示几何不冒充计算结果；显式保留 XYZ 的键级未知性质。"""
    lines = ["12", "Benzene · demonstration geometry"]
    for element, radius in (("C", 1.397), ("H", 2.481)):
        for i in range(6):
            angle = math.pi * i / 3
            lines.append("{} {:.8f} {:.8f} 0.0".format(element, radius * math.cos(angle), radius * math.sin(angle)))
    return parse_xyz("\n".join(lines), name="Benzene")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.session = Session(molecule=demo_benzene(), calculation=CalculationSpec(job_type="OPT"))
        self.dirty = False
        self._loading = True
        self._workspace_version = 0
        self._reader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orcaview-import")
        self._read_future = None
        self._pending_result = None
        self._read_timer = QTimer(self)
        self._read_timer.setInterval(50)
        self._read_timer.timeout.connect(self._finish_read)
        self.resize(1440, 980)
        self.setMinimumSize(1120, 780)
        self.setStyleSheet(STYLE)
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
        self.subtitle = QLabel(tr("结构预览 / 三维交互原型"))
        self.subtitle.setObjectName("muted")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.heading)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.viewport, 1)
        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setObjectName("workspaceTabs")
        self.workspace_tabs.tabBar().setObjectName("workspaceTabBar")
        self.workspace_tabs.addTab(center, tr("结构与计算"))
        self.foundation_panel = FoundationPanel()
        # Let the splitters inside the results page adapt to each animation frame.
        self.foundation_panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.workspace_tabs.addTab(self.foundation_panel, tr("结果"))
        self.setCentralWidget(self.workspace_tabs)
        self._create_tree()
        self._create_inspector()
        self._create_bottom()
        self._structure_bottom_visible = True
        self.workspace_tabs.currentChanged.connect(self._workspace_changed)
        self.viewport.selection_changed.connect(self._selection_changed)
        self._create_status_bar(versions)
        self._load_controls()
        self.columns = WorkspaceColumns(self, self.tree_dock, self.inspector_dock)
        self.resizeDocks([self.bottom_dock], [260], Qt.Orientation.Vertical)

    def _action(self, title, slot, shortcut=None):
        action = QAction(title, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def _create_actions(self):
        menu = self.menuBar().addMenu(tr("文件"))
        self.open_file_action = self._action(tr("打开文件…"), self.open_file, "Ctrl+O")
        menu.addAction(self.open_file_action)
        menu.addAction(self._action(tr("打开项目…"), self.open_project))
        menu.addAction(self._action(tr("保存项目…"), self.save_project_dialog, "Ctrl+S"))
        menu.addAction(self._action(tr("导出 ORCA 输入…"), self.export_input))
        menu.addAction(self._action(tr("编辑原生 ORCA 输入…"), self.open_native_input_editor))
        self.import_action = self._action(tr("导入 ORCA 计算结果…"), self.import_native_output)
        self.summary_action = self._action(tr("读取 ORCA 输出摘要…"), self.open_output)
        menu.addAction(self.import_action)
        menu.addAction(self.summary_action)
        view = self.menuBar().addMenu(tr("视图"))
        view.addAction(self._action(tr("复位视图"), self._fit_active_view))
        labels = QAction(tr("显示全部原子标签"), self)
        labels.setCheckable(True)
        labels.toggled.connect(self._toggle_labels)
        view.addAction(labels)
        view.addAction(self._action(tr("界面语言…"), lambda: LanguageDialog(self).exec()))
        calculation = self.menuBar().addMenu(tr("计算"))
        calculation.addAction(self._action(tr("查找计算方法…"), self.find_method, "Ctrl+K"))
        data_menu = self.menuBar().addMenu(tr("数据"))
        data_menu.addAction(self._action(tr("结果"), lambda: self.workspace_tabs.setCurrentWidget(self.foundation_panel)))
        data_menu.addAction(self._action(tr("载入 M6 合成电荷样例"), self.load_analysis_demo))
        data_menu.addAction(self._action(tr("载入 M1 原子电荷样例"), self.load_foundation_demo))
        help_menu = self.menuBar().addMenu(tr("帮助"))
        help_menu.addAction(self._action(tr("ORCA 6.1.1 计算手册…"), lambda: ManualDialog(self).exec()))
        help_menu.addAction(self._action(tr("关于框架"), lambda: QMessageBox.information(
            self, "OrcaView", tr("OrcaView {}\nORCA 前后处理桌面原型\n\n支持 XYZ、输入模板、计算日志和光谱。", __version__))))

    def _create_toolbar(self, platform_name):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        mark = QLabel()
        mark.setPixmap(QIcon(str(APP_ICON)).pixmap(QSize(32, 32), self.devicePixelRatioF()))
        toolbar.addWidget(mark)
        brand = QLabel("OrcaView")
        brand.setObjectName("brand")
        toolbar.addWidget(brand)
        for title, slot in [(tr("打开文件"), self.open_file), (tr("打开项目"), self.open_project),
                            (tr("保存项目"), self.save_project_dialog)]:
            button = QPushButton(title)
            button.clicked.connect(slot)
            if slot == self.open_file:
                self.open_file_action.enabledChanged.connect(button.setEnabled)
            toolbar.addWidget(button)
        import_button = QPushButton(tr("导入计算结果"))
        import_button.setObjectName("primary")
        import_button.setToolTip(self.import_action.text())
        import_button.clicked.connect(self.import_action.trigger)
        self.import_action.changed.connect(lambda: import_button.setEnabled(self.import_action.isEnabled()))
        toolbar.addWidget(import_button)
        fit_button = QPushButton(tr("复位视图"))
        fit_button.clicked.connect(self._fit_active_view)
        toolbar.addWidget(fit_button)
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().Policy.Expanding, spacer.sizePolicy().Policy.Preferred)
        toolbar.addWidget(spacer)
        badge = QLabel(platform_name)
        badge.setObjectName("platformBadge")
        badge.setAccessibleName(tr("运行平台"))
        toolbar.addWidget(badge)

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
        system.setAccessibleName(tr("系统版本"))
        layout.addWidget(system)
        message = QLabel()
        message.setObjectName("statusMessage")
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        bar.messageChanged.connect(message.setText)
        layout.addWidget(message, 1)
        self.pending_result_button = QPushButton(tr("打开已读取的文件"))
        self.pending_result_button.clicked.connect(self._open_pending_result)
        layout.addWidget(self.pending_result_button)
        self.pending_result_button.hide()
        self.cancel_read_button = QPushButton(tr("取消读取"))
        self.cancel_read_button.clicked.connect(self._cancel_read)
        layout.addWidget(self.cancel_read_button)
        self.cancel_read_button.hide()
        software = QLabel(versions.software_version)
        software.setObjectName("softwareVersion")
        software.setAccessibleName(tr("OrcaView 版本和适配的 ORCA 版本"))
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
        self.tree_dock = self._dock(tr("项目导航"), self.tree, Qt.DockWidgetArea.LeftDockWidgetArea)

    def _spin(self, minimum, maximum, value):
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.setValue(value)
        control.valueChanged.connect(self._settings_changed)
        return control

    def _create_inspector(self):
        panel = QWidget()
        panel.setObjectName("calculationInspector")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 18, 16, 14)
        label = QLabel(tr("计算设置"))
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
        auxiliary_labels = {"aux_j": tr("库仑拟合 AuxJ"), "aux_jk": tr("库仑/交换 AuxJK"),
                            "aux_c": tr("相关拟合 AuxC"), "cabs": tr("互补基组 CABS")}
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
            field.setSpecialValueText(tr("未设置"))
        self.nroots = self._spin(1, 2147483647, 5)
        self.reference_functional = QComboBox()
        self.reference_functional.addItems(list(RESPONSE_FUNCTIONALS))
        self.reference_functional.setCurrentText("B3LYP")
        self.electron_channel = QComboBox()
        self.electron_channel.addItem(tr("请选择自旋通道"), None)
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
        self.multiplicity = self._spin(1, 101, 1)
        self.cores = self._spin(1, 256, 4)
        self.maxcore = self._spin(1, 1048576, 1000)
        for label, control in [(tr("方法类别"), self.method_group), (tr("计算方法"), self.method), (tr("轨道基组"), self.basis),
                               (tr("作业类型"), self.job)]:
            form.addRow(label, control)
        self.method_hint = QLabel(tr("数值频率需要对多个位移结构重复计算，耗时随原子数增加。"))
        self.method_hint.setWordWrap(True)
        self.method_hint.setObjectName("muted")
        form.addRow(self.method_hint)
        for label, control in [(tr("活性电子数"), self.active_electrons), (tr("活性轨道数"), self.active_orbitals),
                               (tr("参考泛函"), self.reference_functional), (tr("目标根数"), self.nroots), (tr("电荷"), self.charge),
                               (tr("自旋多重度"), self.multiplicity), (tr("电子自旋通道"), self.electron_channel),
                               (tr("参考波函数"), self.wavefunction), (tr("标量相对论"), self.relativity),
                               (tr("积分近似"), self.integral_approximation), (tr("溶剂模型"), self.solvation_model),
                               (tr("溶剂"), self.solvent)]:
            form.addRow(label, control)
        for name, label in auxiliary_labels.items():
            form.addRow(label, self.auxiliary_bases[name])
        for label, control in [(tr("色散修正"), self.dispersion), (tr("数值积分网格"), self.integration_grid),
                               (tr("冻结内层轨道"), self.frozen_core), (tr("PNO 精度"), self.pno_preset),
                               (tr("处理核心数"), self.cores), (tr("每核内存 / MB"), self.maxcore)]:
            form.addRow(label, control)
        layout.addWidget(form)
        self.block_options = BlockOptionsPanel()
        self.block_options.changed.connect(self._settings_changed)
        layout.addWidget(self.block_options)
        self.memory_hint = QLabel()
        self.memory_hint.setWordWrap(True)
        self.memory_hint.setObjectName("muted")
        layout.addWidget(self.memory_hint)
        self.validation = QLabel()
        self.validation.setWordWrap(True)
        layout.addWidget(self.validation)
        self.export_button = QPushButton(tr("导出 .inp"))
        self.export_button.setObjectName("primary")
        self.export_button.clicked.connect(self.export_input)
        layout.addWidget(self.export_button)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        self.selection = QLabel(tr("点击原子查看坐标"))
        self.selection.setWordWrap(True)
        layout.addWidget(self.selection)
        layout.addStretch()
        scroll = InspectorScrollArea()
        scroll.setMinimumWidth(240)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(panel)
        self.inspector_dock = self._dock(tr("属性与设置"), scroll, Qt.DockWidgetArea.RightDockWidgetArea)

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
                control.addItem(tr("自动"), None)
            for value in choices:
                control.addItem(tr("自动") if value == "Auto" else value, value)
            index = control.findData(selected)
            if index >= 0:
                control.setCurrentIndex(index)

    def _refresh_basis_options(self, spec=None):
        method = self.method.currentText()
        basis = self.basis.currentData()
        approximation = self.integral_approximation.currentData()
        for name, control, options in (("relativity", self.relativity, scalar_options(method, basis)),
                                       ("integration_grid", self.integration_grid, grid_options(method, approximation))):
            selected = getattr(spec, name) if spec is not None else control.currentData()
            self._fill_options(control, options, selected or "Auto")
            self.method_form.setRowVisible(control, len(options) > 1)
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
                self.solvent.addItem(tr("自定义介电常数（%xtb EPSILON）"), None)
                if custom:
                    self.solvent.setCurrentIndex(self.solvent.count() - 1)
        self.method_form.setRowVisible(self.solvent, bool(choices))

    def _solvation_changed(self):
        self._fill_solvents(self.solvent.currentData())
        self._settings_changed()

    def _set_integral_options(self, spec=None):
        method = self.method.currentText()
        job = self.job.currentData()
        references = reference_options(method, job)
        selected = spec.wavefunction if spec else self.wavefunction.currentData()
        self._fill_options(self.wavefunction, references, selected or "Auto")
        self.method_form.setRowVisible(self.wavefunction, len(references) > 1)
        models = solvation_options(method, job)
        selected = spec.solvation_model if spec else self.solvation_model.currentData()
        custom = ((spec.solvation_model == "DDCOSMO" and spec.solvent is None) if spec else
                  self.solvation_model.currentData() == "DDCOSMO" and self.solvent.currentData() is None)
        self._fill_options(self.solvation_model, models, selected)
        self.solvation_model.setItemText(0, tr("气相"))
        self.method_form.setRowVisible(self.solvation_model, len(models) > 1)
        self._fill_solvents(spec.solvent if spec else self.solvent.currentData(), custom=custom)
        approximations = integral_options(self.method.currentText(), self.job.currentData())
        selected = spec.integral_approximation if spec is not None else self.integral_approximation.currentData()
        self._fill_options(self.integral_approximation, approximations, selected or "Auto")
        self.method_form.setRowVisible(self.integral_approximation, len(approximations) > 1)
        self._refresh_basis_options(spec)

    def _job_changed(self):
        previous = self.integral_approximation.currentText()
        self._set_integral_options()
        if previous != self.integral_approximation.currentText():
            self.statusBar().showMessage(tr("{job} 的积分近似已切换为{approximation}。", job=self.job.currentText(), approximation=self.integral_approximation.currentText()), 7000)
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
                self.basis.addItem(tr("方法内置 / 固定"), basis)
        self.basis.setEnabled(preset.uses_orbital_basis)
        for name, control, choices in (("frozen_core", self.frozen_core, frozen_core_options(method)),
                                       ("pno_preset", self.pno_preset, pno_options(method)),
                                       ("dispersion", self.dispersion, dispersion_options(method))):
            selected = getattr(spec, name) if spec is not None else control.currentData()
            self._fill_options(control, choices, selected or "Auto")
            self.method_form.setRowVisible(control, len(choices) > 1)
        job_labels = {"SP": tr("单点能  ·  SP"), "OPT": tr("几何优化  ·  Opt"), "FREQ": tr("频率"), "OPT_FREQ": tr("优化 + 频率"),
                      "OPT_TS": tr("过渡态优化 · OptTS"), "IRC": tr("内禀反应坐标 · IRC")}
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
        dialog = QInputDialog(self)
        dialog.setWindowTitle(tr("查找计算方法"))
        dialog.setLabelText(tr("方法名称或别名"))
        dialog.setComboBoxItems(list(METHODS))
        dialog.setComboBoxEditable(True)
        dialog.setOkButtonText(tr("选择"))
        dialog.setCancelButtonText(tr("取消"))
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
            QMessageBox.warning(self, tr("未找到计算方法"), tr("方法目录中没有“{query}”。", query=query))
            return
        self.workspace_tabs.setCurrentIndex(0)
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
            changes.append(tr("作业类型已切换为{job}", job=self.job.currentText()))
        if previous_basis != self.basis.currentText():
            changes.append(tr("轨道基组已切换为{basis}", basis=self.basis.currentText()))
        if changes:
            self.statusBar().showMessage(f"{self.method.currentText()} · " + "，".join(changes), 7000)
        self._settings_changed()

    def _text_panel(self):
        panel = QPlainTextEdit()
        panel.setReadOnly(True)
        panel.setFont(QFont("Menlo", 11))
        return panel

    def _create_bottom(self):
        self.tabs = QTabWidget()
        self.tabs.setObjectName("inputOutputTabs")
        self.tabs.setTabBar(PreviewTabBar(self.tabs, self.workspace_tabs, self.tree_dock, self.inspector_dock))
        self.tabs.setDocumentMode(True)
        self.input_preview = self._text_panel()
        self.output_summary = self._text_panel()
        self.output_summary.setPlainText(tr("通过“文件 → 读取 ORCA 输出摘要”查看单作业日志。\n单点能和逐原子电荷可通过“导入单点结果”打开。"))
        self.log = self._text_panel()
        self.log.setPlainText(tr("OrcaView 框架已启动。\n示例结构仅供交互演示；尚未执行任何计算。"))
        for widget, name in [(self.input_preview, tr("ORCA 输入预览")), (self.output_summary, tr("结果摘要")), (self.log, tr("消息与日志"))]:
            self.tabs.addTab(widget, name)
        self.bottom_dock = self._dock(tr("输入与结果"), self.tabs, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.bottom_dock.setObjectName("inputOutputDock")

    def _load_controls(self, *, project_path=None):
        self._workspace_version += 1
        self._loading = True
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
            # 载入项目可超出默认控件范围，扩展范围以保留原值。
            control.setRange(min(control.minimum(), value), max(control.maximum(), value))
            control.setValue(value)
        self.block_options.load(spec)
        self.viewport.set_molecule(molecule)
        self._set_structure_heading(project_path or self.session.source_path)
        counts = Counter(a.element for a in molecule.atoms)
        formula = " ".join("{}{}".format(element, counts[element] if counts[element] > 1 else "") for element in sorted(counts))
        self.subtitle.setText(tr("{}  /  {} 个原子  /  科学坐标 Å", formula, len(molecule.atoms)))
        self.tree.set_structure(molecule.name)
        self.dirty = False
        self._loading = False
        self._update_preview()
        self.foundation_panel.set_document(self.session.document, input_path=self.session.source_path,
                                           project_path=project_path)
        self.foundation_panel.set_log_report(self.session.log_report)
        self._update_title()

    def _set_structure_heading(self, path):
        name = display_file_name(path, self.session.molecule.name)
        self.heading.setText(name)
        self.heading.setToolTip(str(path or name))

    def _settings_changed(self, *args):
        if self._loading:
            return
        self._workspace_version += 1
        self.dirty = True
        self._update_title()
        self._update_preview()
        self.foundation_panel.set_document(self.session.document)

    def _workspace_changed(self, index):
        showing_results = self.workspace_tabs.widget(index) is self.foundation_panel
        self.columns.set_results(showing_results)
        if showing_results:
            self._structure_bottom_visible = not self.bottom_dock.isHidden()
            self.bottom_dock.hide()
            self.foundation_panel.set_document(self.session.document)
        else:
            self.bottom_dock.setVisible(self._structure_bottom_visible)

    def _fit_active_view(self):
        if self.workspace_tabs.currentWidget() is self.foundation_panel:
            self.foundation_panel.viewport.fit()
        else:
            self.viewport.fit()

    def open_result_session(self, session, dataset_id=None, *, mark_dirty=True, project_path=None,
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
        self._load_controls(project_path=project_path)
        self.workspace_tabs.setCurrentWidget(self.foundation_panel)
        if selected is not None:
            self.foundation_panel.view_dataset(selected.dataset_id)
        self.dirty = mark_dirty
        self._update_title()
        self.statusBar().showMessage(message if message is not None else tr("原子按序号排列，点选一行可在结构中定位。"), timeout_ms)

    def load_analysis_demo(self):
        if self._guard_discard():
            session, dataset_id = build_result_demo()
            self.open_result_session(session, dataset_id, message=tr("已载入 M6 合成电荷样例"))

    def load_foundation_demo(self):
        if not self._guard_discard():
            return
        session = build_foundation_demo()
        charge = next(data for data in session.document.records()[1] if data.kind == "atomic_charge")
        self.open_result_session(session, charge.dataset_id, message=tr("已载入 M1 合成原子电荷样例"))
        self.log.appendPlainText(tr("已载入 M1 合成原子电荷样例，包含一个缺失值。"))

    def _update_title(self):
        self.setWindowTitle("{}{} · OrcaView {}".format("* " if self.dirty else "", self.session.molecule.name, __version__))

    def _update_frequency_labels(self, spec):
        numerical = uses_numerical_frequencies(spec)
        for job, label in (("FREQ", tr("数值频率  ·  NumFreq") if numerical else tr("解析频率  ·  Freq")),
                           ("OPT_FREQ", tr("优化 + 数值频率") if numerical else tr("优化 + 频率"))):
            index = self.job.findData(job)
            if index >= 0:
                self.job.setItemText(index, label)
        self.method_form.setRowVisible(self.method_hint, numerical and spec.job_type in ("FREQ", "OPT_FREQ"))

    def _update_preview(self):
        cores, memory = self.cores.value(), self.maxcore.value()
        self.memory_hint.setText(tr("内存估算：{} MB × {} = {:,} MB\n此值是按核分配的估算，并非进程硬上限。",
                                    memory, cores, memory * cores))
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
                **{name: control.currentData() for name, control in self.auxiliary_bases.items()},
            )
            self._update_frequency_labels(spec)
            removed = self.block_options.set_context(spec)
            if removed:
                names = "、".join(f"%{block} {key}" for block, key in removed)
                message = tr("已移除不适用于当前计算的设置：{names}", names=names)
                self.log.appendPlainText(message)
                self.statusBar().showMessage(message, 10000)
            spec = replace(spec, block_options=self.block_options.overrides())
            self._refresh_auxiliary_controls(spec)
            spec = replace(spec, **{name: control.currentData() for name, control in self.auxiliary_bases.items()})
            text = self.session.apply_settings(spec, self.charge.value(), self.multiplicity.value())
            if spec.peak_maxcore_per_process != spec.maxcore_mb:
                peak = spec.peak_maxcore_per_process
                self.memory_hint.setText(tr("内存估算：{peak:,} MB × {spec.cores} = {total:,} MB\n取各模块较高的每核值，实际峰值取决于运行阶段。", peak=peak, spec=spec, total=peak * spec.cores))
            self.input_preview.setPlainText(text)
            self.validation.setText(tr("● 基础结构与电子数校验通过"))
            self.validation.setToolTip("")
            self.validation.setStyleSheet("color: #466446; padding: 8px 0;")
            self.export_button.setEnabled(True)
            return True
        except ValueError as exc:
            message = diagnostic_text(exc)
            self.input_preview.setPlainText(tr("输入尚不可导出：\n{}", message))
            self.validation.setText("● " + wrap_parameter_text(message))
            self.validation.setToolTip(message)
            self.validation.setStyleSheet("color: #944A25; padding: 8px 0;")
            self.export_button.setEnabled(False)
            return False

    def _selection_changed(self, selected):
        atoms = self.session.molecule.atoms
        if not selected:
            self.selection.setText(tr("点击原子查看坐标"))
            return
        lines = []
        for index in selected:
            a = atoms[index]
            lines.append("{}{}  ({:.4f}, {:.4f}, {:.4f}) Å".format(a.element, index + 1, a.x, a.y, a.z))
        self.selection.setText("\n".join(lines))

    def _toggle_labels(self, enabled):
        self.viewport.labels = enabled
        self.viewport.update()
        self.foundation_panel.viewport.labels = enabled
        self.foundation_panel.viewport.update()

    def _error(self, exc):
        message = diagnostic_text(exc)
        self.log.appendPlainText(message)
        QMessageBox.warning(self, tr("操作未完成"), message)

    def _guard_discard(self):
        if not self.dirty:
            return True
        choice = QMessageBox.question(self, tr("未保存的设置"), tr("是否先保存当前项目？"), QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Save:
            return self.save_project_dialog()
        return choice == QMessageBox.StandardButton.Discard

    def open_file(self):
        if not self.open_file_action.isEnabled():
            return
        filename, _ = QFileDialog.getOpenFileName(self, tr("打开文件"), "", open_file_filters(tr))
        if not filename:
            return
        path = Path(filename)
        try:
            if path.name.lower().endswith(".oview.json"):
                self._open_project_path(filename)
            elif path.suffix.lower() in (".out", ".log"):
                self._start_read(path, read_native_session)
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

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("打开项目"), "", "OrcaView (*.oview.json);;JSON (*.json)")
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
                self.workspace_tabs.setCurrentIndex(0)
            self.log.appendPlainText(tr("已载入项目：{}", path))
        except (ValueError, OSError) as exc:
            self._error(exc)

    def save_project_dialog(self):
        if not self._update_preview():
            self._error(ValueError(tr("请先修正计算设置，再保存项目。")))
            return False
        path, _ = QFileDialog.getSaveFileName(self, tr("保存项目"), self.session.molecule.name + ".oview.json", "OrcaView (*.oview.json)")
        if not path:
            return False
        try:
            save_project(self.session, Path(path))
            self._set_structure_heading(path)
            self.foundation_panel.set_document(self.session.document, project_path=path)
            self.dirty = False
            self._update_title()
            self.log.appendPlainText(tr("已保存项目：{}", path))
            return True
        except (ValueError, OSError) as exc:
            self._error(exc)
            return False

    def export_input(self):
        if not self._update_preview():
            self._error(ValueError(tr("请先修正计算设置，再导出输入。")))
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("导出 ORCA 输入"), self.session.molecule.name + ".inp", tr("ORCA 输入") + " (*.inp)")
        if path:
            try:
                Path(path).write_text(self.session.input_text(), encoding="utf-8")
                self.log.appendPlainText(tr("已导出 ORCA 输入：{}", path))
                self.statusBar().showMessage(tr("输入已导出：{}", path), 8000)
            except (ValueError, OSError) as exc:
                self._error(exc)

    def open_native_input_editor(self):
        initial = self.session.input_text() if self._update_preview() else ""
        edit_native_input(self, initial)

    def import_native_output(self):
        if not self.import_action.isEnabled():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("导入 ORCA 计算结果"), "",
                                              tr("ORCA 输出") + " (*.out *.log);;" + tr("全部文件") + " (*)")
        if path:
            self._start_read(Path(path), read_native_session)

    def _show_native_result(self, path, session):
        self.open_result_session(session, message=tr("已导入 {path.name} 的结构与计算结果，可保存项目。", path=path))
        self.log.appendPlainText(tr("已将 {path} 的结果导入独立项目。", path=path))

    def open_output(self):
        if not self.summary_action.isEnabled():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("读取单作业输出"), "", tr("ORCA 输出") + " (*.out *.log);;" + tr("全部文件") + " (*)")
        if not path:
            return
        job, accepted = QInputDialog.getItem(self, tr("输出作业类型"), tr("选择原始作业类型（用于收敛判定）"), list(ALL_JOBS), 0, False)
        if not accepted:
            return
        self._start_read(Path(path), read_summary_view, job)

    def _show_summary(self, path, result):
        self.output_summary.setPlainText(result.text)
        self.tabs.setCurrentWidget(self.output_summary)
        if result.report.properties or result.report.spectra:
            self._show_log_only(path, result.report)
        else:
            self.workspace_tabs.setCurrentIndex(0)
        self.log.appendPlainText(tr("已读取输出摘要：{path}", path=path))
        self.statusBar().showMessage(tr("已读取 {path.name} 的摘要", path=path), 8000)

    def _show_log_only(self, path, report):
        self.workspace_tabs.setCurrentWidget(self.foundation_panel)
        self.foundation_panel.set_log_report(report, standalone=True)
        self.statusBar().showMessage(tr("正在浏览独立日志 {path.name}，当前编辑项目保留。", path=path), 8000)

    def _read_context(self):
        return self._workspace_version, self.session.document.records()

    def _start_read(self, path, reader, *args):
        self._read_origin = self._read_context()
        self._read_path = path
        self.open_file_action.setEnabled(False)
        self.import_action.setEnabled(False)
        self.summary_action.setEnabled(False)
        self.cancel_read_button.setText(tr("取消打开"))
        self.cancel_read_button.show()
        self.statusBar().showMessage(tr("正在读取 {path.name}…", path=path))
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
                self.cancel_read_button.setText(tr("放弃打开"))
                self.statusBar().showMessage(tr("{path.name} 已就绪，可在完成当前操作后打开。", path=path))
            else:
                if isinstance(result, (Session, OpenedStructure)) and not self._guard_discard():
                    self._reset_reader()
                else:
                    self._display_read_result(path, result)
        except Exception as exc:
            self._reset_reader()
            if isinstance(exc, OrcaImportError):
                details = "\n".join(
                    f"{issue.code} · " + (tr("第 {issue.line} 行 · ", issue=issue) if issue.line else "") + diagnostic_text(issue.message)
                    for issue in exc.issues
                )
            else:
                details = diagnostic_text(exc)
            self.statusBar().showMessage(tr("读取失败：{path.name}", path=path), 8000)
            self._error(ValueError(f"{path.name}\n{details}"))

    def _open_pending_result(self):
        if self._pending_result is None:
            return
        path, result = self._pending_result
        if isinstance(result, (Session, OpenedStructure)) and not self._guard_discard():
            return
        self._display_read_result(path, result)

    def _display_read_result(self, path, result):
        self._reset_reader()
        if isinstance(result, PeriodicFile):
            dialog = QMessageBox(QMessageBox.Icon.Question, tr("周期性结构"),
                                 tr("{path.name} 包含周期性结构。是否去掉周期性，显示一个有限结构？", path=path),
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
            dialog.button(QMessageBox.StandardButton.Yes).setText(tr("是"))
            dialog.button(QMessageBox.StandardButton.No).setText(tr("否"))
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
            if dialog.exec() == QMessageBox.StandardButton.Yes:
                reader = read_native_session if path.suffix.lower() in (".out", ".log") else read_structure_file
                self._start_read(path, reader, result)
            else:
                self.statusBar().showMessage(tr("不支持周期性结构。"), 8000)
                QMessageBox.information(self, tr("周期性结构"), tr("不支持周期性结构。"))
        elif isinstance(result, OpenedStructure):
            self.session = result.session(self.session.calculation)
            self._load_controls()
            self.workspace_tabs.setCurrentIndex(0)
            if result.record.generated_3d:
                message = tr("已用 Open Babel 生成 {path.name} 的三维构象。", path=path)
            elif result.record.removed_periodicity:
                message = tr("已去掉 {path.name} 的周期性，显示有限结构。", path=path)
            else:
                message = tr("已从 {path.name} 载入分子结构。", path=path)
            self.log.appendPlainText(message)
            self.statusBar().showMessage(message, 8000)
        elif isinstance(result, Session):
            self._show_native_result(path, result)
        elif isinstance(result, SummaryView):
            self._show_summary(path, result)
        else:
            self._show_log_only(path, result)

    def _reset_reader(self):
        self._read_timer.stop()
        self._read_origin = None
        self._read_future = None
        self._pending_result = None
        self.pending_result_button.hide()
        self.cancel_read_button.hide()
        self.open_file_action.setEnabled(True)
        self.import_action.setEnabled(True)
        self.summary_action.setEnabled(True)

    def _cancel_read(self):
        if self._read_future is not None:
            # A reader already parsing may finish independently. Its result is discarded.
            self._read_future.cancel()
        self._reset_reader()
        self.statusBar().showMessage(tr("已取消打开文件。"), 8000)

    def closeEvent(self, event):
        if self._guard_discard():
            self._cancel_read()
            self._reader.shutdown(wait=False, cancel_futures=True)
            event.accept()
        else:
            event.ignore()


def launch(screenshot=None):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("OrcaView")
    load_interface_language(app)
    app.setWindowIcon(QIcon(str(APP_ICON)))
    app.setFont(QFont("Arial", 12))
    window = MainWindow()
    window.show()
    if screenshot is not None:
        # 截图用途也走真实窗口绘制路径，便于无显示器环境验证。
        def capture():
            success = window.grab().save(str(screenshot))
            app.exit(0 if success else 2)
        QTimer.singleShot(600, capture)
    return app.exec()

"""Choose a language and a directory for downloaded interface packs."""

from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QSettings, QStandardPaths, QTranslator, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from orcaview.i18n import BASE_LOCALE, activate_language, discover_languages, tr


def _settings():
    return QSettings("OrcaView", "OrcaView")


def _directory(settings):
    default = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / "languages"
    return Path(settings.value("interface/languageDirectory", str(default), type=str)).expanduser()


def load_interface_language(app, settings=None):
    """Called before constructing the first window, including after an upgrade."""
    if settings is None:
        settings = _settings()
    packs, _ = discover_languages(_directory(settings))
    pack = packs.get(settings.value("interface/language", BASE_LOCALE, type=str), packs[BASE_LOCALE])
    activate_language(pack)
    previous = getattr(app, "_orcaview_qt_translator", None)
    if previous is not None:
        app.removeTranslator(previous)
        previous.deleteLater()
        app._orcaview_qt_translator = None
    qt = QTranslator(app)
    locale = {"zh-Hans": "zh_CN", "zh-Hant": "zh_TW"}.get(pack.locale, pack.locale.replace("-", "_"))
    translations = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if qt.load("qtbase_" + locale, translations):
        app.installTranslator(qt)
        app._orcaview_qt_translator = qt
    else:
        qt.deleteLater()
    return pack.locale


class LanguageDialog(QDialog):
    def __init__(self, parent=None, *, settings=None):
        super().__init__(parent)
        self.settings = _settings() if settings is None else settings
        self.setWindowTitle(tr("界面语言"))
        self.resize(580, 200)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        path_row = QHBoxLayout()
        self.directory = QLineEdit(str(_directory(self.settings)))
        self.directory.setReadOnly(True)
        path_row.addWidget(self.directory, 1)
        choose = QPushButton(tr("选择目录…"))
        choose.clicked.connect(self._choose_directory)
        path_row.addWidget(choose)
        open_folder = QPushButton(tr("打开目录"))
        open_folder.clicked.connect(self._open_directory)
        path_row.addWidget(open_folder)
        form.addRow(tr("语言包目录"), path_row)
        language_row = QHBoxLayout()
        self.languages = QComboBox()
        language_row.addWidget(self.languages, 1)
        refresh = QPushButton(tr("刷新语言包"))
        refresh.clicked.connect(lambda: self._refresh(self.languages.currentData()))
        language_row.addWidget(refresh)
        form.addRow(tr("语言"), language_row)
        self.report = QLabel()
        self.report.setWordWrap(True)
        self.report.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.report)
        layout.addWidget(QLabel(tr("重新启动 OrcaView 后生效。")))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("保存"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("取消"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh(self.settings.value("interface/language", BASE_LOCALE, type=str))

    def _choose_directory(self):
        selected = QFileDialog.getExistingDirectory(self, tr("选择语言包目录"), self.directory.text())
        if selected:
            self.directory.setText(selected)
            self._refresh(self.languages.currentData())

    def _open_directory(self):
        path = Path(self.directory.text())
        try:
            path.mkdir(parents=True, exist_ok=True)
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except OSError:
            opened = False
        if not opened:
            QMessageBox.warning(self, tr("界面语言"), tr("无法打开目录：{path}", path=path))

    def _refresh(self, preferred):
        packs, failures = discover_languages(self.directory.text())
        self.languages.clear()
        for pack in packs.values():
            self.languages.addItem(pack.name, pack.locale)
        self.languages.setCurrentIndex(max(0, self.languages.findData(preferred)))
        self.report.setText(tr("未能读取语言包：{files}", files="\n".join(failures)) if failures else "")
        self.report.setVisible(bool(failures))

    def accept(self):
        selected = self.languages.currentData()
        self._refresh(selected)
        if self.languages.currentData() != selected:
            QMessageBox.warning(self, tr("界面语言"), tr("所选语言包已不可用。"))
            return
        self.settings.setValue("interface/languageDirectory", self.directory.text())
        self.settings.setValue("interface/language", selected)
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            QMessageBox.warning(self, tr("界面语言"), tr("无法保存语言设置。"))
            return
        super().accept()

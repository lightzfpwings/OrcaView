"""Manually check GitHub releases and hand a verified update to the user."""

from pathlib import Path
from threading import Event
from time import monotonic

from PySide6.QtCore import QLocale, QObject, QRunnable, QStandardPaths, Qt, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

from orcaview import __version__
from orcaview.application.update_download import download_update, install_portable
from orcaview.application.updates import RELEASES_URL, check_for_update
from orcaview.i18n import diagnostic_text, tr


class _UpdateSignals(QObject):
    progress = Signal(object, int)
    installing = Signal(object)
    finished = Signal(object, object, object)


class _UpdateTask(QRunnable):
    def __init__(self, asset=None, directory=None):
        super().__init__()
        self.asset = asset
        self.directory = directory
        self.signals = _UpdateSignals()
        self.stop = Event()
        self._last_progress = 0.0

    def _report_progress(self, received, total):
        now = monotonic()
        if total > 0 and (received == total or now - self._last_progress >= 0.1):
            self._last_progress = now
            self.signals.progress.emit(self, min(100, received * 100 // total))

    def run(self):
        try:
            if self.asset is None:
                result = check_for_update(__version__, cancelled=self.stop.is_set)
            else:
                result = download_update(self.asset, self.directory, progress=self._report_progress,
                                         cancelled=self.stop.is_set)
                if not self.asset.name.lower().endswith(".dmg"):
                    self.signals.installing.emit(self)
                    result = install_portable(self.asset, result, self.directory, cancelled=self.stop.is_set)
        except Exception as error:
            self.signals.finished.emit(self, None, error)
        else:
            self.signals.finished.emit(self, result, None)


class UpdateDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("updateDialog")
        self.setWindowTitle(tr("检查更新"))
        self.setMinimumWidth(480)
        self.release = None
        self._task = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(QLabel(tr("当前版本 {version}", version=__version__)))
        self.status = QLabel()
        self.status.setObjectName("updateStatus")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setObjectName("updateProgress")
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.page_button = QPushButton(tr("GitHub 发布页"))
        self.page_button.clicked.connect(self.open_release_page)
        buttons.addWidget(self.page_button)
        buttons.addStretch()
        self.check_button = QPushButton(tr("重新检查"))
        self.check_button.clicked.connect(self.check)
        buttons.addWidget(self.check_button)
        self.install_button = QPushButton(tr("下载并安装…"))
        self.install_button.setObjectName("installUpdateButton")
        self.install_button.clicked.connect(self.download)
        buttons.addWidget(self.install_button)
        self.cancel_button = QPushButton(tr("取消"))
        self.cancel_button.clicked.connect(self.cancel)
        buttons.addWidget(self.cancel_button)
        close = QPushButton(tr("关闭"))
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._controls()

    def _controls(self, *, offer_download=False):
        busy = self._task is not None
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)
        self.check_button.setVisible(not busy and not offer_download)
        self.install_button.setVisible(not busy and offer_download)

    def _start(self, task):
        self._task = task
        task.signals.progress.connect(self._progress)
        task.signals.installing.connect(self._installing)
        task.signals.finished.connect(self._finished)
        self.progress.setRange(0, 0)
        self._controls()
        QThreadPool.globalInstance().start(task)

    def check(self):
        if self._task is None:
            self.release = None
            self.status.setText(tr("正在检查 GitHub 发布版本…"))
            self._start(_UpdateTask())

    def open_release_page(self):
        url = self.release.page_url if self.release else RELEASES_URL
        if not QDesktopServices.openUrl(QUrl(url)):
            self.status.setText(tr("请在浏览器中打开 {url}", url=url))

    def download(self):
        if self._task is not None or not self.release or not self.release.asset:
            return
        asset = self.release.asset
        is_dmg = asset.name.lower().endswith(".dmg")
        title = tr("选择安装包保存位置") if is_dmg else tr("选择新版 OrcaView 的安装目录")
        directory = QFileDialog.getExistingDirectory(
            self, title, QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation))
        if directory and self.isVisible():
            self.status.setText(tr("正在下载并校验 {name}…", name=asset.name))
            self._start(_UpdateTask(asset, Path(directory)))

    def cancel(self):
        if self._task is not None:
            self._task.stop.set()
            self.cancel_button.setEnabled(False)
            self.status.setText(tr("正在取消…"))

    def done(self, result):
        if self._task is not None:
            self._task.stop.set()
            self._task = None
        super().done(result)

    @Slot(object, int)
    def _progress(self, task, percent):
        if task is self._task:
            self.progress.setRange(0, 100)
            self.progress.setValue(percent)

    @Slot(object)
    def _installing(self, task):
        if task is self._task and not task.stop.is_set():
            self.progress.setRange(0, 0)
            self.status.setText(tr("正在将新版本解压到安装目录…"))

    @Slot(object, object, object)
    def _finished(self, task, result, error):
        if task is not self._task:
            return
        self._task = None
        self._controls(offer_download=task.asset is not None)
        if task.stop.is_set() and (task.asset is None or result is None):
            self.status.setText(tr("已取消。"))
        elif error is not None:
            detail = diagnostic_text(error)
            self.status.setText(tr("检查更新失败。\n{error}", error=detail) if task.asset is None
                                else tr("下载或安装失败。\n{error}", error=detail))
        elif task.asset is None:
            self._show_release(result)
        else:
            self._show_installation(task, result)

    def _show_release(self, release):
        self.release = release
        if release is None:
            self.status.setText(tr("GitHub 上没有更新的版本。"))
            return
        message = tr("发现新版本 {version}。", version=release.version)
        if release.asset:
            size = QLocale().formattedDataSize(release.asset.size)
            self.status.setText(f"{message}\n{release.asset.name}  ({size})")
            self._controls(offer_download=True)
        else:
            self.status.setText(message + "\n" + tr("此版本没有适用于当前系统的可校验安装包。"))

    def _show_installation(self, task, path):
        self._controls()
        if task.asset.name.lower().endswith(".dmg"):
            target = path
            message = tr("请打开磁盘映像，将 OrcaView 拖入“应用程序”文件夹。\n{path}", path=path)
        else:
            target = path.parent
            message = tr("新版已安装到 {folder}\n从此目录运行 {name} 即可打开新版本。",
                         folder=target, name=path.name)
        if not task.stop.is_set() and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            message += "\n" + tr("系统未能打开此位置，请手动打开。")
        self.status.setText(message)

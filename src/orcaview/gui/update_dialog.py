"""Manually check GitHub releases and hand a verified update to the user."""

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic

from PySide6.QtCore import QLocale, QObject, QRunnable, QStandardPaths, Qt, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

from orcaview import __version__
from orcaview.application.macos_update import PreparedMacUpdate, current_macos_installation, prepare_macos_update
from orcaview.application.update_download import (
    current_portable_installation, download_update, install_portable, prepare_portable_update, schedule_portable_update,
)
from orcaview.application.updates import RELEASES_URL, check_for_update
from orcaview.i18n import diagnostic_text, tr


class _UpdateSignals(QObject):
    progress = Signal(object, int)
    installing = Signal(object)
    finished = Signal(object, object, object)


class _UpdateTask(QRunnable):
    def __init__(self, asset=None, directory=None, replace_target=None):
        super().__init__()
        self.asset = asset
        self.directory = directory
        self.replace_target = replace_target
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
                is_mac = self.asset.name.lower().endswith(".dmg")
                if self.replace_target is not None or self.asset.name.endswith("-Windows-x64-portable.zip"):
                    with TemporaryDirectory(prefix="orcaview-download-") as temp:
                        archive = download_update(self.asset, Path(temp), progress=self._report_progress,
                                                  cancelled=self.stop.is_set)
                        self.signals.installing.emit(self)
                        if self.replace_target is None:
                            result = install_portable(self.asset, archive, self.directory, cancelled=self.stop.is_set)
                        else:
                            prepare = prepare_macos_update if is_mac else prepare_portable_update
                            result = prepare(self.asset, archive, self.replace_target, cancelled=self.stop.is_set)
                else:
                    result = download_update(self.asset, self.directory, progress=self._report_progress,
                                             cancelled=self.stop.is_set)
                    if not is_mac:
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
        self.setWindowTitle(tr("Check for Updates"))
        self.release = None
        self._task = None
        self._prepared = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        # Let the layout raise the dialog minimum when longer actions appear.
        layout.addStrut(440)
        layout.addWidget(QLabel(tr("Current version {version}", version=__version__)))
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
        self.page_button = QPushButton(tr("GitHub releases"))
        self.page_button.clicked.connect(self.open_release_page)
        buttons.addWidget(self.page_button)
        buttons.addStretch()
        self.check_button = QPushButton(tr("Check again"))
        self.check_button.clicked.connect(self.check)
        buttons.addWidget(self.check_button)
        self.install_button = QPushButton(tr("Download and install…"))
        self.install_button.setObjectName("installUpdateButton")
        self.install_button.clicked.connect(self.download)
        buttons.addWidget(self.install_button)
        self.manual_button = QPushButton(tr("Install manually…"))
        self.manual_button.clicked.connect(lambda: self.download(manual=True))
        buttons.addWidget(self.manual_button)
        self.restart_button = QPushButton(tr("Quit and update"))
        self.restart_button.setObjectName("restartForUpdate")
        self.restart_button.clicked.connect(parent.close)
        buttons.addWidget(self.restart_button)
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.clicked.connect(self.cancel)
        buttons.addWidget(self.cancel_button)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._controls()

    def _controls(self, *, offer_download=False):
        busy = self._task is not None
        ready = self._prepared is not None
        self.cancel_button.setVisible(busy or ready)
        self.cancel_button.setEnabled(busy or ready)
        self.progress.setVisible(busy)
        self.check_button.setVisible(not busy and not offer_download and not ready)
        self.install_button.setVisible(not busy and offer_download and not ready)
        self.restart_button.setVisible(ready)
        self.manual_button.setVisible(bool(offer_download and not busy and not ready
                                           and self.release and self.release.asset
                                           and self._current_installation()))

    def _start(self, task):
        self._task = task
        task.signals.progress.connect(self._progress)
        task.signals.installing.connect(self._installing)
        task.signals.finished.connect(self._finished)
        self.progress.setRange(0, 0)
        self._controls()
        QThreadPool.globalInstance().start(task)

    def check(self):
        if self._task is None and self._prepared is None:
            self.release = None
            self.status.setText(tr("Checking GitHub releases…"))
            self._start(_UpdateTask())

    def open_release_page(self):
        url = self.release.page_url if self.release else RELEASES_URL
        if not QDesktopServices.openUrl(QUrl(url)):
            self.status.setText(tr("Open {url} in your browser.", url=url))

    def download(self, *, manual=False):
        if self._prepared is not None or self._task is not None or not self.release or not self.release.asset:
            return
        asset = self.release.asset
        is_dmg = asset.name.lower().endswith(".dmg")
        target = None if manual else self._current_installation()
        directory = None
        if target is None:
            title = tr("Choose where to save the installer") if is_dmg else tr("Choose an installation location (select an existing OrcaView folder to replace it)")
            directory = QFileDialog.getExistingDirectory(
                self, title, QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation))
            if manual and directory and not is_dmg and Path(directory).resolve() == self._current_installation():
                target = Path(directory).resolve()
        if (target is not None or directory) and self.isVisible():
            self.status.setText(tr("Downloading and verifying {name}…", name=asset.name))
            self._start(_UpdateTask(asset, Path(directory) if directory else None, target))

    def _current_installation(self):
        if self.release.asset.name.lower().endswith(".dmg"):
            return current_macos_installation()
        return current_portable_installation()

    def cancel(self):
        if self._task is not None:
            self._task.stop.set()
            self.cancel_button.setEnabled(False)
            self.status.setText(tr("Canceling…"))
        elif self._prepared is not None:
            self._prepared.discard()
            self._prepared = None
            self._controls(offer_download=True)
            self.status.setText(tr("Canceled."))

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
            self.status.setText(tr("Extracting the new version to the installation folder…"))

    @Slot(object, object, object)
    def _finished(self, task, result, error):
        if task is not self._task or (task.stop.is_set() and task.replace_target is not None):
            if task.replace_target is not None and result is not None:
                result.discard()
            if task is self._task:
                self._task = None
                self._controls(offer_download=True)
                self.status.setText(tr("Canceled."))
            return
        self._task = None
        self._controls(offer_download=task.asset is not None)
        if task.stop.is_set() and (task.asset is None or result is None):
            self.status.setText(tr("Canceled."))
        elif error is not None:
            detail = diagnostic_text(error)
            self.status.setText(tr("Could not check for updates.\n{error}", error=detail) if task.asset is None
                                else tr("Could not download or install the update.\n{error}", error=detail))
        elif task.asset is None:
            self._show_release(result)
        elif task.replace_target is not None:
            self._prepared = result
            self._controls()
            message = tr("The update is ready. You can save your project now. OrcaView will update in place and restart when you quit.\n{path}",
                         path=task.replace_target)
            if not isinstance(result, PreparedMacUpdate):
                message += "\n" + tr("Previous version backup: {path}", path=result.backup)
            self.status.setText(message)
        else:
            self._show_installation(task, result)

    def _show_release(self, release):
        self.release = release
        if release is None:
            self.status.setText(tr("No newer version is available on GitHub."))
            return
        message = tr("Version {version} is available.", version=release.version)
        if release.asset:
            size = QLocale().formattedDataSize(release.asset.size)
            target = self._current_installation()
            if target is not None:
                message += "\n" + tr("This installation will be updated in place: {path}", path=target)
            self.install_button.setText(tr("Download and replace…") if target is not None else tr("Download and install…"))
            self.status.setText(f"{message}\n{release.asset.name}  ({size})")
            self._controls(offer_download=True)
        else:
            self.status.setText(message + "\n" + tr("This release has no verifiable installer for this system."))

    def _show_installation(self, task, path):
        self._controls()
        if task.asset.name.lower().endswith(".dmg"):
            target = path
            message = tr("Open the disk image, quit the old version, drag OrcaView to its original location and choose Replace.\n{path}", path=path)
        else:
            target = path.parent
            message = tr("Installed to {folder}\nRun {name} from this folder to open the new version.",
                         folder=target, name=path.name)
        if not task.stop.is_set() and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            message += "\n" + tr("Please open this location manually.")
        self.status.setText(message)

    def finish_on_exit(self):
        """Called by the main window after the ordinary save/discard prompt."""
        update = self._prepared
        if update is None:
            return True
        self._prepared = None
        try:
            if isinstance(update, PreparedMacUpdate):
                update.install_on_exit()
            else:
                schedule_portable_update(update)
        except (OSError, RuntimeError) as error:
            update.discard()
            self._controls(offer_download=True)
            self.status.setText(tr("Could not download or install the update.\n{error}", error=diagnostic_text(error)))
            self.show()
            self.raise_()
            return False
        return True

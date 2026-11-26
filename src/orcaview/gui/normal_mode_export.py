"""Render one selected ORCA vibrational mode as a looping GIF or an MP4 clip."""

import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox, QProgressDialog, QPushButton

from orcaview.gui.file_dialogs import suggested_file
from orcaview.i18n import diagnostic_text, tr
from orcaview.results.vibration_playback import AMPLITUDE_RANGE, SPEED_RANGE


FPS = 25  # Four centiseconds is exactly representable in GIF.
LONG_EDGE = 1280


class _ExportCanceled(Exception):
    pass


def save_mode_animation(viewport, path, *, amplitude, speed, phase=0., progress=None):
    """Stream frames from the current camera. Return False if the caller cancels."""
    from orcaview.gui.normal_mode_movie import write_movie

    target = Path(path)
    suffix = target.suffix.lower()
    if suffix not in (".gif", ".mp4"):
        raise ValueError(tr("Choose a GIF or MP4 filename."))
    if not (AMPLITUDE_RANGE[0] <= amplitude <= AMPLITUDE_RANGE[1] and
            SPEED_RANGE[0] <= speed <= SPEED_RANGE[1] and math.isfinite(phase)):
        raise ValueError(tr("Amplitude must be 0.01–1.00 Å and playback speed must be 0.1–3.0×."))
    if not viewport.has_exportable_structure() or viewport.size().isEmpty():
        raise ValueError(tr("Select a vibrational mode before exporting."))
    cycles = 1 if suffix == ".gif" else 3
    count = round(cycles * FPS / speed)
    width, height = viewport.width(), viewport.height()
    scale = LONG_EDGE / max(width, height)
    # Both H.264 chroma planes and GIF benefit from a fixed canvas per frame.
    size = tuple(max(2, 2 * round(value * scale / 2)) for value in (width, height))

    def update(done):
        if progress is not None and progress(done, count) is False:
            raise _ExportCanceled

    def frames():
        for index in range(count):
            update(index)
            distance = amplitude * math.sin(phase + math.tau * cycles * index / count)
            image = QImage(*size, QImage.Format.Format_RGB32)
            if image.isNull():
                raise OSError(tr("Could not allocate the animation frame."))
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            try:
                painter.translate((size[0] - width * scale) / 2, (size[1] - height * scale) / 2)
                painter.scale(scale, scale)
                viewport.paint_displacement(painter, distance)
            finally:
                painter.end()
            yield image

    try:
        with TemporaryDirectory(prefix=".orcaview-animation-", dir=target.parent) as directory:
            encoded = Path(directory) / ("animation" + suffix)
            write_movie(encoded, frames(), FPS)
            update(count)
            os.replace(encoded, target)
    except _ExportCanceled:
        return False
    return True


def export_animation_button(dialog):
    button = QPushButton(tr("Export animation…"))
    button.setAutoDefault(False)
    formats = QMenu(button)
    for ext, text in (("gif", tr("Animated GIF")), ("mp4", tr("MP4 video"))):
        formats.addAction(text).triggered.connect(lambda checked=False, ext=ext: _choose_file(dialog, ext))
    button.setMenu(formats)
    return button


def _choose_file(dialog, ext):
    group = dialog.groups[dialog.group_choice.currentIndex()]
    mode = group.modes[dialog.mode_table.currentRow()]
    name = f"mode-{mode.index}-{mode.frequency:.2f}cm-1"
    picker = QFileDialog(dialog, tr("Export animation…"))
    picker.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    picker.setNameFilter(f"{ext.upper()} (*.{ext})")
    picker.setDefaultSuffix(ext)
    picker.selectFile(suggested_file(dialog, name, "." + ext))
    try:
        if not picker.exec():
            return
        filename = Path(picker.selectedFiles()[0])
    finally:
        picker.deleteLater()
    if filename.suffix.lower() != "." + ext:
        QMessageBox.warning(dialog, tr("Export animation…"), tr("Use the selected .{ext} extension.", ext=ext))
        return
    progress = QProgressDialog(tr("Exporting animation…"), tr("Cancel"), 0, 100, dialog)
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setMinimumDuration(0)

    def advance(done, total):
        progress.setMaximum(total)
        progress.setValue(done)
        return not progress.wasCanceled()

    playing = dialog.play.isChecked()
    dialog.play.setChecked(False)
    try:
        save_mode_animation(dialog.viewport, filename, amplitude=dialog.amplitude.value(),
                            speed=dialog.speed.value(), phase=dialog._phase, progress=advance)
    except (OSError, ValueError) as exc:
        progress.close()
        QMessageBox.warning(dialog, tr("Export animation…"), diagnostic_text(exc))
    finally:
        progress.close()
        progress.deleteLater()
        dialog.play.setChecked(playing)

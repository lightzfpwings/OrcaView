"""Session-local starting locations for document dialogs."""

from pathlib import Path
import re

from PySide6.QtCore import QStandardPaths


def set_document_directory(widget, source):
    """Use the folder the user opened, including when the file is a symlink."""
    directory = str(Path(source).absolute().parent) if source else None
    widget.setProperty("documentDirectory", directory)


def document_directory(widget):
    while widget is not None:
        directory = widget.property("documentDirectory")
        if directory and Path(directory).is_dir():
            return Path(directory)
        widget = widget.parentWidget()
    desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    return Path(desktop) if desktop and Path(desktop).is_dir() else Path.home()


def suggested_file(widget, name, suffix):
    # A molecule title may contain a path separator or a Windows drive prefix.
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "molecule"
    return str(document_directory(widget) / (filename + suffix))

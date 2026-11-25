"""Personal GUI and CLI preferences with read-through for older desktop installations."""

import json
import os
from pathlib import Path
import sys

from orcaview.i18n import BASE_LOCALE
from orcaview.io.atomic_file import write_bytes


def data_directory():
    override = os.environ.get("ORCAVIEW_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / "OrcaView"


def read_preferences(group, defaults, settings=None):
    if settings is None:
        path = data_directory() / (group + ".json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if os.environ.get("ORCAVIEW_CONFIG_DIR"):
                return dict(defaults)
            try:
                from PySide6.QtCore import QSettings
            except (ImportError, OSError):
                return dict(defaults)
            settings = QSettings("OrcaView", "OrcaView")
        except (ValueError, UnicodeError):
            return dict(defaults)
        else:
            if not isinstance(data, dict):
                return dict(defaults)
            return {key: data[key] if isinstance(data.get(key), str) else value for key, value in defaults.items()}
    return {key: settings.value("interface/" + key, value, type=str) for key, value in defaults.items()}


def write_preferences(group, values, settings=None):
    if settings is not None:
        for key, value in values.items():
            settings.setValue("interface/" + key, value)
        settings.sync()
        if settings.status() != settings.Status.NoError:
            raise OSError("Could not save user preferences.")
        return
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(values, ensure_ascii=False) + "\n").encode("utf-8")
    write_bytes(directory / (group + ".json"), data)


def language_preferences(settings=None):
    return read_preferences("language", {"language": BASE_LOCALE,
                                         "languageDirectory": str(data_directory() / "languages")}, settings)

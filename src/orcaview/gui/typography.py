"""Desktop interface and fixed-width fonts used by the Qt workspaces."""

from string import Template
import sys

from PySide6.QtCore import QLocale
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
from PySide6.QtWidgets import QApplication


WINDOWS = sys.platform == "win32"

_CJK_FAMILIES = {
    QLocale.Script.SimplifiedHanScript: ("Microsoft YaHei UI", "Microsoft YaHei"),
    QLocale.Script.TraditionalHanScript: ("Microsoft JhengHei UI", "Microsoft JhengHei"),
    QLocale.Script.JapaneseScript: ("Yu Gothic UI", "Meiryo UI"),
}


def interface_font(locale):
    if not WINDOWS:
        return QFont("Arial", 12)
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    script = QLocale(locale).script()
    candidates = _CJK_FAMILIES.get(script, ())
    if not candidates:
        return font
    installed = {name.casefold(): name for name in QFontDatabase.families()}
    for name in candidates:
        family = installed.get(name.casefold())
        if family is None:
            continue
        font.setFamilies(list(dict.fromkeys([family, *font.families()])))
        font.setStyleName("")
        font.setWeight(QFont.Weight.Normal)
        if script != QLocale.Script.JapaneseScript and any(
            QFontDatabase.weight(family, face) == QFont.Weight.Light and not QFontDatabase.italic(family, face)
            for face in QFontDatabase.styles(family)
        ):
            font.setWeight(QFont.Weight.Light)
        break
    return font


def fixed_font():
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if WINDOWS:
        # A backend can return the generic "monospace" alias. A concrete
        # installed face must come before the proportional CJK fallback.
        for family in (QFontInfo(font).family(), "Consolas", "Courier New", "Cascadia Mono", "Liberation Mono"):
            if QFontDatabase.hasFamily(family) and QFontDatabase.isFixedPitch(family):
                font.setFamilies(list(dict.fromkeys([family, *QApplication.font().families()])))
                break
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setWeight(QFont.Weight.Normal)
    return font


def preview_font():
    return fixed_font() if WINDOWS else QFont("Menlo", 11)


def stylesheet(source):
    # Each workspace installs its own QSS. Resolve its weights at the point
    # of installation so a child stylesheet cannot reintroduce bold headings.
    return Template(source).substitute(
        heading_weight=400 if WINDOWS else 700,
        section_weight=400 if WINDOWS else 600,
        header_rule="QHeaderView { font-weight: 400; }" if WINDOWS else "",
        dock_family="" if WINDOWS else 'font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;',
    )

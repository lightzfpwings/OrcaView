"""Downloaded interface packs, persistent selection and scientific values."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orcaview.i18n import BASE_LOCALE, activate_language, diagnostic_text, discover_languages, tr


def write_pack(directory, filename, locale, name, messages):
    path = directory / filename
    path.write_text(json.dumps({"locale": locale, "name": name, "messages": messages},
                               ensure_ascii=False), encoding="utf-8")
    return path


class LanguagePacksTest(unittest.TestCase):
    def test_external_override_partial_fallback_and_template_safety(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundled, downloads = root / "bundled", root / "downloads"
            bundled.mkdir()
            downloads.mkdir()
            write_pack(bundled, "de.json", "de", "Deutsch", {"项目导航": "Projektnavigation", "结果": "Ergebnisse"})
            write_pack(downloads, "custom-name.json", "de", "Deutsch (lokal)",
                       {"结果": "Resultate", "{source} 的结果": "Resultate für {source}",
                        "{name} 需要整数": "{name} muss eine ganze Zahl sein"})
            bad = write_pack(downloads, "bad.json", "en", "English",
                             {"{source} 的结果": "Results for {source.__class__}"})
            packs, problems = discover_languages(downloads, bundled=bundled)
            self.assertEqual(problems, [str(bad)])
            self.assertEqual(set(packs), {BASE_LOCALE, "de"})
            self.addCleanup(activate_language, packs[BASE_LOCALE])
            activate_language(packs["de"])
            self.assertEqual(tr("结果"), "Resultate")
            self.assertEqual(tr("项目导航"), "Projektnavigation")
            self.assertEqual(tr("缺少的词条"), "缺少的词条")
            self.assertEqual(tr("{source} 的结果", source="结果.xyz"), "Resultate für 结果.xyz")
            self.assertEqual(diagnostic_text(ValueError("%scf.MaxIter 需要整数")),
                             "%scf.MaxIter muss eine ganze Zahl sein")


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QCoreApplication, QEvent, QSettings
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication, "Requires PySide6")
class LanguageSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_directory_refresh_persist_relaunch_and_remove(self):
        from orcaview.gui.language_settings import LanguageDialog, load_interface_language
        from orcaview.gui.main_window import MainWindow

        app = self.app
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            ini = str(directory / "config.ini")
            settings = QSettings(ini, QSettings.Format.IniFormat)
            settings.setValue("interface/languageDirectory", str(directory))
            load_interface_language(app, settings)
            win = MainWindow()
            original_text = win.input_preview.toPlainText()
            win.close()
            dialog = LanguageDialog(settings=settings)
            self.assertEqual(dialog.languages.currentData(), BASE_LOCALE)
            display_family = "Localized method family"
            from orcaview.core.methods import METHODS
            family = METHODS[win.session.calculation.method].family
            messages = {"项目导航": "My projects", "输入": "Input setup", "设计": "Molecule design",
                        "输入与结果": "Input and results", family: display_family}
            downloaded = write_pack(directory, "custom.json", "en-GB", "English (custom)", messages)
            dialog._refresh("en-GB")
            self.assertEqual(dialog.languages.currentData(), "en-GB")
            dialog.accept()
            loaded = QSettings(ini, QSettings.Format.IniFormat)
            self.assertEqual(load_interface_language(app, loaded), "en-GB")
            self.addCleanup(activate_language, discover_languages()[0][BASE_LOCALE])
            localized = MainWindow()
            self.assertEqual(localized.tree_dock.windowTitle(), "My projects")
            self.assertEqual(localized.workspace_tabs.tabText(0), "Input setup")
            self.assertEqual(localized.workspace_tabs.tabText(1), "Molecule design")
            self.assertEqual(localized.method_group.currentText(), display_family)
            self.assertEqual(localized.method_group.currentData(), family)
            self.assertEqual(localized.input_preview.toPlainText(), original_text)
            localized.tree.set_structure("项目导航")
            self.assertIn("项目导航", localized.tree.topLevelItem(0).child(0).text(0))
            localized.close()
            downloaded.unlink()
            self.assertEqual(load_interface_language(app, loaded), BASE_LOCALE)
            self.assertEqual(tr("项目导航"), "项目导航")
            for widget in (win, localized, dialog):
                widget.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()

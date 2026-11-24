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
    def test_chinese_requires_an_external_pack(self):
        packs, failures = discover_languages()
        self.assertEqual(list(packs), ["en"])
        self.assertFalse(failures)
        self.addCleanup(activate_language, packs["en"])
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            write_pack(folder, "zh-Hans.json", "zh-Hans", "简体中文", {"Plot settings…": "绘图设置…"})
            translated, failures = discover_languages(folder)
            self.assertFalse(failures)
            activate_language(translated["zh-Hans"])
            self.assertEqual(tr("Plot settings…"), "绘图设置…")
            self.assertEqual(tr("Untranslated option"), "Untranslated option")
        activate_language(discover_languages()[0]["en"])
        self.assertEqual(tr("Plot settings…"), "Plot settings…")

    def test_external_override_partial_fallback_and_template_safety(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundled, downloads = root / "bundled", root / "downloads"
            bundled.mkdir()
            downloads.mkdir()
            write_pack(bundled, "de.json", "de", "Deutsch", {"Project navigation": "Projektnavigation", "Result": "Ergebnisse"})
            write_pack(downloads, "custom-name.json", "de", "Deutsch (lokal)",
                       {"Result": "Resultate", "Results for {source}": "Resultate für {source}",
                        "{name} requires an integer": "{name} muss eine ganze Zahl sein"})
            bad = write_pack(downloads, "bad.json", "fr", "French",
                             {"Results for {source}": "Results for {source.__class__}"})
            packs, problems = discover_languages(downloads, bundled=bundled)
            self.assertEqual(problems, [str(bad)])
            self.assertEqual(set(packs), {BASE_LOCALE, "de"})
            self.addCleanup(activate_language, packs[BASE_LOCALE])
            activate_language(packs["de"])
            self.assertEqual(tr("Result"), "Resultate")
            self.assertEqual(tr("Project navigation"), "Projektnavigation")
            self.assertEqual(tr("Missing entry"), "Missing entry")
            self.assertEqual(tr("Results for {source}", source="结果.xyz"), "Resultate für 结果.xyz")
            self.assertEqual(diagnostic_text(ValueError("%scf.MaxIter requires an integer")),
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
            messages = {"Project navigation": "My projects", "Input": "Input setup", "Design": "Molecule design",
                        "Input and results": "Input and results", family: display_family}
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
            self.assertEqual(tr("Project navigation"), "Project navigation")
            for widget in (win, localized, dialog):
                widget.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()

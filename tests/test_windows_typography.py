"""Exercise Windows font selection and the text actually drawn by Qt widgets."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, QVariantAnimation
    from PySide6.QtGui import QFont, QFontDatabase, QTextLayout
    from PySide6.QtWidgets import QApplication, QLabel, QStyle, QStyleOptionTab
    from orcaview.gui import typography
    from orcaview.gui.main_window import MainWindow
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


@unittest.skipUnless(QApplication, "requires Qt")
class WindowsTypographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_windows_selects_installed_ui_family_for_the_interface_language(self):
        families = ["Microsoft YaHei UI", "Microsoft YaHei", "Microsoft JhengHei UI", "Yu Gothic UI"]
        with patch.object(typography, "WINDOWS", True), \
             patch.object(QFontDatabase, "families", return_value=families), \
             patch.object(QFontDatabase, "styles", return_value=["Regular", "Light"]), \
             patch.object(QFontDatabase, "italic", return_value=False), \
             patch.object(QFontDatabase, "weight", side_effect=lambda family, style:
                          QFont.Weight.Light if style == "Light" else QFont.Weight.Normal):
            for locale, family in (("zh-Hans", "Microsoft YaHei UI"),
                                   ("zh-Hant", "Microsoft JhengHei UI"), ("ja", "Yu Gothic UI")):
                with self.subTest(locale=locale):
                    font = typography.interface_font(locale)
                    self.assertEqual(font.families()[0], family)
                    if locale.startswith("zh"):
                        self.assertEqual(font.weight(), QFont.Weight.Light)

    def test_missing_light_face_and_missing_cjk_family(self):
        native = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        with patch.object(typography, "WINDOWS", True), \
             patch.object(QFontDatabase, "families", return_value=["Microsoft YaHei"]) as families, \
             patch.object(QFontDatabase, "styles", return_value=["Regular"]), \
             patch.object(QFontDatabase, "weight", return_value=QFont.Weight.Normal):
            font = typography.interface_font("zh-Hans")
            self.assertEqual(font.families()[0], "Microsoft YaHei")
            self.assertEqual(font.weight(), QFont.Weight.Normal)
            families.return_value = []
            self.assertEqual(typography.interface_font("zh-Hans").families()[0], native.families()[0])
            self.assertEqual(typography.interface_font("en").families()[0], native.families()[0])

    def test_other_platforms_keep_their_existing_interface_and_preview_fonts(self):
        with patch.object(typography, "WINDOWS", False):
            self.assertEqual(typography.interface_font("zh-Hans"), QFont("Arial", 12))
            self.assertEqual(typography.preview_font(), QFont("Menlo", 11))

    def test_windows_widgets_render_regular_headings_and_keep_wide_enough_tabs(self):
        with patch.object(typography, "WINDOWS", True):
            self.addCleanup(self.app.setFont, self.app.font())
            ui_font = typography.interface_font("zh-Hans")
            # The package normally selects YaHei on Windows. Use a real CJK
            # Light face when running this widget test on another desktop.
            if ui_font.weight() != QFont.Weight.Light:
                for family in ("PingFang SC", "Noto Sans CJK SC"):
                    if family in QFontDatabase.families() and "Light" in QFontDatabase.styles(family):
                        ui_font.setFamily(family)
                        break
                ui_font.setStyleName("")
                ui_font.setWeight(QFont.Weight.Light)
            self.app.setFont(ui_font)
            window = MainWindow()
            self.addCleanup(window.close)
            # The header image comparison needs the table to have settled
            # at its final width on both captures.
            for animation in window.columns.findChildren(QVariantAnimation):
                animation.setDuration(0)
            window.resize(window.minimumSize())
            window.show()
            self.app.processEvents()

            for control in (window.method, window.export_button, window.tabs.tabBar(),
                            window.workspace_tabs.tabBar()):
                self.assertEqual(control.font().weight(), QFont.Weight.Light)
            family = ui_font.families()[0]
            if "Light" in QFontDatabase.styles(family) and family in QFontDatabase.families(
                    QFontDatabase.WritingSystem.SimplifiedChinese):
                layout = QTextLayout("分子", window.tabs.tabBar().font())
                layout.beginLayout()
                layout.createLine()
                layout.endLayout()
                glyphs = layout.glyphRuns()[0].rawFont()
                self.assertEqual(glyphs.weight(), QFont.Weight.Light)
            self.assertEqual(window.method.font().families()[0], ui_font.families()[0])
            for page, name, size in ((window.input_page, "heading", 18),
                                     (window.design_panel, "designSection", 13),
                                     (window.foundation_panel, "foundationTitle", 22),
                                     (window.foundation_panel, "sectionTitle", 14)):
                with self.subTest(label=name):
                    window.workspace_tabs.setCurrentWidget(page)
                    self.app.processEvents()
                    label = page.findChild(QLabel, name)
                    self.assertTrue(label.isVisible())
                    self.assertEqual(label.font().weight(), QFont.Weight.Normal)
                    self.assertEqual(label.font().pixelSize(), size)

            # QHeaderView applies section QSS at paint time. header.font() alone
            # misses inherited bold sections as well as local table overrides.
            header = window.foundation_panel.atoms.horizontalHeader()
            self.assertTrue(header.isVisible())
            actual = header.grab().toImage()
            header.setStyleSheet("QHeaderView::section { font-weight: 400; }")
            self.app.processEvents()
            self.assertEqual(actual, header.grab().toImage())

            window.workspace_tabs.setCurrentWidget(window.input_page)
            self.app.processEvents()
            self.assertEqual(window.tree_dock.font().weight(), QFont.Weight.Normal)
            self.assertEqual(window.bottom_dock.titleBarWidget().height(), 0)
            self.assertEqual(window.tabs.tabBar().mapTo(window.bottom_dock, QPoint()).y(), 0)
            preview_metrics = window.input_preview.fontMetrics()
            self.assertEqual(preview_metrics.horizontalAdvance("iiiiiiii"),
                             preview_metrics.horizontalAdvance("WWWWWWWW"))
            self.assertEqual(window.input_preview.font().weight(), QFont.Weight.Normal)
            for bar in (window.workspace_tabs.tabBar(), window.tabs.tabBar()):
                for index in range(bar.count()):
                    with self.subTest(tab=bar.tabText(index)):
                        option = QStyleOptionTab()
                        bar.initStyleOption(option, index)
                        rect = bar.style().subElementRect(QStyle.SubElement.SE_TabBarTabText, option, bar)
                        self.assertGreaterEqual(rect.width(), option.fontMetrics.horizontalAdvance(bar.tabText(index)))
                        self.assertGreaterEqual(rect.height(), option.fontMetrics.height())


if __name__ == "__main__":
    unittest.main()

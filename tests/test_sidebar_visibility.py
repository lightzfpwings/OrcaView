"""Check workspace borders, native dock titles and scrollable content."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.main_window import MainWindow
    from orcaview.gui.typography import interface_font
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False
else:
    HAS_QT = True


@unittest.skipUnless(HAS_QT, "未安装可选 Qt 依赖")
class SidebarVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.addClassCleanup(cls.app.setFont, cls.app.font())
        cls.app.setFont(interface_font("zh-Hans"))

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.settle()
        self.addCleanup(self.window.close)

    def settle(self):
        for _ in range(4):
            self.app.processEvents()

    @staticmethod
    def title_ink_rows(dock):
        height = dock.widget().mapTo(dock, QPoint()).y()
        image = dock.grab(QRect(0, 0, 140, height)).toImage()
        ratio = image.devicePixelRatio()
        # Sample the title text beyond the native float icon on macOS.
        left = round(35 * ratio)
        right = round(130 * ratio)
        return sum(any(image.pixelColor(x, y).lightness() < 128 for x in range(left, right))
                   for y in range(image.height()))

    def test_titles_draw_the_full_height_of_their_chinese_glyphs(self):
        docks = (self.window.tree_dock, self.window.inspector_dock)
        displayed = [self.title_ink_rows(dock) for dock in docks]
        # Render the same native title at the same DPI with room for the
        # descenders. Its reference ink height accounts for platform fonts.
        for dock in docks:
            dock.setStyleSheet("QDockWidget::title { padding: 0 9px; }")
        self.settle()
        for actual, dock in zip(displayed, docks):
            reference = self.title_ink_rows(dock)
            self.assertGreater(reference, 5)
            self.assertGreaterEqual(actual, reference - 1, dock.windowTitle())

    def test_bottom_dock_starts_at_the_functional_tab_row(self):
        window = self.window
        dock = window.bottom_dock
        bar = window.tabs.tabBar()
        self.assertEqual(dock.windowTitle(), "输入与结果")
        self.assertIs(dock.widget(), window.tabs)
        self.assertEqual([bar.tabText(i) for i in range(bar.count())],
                         ["ORCA 输入预览", "结果摘要", "消息与日志"])
        for size in (window.size(), window.minimumSize()):
            window.resize(size)
            self.settle()
            with self.subTest(size=size):
                self.assertTrue(dock.isVisible() and bar.isVisible())
                self.assertEqual(dock.titleBarWidget().height(), 0)
                self.assertEqual(bar.mapTo(dock, bar.tabRect(0).topLeft()).y(), 0)

    def test_workspace_edges_meet_as_single_continuous_lines(self):
        window = self.window
        center = window.workspace_tabs.geometry()
        header = window.tree.mapTo(window, QPoint()).y() - 1
        bottom = window.bottom_dock.y() - 1
        image = window.grab().toImage()
        scale = image.devicePixelRatio()

        def color(x, y):
            return image.pixelColor(int((x + 0.5) * scale), int((y + 0.5) * scale))

        stroke = color(center.left() - 12, header)
        self.assertNotEqual(stroke, color(center.left() - 12, header - 1))
        for x in (center.left() - 1, center.right() + 1):
            for y in (header, bottom):
                with self.subTest(x=x, y=y):
                    for offset in range(-3, 4):
                        self.assertEqual(color(x + offset, y), stroke)
                    self.assertEqual(color(x, y - 1), stroke)
                    self.assertNotEqual(color(x - 1, y - 1), stroke)
                    self.assertNotEqual(color(x + 1, y - 1), stroke)
                    if y == header:
                        self.assertEqual(color(x, y + 1), stroke)
                        self.assertNotEqual(color(x - 1, y + 1), stroke)
                        self.assertNotEqual(color(x + 1, y + 1), stroke)

    def test_last_items_are_visible_when_both_short_sidebars_scroll_to_the_end(self):
        window = self.window
        window.resize(window.minimumSize())
        tree = window.tree
        tree.set_structure("长结构名称_Geometry_Relaxation_" * 60)
        window.block_options.toggle.click()
        window.block_options.groups["scf"].toggle.click()
        self.settle()
        scroll = window.inspector_dock.widget()
        for area in (scroll, tree):
            bar = area.verticalScrollBar()
            self.assertGreater(bar.maximum(), 0)
            bar.setValue(bar.maximum())
        self.settle()
        root = tree.topLevelItem(0)
        last = tree.indexFromItem(root.child(root.childCount() - 1))
        self.assertTrue(tree.viewport().rect().contains(tree.visualRect(last)))
        label = window.selection
        last_box = QRect(label.mapTo(scroll.viewport(), QPoint()), label.size())
        self.assertTrue(scroll.viewport().rect().contains(last_box))
        self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))

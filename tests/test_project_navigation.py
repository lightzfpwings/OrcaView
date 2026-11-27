"""Layout and native interaction of the project's navigation tree."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog, QStyle, QStyleOptionViewItem
    from orcaview.gui.main_window import MainWindow
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False
else:
    HAS_QT = True


@unittest.skipUnless(HAS_QT, 'Optional Qt dependency is not installed')
class ProjectNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.tree = self.window.tree
        self.addCleanup(self.window.close)
        self.app.processEvents()

    def test_opened_structure_name_reflows_without_indenting_children(self):
        name = "催化反应中间体过渡态结构优化" + "LongUnbrokenFileName" * 4 + "𠮷"
        with TemporaryDirectory() as folder:
            path = Path(folder) / (name + ".xyz")
            path.write_text("1\n\nHe 0 0 0\n")
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")):
                self.window.open_xyz()

        root = self.tree.topLevelItem(0)
        structure = root.child(0)
        raw = 'Structure  ·  ' + name
        self.assertEqual(structure.text(0), raw)
        heights = []
        for width in (160, 390, 160):
            self.window.tree_dock.setFixedWidth(width)
            for _ in range(3):
                self.app.processEvents()
            starts = []
            for item in (root, *(root.child(i) for i in range(root.childCount()))):
                index = self.tree.indexFromItem(item)
                option = QStyleOptionViewItem()
                self.tree.initViewItemOption(option)
                option.rect = self.tree.visualRect(index)
                self.tree.itemDelegateForIndex(index).initStyleOption(option, index)
                area = self.tree.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText,
                                                        option, self.tree)
                starts.append(area.left())
                self.assertEqual(item.toolTip(0), item.text(0))
                self.assertEqual(option.text.replace("\u2028", ""), item.text(0))
                for line in option.text.split("\u2028"):
                    self.assertLessEqual(option.fontMetrics.horizontalAdvance(line.rstrip()),
                                         area.width())
                self.assertLessEqual(option.rect.right(), self.tree.viewport().rect().right())
            self.assertEqual(len(set(starts)), 1)
            self.assertEqual(self.tree.horizontalScrollBar().maximum(), 0)
            heights.append(self.tree.visualItemRect(structure).height())
        self.assertGreater(heights[0], heights[1])
        self.assertEqual(heights[0], heights[2])

    def test_trailing_disclosure_and_keyboard_navigation(self):
        root = self.tree.topLevelItem(0)
        root_row = self.tree.visualRect(self.tree.indexFromItem(root))
        position = self.tree.columnViewportPosition(1) + self.tree.columnWidth(1) // 2
        arrow = QPoint(position, root_row.center().y())
        self.assertGreater(arrow.x(), root_row.right())
        QTest.mouseClick(self.tree.viewport(), Qt.MouseButton.LeftButton, pos=arrow)
        self.assertFalse(root.isExpanded())
        self.tree.setCurrentItem(root)
        QTest.keyClick(self.tree, Qt.Key.Key_Right)
        self.assertTrue(root.isExpanded())
        QTest.keyClick(self.tree, Qt.Key.Key_Down)
        self.assertEqual(self.tree.currentItem(), root.child(0))
        self.tree.setCurrentItem(root)
        QTest.keyClick(self.tree, Qt.Key.Key_Left)
        self.assertFalse(root.isExpanded())

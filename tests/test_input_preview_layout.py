"""Exercise the bottom input/output tabs at the actual workspace dock edges."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QKeySequence
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.main_window import MainWindow
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False
else:
    HAS_QT = True


@unittest.skipUnless(HAS_QT, 'Optional Qt dependency is not installed')
class InputPreviewLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.addCleanup(self.window.close)
        self.tabs = self.window.tabs
        self.bar = self.tabs.tabBar()
        self.settle()

    def settle(self):
        for _ in range(5):
            self.app.processEvents()

    def assert_dock_alignment(self):
        w = self.window
        expected = [widget.mapTo(w, QPoint()).x()
                    for widget in (w.tree_dock, w.workspace_tabs, w.inspector_dock)]
        starts = [self.bar.mapTo(w, self.bar.tabRect(i).topLeft()).x() for i in range(3)]
        self.assertEqual(starts, expected)
        right = self.bar.mapTo(w, self.bar.tabRect(2).topRight()).x()
        self.assertEqual(right, w.inspector_dock.geometry().right())

    def left_handle(self):
        rect = self.window.workspace_tabs.geometry()
        return QPoint(rect.left() - 1, rect.center().y())

    def test_tab_edges_follow_resize_drag_reset_and_workspace_switch(self):
        w = self.window
        for width, height in ((1440, 900), (1120, 780)):
            w.resize(width, height)
            self.settle()
            self.assert_dock_alignment()
        initial = w.tree_dock.width()
        start = self.left_handle()
        QTest.mouseMove(w, start)
        QTest.mousePress(w, Qt.MouseButton.LeftButton, pos=start)
        for distance in (15, 30, 50):
            moved = start + QPoint(distance, 0)
            QTest.mouseMove(w, moved)
            self.settle()
        QTest.mouseRelease(w, Qt.MouseButton.LeftButton, pos=moved)
        self.settle()
        self.assertGreater(w.tree_dock.width(), initial + 20)
        self.assert_dock_alignment()
        QTest.mouseDClick(w.windowHandle(), Qt.MouseButton.LeftButton, pos=self.left_handle())
        self.settle()
        self.assertAlmostEqual(w.tree_dock.width(), initial, delta=1)
        self.assert_dock_alignment()

        self.tabs.setCurrentWidget(w.output_summary)
        w.workspace_tabs.setCurrentWidget(w.foundation_panel)
        QTest.qWait(300)
        self.assertFalse(w.bottom_dock.isVisible())
        w.workspace_tabs.setCurrentIndex(0)
        QTest.qWait(300)
        self.assertTrue(w.bottom_dock.isVisible())
        self.assertIs(self.tabs.currentWidget(), w.output_summary)
        self.assert_dock_alignment()

    def test_float_redock_preserves_tabs_and_the_editable_input_preview(self):
        w = self.window
        pages = (w.input_preview, w.output_summary, w.log)
        texts = [p.toPlainText() for p in pages]
        self.assertIs(self.tabs.currentWidget(), w.input_preview)
        self.assertEqual(texts[0], w.session.input_text())
        for index, page in enumerate(pages):
            QTest.mouseClick(self.bar, Qt.MouseButton.LeftButton, pos=self.bar.tabRect(index).center())
            self.assertIs(self.tabs.currentWidget(), page)
            self.assertEqual(page.isReadOnly(), page is not w.input_preview)
        dock = w.bottom_dock
        dock.setFloating(True)
        dock.resize(901, 290)
        self.settle()
        self.assertTrue(dock.isFloating())
        self.assertIs(self.tabs.currentWidget(), w.log)
        widths = [self.bar.tabRect(i).width() for i in range(3)]
        self.assertLessEqual(max(widths) - min(widths), 1)
        self.assertEqual(sum(widths), self.tabs.width())
        dock.setFloating(False)
        self.settle()
        self.assertEqual(w.dockWidgetArea(dock), Qt.DockWidgetArea.BottomDockWidgetArea)
        self.assertIs(self.tabs.currentWidget(), w.log)
        self.assertEqual([p.toPlainText() for p in pages], texts)
        self.assert_dock_alignment()
        QTest.mouseClick(self.bar, Qt.MouseButton.LeftButton, pos=self.bar.tabRect(0).center())
        w.input_preview.setFocus()
        QTest.keySequence(w.input_preview, QKeySequence.StandardKey.SelectAll)
        self.assertTrue(w.input_preview.textCursor().hasSelection())
        QTest.keySequence(w.input_preview, QKeySequence.StandardKey.Copy)
        self.assertEqual(self.app.clipboard().text(), texts[0])
        QTest.keyClicks(w.input_preview, "xyz")
        self.assertEqual(w.input_preview.toPlainText(), "xyz")
        QTest.keyClick(w.input_preview, Qt.Key.Key_Escape)
        self.assertEqual(w.input_preview.toPlainText(), texts[0])

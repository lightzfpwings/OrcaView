"""Check the live structure workspace across resize, tab changes and docking."""

import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QAbstractAnimation, QPoint, Qt, QVariantAnimation
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDockWidget
    from orcaview.gui.main_window import MainWindow
    from orcaview.gui.result_import import read_native_session
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False
else:
    HAS_QT = True


@unittest.skipUnless(HAS_QT, "未安装可选 Qt 依赖")
class WorkspaceColumnsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        # Tests seek to explicit fractions. Allow Qt to process real layout events
        # between samples without the wall clock advancing the animation past them.
        self.window.columns.findChild(QVariantAnimation).setDuration(60_000)
        self.window.show()
        self.settle()
        self.addCleanup(self.window.close)

    def settle(self):
        # Resizes and page changes queue another Qt layout pass.
        for _ in range(4):
            self.app.processEvents()

    def panes(self):
        return (self.window.tree_dock, self.window.workspace_tabs, self.window.inspector_dock)

    def separator(self, side):
        left, middle, right = [widget.geometry() for widget in self.panes()]
        first, second = (left, middle) if side == "left" else (middle, right)
        return QPoint((first.right() + 1 + second.left()) // 2, middle.center().y())

    def separator_hit_point(self, side):
        point = self.separator(side)
        left, middle, right = [widget.geometry() for widget in self.panes()]
        gap = (middle.left() - left.right() - 1 if side == "left"
               else right.left() - middle.right() - 1)
        if self.app.platformName() == "cocoa" and gap == 1:
            # Test the outside edge of the native five-pixel resize handle.
            point += QPoint(-2 if side == "left" else 2, 0)
        return point

    def drag_separator(self, side, offset):
        start = self.separator(side)
        QTest.mouseMove(self.window, start)
        QTest.mousePress(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        for fraction in (.15, .5, 1):
            end = start + QPoint(round(offset * fraction), 0)
            QTest.mouseMove(self.window, end)
            self.settle()
        QTest.mouseRelease(self.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
        self.settle()

    def double_click(self, widget, point):
        QTest.mouseDClick(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        self.settle()

    def assert_proportions(self, weights):
        widths = [widget.width() for widget in self.panes()]
        for width, weight in zip(widths, weights):
            expected = sum(widths) * weight / sum(weights)
            self.assertAlmostEqual(width, expected, delta=2, msg=f"widths={widths}, ratio={weights}")

    def seek_transition(self, fraction, require_running=False):
        # Advance Qt's real animation deterministically without a machine-speed-dependent sleep.
        active = [animation for animation in self.window.columns.findChildren(QVariantAnimation)
                  if animation.state() == QAbstractAnimation.State.Running]
        if require_running:
            self.assertTrue(active, "Expected an active sidebar animation")
        for animation in active:
            forward = animation.direction() == QAbstractAnimation.Direction.Forward
            time_fraction = fraction if forward else 1 - fraction
            animation.setCurrentTime(round(animation.duration() * time_fraction))
        self.settle()

    def show_results(self):
        self.window.workspace_tabs.setCurrentWidget(self.window.foundation_panel)
        self.seek_transition(1)

    def show_structure(self):
        self.window.workspace_tabs.setCurrentIndex(0)
        self.seek_transition(1)

    def visit_results(self):
        self.show_results()
        self.show_structure()

    def test_imported_result_panes_follow_window_quarters(self):
        path = Path(__file__).resolve().parents[1] / "examples/m5_orca/water-sp.out"
        session = read_native_session(path)
        self.window.open_result_session(session, mark_dirty=False)
        self.seek_transition(1)
        panel = self.window.foundation_panel
        splitter = panel.geometry_pane.parentWidget()
        for width in (1120, 1280, 1440):
            self.window.resize(width, 900)
            self.settle()
            self.assert_proportions((1, 6, 1))
            sizes = splitter.sizes()
            self.assertLessEqual(max(sizes) - min(sizes), 1)
            for index in range(3):
                pane = splitter.widget(index)
                center = pane.mapTo(self.window, pane.rect().center()).x()
                self.assertAlmostEqual(center, width * (index + 1) / 4, delta=2)
            panel.set_log_report(session.log_report, standalone=True)
            self.settle()
            left, middle, right = splitter.sizes()
            self.assertEqual(middle, 0)
            self.assertAlmostEqual(left, right, delta=1)
            panel.set_log_report(session.log_report)
            self.settle()
            self.assertEqual(splitter.sizes(), sizes)

        # After a user drag, resizing honors their proportions.
        splitter.moveSplitter(sizes[0] + 55, 1)
        moved = splitter.sizes()
        self.assertGreater(moved[0], sizes[0] + 45)
        self.window.resize(1280, 800)
        self.settle()
        scaled = splitter.sizes()
        for old, new in zip(moved, scaled):
            self.assertAlmostEqual(old / sum(moved), new / sum(scaled), delta=0.005)

    def test_default_columns_and_headers_align_at_both_window_sizes(self):
        window = self.window
        for width, height in ((1440, 980), (1120, 780)):
            with self.subTest(width=width):
                window.resize(width, height)
                self.settle()
                self.assert_proportions((1, 2, 1))
                self.show_results()
                self.assertTrue(window.tree_dock.isVisible())
                self.assertTrue(window.inspector_dock.isVisible())
                self.assert_proportions((1, 6, 1))
                self.show_structure()
                self.assert_proportions((1, 2, 1))
                left, middle, right = [widget.geometry() for widget in self.panes()]
                for rect in (left, right):
                    self.assertAlmostEqual(rect.top(), middle.top(), delta=1)
                    self.assertAlmostEqual(rect.bottom(), middle.bottom(), delta=1)
                bottom = window.bottom_dock.geometry()
                self.assertGreater(bottom.top(), middle.bottom())
                self.assertEqual((bottom.left(), bottom.right()), (left.left(), right.right()))
                for widget in (window.tree_dock.widget(), window.inspector_dock.widget()):
                    top = widget.mapTo(window, QPoint()).y()
                    page_top = window.workspace_tabs.currentWidget().mapTo(window, QPoint()).y()
                    self.assertAlmostEqual(top, page_top, delta=2)
                bar = window.workspace_tabs.tabBar()
                first_tab = bar.mapTo(window.workspace_tabs, bar.tabRect(0).topLeft())
                self.assertLessEqual(abs(first_tab.x()), 12)

    def test_dragged_columns_survive_switching_pages_and_resizing(self):
        left, _, _ = self.panes()
        initial = left.width()
        self.drag_separator("left", 60)
        self.assertGreater(left.width() - initial, 25)
        custom = tuple(widget.width() for widget in self.panes())
        self.visit_results()
        self.assert_proportions(custom)
        self.window.resize(1320, 850)
        self.settle()
        self.assert_proportions(custom)

    def test_resize_while_in_history_restores_custom_structure_shares(self):
        self.drag_separator("left", 45)
        self.drag_separator("right", -30)
        structure_widths = tuple(pane.width() for pane in self.panes())
        self.show_results()
        self.assert_proportions((1, 6, 1))
        self.window.resize(self.window.minimumSize())
        self.settle()
        self.assert_proportions((1, 6, 1))
        self.show_structure()
        self.assert_proportions(structure_widths)

    def test_history_drag_and_double_click_are_local_to_the_current_visit(self):
        left, _, right = self.panes()
        self.drag_separator("left", 38)
        self.drag_separator("right", -25)
        structure_widths = tuple(pane.width() for pane in self.panes())
        for side, dock, other in (("left", left, right), ("right", right, left)):
            with self.subTest(reset_side=side):
                self.show_results()
                self.assert_proportions((1, 6, 1))
                eighth = sum(pane.width() for pane in self.panes()) / 8
                self.drag_separator("left", 40)
                self.drag_separator("right", -28)
                self.assertGreater(dock.width(), eighth + 15)
                self.assertGreater(other.width(), eighth + 15)
                other_width = other.width()
                self.double_click(self.window.windowHandle(), self.separator_hit_point(side))
                self.assertAlmostEqual(dock.width(), eighth, delta=2)
                self.assertAlmostEqual(other.width(), other_width, delta=1)
                self.show_structure()
                self.assert_proportions(structure_widths)
        self.show_results()
        self.assert_proportions((1, 6, 1))

    def test_animation_reverses_in_place_without_hiding_sidebars(self):
        window = self.window
        left, _, right = self.panes()
        self.drag_separator("left", 38)
        original = left.width(), right.width()
        compact = sum(pane.width() for pane in self.panes()) / 8
        visibility = []
        for dock in (left, right):
            dock.visibilityChanged.connect(visibility.append)

        window.workspace_tabs.setCurrentWidget(window.foundation_panel)
        self.seek_transition(.5, require_running=True)
        halfway = left.width(), right.width()
        for width, start in zip(halfway, original):
            self.assertGreater(width, compact + 2)
            self.assertLess(width, start - 2)

        window.workspace_tabs.setCurrentIndex(0)
        for dock, previous in zip((left, right), halfway):
            self.assertAlmostEqual(dock.width(), previous, delta=2)
        self.seek_transition(.65, require_running=True)
        for dock, previous, start in zip((left, right), halfway, original):
            self.assertGreater(dock.width(), previous)
            self.assertLess(dock.width(), start)

        self.show_results()
        self.assert_proportions((1, 6, 1))
        self.show_structure()
        for dock, start in zip((left, right), original):
            self.assertAlmostEqual(dock.width(), start, delta=2)
        self.assertNotIn(False, visibility)

    def test_double_click_restores_only_the_chosen_side(self):
        left, middle, right = self.panes()
        side_docks = {"left": left, "right": right}
        # Also reverse the order, so either side can be the first to reset.
        for size, sides in (((1440, 980), ("left", "right")),
                            ((1120, 780), ("right", "left"))):
            with self.subTest(size=size, first=sides[0]):
                self.window.resize(*size)
                self.settle()
                self.drag_separator("left", 45)
                self.drag_separator("right", -30)
                quarter = sum(widget.width() for widget in self.panes()) / 4
                for dock in side_docks.values():
                    self.assertGreater(dock.width() - quarter, 15)
                for side in sides:
                    dock = side_docks[side]
                    opposite = right if dock is left else left
                    opposite_width = opposite.width()
                    self.double_click(self.window.windowHandle(), self.separator_hit_point(side))
                    self.assertAlmostEqual(dock.width(), quarter, delta=2)
                    self.assertAlmostEqual(opposite.width(), opposite_width, delta=1)
                    self.assertAlmostEqual(middle.width(), 4 * quarter - dock.width() - opposite_width, delta=2)
                    restored = tuple(widget.width() for widget in self.panes())
                    self.visit_results()
                    self.assert_proportions(restored)
                self.assert_proportions((1, 2, 1))

    def test_reset_during_transition_leaves_opposite_edge_animating_across_resize(self):
        window = self.window
        left, _, right = self.panes()
        window.workspace_tabs.setCurrentWidget(window.foundation_panel)
        self.seek_transition(.4, require_running=True)
        self.double_click(window.windowHandle(), self.separator_hit_point("left"))
        total = sum(pane.width() for pane in self.panes())
        self.assertAlmostEqual(left.width(), total / 8, delta=2)
        self.assertGreater(right.width(), total / 8 + 5)
        window.resize(window.minimumSize())
        self.seek_transition(.65, require_running=True)
        total = sum(pane.width() for pane in self.panes())
        self.assertAlmostEqual(left.width(), total / 8, delta=2)
        self.assertGreater(right.width(), total / 8 + 5)
        self.seek_transition(1)
        self.assert_proportions((1, 6, 1))

    def test_viewport_double_click_preserves_zoom_and_columns(self):
        viewport = self.window.viewport
        self.drag_separator("left", 35)
        widths = tuple(widget.width() for widget in self.panes())
        viewport.zoom = 2
        self.double_click(viewport, viewport.rect().center())
        self.assertEqual(viewport.zoom, 2)
        self.assertEqual(tuple(widget.width() for widget in self.panes()), widths)

    def test_absent_separator_does_not_resize_hidden_or_floating_dock(self):
        left, _, right = self.panes()
        self.drag_separator("left", 35)
        self.drag_separator("right", -30)
        for side, floating, dock, other in (("left", True, left, right),
                                            ("right", False, right, left)):
            with self.subTest(side=side, floating=floating):
                old_separator = self.separator(side)
                if floating:
                    dock.setFloating(True)
                else:
                    dock.hide()
                self.settle()
                widths = dock.width(), other.width()
                self.double_click(self.window, old_separator)
                self.assertEqual((dock.width(), other.width()), widths)
                self.assertEqual(dock.isFloating(), floating)
                self.assertEqual(dock.isVisible(), floating)
                dock.setFloating(False)
                dock.show()
                self.settle()

    def test_project_navigation_can_float_and_redock(self):
        dock = self.window.tree_dock
        self.assertTrue(dock.features() & QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.assertTrue(dock.features() & QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        dock.setFloating(True)
        self.settle()
        self.assertTrue(dock.isFloating())
        self.visit_results()
        self.assertTrue(dock.isFloating())
        self.assertTrue(dock.isVisible())
        dock.setFloating(False)
        self.settle()
        self.assertFalse(dock.isFloating())
        self.assertEqual(self.window.dockWidgetArea(dock), Qt.DockWidgetArea.LeftDockWidgetArea)

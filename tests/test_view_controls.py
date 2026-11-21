"""Exercise the shared molecule camera through its toolbar and mouse gestures."""

import math
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QPushButton, QWidget
    from orcaview.gui.main_window import MainWindow
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    MainWindow = None


AXES = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def orientation(viewport):
    return tuple(viewport.camera_transform(*axis) for axis in AXES)


@unittest.skipIf(MainWindow is None, "requires Qt")
class ViewControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.close_window)
        self.views = (self.window.viewport, self.window.foundation_panel.viewport)

    def close_window(self):
        self.window.dirty = False
        self.window.close()

    def click(self, name):
        button = self.window.findChild(QPushButton, name)
        self.assertIsNotNone(button, name)
        self.assertTrue(button.isVisible(), name)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)

    def assert_vector(self, actual, expected):
        for observed, target in zip(actual, expected):
            self.assertAlmostEqual(observed, target, places=8)

    def test_rotation_buttons_show_distinct_icons_with_accessible_names(self):
        controls = self.window.findChild(QWidget, "rotationControls")
        buttons = controls.findChildren(QPushButton)
        self.assertEqual(len(buttons), 6)
        rendered = []
        names = set()
        for button in buttons:
            with self.subTest(button=button.objectName()):
                self.assertTrue(button.isVisible())
                self.assertEqual(button.text(), "")
                self.assertTrue(button.accessibleName().strip())
                self.assertTrue(button.toolTip().strip())
                self.assertNotIn(button.accessibleName(), names)
                names.add(button.accessibleName())
                image = button.icon().pixmap(button.iconSize()).toImage()
                self.assertFalse(image.isNull())
                self.assertGreater(len({image.pixel(x, y) for y in range(image.height())
                                        for x in range(image.width())}), 1)
                self.assertNotIn(image, rendered)
                rendered.append(image)

    def test_six_buttons_apply_typed_degrees_to_the_active_page(self):
        angle = self.window.findChild(QDoubleSpinBox, "rotationAngle")
        self.assertIsNotNone(angle)
        self.assertEqual(angle.value(), 15)
        self.assertIn("°", angle.suffix())
        angle.setFocus()
        angle.selectAll()
        QTest.keyClicks(angle, "22" + angle.locale().decimalPoint() + "5")
        QTest.keyClick(angle, Qt.Key.Key_Return)
        self.assertEqual(angle.value(), 22.5)

        sine, cosine = math.sin(math.pi / 8), math.cos(math.pi / 8)
        directions = (
            ("rotateLeft", AXES[2], (-sine, 0, cosine)),
            ("rotateRight", AXES[2], (sine, 0, cosine)),
            ("rotateForward", AXES[1], (0, cosine, sine)),
            ("rotateBackward", AXES[1], (0, cosine, -sine)),
            ("rotateUp", AXES[0], (cosine, sine, 0)),
            ("rotateDown", AXES[0], (cosine, -sine, 0)),
        )
        head = self.window.session.document.head
        preview = self.window.input_preview.toPlainText()
        pages = ((self.window.input_page, self.window.viewport),
                 (self.window.design_panel, self.window.design_panel.viewport),
                 (self.window.foundation_panel, self.window.foundation_panel.viewport))
        for page, viewport in pages:
            self.window.workspace_tabs.setCurrentWidget(page)
            self.app.processEvents()
            inactive = [(other, orientation(other)) for _, other in pages if other is not viewport]
            for name, probe, expected in directions:
                with self.subTest(page=page, button=name):
                    self.click("resetView")
                    self.click(name)
                    self.assert_vector(viewport.camera_transform(*probe), expected)
                    for other, expected_orientation in inactive:
                        self.assertEqual(orientation(other), expected_orientation)
        self.assertIs(self.window.session.document.head, head)
        self.assertEqual(self.window.input_preview.toPlainText(), preview)

    def test_rotations_compose_about_screen_axes(self):
        self.window.findChild(QDoubleSpinBox, "rotationAngle").setValue(90)
        self.click("rotateUp")
        viewport = self.views[0]
        image = viewport.grab().toImage().scaled(viewport.size())
        # The +x shaft is red. A quarter turn moves it above the triad origin.
        x, y = image.width() - 48, image.height() - 52 - 16
        color = image.pixelColor(x, y).getRgb()[:3]
        self.assertTrue(all(abs(a - b) < 50 for a, b in zip(color, (172, 83, 76))), color)
        self.click("resetView")
        # Local +z points right after yaw, then up after screen-plane roll.
        self.click("rotateRight")
        self.click("rotateUp")
        self.assert_vector(self.views[0].camera_transform(*AXES[2]), AXES[1])
        self.click("rotateDown")
        self.click("rotateLeft")
        for actual, expected in zip(orientation(self.views[0]), AXES):
            self.assert_vector(actual, expected)

    def test_drag_pan_pick_double_click_and_reset(self):
        viewport = self.views[0]
        head = self.window.session.document.head
        preview = self.window.input_preview.toPlainText()
        initial = tuple(viewport._projected)
        self.assertTrue(initial)
        anchor = viewport.rect().center()

        def drag(button, delta):
            QTest.mousePress(viewport, button, pos=anchor)
            QTest.mouseMove(viewport, anchor + delta)
            QTest.mouseRelease(viewport, button, pos=anchor + delta)
            viewport.repaint()

        drag(Qt.MouseButton.LeftButton, QPoint(36, 18))
        rotated = orientation(viewport)
        self.assertNotEqual(rotated, AXES)
        self.assertEqual(viewport.selected, [])
        rotated_positions = tuple(viewport._projected)
        shift = QPoint(39, -24)
        drag(Qt.MouseButton.RightButton, shift)
        self.assertEqual(orientation(viewport), rotated)
        self.assertEqual(viewport.selected, [])
        panned = tuple(viewport._projected)
        for (x, y, z, size), (old_x, old_y, old_z, old_size) in zip(panned, rotated_positions):
            self.assertAlmostEqual(x - old_x, shift.x())
            self.assertAlmostEqual(y - old_y, shift.y())
            self.assertEqual((z, size), (old_z, old_size))

        index = max(range(len(panned)), key=lambda i: panned[i][2])
        x, y = panned[index][:2]
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=QPoint(round(x), round(y)))
        self.assertEqual(viewport.selected, [index])
        QTest.mouseDClick(viewport, Qt.MouseButton.LeftButton, pos=anchor)
        viewport.repaint()
        self.assertEqual(orientation(viewport), rotated)
        self.assertEqual(tuple(viewport._projected), panned)

        self.click("resetView")
        viewport.repaint()
        self.assertEqual(orientation(viewport), AXES)
        self.assertEqual(tuple(viewport._projected), initial)
        self.assertIs(self.window.session.document.head, head)
        self.assertEqual(self.window.input_preview.toPlainText(), preview)

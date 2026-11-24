"""Headless checks of structure-only rendering, custom PDF pages and atomic writes."""

import os
from pathlib import Path
import re
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QPointF, QRectF, QSize, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPen
    from PySide6.QtWidgets import QApplication
    from orcaview.gui.structure_export import (
        MAX_CANVAS_DIMENSION, MAX_EXPORT_SCALE, capture_structure, paint_structure_canvas, save_structure_image,
        validate_structure_size,
    )
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    QApplication = None


class Drawing:
    def __init__(self):
        self.dimensions = QSize(80, 60)
        self.color = QColor("#ba3030")
        self.calls = 0

    def size(self):
        return self.dimensions

    def paint_structure(self, painter):
        self.calls += 1
        painter.fillRect(QRectF(30, 25, 20, 10), self.color)
        # An offscreen atom, a partially visible bond, and a natural text label.
        painter.fillRect(QRectF(-14, 0, 8, 6), Qt.GlobalColor.green)
        painter.fillRect(QRectF(75, 0, 15, 5), Qt.GlobalColor.blue)
        font = painter.font()
        font.setPixelSize(15)
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(QPointF(2, 55), "Cl₂")


class LabelAndBond:
    def size(self):
        return QSize(400, 120)

    def paint_structure(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#aa0000"), 3.0))
        painter.drawLine(QPointF(50, 45), QPointF(50, 75))
        font = painter.font()
        font.setPixelSize(15)
        painter.setFont(font)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(QPointF(104, 69), "Cl₂")


@unittest.skipUnless(QApplication, "Requires Qt")
class StructureExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.drawing = Drawing()

    def canvas(self, snapshot, width, height, dpi, *, scale=1):
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDotsPerMeterX(round(dpi / .0254))
        image.setDotsPerMeterY(round(dpi / .0254))
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            paint_structure_canvas(painter, snapshot, width, height, scale=scale)
        finally:
            painter.end()
        return image

    def test_snapshot_is_detached_and_compensates_output_dpi_for_shapes_and_text(self):
        snapshot = capture_structure(self.drawing)
        self.assertIs(capture_structure(snapshot), snapshot)
        self.drawing.color = QColor("yellow")
        self.drawing.dimensions.setWidth(160)
        snapshot.size().setWidth(200)
        self.assertEqual(snapshot.size(), QSize(80, 60))
        native = self.canvas(snapshot, 80, 60, 96)
        self.assertEqual(native.pixelColor(30, 25).name(), "#ba3030")
        self.assertTrue(any(native.pixelColor(x, y).alpha() > 100 for x in range(2, 27) for y in range(40, 57)))
        for dpi in (72, 144):
            other = self.canvas(snapshot, 80, 60, dpi)
            self.assertEqual(bytes(native.constBits()), bytes(other.constBits()))
        self.assertEqual(self.drawing.calls, 1)

    def test_png_centered_padding_and_crop_include_only_the_original_canvas(self):
        snapshot = capture_structure(self.drawing)
        images = []
        for width, height in ((80, 60), (120, 80), (40, 30), (121, 81), (41, 31)):
            path = self.root / f"canvas-{width}.png"
            self.assertIsNone(save_structure_image(snapshot, path, "PNG", width, height, True))
            image = QImage(str(path))
            self.assertEqual(image.size(), QSize(width, height))
            images.append(image)
        natural, padded, cropped, odd_padding, odd_crop = images
        self.assertEqual(natural, padded.copy(20, 10, 80, 60))
        self.assertEqual(cropped, natural.copy(20, 15, 40, 30))
        self.assertEqual(natural, odd_padding.copy(20, 10, 80, 60))
        self.assertEqual(odd_crop, natural.copy(20, 15, 41, 31))
        self.assertEqual(natural.pixelColor(79, 1), QColor("blue"))
        for x, y in ((10, 12), (100, 11), (0, 0), (119, 79)):
            self.assertEqual(padded.pixelColor(x, y).alpha(), 0)
        self.assertEqual(cropped.pixelColor(10, 10).name(), "#ba3030")
        self.assertEqual(cropped.pixelColor(9, 10).alpha(), 0)

    def test_opaque_raster_formats_store_density_and_bmp_is_uncompressed_24_bit(self):
        for fmt in ("png", "jpeg", "bmp"):
            path = self.root / fmt
            save_structure_image(self.drawing, path, fmt, 360, 240, transparent=fmt != "png", scale=3)
            image = QImage(str(path))
            self.assertEqual(image.size(), QSize(360, 240))
            self.assertAlmostEqual(image.dotsPerMeterX() * .0254, 288, delta=1)
            self.assertAlmostEqual(image.dotsPerMeterY() * .0254, 288, delta=1)
            self.assertEqual(image.pixelColor(1, 1), QColor("white"))
            self.assertGreater(image.pixelColor(180, 120).red(), image.pixelColor(180, 120).green() + 60)
            if fmt == "bmp":
                raw = path.read_bytes()
                self.assertEqual(raw[:2], b"BM")
                planes, bpp, compression = struct.unpack_from("<HHI", raw, 26)
                self.assertEqual((planes, bpp, compression), (1, 24, 0))

    def test_vector_scaling_draws_high_resolution_text_and_bonds_before_padding_or_crop(self):
        snapshot = capture_structure(LabelAndBond())
        images = []
        for width, height, scale in ((400, 120, 1), (1600, 480, 4), (1721, 545, 4), (1445, 435, 4)):
            path = self.root / f"vector-{width}.png"
            save_structure_image(snapshot, path, "PNG", width, height, True, scale=scale)
            image = QImage(str(path))
            self.assertEqual(image.size(), QSize(width, height))
            self.assertEqual(image.logicalDpiX(), 96 * scale)
            images.append(image)
        normal, large, padded, cropped = images
        self.assertEqual(large, padded.copy(60, 32, 1600, 480))
        self.assertEqual(cropped, large.copy(78, 23, 1445, 435))
        self.assertEqual(padded.pixelColor(59, 100).alpha(), 0)
        # A three-logical-pixel stroke is actually drawn twelve device pixels wide.
        self.assertEqual([x for x in range(190, 210) if large.pixelColor(x, 240).alpha() > 127],
                         list(range(194, 206)))
        base_text = normal.copy(100, 50, 35, 23)
        export_text = large.copy(400, 200, 140, 92)
        self.assertNotEqual(export_text, base_text.scaled(140, 92, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                        Qt.TransformationMode.FastTransformation))
        # Glyphs occupy the same logical area in a preview painted at a different DPI.
        preview_text = self.canvas(snapshot, 1600, 480, 72, scale=4).copy(400, 200, 140, 92)
        def ink_bounds(image):
            points = [(x, y) for y in range(image.height()) for x in range(image.width())
                      if image.pixelColor(x, y).alpha() > 127]
            return tuple(f(axis) for axis in zip(*points) for f in (min, max))

        small_bounds = ink_bounds(base_text)
        large_bounds = ink_bounds(export_text)
        self.assertEqual(ink_bounds(preview_text), large_bounds)
        for small, full in zip(small_bounds, large_bounds):
            self.assertAlmostEqual(full / 4, small, delta=2)

    def test_pdf_media_content_transparency_and_cross_reference_offsets(self):
        for transparent in (True, False):
            path = self.root / f"page-{transparent}.pdf"
            save_structure_image(self.drawing, path, "pdf", 101, 79, transparent)
            raw = path.read_bytes()
            for key in (b"MediaBox", b"TrimBox"):
                match = re.search(rb"/" + key + rb" \[0 0 ([\d.]+) ([\d.]+)\]", raw)
                self.assertEqual(tuple(map(float, match.groups())), (75.75, 59.25))
            self.assertNotIn(b"/Subtype /Image", raw)
            ref = re.search(rb"/Contents (\d+) 0 R", raw).group(1)
            stream = re.search(rb"^" + ref + rb" 0 obj\n.*?stream\r?\n(.*?)\r?\nendstream", raw, re.M | re.S)
            content = zlib.decompress(stream.group(1))
            self.assertIn(b"BT", content)  # Label is embedded text.
            # Native 20 x 10 shape, translated to the center of the custom page.
            self.assertRegex(content, rb"40 35 m\n60 35 l\n60 45 l|40 35 20 10 re")
            self.assertEqual(b"1 1 1 scn" in content, not transparent)
            offset = int(re.search(rb"startxref\s+(\d+)", raw).group(1))
            self.assertTrue(raw[offset:].startswith(b"xref"))
            entries = re.findall(rb"^(\d{10}) 00000 n", raw[offset:], re.M)
            self.assertGreater(len(entries), 3)
            for number, location in enumerate(entries, 1):
                self.assertTrue(raw[int(location):].startswith(f"{number} 0 obj".encode()))

    def test_pdf_keeps_print_dimensions_and_fractional_points_with_vector_text(self):
        for scale, width, height in ((1, 400, 120), (4, 1600, 480), (4, 1721, 545),
                                     (7, 36, 38), (7, 2811, 845), (MAX_EXPORT_SCALE, 3200, 960)):
            expected = (width * .75 / scale, height * .75 / scale)
            path = self.root / f"print-{width}.pdf"
            save_structure_image(LabelAndBond(), path, "PDF", width, height, True, scale=scale)
            raw = path.read_bytes()
            for key in (b"MediaBox", b"TrimBox"):
                match = re.search(rb"/" + key + rb" \[0 0 ([\d.]+) ([\d.]+)\]", raw)
                for dimension, points in zip(match.groups(), expected):
                    self.assertLessEqual(float(dimension), points)
                    self.assertAlmostEqual(float(dimension), points, delta=1e-6)
            self.assertNotIn(b"/Subtype /Image", raw)
            self.assertIn(b"/Type /Font", raw)
            offset = int(re.search(rb"startxref\s+(\d+)", raw).group(1))
            self.assertTrue(raw[offset:].startswith(b"xref"))
            entries = re.findall(rb"^(\d{10}) 00000 n", raw[offset:], re.M)
            for number, location in enumerate(entries, 1):
                self.assertTrue(raw[int(location):].startswith(f"{number} 0 obj".encode()))

    def test_invalid_sizes_formats_and_failed_writes_preserve_destination(self):
        target = self.root / "existing"
        target.write_bytes(b"keep me")
        for width, height, fmt in ((0, 1, "PNG"), (True, 20, "PDF"), (2.5, 90, "PNG"),
                                   (1, MAX_CANVAS_DIMENSION + 1, "PDF"), (8000, 8000, "BMP"), (5, 5, "SVG")):
            with self.subTest(width=width, height=height, fmt=fmt), self.assertRaises(ValueError):
                save_structure_image(self.drawing, target, fmt, width, height)
        for scale in (0, True, 2.5, MAX_EXPORT_SCALE + 1):
            with self.subTest(scale=scale), self.assertRaisesRegex(ValueError, "Image scale"):
                save_structure_image(self.drawing, target, "PNG", 6, 8, scale=scale)
        self.assertEqual(self.drawing.calls, 0)
        self.assertIsNone(validate_structure_size(8000, 8000, "PDF"))
        with patch("orcaview.gui.structure_export._write_pdf", side_effect=OSError("encode failure")):
            with self.assertRaisesRegex(OSError, "encode failure"):
                save_structure_image(self.drawing, target, "PDF", 10, 10)
        with self.assertRaises(OSError):
            save_structure_image(self.drawing, self.root / "missing" / "file.png", "PNG", 10, 10)
        self.assertEqual(target.read_bytes(), b"keep me")
        self.assertEqual(list(self.root.iterdir()), [target])

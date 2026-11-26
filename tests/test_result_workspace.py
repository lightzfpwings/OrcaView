"""Exercise result navigation through the desktop and the M5/M6 producer contracts."""

from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QLabel, QMessageBox
    from orcaview.application.project import save_project
    from orcaview.application.session import Session
    from orcaview.core.provenance import ArtifactRef, Provenance
    from orcaview.core.results import DatasetAxis, ResultDataset
    from orcaview.gui.main_window import MainWindow
    from orcaview.orca.log_properties import LogProperty
    from orcaview.orca.log_report import LogReport, parse_log_report
    from orcaview.orca.log_spectra import SpectrumTable
    HAS_QT = True
except ModuleNotFoundError as exc:
    if not (exc.name and exc.name.startswith("PySide6")):
        raise
    HAS_QT = False


NATIVE_SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "m5_orca" / "water-sp.out"


@unittest.skipUnless(HAS_QT, 'Optional Qt dependency is not installed')
class ResultWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.panel = self.window.foundation_panel
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self._close)

    def _close(self):
        self.window.dirty = False
        self.window.close()
        self.app.processEvents()

    def _wait_for(self, condition):
        deadline = time.monotonic() + 5
        while not condition():
            if time.monotonic() >= deadline:
                self.fail('Timed out waiting for desktop import')
            QTest.qWait(10)

    def _demo(self):
        self.window.load_analysis_demo()
        self.app.processEvents()
        document = self.window.session.document
        data = next(item for item in document.records()[1]
                    if item.method == "Hirshfeld" and item.values is not None)
        self.assertEqual(self.panel.selected_snapshot.ref, data.geometry)
        self.assertIs(self.window.workspace_tabs.currentWidget(), self.panel)
        return document, data

    def _row_ids(self):
        return [self.panel.atoms.item(row, 0).data(Qt.ItemDataRole.UserRole)
                for row in range(self.panel.atoms.rowCount())]

    def _source_files(self):
        lines = [line.split("  ", 1) for line in self.panel.evidence.toPlainText().splitlines()
                 if line.strip()]
        self.assertTrue(lines)
        self.assertEqual([line[0] for line in lines], ['File path', 'File type'] * (len(lines) // 2))
        return [(address[1], kind[1]) for address, kind in zip(lines[::2], lines[1::2])]

    def _choose_dataset(self, data):
        table = self.panel.datasets
        item = next(table.item(r, c) for r in range(table.rowCount()) for c in (0, 2)
                    if table.item(r, c).data(Qt.ItemDataRole.UserRole) == data.dataset_id)
        table.scrollToItem(item)
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, table.visualItemRect(item).center())
        self.app.processEvents()
        self.assertEqual(table.currentItem(), item)

    def _import_file(self, path):
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")):
            self.window.import_native_output()

    def test_source_details_for_xyz_without_the_original_file_after_reopening_project(self):
        with tempfile.TemporaryDirectory() as directory:
            xyz = Path(directory) / "water sample.xyz"
            xyz.write_text("3\nwater\nO 0 0 0\nH 0.76 0 0.59\nH -0.76 0 0.59\n", encoding="utf-8")
            project = Path(directory) / "sample.oview.json"
            expected = [(str(xyz.resolve()), 'XYZ coordinate file (.xyz)')]
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(xyz), "")):
                self.window.open_xyz()
            self.window.workspace_tabs.setCurrentWidget(self.panel)
            self.assertEqual(self.panel.title.text(), "water sample")
            self.assertEqual(self.window.heading.text(), "water sample")
            self.assertEqual(self._source_files(), expected)
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(project), "")):
                self.assertTrue(self.window.save_project_dialog())
            self.assertEqual(self.panel.title.text(), "sample")
            self.assertEqual(self.window.heading.text(), "sample")
            xyz.unlink()
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(project), "")):
                self.window.open_project()
            self.window.workspace_tabs.setCurrentWidget(self.panel)
            self.assertEqual(self._source_files(), expected)
            self.assertEqual(self.panel.title.text(), "sample")

    def test_sourceless_geometry_uses_the_project_file_once_reopened(self):
        self.window.workspace_tabs.setCurrentWidget(self.panel)
        self.assertEqual(self._source_files(), [('None', 'None')])
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "built in.oview.json"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(project), "")):
                self.assertTrue(self.window.save_project_dialog())
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(project), "")):
                self.window.open_project()
            self.window.workspace_tabs.setCurrentWidget(self.panel)
            (address, kind), = self._source_files()
            self.assertTrue(Path(address).is_absolute())
            self.assertTrue(project.samefile(address))
            self.assertIn("OrcaView", kind)
            self.assertIn('project', kind)

    def test_legacy_project_prefers_recorded_relative_xyz_path_to_the_project_container(self):
        recorded = "original structures/water.xyz"
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "legacy.oview.json"
            save_project(Session(source_path=recorded), project)
            self.assertEqual(json.loads(project.read_text(encoding="utf-8"))["schema_version"], 1)
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(project), "")):
                self.window.open_project()
            self.window.workspace_tabs.setCurrentWidget(self.panel)
            self.assertEqual(self._source_files(), [(recorded, 'XYZ coordinate file (.xyz)')])

    def test_file_report_spectra_and_property_history_do_not_claim_project_geometry(self):
        document, _ = self._demo()
        source = ArtifactRef.from_bytes(b"example", "orca-out", "/results/spectra.log")
        props = (LogProperty('Electronic energy', 'Final single-point energy', -75.5, "Eh", 17, 'Optimization step 1'),
                 LogProperty('Electronic energy', 'Final single-point energy', -76.0, "Eh", 43, 'Optimization step 2'),
                 LogProperty('Electric properties', 'Dipole moment', 0.0, "D", 47))
        nmr = SpectrumTable("nmr", 'NMR shielding', ('Atom', 'Shielding / ppm'),
                            (("1 C", 0.0), ("2 H", None)), 56)
        ir = SpectrumTable("ir", 'Infrared spectrum', ('Vibrational mode', 'Wavenumber / cm⁻¹', 'Intensity / km·mol⁻¹'),
                           ((1, 1595.0, 12.0),), 61)
        report = LogReport(source, props, (nmr, ir), 'Normal termination')
        self.panel.set_log_report(report, standalone=True)
        self.assertTrue(self.panel.geometry_pane.isHidden())
        self.assertEqual(self.panel.inspector_tabs.count(), 2)
        self.assertIsNone(self.panel.selection_context)
        self.assertEqual(self.panel.title.text(), "spectra")
        self.assertIsNone(self.panel.findChild(QLabel, "foundationBanner"))
        self.assertIn(report.status, self.panel.details.text())
        self.assertEqual(self.panel.datasets.rowCount(), 1)
        self.assertEqual([self.panel.datasets.item(0, col).text() for col in range(4)],
                         ['Final single-point energy', "-76.0 Eh", 'Dipole moment', "0.0 D"])
        model = self.panel.log_table.model()
        self.assertEqual(model.rowCount(), 2)
        self.assertEqual(model.data(model.index(0, 3)), "43")
        self.assertEqual(model.data(model.index(1, 0)), "-75.5")
        self.panel.spectra.setCurrentItem(self.panel.spectra.topLevelItem(0))
        self.assertEqual(model.headerData(1, Qt.Orientation.Horizontal), 'Shielding / ppm')
        self.assertEqual(model.data(model.index(0, 1)), "0.0")
        self.assertEqual(model.data(model.index(1, 1)), "—")
        self.assertEqual(self._source_files(), [(source.path_hint, 'ORCA log file (.log)')])
        self.panel.set_document(document)
        self.assertEqual(self.panel.table_title.text(), nmr.title)
        self.panel.spectra.setCurrentItem(self.panel.spectra.topLevelItem(1))
        self.panel.datasets.setCurrentItem(self.panel.datasets.item(0, 0))
        self.assertTrue(self.panel.spectrum_preview.isVisible())
        self.assertIn(ir.title, self.panel.spectrum_preview.toolTip())
        self.panel.view_geometry(document.head.ref)
        self.assertIs(self.panel.tables.currentWidget(), self.panel.log_table)
        self.panel.set_log_report(replace(report, spectra=()), standalone=True)
        self.assertEqual(self.panel.spectra.topLevelItemCount(), 0)
        self.assertTrue(self.panel.spectrum_preview.isHidden())
        self.panel.set_log_report(replace(report, properties=(), spectra=()), standalone=True)
        self.assertEqual(self._source_files(), [(source.path_hint, 'ORCA log file (.log)')])
        self.panel.set_document(type(document).restore(*document.records()))
        self.assertFalse(self.panel.geometry_pane.isHidden())
        self.assertEqual(self.panel.inspector_tabs.count(), 2)
        self.assertEqual(self.panel.title.text(), document.head.molecule.name)

    def test_same_file_energy_merges_by_source_line_and_keeps_atom_binding(self):
        original = self.window.session.document
        self._import_file(NATIVE_SAMPLE)
        self._wait_for(lambda: self.window.session.document is not original)
        document = self.window.session.document
        energy = next(d for d in document.records()[1] if d.kind == "energy")
        raw = NATIVE_SAMPLE.read_bytes()
        source = ArtifactRef.from_bytes(raw, "orca-out", str(NATIVE_SAMPLE))
        report = parse_log_report(raw.decode().splitlines(), source)
        self.panel.set_log_report(report)
        energy_rows = [self.panel.datasets.item(i, c) for i in range(self.panel.datasets.rowCount()) for c in (0, 2)
                       if f"{energy.values[0]} Eh" == self.panel.datasets.item(i, c + 1).text()]
        self.assertEqual(len(energy_rows), 1)
        self.assertEqual(energy_rows[0].data(Qt.ItemDataRole.UserRole), energy.dataset_id)
        self.panel.datasets.setCurrentItem(energy_rows[0])
        self.assertIn(dict(energy.provenance.parameters)["energy_line"], self.panel.details.text())
        self.assertEqual(self._source_files(), [(str(NATIVE_SAMPLE), 'ORCA output file (.out)')])
        self.assertEqual(self.panel.selected_snapshot.ref, energy.geometry)
        headers = [self.panel.atoms.horizontalHeaderItem(c).text() for c in range(self.panel.atoms.columnCount())]
        self.assertNotIn('Stable ID', headers)
        self.assertEqual(set(self._row_ids()), set(document.resolve(energy.geometry).atom_ids))

        head = document.head
        edited = document.publish_revision(head.ref, replace(head.molecule, name="edited"), head.atom_ids)
        self.panel.set_document(document)
        self.panel.view_geometry(edited.ref)
        dipole = LogProperty('Electric properties', 'Dipole moment', 1.53, "D", 65)
        self.panel.set_log_report(replace(report, properties=report.properties + (dipole,)))
        self.panel.view_geometry(edited.ref)
        self.panel.datasets.setCurrentItem(self.panel._series_items[1])
        self.assertEqual(self.panel.selected_snapshot.ref, energy.geometry)
        self.assertEqual(self._source_files(), [(str(NATIVE_SAMPLE), 'ORCA output file (.out)')])
        self.assertFalse(any('Revision' in label.text() for label in self.panel.geometry_pane.findChildren(QLabel)
                             if label.isVisible()))
        self.assertEqual(document.head.ref, edited.ref)
        original_details = self.panel.details.text()
        viewport = self.panel.viewport
        viewport.repaint()
        for x, y, _, _ in viewport._projected[:2]:
            QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=QPoint(round(x), round(y)))
        self.assertTrue(self.panel.bond_length.isVisible())
        self.assertEqual(self.panel.details.text(), original_details)

        other = ArtifactRef.from_bytes(b"different file", "orca-out", str(NATIVE_SAMPLE))
        self.panel.set_log_report(replace(report, source=other, properties=(dipole,)))
        self.assertTrue(self.panel.geometry_pane.isHidden())
        self.assertIsNone(self.panel.selection_context)
        self.assertFalse(self.panel.bond_length.isVisible())
        self.panel.view_geometry(edited.ref)
        self.assertFalse(self.panel.geometry_pane.isHidden())

    def test_log_lists_only_reported_populations(self):
        original = self.window.session.document
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "energy-only.out"
            raw = NATIVE_SAMPLE.read_text().replace("MULLIKEN ATOMIC CHARGES", "UNRELATED DATA")
            path.write_text(raw)
            self._import_file(path)
            self._wait_for(lambda: self.window.session.document is not original)
        datasets = self.window.session.document.records()[1]
        missing = next(d for d in datasets if d.kind == "mulliken-charge" and d.values is None)
        self.assertNotIn(missing.dataset_id, self.panel._dataset_items)
        self.panel.set_log_report(None)
        name = self.panel._dataset_items[missing.dataset_id]
        self.assertIn('All values missing', self.panel.datasets.item(name.row(), name.column() + 1).text())

    @contextmanager
    def _reading_in_background(self):
        from orcaview.gui.main_window import read_native_session

        started, release = Event(), Event()

        def delayed_reader(path):
            started.set()
            if not release.wait(timeout=5):
                raise TimeoutError('Timed out waiting for the test to release its background read')
            return read_native_session(path)

        with patch("orcaview.gui.main_window.read_native_session", side_effect=delayed_reader):
            try:
                self._import_file(NATIVE_SAMPLE)
                self._wait_for(started.is_set)
                self.assertFalse(self.window.import_action.isEnabled())
                yield
            finally:
                release.set()

    def test_import_m5_then_save_close_source_and_open_project_in_result_workspace(self):
        original = self.window.session.document
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "renamed.water.out"
            project = Path(directory) / "reopened.water.oview.json"
            source.write_bytes(NATIVE_SAMPLE.read_bytes())
            expected_files = [(str(source.resolve()), 'ORCA output file (.out)')]
            self._import_file(source)
            self._wait_for(lambda: self.window.session.document is not original)
            document = self.window.session.document
            by_kind = {d.kind: d for d in document.records()[1]}
            energy, charges = by_kind["energy"], by_kind["mulliken-charge"]
            self.assertEqual(by_kind["mulliken-electrons"].values, (8.42, .8, .78))
            self.assertEqual(energy.provenance.producer, "orcaview.orca.native-output")
            self.assertEqual(energy.values, (-76.123456789012,))
            self.assertIs(self.window.workspace_tabs.currentWidget(), self.panel)
            self._choose_dataset(energy)
            self.assertEqual(self.panel.title.text(), "renamed.water")
            self.assertIsNone(self.panel.findChild(QLabel, "foundationBanner"))
            self.assertIn(str(energy.values[0]), self.panel.details.text())
            self.assertIn("hartree", self.panel.details.text())
            self.assertIn('Synthetic', self.panel.details.text())
            self.assertEqual(self._source_files(), expected_files)
            frame = document.resolve(energy.geometry)
            self.assertIsNotNone(frame.ref.frame_id)
            self.assertEqual(self.panel.selected_snapshot, frame)
            self._choose_dataset(charges)
            self.assertEqual(self.panel.selected_snapshot.ref, charges.geometry)
            self.assertIn("Mulliken", self.panel.details.text())
            by_id = dict(zip(charges.axes[0].ids, charges.values))
            for row, atom_id in enumerate(self._row_ids()):
                self.assertEqual(float(self.panel.atoms.item(row, 2).text()), by_id[atom_id])

            expected = document.records()
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(project), "")):
                self.assertTrue(self.window.save_project_dialog())
            source.unlink()
            self.window.workspace_tabs.setCurrentIndex(0)
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(project), "")):
                self.window.open_project()
            reopened = self.window.session.document
            self.assertIsNot(reopened, document)
            self.assertEqual(reopened.records(), expected)
            self.assertIs(self.window.workspace_tabs.currentWidget(), self.panel)
            self._choose_dataset(reopened.dataset(charges.dataset_id))
            self.assertEqual(self.panel.title.text(), "reopened.water")
            self.assertEqual(self._source_files(), expected_files)
            self.assertEqual(self.panel.selected_snapshot, frame)
            self.assertFalse(self.window.dirty)

    def test_m6_partial_values_and_metadata_point_to_the_historical_frame(self):
        document, data = self._demo()
        frame = document.resolve(data.geometry)
        self.assertIsNotNone(frame.ref.frame_id)
        self.assertNotEqual(frame.atom_ids, document.head.atom_ids)
        self.assertNotEqual(frame.atom_ids, data.axes[0].ids)
        self.assertEqual(self.panel.viewport.molecule, frame.molecule)
        self.assertIn('Synthetic', self.panel.details.text())
        metadata = self.panel.details.text()
        for expected in (data.method, data.density, data.missing_reason, *data.quality):
            self.assertIn(expected, metadata)
        sources = self._source_files()
        self.assertCountEqual([path for path, _ in sources],
                              [parent.path_hint or 'Not recorded' for parent in data.provenance.parents])
        for path, kind in sources:
            self.assertIn("molden" if path.endswith(".molden") else "json", kind.lower())
        by_id = dict(zip(data.axes[0].ids, data.values))
        self.assertIn(0.0, by_id.values())
        self.assertIn(None, by_id.values())
        for row, atom_id in enumerate(self._row_ids()):
            cell = self.panel.atoms.item(row, 2).text()
            if by_id[atom_id] is None:
                self.assertIn('Missing', cell)
            else:
                self.assertEqual(float(cell), by_id[atom_id])

    def test_atom_headers_preserve_frame_order_and_selected_identity(self):
        document, partial = self._demo()
        frame = document.resolve(partial.geometry)
        axis = DatasetAxis("atom", frame.atom_ids[::-1])
        values = (2**60 + 1, 9, 2**60)
        data = ResultDataset("count", frame.ref, Provenance("fixture"), "int64", (3,), "1",
                             values, (axis,))
        document.add_dataset(data)
        self.panel.refresh_document()
        self._choose_dataset(data)
        table = self.panel.atoms
        header = table.horizontalHeader()
        self.assertFalse(header.isSortIndicatorShown())
        by_id = dict(zip(axis.ids, values))
        row = next(row for row, atom_id in enumerate(frame.atom_ids)
                   if frame.index_of(atom_id) != document.head.index_of(atom_id))
        table.selectRow(row)
        for column in range(table.columnCount()):
            table.scrollToItem(table.item(row, column))
            center = header.sectionViewportPosition(column) + header.sectionSize(column) // 2
            point = QPoint(center, header.height() // 2)
            self.assertTrue(header.viewport().rect().contains(point))
            for _ in range(2):
                QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=point)
                self.assertEqual(self._row_ids(), list(frame.atom_ids))
        self.assertEqual([table.item(i, 0).text() for i in range(table.rowCount())], ["1", "2", "3"])
        self.assertEqual([table.item(i, 2).text() for i in range(table.rowCount())],
                         [str(by_id[atom_id]) for atom_id in frame.atom_ids])
        self.assertEqual(self.panel.viewport.selected, [row])
        self.assertEqual(self.panel.selection_context.geometry, frame.ref)
        self.assertEqual(self.panel.selection_context.atom_ids, (frame.atom_ids[row],))
        self.assertEqual([item.row() for item in table.selectionModel().selectedRows()], [row])
        self.window.workspace_tabs.setCurrentIndex(0)
        self.window.workspace_tabs.setCurrentWidget(self.panel)
        self.panel.view_geometry(document.head.ref)
        self.assertEqual(self._row_ids(), list(document.head.atom_ids))
        self._choose_dataset(data)
        self.assertEqual(self._row_ids(), list(frame.atom_ids))
        table.clearSelection()
        self.panel.viewport.repaint()
        self.app.processEvents()
        x, y, _, _ = self.panel.viewport._projected[0]
        QTest.mouseClick(self.panel.viewport, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, QPoint(round(x), round(y)))
        selected_rows = self.panel.atoms.selectionModel().selectedRows()
        self.assertEqual([self._row_ids()[item.row()] for item in selected_rows], [frame.atom_ids[0]])

    def test_late_result_refresh_and_bad_reference_preserve_view_and_edit_head(self):
        document, data = self._demo()
        frame = document.resolve(data.geometry)
        head = document.head
        self.panel.atoms.selectRow(1)
        selected = self.panel.selection_context
        self.panel.viewport.yaw += 0.2
        yaw = self.panel.viewport.yaw
        late = ResultDataset("count", frame.ref, Provenance("fixture"), "int64", (), "1", (2,))
        document.add_dataset(late)
        self.panel.refresh_document()
        self.assertEqual(self.panel.selection_context, selected)
        self.assertEqual(self.panel.viewport.yaw, yaw)
        self.assertEqual(self.panel.selected_snapshot, frame)
        with self.assertRaises(ValueError):
            self.panel.view_geometry(replace(frame.ref, document_id="foreign-document"))
        with self.assertRaises(ValueError):
            self.panel.view_dataset("unknown-dataset")
        self.assertEqual(self.panel.selected_snapshot, frame)
        self.assertEqual(self.panel.selection_context, selected)
        self._choose_dataset(late)
        self.assertEqual(self.panel.selected_snapshot.ref, frame.ref)
        self.assertIs(document.head, head)
        self.assertEqual(self.window.viewport.molecule, head.molecule)

    def test_press_on_old_frame_cannot_pick_removed_atom_after_switch(self):
        document, data = self._demo()
        frame = document.resolve(data.geometry)
        shorter = next(snapshot for snapshot in document.records()[0] if len(snapshot.atom_ids) == 2)
        removed_index = len(frame.atom_ids) - 1
        self.assertNotIn(frame.atom_ids[removed_index], shorter.atom_ids)
        viewport = self.panel.viewport
        viewport.repaint()
        x, y, _, _ = viewport._projected[removed_index]
        old_point = QPoint(round(x), round(y))
        button = Qt.MouseButton.LeftButton
        modifiers = Qt.KeyboardModifier.NoModifier
        QTest.mousePress(viewport, button, modifiers, old_point)
        # Keep the release between switching geometry and the next paint event.
        viewport.setUpdatesEnabled(False)
        try:
            self.panel.view_geometry(shorter.ref)
            emitted = []
            viewport.selection_changed.connect(emitted.append)
            QTest.mouseRelease(viewport, button, modifiers, old_point)
            self.assertEqual(emitted, [])
            QTest.mouseClick(viewport, button, modifiers, old_point)
            self.assertFalse(any(emitted))
            self.assertEqual(self.panel.selection_context.atom_ids, ())
        finally:
            viewport.setUpdatesEnabled(True)
        viewport.repaint()
        x, y, _, _ = viewport._projected[1]
        QTest.mouseClick(viewport, button, modifiers, QPoint(round(x), round(y)))
        self.assertEqual(self.panel.selection_context.geometry, shorter.ref)
        self.assertEqual(self.panel.selection_context.atom_ids, (shorter.atom_ids[1],))

    def test_missing_entire_atom_payload_shows_reason_for_each_source_atom(self):
        document, partial = self._demo()
        whole = replace(partial, dataset_id="all-missing", values=None,
                        missing_reason='The synthetic example omits the full charge table')
        document.add_dataset(whole)
        self.panel.refresh_document()
        self._choose_dataset(whole)
        self.assertEqual(set(self._row_ids()), set(whole.axes[0].ids))
        for row in range(self.panel.atoms.rowCount()):
            self.assertIn('Missing', self.panel.atoms.item(row, 2).text())
        self.assertIn(whole.missing_reason, self.panel.details.text())

    def test_invalid_output_and_project_reference_leave_active_document_and_file_intact(self):
        original, partial = self._demo()
        before = original.records()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "sample.oview.json"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(project), "")):
                self.assertTrue(self.window.save_project_dialog())
            corrupted = json.loads(project.read_text(encoding="utf-8"))
            corrupted["document"]["datasets"][0]["geometry"]["document_id"] = "foreign"
            project.write_text(json.dumps(corrupted), encoding="utf-8")
            source_bytes = project.read_bytes()
            with patch.object(self.window, "_error") as error:
                with patch.object(QFileDialog, "getOpenFileName", return_value=(str(project), "")):
                    self.window.open_project()
                error.assert_called_once()
            self.assertEqual(project.read_bytes(), source_bytes)
            output = Path(directory) / "broken.out"
            incomplete = b"Program Version 6.1.1\n"
            output.write_bytes(incomplete)
            with patch.object(self.window, "_error") as error:
                self._import_file(output)
                self._wait_for(lambda: error.called)
            self.assertEqual(output.read_bytes(), incomplete)
        self.assertIs(self.window.session.document, original)
        self.assertEqual(original.records(), before)
        self.assertEqual(self.panel.selected_snapshot.ref, partial.geometry)

    def test_cancel_discard_preserves_edit_and_result_selection(self):
        document, data = self._demo()
        self.assertTrue(self.window.dirty)
        self.panel.atoms.selectRow(0)
        selected = self.panel.selection_context
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel) as dialog:
            self.window.load_foundation_demo()
            dialog.assert_called_once()
        self.assertIs(self.window.session.document, document)
        self.assertEqual(self.panel.selected_snapshot.ref, data.geometry)
        self.assertEqual(self.panel.selection_context, selected)
        self.assertTrue(self.window.dirty)

    def test_background_import_waits_for_confirmation_after_user_switches_document(self):
        with self._reading_in_background():
            document, data = self._demo()
            selected = self.panel.selected_snapshot
            self.assertEqual(selected.ref, data.geometry)
        self._wait_for(self.window.pending_result_button.isVisible)
        self.assertIs(self.window.session.document, document)
        self.assertEqual(self.panel.selected_snapshot, selected)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.window.pending_result_button.click()
        self.assertIs(self.window.session.document, document)
        self.assertTrue(self.window.pending_result_button.isVisible())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard):
            self.window.pending_result_button.click()
        self.assertIsNot(self.window.session.document, document)
        energy = next(item for item in self.window.session.document.records()[1] if item.kind == "energy")
        self.assertEqual(energy.provenance.producer, "orcaview.orca.native-output")
        self.assertEqual(self.panel.selected_snapshot.ref, energy.geometry)
        self.assertFalse(self.window.pending_result_button.isVisible())

    def test_cancel_background_import_discards_result_and_allows_new_read(self):
        original = self.window.session.document
        initial_records = original.records()
        with self._reading_in_background():
            self.assertTrue(self.window.cancel_read_button.isVisible())
            self.window.cancel_read_button.click()
        self._wait_for(self.window.import_action.isEnabled)
        self.assertIs(self.window.session.document, original)
        self.assertEqual(original.records(), initial_records)
        self.assertFalse(self.window.pending_result_button.isVisible())
        self._import_file(NATIVE_SAMPLE)
        self._wait_for(lambda: self.window.session.document is not original)

    def test_text_summary_stays_separate_from_the_active_geometry(self):
        original = self.window.session.document
        expected = original.records()
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(NATIVE_SAMPLE), "")):
            with patch.object(QInputDialog, "getItem", return_value=("SP", True)):
                self.window.open_output()
        self._wait_for(lambda: str(NATIVE_SAMPLE) in self.window.output_summary.toPlainText())
        self.assertIs(self.window.tabs.currentWidget(), self.window.output_summary)
        self.assertIn("-76.123456789012", self.window.output_summary.toPlainText())
        self.assertIs(self.window.session.document, original)
        self.assertEqual(original.records(), expected)
        self.assertFalse(self.window.dirty)

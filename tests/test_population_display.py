from dataclasses import replace
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orcaview.application.project import load_project, save_project
from orcaview.core.results import DatasetAxis
from orcaview.gui.result_import import read_native_session
from orcaview.orca._native_output import reported_geometry
from orcaview.orca.populations import population_columns
from orcaview.core.models import Molecule

ROOT = Path(__file__).resolve().parents[1]
OH = ROOT / "examples/populations/hydroxyl.out"


class PopulationImportTests(unittest.TestCase):
    def test_real_radical_populations_retain_distinct_quantities_sources_and_frame(self):
        session = read_native_session(OH)
        columns = [d for d in session.document.records()[1] if d.shape]
        by_kind = {d.kind: d for d in columns}
        self.assertEqual(len(by_kind), 13)
        self.assertEqual(len(columns), len(by_kind))
        self.assertEqual(by_kind["mulliken-electrons"].values, (8.1692, .8308))
        self.assertEqual(by_kind["mulliken-charge"].values, (-.169224, .169224))
        self.assertEqual(by_kind["mulliken-spin"].values, (1.024339, -.024339))
        self.assertEqual(by_kind["loewdin-electrons"].values, (8.059322, .940678))
        self.assertEqual(by_kind["mbis-electrons"].values, (8.357005, .642993))
        self.assertEqual(by_kind["chelpg-charge"].values, (-.358578, .358578))
        log = OH.read_text().splitlines()
        props = dict(by_kind["mulliken-electrons"].provenance.parameters)
        self.assertIn("NA", log[int(props["population_line"]) - 1])
        props = dict(by_kind["loewdin-electrons"].provenance.parameters)
        self.assertEqual(props["population_formula"], "ZA - q")
        self.assertIn("(A.U.)", log[int(props["nuclear_charge_line"]) - 1])
        with TemporaryDirectory() as tmp:
            project = Path(tmp, "radical.oview.json")
            save_project(session, project)
            saved = load_project(project)
            for d in columns:
                self.assertEqual(saved.document.dataset(d.dataset_id), d)
                self.assertEqual(saved.document.resolve(d.geometry).atom_ids, d.axes[0].ids)

    def test_absent_spin_damaged_tables_and_repeated_occurrences(self):
        ordinary = read_native_session(ROOT / "examples/m5_orca/water-sp.out")
        datasets = {d.kind: d for d in ordinary.document.records()[1]}
        self.assertNotIn("mulliken-spin", datasets)
        self.assertEqual(datasets["mulliken-electrons"].values, (8.42, .8, .78))
        raw = OH.read_text()
        start = raw.index("LOEWDIN ATOMIC CHARGES AND SPIN POPULATIONS")
        block = raw[start:raw.index("\n\n", start) + 2]
        raw = raw[:start] + block + raw[start:]
        raw = raw.replace("1 H    0.357007    0.642993", "2 H    0.357007    0.642993")
        with TemporaryDirectory() as tmp:
            path = Path(tmp, "broken.log")
            path.write_text(raw)
            records = read_native_session(path).document.records()[1]
        spins = [d for d in records if d.kind == "loewdin-spin"]
        self.assertEqual(len(spins), 2)
        self.assertEqual(len({dict(d.provenance.parameters)["population_series"] for d in spins}), 2)
        self.assertFalse(any(d.kind.startswith("mbis-") for d in records))

    def test_marked_ecp_nuclear_charge_determines_electron_count(self):
        text = """| 1> * xyz -1 1
CARTESIAN COORDINATES (ANGSTROEM)
---
I 0.000000 0.000000 0.000000

CARTESIAN COORDINATES (A.U.)
---
NO LB ZA FRAG MASS X Y Z
0 I 25.0000* 0 126.900 0.000000 0.000000 0.000000
* core charge reduced due to ECP

LOEWDIN ATOMIC CHARGES
---
0 I : -1.000000
"""
        atoms, charge, mult, line = reported_geometry(text)
        cols = population_columns(text.splitlines(), line, Molecule("iodide", atoms, charge=charge, multiplicity=mult))
        self.assertEqual({c.kind: c.values for c in cols}["loewdin-electrons"], (26.,))
        self.assertIsNone(reported_geometry(text.replace("25.0000*", "25.0000")))
        self.assertIsNone(reported_geometry(text.replace("core charge reduced due to ECP", "unverified")))


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    from orcaview.gui.foundation_panel import FoundationPanel
    from orcaview.gui.population_dialog import PopulationDialog
    from orcaview.gui.population_map import MISSING_COLOR, PALETTES, PopulationMap, PopulationStyle
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication, "Requires PySide6")
class PopulationDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.session = read_native_session(OH)
        self.data = next(d for d in self.session.document.records()[1] if d.kind == "mulliken-spin")
        self.frame = self.session.document.resolve(self.data.geometry)

    def test_signed_palette_endpoints_clipping_midpoint_reversal_and_missing_ids(self):
        for colors in PALETTES.values():
            style = PopulationStyle(colors=colors, range_mode="manual", lower=-.5, upper=.5)
            display = PopulationMap(self.data, self.frame, style)
            self.assertEqual(display.color(-12).name(), colors[0])
            self.assertEqual(display.color(12).name(), colors[-1])
            rev = PopulationMap(self.data, self.frame, replace(style, reverse=True))
            self.assertEqual(rev.color(-12), display.color(12))
        style = PopulationStyle(range_mode="symmetric")
        mapped = PopulationMap(self.data, self.frame, style)
        self.assertEqual((mapped.low, mapped.high), (-1.024339, 1.024339))
        self.assertEqual(mapped.color(0).name(), "#ffffff")
        manual = replace(style, range_mode="manual", lower=-.1, upper=1.2, midpoint=0.)
        self.assertEqual(PopulationMap(self.data, self.frame, manual).color(0).name(), "#ffffff")
        with self.assertRaises(ValueError):
            replace(manual, midpoint=-.2)
        ids = self.frame.atom_ids
        reordered = replace(self.data, axes=(DatasetAxis("atom", ids[::-1]),), values=self.data.values[::-1])
        self.assertEqual(PopulationMap(reordered, self.frame, style).values, mapped.values)
        subset = replace(self.data, shape=(1,), axes=(DatasetAxis("atom", (ids[1],)),), values=(0.,))
        sparse = PopulationMap(subset, self.frame, PopulationStyle())
        self.assertEqual((sparse.low, sparse.high, sparse.labels), (0., 0., ("—", "0.000")))
        self.assertEqual(sparse.colors, (MISSING_COLOR, QColor("#ffffff")))
        with self.assertRaises(ValueError):
            replace(style, range_mode="manual", lower=1, upper=1)

    def test_dialog_applies_or_restores_dataset_and_geometry_bound_display(self):
        panel = FoundationPanel()
        panel.set_document(self.session.document)
        panel.set_log_report(self.session.log_report)
        panel.view_dataset(self.data.dataset_id)
        self.assertEqual(panel.viewport.population_map.values, self.data.values)
        target = next(d for d in panel._populations if d.kind == "mbis-electrons")
        def edit(accept):
            dialog = QApplication.activeModalWidget()
            dialog.quantity.setCurrentIndex(dialog.quantity.findData(target.dataset_id))
            dialog.labels.setChecked(False)
            dialog.color_atoms.setChecked(True)
            dialog.palette.setCurrentIndex(dialog.palette.findData("Black–white"))
            dialog.range_mode.setCurrentIndex(dialog.range_mode.findData("manual"))
            dialog.lower.setValue(10)
            self.assertFalse(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
            dialog.lower.setValue(0)
            dialog.upper.setValue(9)
            self.assertEqual(panel.viewport.population_map.high, 9)
            if accept:
                dialog.accept()
            else:
                dialog.reject()
        for accept in (False, True):
            errors = []
            def interact():
                try:
                    edit(accept)
                except Exception as error:
                    errors.append(error)
                    QApplication.activeModalWidget().reject()
            QTimer.singleShot(0, interact)
            panel._configure_populations()
            if errors:
                raise errors[0]
            self.assertEqual(panel.viewport.population_map.values, target.values if accept else self.data.values)
        self.assertEqual(panel._dataset_id, target.dataset_id)
        self.assertTrue(panel.viewport.population_map.style.color_atoms)
        self.assertFalse(panel.viewport.population_map.style.labels)
        panel.view_geometry(self.session.document.head.ref)
        self.assertIsNone(panel.viewport.population_map)
        self.assertTrue(panel.population_button.isHidden())
        panel.close()

    def test_named_custom_palette_round_trip_and_manual_limits(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"ORCAVIEW_CONFIG_DIR": tmp}):
            dialog = PopulationDialog((self.data,), self.data.dataset_id, PopulationStyle())
            dialog.range_mode.setCurrentIndex(dialog.range_mode.findData("manual"))
            dialog.lower.setValue(-.25)
            dialog.upper.setValue(.75)
            dialog.use_midpoint.setChecked(True)
            dialog.midpoint.setValue(.1)
            with patch("orcaview.gui.population_dialog.QColorDialog.getColor", return_value=QColor("#238473")):
                dialog._edit_color(0)
            with patch("orcaview.gui.population_dialog.QInputDialog.getText", return_value=("OH", True)):
                dialog._save_preset()
            second = PopulationDialog((self.data,), self.data.dataset_id, PopulationStyle())
            second.palette.setCurrentIndex(second.palette.findData("saved/OH"))
            self.assertEqual((second.colors[0], second.lower.value(), second.upper.value()), ("#238473", -.25, .75))
            self.assertEqual(second.style_value().midpoint, .1)
            second.reject()
            dialog.reject()

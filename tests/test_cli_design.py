"""Design recipes use stable identities and publish only after the full recipe succeeds."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orcaview.application.project import load_project
from orcaview.cli import main


class DesignCliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.water = self.folder / "water.xyz"
        self.water.write_text("3\nwater\nO 0 0 0\nH .96 0 0\nH -.25 .93 0\n")
        self.project = self.folder / "saved.oview.json"

    def call(self, source, *flags, code=0, stdin=""):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(["design", str(source), *map(str, flags)])
        self.assertEqual(result, code, stderr.getvalue())
        if code:
            self.assertEqual(stdout.getvalue(), "")
            return stderr.getvalue()
        return json.loads(stdout.getvalue())

    def test_ordered_edits_measurement_selection_and_atomic_failure(self):
        steps = [
            {"op": "select", "atom_ids": [1, 2]},
            {"op": "set-bond-length", "target": 1.11},
            {"op": "undo"}, {"op": "redo"}, {"op": "measure"},
            {"op": "set-sketch-layout", "xy": [[2, 2], [3, 2], [2, 3]]},
            {"op": "move-sketch-atom", "atom_id": 2, "x": 3.3, "y": 2.2},
        ]
        report = self.call(self.water, "--script", "-", "-o", self.project, stdin=json.dumps(steps))
        self.assertEqual(report["selected_atom_ids"], [a["id"] for a in report["atoms"][:2]])
        self.assertAlmostEqual(report["operations"][4]["value"], 1.11)
        self.assertEqual(report["sketch_xy"][1], [3.3, 2.2])
        self.assertEqual(report["bond_source"], "stored")
        self.assertEqual(report["atoms"][1]["x"], 1.11)
        current = load_project(self.project).document.head
        self.assertEqual(list(current.atom_ids), [a["id"] for a in report["atoms"]])
        for bad in ({"op": "move-atom", "atom_id": 0, "x": 2, "y": 0, "z": 1},
                    {"op": "undo", "extra": 1}, {"op": "select", "atom_ids": ["missing"]}):
            before = self.project.read_bytes()
            error = self.call(self.project, "--apply", '{"op":"delete-atoms","atom_ids":[3]}',
                              "--apply", json.dumps(bad), "-o", self.project, code=2)
            self.assertIn("Design operation 2", error)
            self.assertEqual(self.project.read_bytes(), before)

    def test_project_stable_ids_and_result_geometry_across_invocations(self):
        report = self.call(self.water, "-o", self.project)
        oxygen, h1, h2 = [a["id"] for a in report["atoms"]]
        initial_ref = report["geometry"]["snapshot_id"]
        flags = [
            {"op": "reorder-atoms", "atom_ids": [h2, h1, oxygen]},
            {"op": "measure", "kind": "angle", "atom_ids": [2, oxygen, 1]},
            {"op": "use-geometry", "snapshot": initial_ref},
            {"op": "symmetry"}, {"op": "diagnostics"},
        ]
        report = self.call(self.project, "--script", "-", stdin=json.dumps(flags))
        self.assertGreater(report["operations"][1]["value"], 90.0)
        self.assertEqual(report["operations"][1]["unit"], "degree")
        self.assertEqual([a["id"] for a in report["atoms"]], [oxygen, h1, h2])
        self.assertEqual(report["operations"][3]["point_group"], "C2v")
        self.assertEqual(report["operations"][4]["issues"], [])

    def test_ring_auto_hydrogens_and_directed_bonds_without_display(self):
        atom = self.folder / "carbon.xyz"
        atom.write_text("1\ncarbon\nC 0 0 0\n")
        steps = [
            {"op": "delete-atoms", "atom_ids": [1]},
            {"op": "insert-ring", "size": 6, "benzene": True, "plane": "XY", "center": [0, 0, 0]},
            {"op": "add-hydrogens"},
            {"op": "set-bond", "atom_a": 7, "atom_b": 1, "order": 1, "style": "wedge"},
            {"op": "measure", "atom_ids": [1, 2]},
        ]
        recipe = self.folder / "recipe.json"
        recipe.write_text(json.dumps(steps))
        report = self.call(atom, "--script", recipe, "-o", self.project)
        self.assertEqual(len(report["atoms"]), 12)
        self.assertEqual(len(report["bonds"]), 12)
        self.assertIn({"a": 7, "b": 1, "order": 1, "style": "wedge"}, report["bonds"])
        self.assertAlmostEqual(report["operations"][-1]["value"], 1.4)
        self.assertEqual(len(report["operations"][2]["added_atom_ids"]), 6)

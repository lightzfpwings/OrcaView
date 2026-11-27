'Project persistence and session errors without Qt or ORCA.'

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orcaview.application.project import load_project, save_project
from orcaview.application.session import Session


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "project.oview.json"

    def test_roundtrip_retains_scientific_data(self):
        session = Session(source_path="/original/water.xyz")
        save_project(session, self.path)
        loaded = load_project(self.path)
        self.assertEqual(session.molecule, loaded.molecule)
        self.assertEqual(session.calculation, loaded.calculation)
        self.assertEqual(session.source_path, loaded.source_path)
        self.assertEqual(session.input_text(), loaded.input_text())

    def test_atomic_failure_preserves_existing_project(self):
        self.path.write_text("original evidence", encoding="utf-8")
        with patch("orcaview.application.project.os.replace", side_effect=OSError("simulated disk error")):
            with self.assertRaises(OSError):
                save_project(Session(), self.path)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "original evidence")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_future_schema_is_rejected(self):
        save_project(Session(), self.path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["schema_version"] = 999
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, 'version'):
            load_project(self.path)

    def test_unknown_nested_fields_are_not_silently_lost(self):
        save_project(Session(), self.path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["molecule"]["future_annotations"] = {"important": True}
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, 'unknown'):
            load_project(self.path)

    def test_failed_import_keeps_current_document(self):
        session = Session()
        original = session.molecule
        self.path.write_text("invalid xyz", encoding="utf-8")
        with self.assertRaises(ValueError):
            session.open_xyz(self.path)
        self.assertIs(session.molecule, original)


if __name__ == "__main__":
    unittest.main()

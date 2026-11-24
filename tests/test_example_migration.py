"""First run after an update performed by the a42 or a43 portable updater."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from orcaview.application import portable_replace as installer


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ExampleMigrationTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.install = Path(temp.name).resolve() / "OrcaView"
        self.examples = self.install / "Examples"
        self.examples.mkdir(parents=True)
        self.backup = self.install.with_name("OrcaView.previous")
        self.backup.mkdir()
        (self.backup / installer._BACKUP_MARK).write_text(json.dumps(str(self.install)))
        self.category = "Catégorie"  # stand-in for a formerly localized folder
        self.sample = "crystal.cif"

    def test_existing_linux_examples_merge_preserves_both_edits_and_runs_once(self):
        old_root = self.backup / installer._LEGACY_EXAMPLES
        old = old_root / self.category
        old.mkdir(parents=True)
        (old / self.sample).write_bytes(b"edit from legacy user")
        (old / "personal.xyz").write_bytes(b"personal")
        current = self.examples / "Structure-import"
        current.mkdir()
        (current / self.sample).write_bytes(b"existing independent edit")
        old_key = "/".join((old_root.name, self.category, self.sample))
        for root in (self.install, self.backup):
            (root / "python").mkdir()
        (self.backup / installer.MANIFEST).write_text(json.dumps({old_key: digest(b"stock 43")}))
        payload = {"Structure-import/" + self.sample: b"stock 44", "water.xyz": b"stock water"}
        seed = self.install / "python/orcaview-examples.zip"
        with zipfile.ZipFile(seed, "w") as z:
            for name, data in payload.items():
                z.writestr(name, data)
        inventory = {f"Examples/{key}": digest(value) for key, value in payload.items()}
        inventory["python/" + seed.name] = digest(seed.read_bytes())
        (self.install / installer.MANIFEST).write_text(json.dumps(inventory))

        installer.restore_examples_after_update(self.install, windows=False)
        self.assertEqual((current / self.sample).read_bytes(), b"existing independent edit")
        self.assertEqual((current / "personal.xyz").read_bytes(), b"personal")
        self.assertEqual((self.examples / "water.xyz").read_bytes(), b"stock water")
        recovered, = self.examples.glob("Recovered-*/Examples/Structure-import/crystal.cif")
        self.assertEqual(recovered.read_bytes(), b"edit from legacy user")
        self.assertTrue((old / self.sample).is_file())
        (self.examples / "water.xyz").unlink()
        installer.restore_examples_after_update(self.install, windows=False)
        self.assertFalse((self.examples / "water.xyz").exists())

    def test_windows_migration_avoids_linked_directories_outside_the_install(self):
        source = self.examples / self.category
        source.mkdir()
        (source / self.sample).write_bytes(b"modified")
        outside = self.install.parent / "outside"
        outside.mkdir()
        (outside / self.sample).write_bytes(b"keep")
        try:
            (self.examples / "Structure-import").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Directory symlinks unavailable")
        old = {f"Examples/{self.category}/{self.sample}": digest(b"old")}
        new = {f"Examples/Structure-import/{self.sample}": digest(b"new")}
        with patch.object(installer, "windows_inventory", side_effect=[new, old]):
            installer.restore_examples_after_update(self.install, windows=True)
        self.assertEqual((outside / self.sample).read_bytes(), b"keep")
        self.assertFalse(source.exists())
        recovered, = self.examples.glob("Recovered-*/Structure-import/crystal.cif")
        self.assertEqual(recovered.read_bytes(), b"modified")

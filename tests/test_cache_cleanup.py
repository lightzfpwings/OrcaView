import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import orcaview


SCRIPT = Path(orcaview.__file__).resolve().parents[2] / "tools/clean_cache.py"
FINDER = bytes.fromhex("0000000142756431") + bytes(64)


@unittest.skipUnless(hasattr(os, "fwalk") and hasattr(os, "O_NOFOLLOW"), "POSIX directory descriptors")
class CacheCleanupTests(unittest.TestCase):
    def test_preview_apply_and_protected_paths(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "checkout"
            root.mkdir()
            subprocess.run(["git", "init", "-q", root], check=True)
            script = root / "tools/clean_cache.py"
            script.parent.mkdir()
            shutil.copyfile(SCRIPT, script)
            def run(*args):
                return subprocess.check_output([sys.executable, "-B", script, *args], cwd=temp, text=True)

            def write(path, content):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                return path

            source = write(root / "src/main.py", b"x = 1\n")
            gone = write(root / "src/deleted.py", b"y = 2\n")
            marked = write(root / "tests/.DS_Store", FINDER)
            for folder in ["src/nested", "src/swapped", "src/Some.app", "src/artifacts",
                           "dist", "artifacts", ".venv"]:
                write(root / folder / "keep.py", b"")
            subprocess.run(["git", "-C", root, "add", "-f", "."], check=True)
            (root / "src/nested/.git").write_text("gitdir: elsewhere\n")
            outside = Path(temp) / "unrelated"
            (root / "src/swapped").rename(outside)
            (root / "src/swapped").symlink_to(outside, target_is_directory=True)

            kept = [marked, write(outside / ".DS_Store", FINDER), write(root / "tools/.DS_Store", b"")]
            for folder in ["dist", "artifacts", ".venv", "src/nested", "src/Some.app",
                           "src/artifacts", "src/personal", ".git"]:
                kept.append(write(root / folder / ".DS_Store", FINDER))
            orphan = Path(py_compile.compile(str(gone), doraise=True))
            gone.unlink()
            kept.append(orphan)
            removed = [write(root / ".DS_Store", FINDER), Path(py_compile.compile(str(source), doraise=True))]
            link = root / "src/.DS_Store"
            link.symlink_to(kept[1])
            first = run()
            self.assertIn("2 file(s) eligible (preview)", first)
            self.assertTrue(all(p.is_file() for p in removed))
            self.assertIn("2 file(s) removed", run("--apply"))
            self.assertTrue(all(not p.exists() for p in removed))
            self.assertTrue(all(p.is_file() for p in kept))
            self.assertTrue(link.is_symlink())
            self.assertIn("0 file(s) removed", run("--apply"))

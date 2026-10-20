"""Tests for install.py --uninstall."""

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import install as install_mod  # noqa: E402


class TestRemoveSkill(unittest.TestCase):
    """Directory removal guards."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name) / "dest"
        self.dest.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_nothing_installed(self):
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertFalse(install_mod.remove_skill(self.dest, False))

    def test_removes_installed_skill(self):
        target = self.dest / "complete-codebase-review"
        target.mkdir()
        (target / "SKILL.md").write_text("x", encoding="utf-8")
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(install_mod.remove_skill(self.dest, False))
        self.assertFalse(target.exists())

    def test_dry_run_keeps_skill(self):
        target = self.dest / "complete-codebase-review"
        target.mkdir()
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(install_mod.remove_skill(self.dest, True))
        self.assertTrue(target.exists())

    def test_removes_plain_file(self):
        target = self.dest / "complete-codebase-review"
        target.write_text("x", encoding="utf-8")
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(install_mod.remove_skill(self.dest, False))
        self.assertFalse(target.exists())


class TestRunUninstall(unittest.TestCase):
    """The --target flow removes only the skill directory."""

    def test_target_uninstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "complete-codebase-review"
            skill.mkdir()
            (skill / "SKILL.md").write_text("x", encoding="utf-8")
            keep = root / "keep.txt"
            keep.write_text("keep", encoding="utf-8")
            with patch("sys.stdout", new_callable=io.StringIO):
                code = install_mod._run_uninstall(str(root), False)
            self.assertEqual(code, 0)
            self.assertFalse(skill.exists())
            self.assertTrue(keep.exists())

    def test_target_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "complete-codebase-review"
            skill.mkdir()
            with patch("sys.stdout", new_callable=io.StringIO):
                code = install_mod._run_uninstall(str(root), True)
            self.assertEqual(code, 0)
            self.assertTrue(skill.exists())

    def test_nothing_to_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("sys.stdout", new_callable=io.StringIO):
                code = install_mod._run_uninstall(tmp, False)
            self.assertEqual(code, 0)

    def test_help_lists_uninstall(self):
        with patch("sys.argv", ["install.py", "--help"]), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            with self.assertRaises(SystemExit):
                install_mod.main()
            self.assertIn("--uninstall", out.getvalue())


if __name__ == "__main__":
    unittest.main()

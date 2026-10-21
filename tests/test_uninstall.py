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

    def test_failure_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "tool" / "skills"
            target.parent.mkdir(parents=True)
            with patch.object(
                install_mod, "get_target_dirs", return_value={"Tool": target}
            ), patch.object(
                install_mod, "remove_skill", side_effect=OSError("denied")
            ), patch("sys.stdout", new_callable=io.StringIO):
                code = install_mod._run_uninstall(None, False)
            self.assertEqual(code, 1)

    def test_local_skills_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".skills" / "complete-codebase-review"
            skill.mkdir(parents=True)
            with patch.object(install_mod.Path, "cwd", return_value=root), \
                 patch.object(
                     install_mod, "get_target_dirs", return_value={}
                 ), patch("sys.stdout", new_callable=io.StringIO):
                code = install_mod._run_uninstall(None, False)
            self.assertEqual(code, 0)
            self.assertFalse(skill.exists())

    def test_help_lists_uninstall(self):
        with patch("sys.argv", ["install.py", "--help"]), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            with self.assertRaises(SystemExit):
                install_mod.main()
            self.assertIn("--uninstall", out.getvalue())


@unittest.skipUnless(sys.platform == "win32", "junctions are Windows-only")
class TestJunctionSelfReference(unittest.TestCase):
    """A junction at the skill path must never delete the target root."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name) / "dest"
        self.dest.mkdir()
        self.keep = self.dest / "other-skill"
        self.keep.mkdir()
        (self.keep / "keep.txt").write_text("keep", encoding="utf-8")
        self.link = self.dest / "complete-codebase-review"
        import subprocess
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(self.link), str(self.dest)],
            check=True, capture_output=True,
        )

    def tearDown(self):
        if self.link.exists() and install_mod._is_link_like(self.link):
            install_mod._remove_link_like(self.link)
        self.tmp.cleanup()

    def test_is_link_like_detects_junction(self):
        self.assertTrue(install_mod._is_link_like(self.link))

    def test_remove_skill_unlinks_without_touching_root(self):
        with patch("sys.stdout", new_callable=io.StringIO):
            removed = install_mod.remove_skill(self.dest, False)
        self.assertTrue(removed)
        self.assertTrue((self.keep / "keep.txt").exists())
        self.assertFalse(self.link.exists())


if __name__ == "__main__":
    unittest.main()

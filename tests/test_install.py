"""Unit tests for install.py."""
import io
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import install


_ARGV_PATCH = ["install.py"]


class TestGetTargetDirs(unittest.TestCase):
    """Tests for get_target_dirs()."""

    def test_returns_dict_with_expected_keys(self):
        dirs = install.get_target_dirs()
        expected_keys = {"Claude Code", "OpenCode", "Cursor", "Continue"}
        self.assertEqual(set(dirs.keys()), expected_keys)

    def test_values_are_path_instances(self):
        dirs = install.get_target_dirs()
        for name, path in dirs.items():
            with self.subTest(agent=name):
                self.assertIsInstance(path, Path)

    def test_paths_are_under_home(self):
        home = Path.home()
        with patch("install.platform.system", return_value="Darwin"):
            dirs = install.get_target_dirs()
        expected = {
            "Claude Code": home / ".claude" / "skills",
            "OpenCode": home / ".opencode" / "skills",
            "Cursor": home / ".cursor" / "skills",
            "Continue": home / ".continue" / "skills",
        }
        self.assertEqual(dirs, expected)

    def test_claude_code_uses_xdg_on_linux(self):
        with (
            patch("install.platform.system", return_value="Linux"),
            patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/xdg"}),
        ):
            dirs = install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], Path("/custom/xdg/claude/skills"))

    def test_claude_code_uses_default_xdg_when_env_unset_on_linux(self):
        env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
        with (
            patch("install.platform.system", return_value="Linux"),
            patch.dict(os.environ, env, clear=True),
        ):
            dirs = install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], Path.home() / ".config" / "claude" / "skills")

    def test_claude_code_uses_default_xdg_when_env_empty_on_linux(self):
        env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
        env["XDG_CONFIG_HOME"] = ""
        with (
            patch("install.platform.system", return_value="Linux"),
            patch.dict(os.environ, env, clear=True),
        ):
            dirs = install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], Path.home() / ".config" / "claude" / "skills")

    def test_claude_code_uses_dot_claude_on_non_linux(self):
        with patch("install.platform.system", return_value="Darwin"):
            dirs = install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], Path.home() / ".claude" / "skills")


class TestCopySkill(unittest.TestCase):
    """Tests for copy_skill()."""

    def setUp(self):
        self.src = Path("/fake/src")
        self.dest = Path("/fake/dest")
        self.skill_dest = self.dest / "complete-codebase-review"

    @patch("install.shutil.copytree")
    @patch("install.shutil.rmtree")
    def test_creates_dest_dir_when_missing(self, mock_rmtree, mock_copytree):
        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "mkdir") as mock_mkdir,
        ):
            result = install.copy_skill(self.src, self.dest)

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        self.assertEqual(result, self.skill_dest)

    @patch("install.shutil.copytree")
    @patch("install.shutil.rmtree")
    def test_removes_existing_skill_dir(self, mock_rmtree, mock_copytree):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "mkdir"),
            patch.object(Path, "is_dir", return_value=True),
        ):
            install.copy_skill(self.src, self.dest)

        mock_rmtree.assert_called_once_with(self.skill_dest)

    @patch("install.shutil.copytree")
    @patch("install.shutil.rmtree")
    def test_removes_existing_skill_file(self, mock_rmtree, mock_copytree):
        unlink = MagicMock()
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "mkdir"),
            patch.object(Path, "is_dir", return_value=False),
            patch.object(Path, "unlink", unlink),
        ):
            install.copy_skill(self.src, self.dest)

        unlink.assert_called_once_with()

    @patch("install.shutil.copytree")
    @patch("install.shutil.rmtree")
    def test_calls_copytree_with_ignore_patterns(self, mock_rmtree, mock_copytree):
        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "mkdir"),
        ):
            install.copy_skill(self.src, self.dest)

        mock_copytree.assert_called_once()
        args, kwargs = mock_copytree.call_args
        self.assertEqual(args[0], self.src)
        self.assertEqual(args[1], self.skill_dest)
        self.assertIn("ignore", kwargs)
        self.assertTrue(callable(kwargs["ignore"]))

    def test_ignore_patterns_excludes_expected_items(self):
        ignore_fn = None
        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "mkdir"),
            patch("install.shutil.copytree") as mock_ct,
        ):
            install.copy_skill(self.src, self.dest)
            ignore_fn = mock_ct.call_args[1]["ignore"]

        names = [
            ".git", "__pycache__", "install.py", "install.sh",
            "install.ps1", ".skills", ".env", ".secret",
            ".credentials", ".code-review-cache",
            "foo.pyc",
            "keep.py", "SKILL.md", "README.md",
        ]
        result = ignore_fn("any/path", names)
        self.assertIn(".git", result)
        self.assertIn("__pycache__", result)
        self.assertIn("install.py", result)
        self.assertIn("foo.pyc", result)
        self.assertNotIn("keep.py", result)
        self.assertNotIn("SKILL.md", result)

    @patch("install.shutil.copytree", side_effect=PermissionError("denied"))
    @patch("install.print_error")
    def test_permission_error_is_raised(self, mock_print_error, mock_copytree):
        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "mkdir"),
        ):
            with self.assertRaises(PermissionError):
                install.copy_skill(self.src, self.dest)
        mock_print_error.assert_called_once()

    @patch("install.shutil.copytree", side_effect=OSError("disk full"))
    @patch("install.print_error")
    def test_os_error_is_raised(self, mock_print_error, mock_copytree):
        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "mkdir"),
        ):
            with self.assertRaises(OSError):
                install.copy_skill(self.src, self.dest)
        mock_print_error.assert_called_once()

    @patch("install.shutil.copytree", side_effect=PermissionError("denied"))
    @patch("install.print_error")
    def test_permission_error_does_not_call_mkdir_on_failure(
        self, mock_print_error, mock_copytree
    ):
        mkdir = MagicMock()
        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "mkdir", mkdir),
        ):
            with self.assertRaises(PermissionError):
                install.copy_skill(self.src, self.dest)
        mkdir.assert_called_once()
        mock_print_error.assert_called_once()


class TestPrintFunctions(unittest.TestCase):
    """Tests for print_* helper functions."""

    def setUp(self):
        self.patcher = patch("sys.stdout", new_callable=io.StringIO)
        self.mock_stdout = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_print_success_contains_green_code(self):
        install.print_success("done")
        output = self.mock_stdout.getvalue()
        self.assertIn("SUCCESS", output)
        self.assertIn("\x1b[92m", output)
        self.assertIn("\x1b[0m", output)
        self.assertIn("done", output)

    def test_print_info_contains_blue_code(self):
        install.print_info("hello")
        output = self.mock_stdout.getvalue()
        self.assertIn("INFO", output)
        self.assertIn("\x1b[94m", output)
        self.assertIn("\x1b[0m", output)
        self.assertIn("hello", output)

    def test_print_error_contains_red_code(self):
        install.print_error("fail")
        output = self.mock_stdout.getvalue()
        self.assertIn("ERROR", output)
        self.assertIn("\x1b[91m", output)
        self.assertIn("\x1b[0m", output)
        self.assertIn("fail", output)

    def test_multiple_calls_accumulate(self):
        install.print_info("first")
        install.print_success("second")
        install.print_error("third")
        output = self.mock_stdout.getvalue()
        self.assertIn("first", output)
        self.assertIn("second", output)
        self.assertIn("third", output)

    def test_output_ends_with_newline(self):
        install.print_info("line")
        output = self.mock_stdout.getvalue()
        self.assertTrue(output.endswith("\n"))


class TestMainArgparse(unittest.TestCase):
    def test_dry_run_does_not_call_copy_skill(self):
        with (
            patch("sys.argv", ["install.py", "--dry-run"]),
            patch("install.get_target_dirs", return_value={
                "Claude Code": Path("/home/user/.claude/skills")
            }),
            patch("install.copy_skill") as mock_copy,
            patch.object(Path, "exists", return_value=True),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            install.main()
        mock_copy.assert_not_called()

    def test_target_flag_installs_to_specified_dir(self):
        with (
            patch("sys.argv", ["install.py", "--target", "/custom/dir"]),
            patch("install.copy_skill") as mock_copy,
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            mock_copy.return_value = Path("/custom/dir/complete-codebase-review")
            install.main()
        mock_copy.assert_called_once()
        _, call_args = mock_copy.call_args[0], mock_copy.call_args
        self.assertEqual(mock_copy.call_args[0][1], Path("/custom/dir"))


class TestMainFunction(unittest.TestCase):
    """Tests for main()."""

    def setUp(self):
        self.file_patch = patch("install.__file__", "/fake/path/install.py")
        self.file_patch.start()
        self.argv_patch = patch("sys.argv", _ARGV_PATCH)
        self.argv_patch.start()

    def tearDown(self):
        self.file_patch.stop()
        self.argv_patch.stop()

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_install_to_detected_agents(
        self, mock_stdout, mock_copy, mock_get_dirs
    ):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
            "OpenCode": Path("/home/user/.opencode/skills"),
        }
        mock_get_dirs.return_value = fake_dirs
        mock_copy.return_value = Path("/installed/complete-codebase-review")

        existing = {p.parent for p in fake_dirs.values()}

        with patch.object(Path, "exists", lambda p: p in existing):
            install.main()

        self.assertEqual(mock_copy.call_count, 2)
        output = mock_stdout.getvalue()
        self.assertIn("SUCCESS", output)
        self.assertIn("Installation complete!", output)

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_no_agent_configs_falls_back_to_local(
        self, mock_stdout, mock_copy, mock_get_dirs
    ):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
            "OpenCode": Path("/home/user/.opencode/skills"),
        }
        mock_get_dirs.return_value = fake_dirs
        mock_copy.return_value = Path.cwd() / ".skills" / "complete-codebase-review"

        with patch.object(Path, "exists", return_value=False):
            install.main()

        output = mock_stdout.getvalue()
        self.assertIn("No existing global tool configurations", output)
        self.assertIn("Installed to local directory", output)

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_local_fallback_when_parent_exists_but_target_missing(
        self, mock_stdout, mock_copy, mock_get_dirs
    ):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
        }
        mock_get_dirs.return_value = fake_dirs
        mock_copy.return_value = Path.cwd() / ".skills" / "complete-codebase-review"

        with patch.object(Path, "exists", return_value=False):
            install.main()

        output = mock_stdout.getvalue()
        self.assertIn("No existing global tool configurations", output)

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_copy_skill_failure_continues_to_next_agent(
        self, mock_stdout, mock_copy, mock_get_dirs
    ):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
            "OpenCode": Path("/home/user/.opencode/skills"),
        }
        mock_get_dirs.return_value = fake_dirs
        mock_copy.side_effect = [PermissionError("denied"), Path("/ok")]

        existing = {p.parent for p in fake_dirs.values()}

        with patch.object(Path, "exists", lambda p: p in existing):
            install.main()

        self.assertEqual(mock_copy.call_count, 2)
        output = mock_stdout.getvalue()
        self.assertIn("Failed to install to Claude Code", output)
        self.assertIn("Installed to OpenCode", output)
        self.assertIn("Installation complete!", output)

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.exit")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_local_install_permission_error_exits(
        self, mock_stdout, mock_exit, mock_copy, mock_get_dirs
    ):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
        }
        mock_get_dirs.return_value = fake_dirs
        mock_copy.side_effect = PermissionError("denied")

        with patch.object(Path, "exists", return_value=False):
            install.main()

        mock_exit.assert_called_once_with(1)

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.exit")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_local_install_oserror_exits(
        self, mock_stdout, mock_exit, mock_copy, mock_get_dirs
    ):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
        }
        mock_get_dirs.return_value = fake_dirs
        mock_copy.side_effect = OSError("disk full")

        with patch.object(Path, "exists", return_value=False):
            install.main()

        mock_exit.assert_called_once_with(1)


class TestGitignoreWarning(unittest.TestCase):
    """Tests for gitignore warning in main() local fallback."""

    def setUp(self):
        self.file_patch = patch("install.__file__", "/fake/path/install.py")
        self.file_patch.start()
        self.argv_patch = patch("sys.argv", _ARGV_PATCH)
        self.argv_patch.start()

    def tearDown(self):
        self.file_patch.stop()
        self.argv_patch.stop()

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_gitignore_warning_shown_when_skills_present(
        self, mock_stdout, mock_copy, mock_get_dirs
    ):
        mock_get_dirs.return_value = {}
        mock_copy.return_value = Path("/x")
        gitignore_content = ".skills\n__pycache__\n"
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text",
                         return_value=gitignore_content),
        ):
            install.main()
        output = mock_stdout.getvalue()
        self.assertIn("gitignore", output.lower())
        self.assertIn(".skills", output)

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_no_gitignore_warning_when_skills_absent(
        self, mock_stdout, mock_copy, mock_get_dirs
    ):
        mock_get_dirs.return_value = {}
        mock_copy.return_value = Path("/x")
        gitignore_content = "__pycache__\n*.pyc\n"
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text",
                         return_value=gitignore_content),
        ):
            install.main()
        output = mock_stdout.getvalue()
        self.assertNotIn("gitignore", output.lower())

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_no_gitignore_warning_when_file_absent(
        self, mock_stdout, mock_copy, mock_get_dirs
    ):
        mock_get_dirs.return_value = {}
        mock_copy.return_value = Path("/x")
        with patch.object(Path, "exists", return_value=False):
            install.main()
        output = mock_stdout.getvalue()
        self.assertNotIn("gitignore", output.lower())


class TestMainEdgeCases(unittest.TestCase):
    """Edge-case tests for main()."""

    def setUp(self):
        self.file_patch = patch("install.__file__", "/fake/path/install.py")
        self.file_patch.start()
        self.argv_patch = patch("sys.argv", _ARGV_PATCH)
        self.argv_patch.start()

    def tearDown(self):
        self.file_patch.stop()
        self.argv_patch.stop()

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_empty_target_dirs_uses_local_fallback(
        self, mock_stdout, mock_copy, mock_get_dirs
    ):
        mock_get_dirs.return_value = {}
        mock_copy.return_value = Path("/x")

        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=""),
        ):
            install.main()

        mock_copy.assert_called_once()
        args, _ = mock_copy.call_args
        self.assertEqual(args[1], Path.cwd() / ".skills")

    @patch("install.get_target_dirs")
    @patch("install.copy_skill")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_one_agent_exists_one_missing_installs_partial(
        self, mock_stdout, mock_copy, mock_get_dirs
    ):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
            "Cursor": Path("/home/user/.cursor/skills"),
        }
        mock_get_dirs.return_value = fake_dirs
        mock_copy.return_value = Path("/installed")

        existing_paths = {Path("/home/user/.claude")}

        with patch.object(Path, "exists", lambda p: p in existing_paths):
            install.main()

        self.assertEqual(mock_copy.call_count, 1)
        output = mock_stdout.getvalue()
        self.assertIn("Detected Claude Code", output)
        self.assertNotIn("Detected Cursor", output)
        self.assertNotIn("No existing global tool configurations", output)
        self.assertIn("Installation complete!", output)

    @patch("install.get_target_dirs")
    @patch("install.copy_skill", side_effect=PermissionError("no write"))
    @patch("install.sys.exit")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_all_agents_fail_and_local_fails_exits(
        self, mock_stdout, mock_exit, mock_copy, mock_get_dirs
    ):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
        }
        mock_get_dirs.return_value = fake_dirs

        with patch.object(Path, "exists", return_value=False):
            install.main()

        mock_exit.assert_called_once_with(1)
        output = mock_stdout.getvalue()
        self.assertIn("Local installation failed", output)


if __name__ == "__main__":
    unittest.main()

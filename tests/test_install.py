"""Unit tests for install.py."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import install


_ARGV_PATCH = ["install.py"]


class _BaseInstallTest(unittest.TestCase):
    def setUp(self):
        self.file_patch = patch("install.__file__", "/fake/path/install.py")
        self.file_patch.start()

    def tearDown(self):
        self.file_patch.stop()


class _BaseInstallTestWithArgv(_BaseInstallTest):
    def setUp(self):
        super().setUp()
        self.argv_patch = patch("sys.argv", _ARGV_PATCH)
        self.argv_patch.start()

    def tearDown(self):
        self.argv_patch.stop()
        super().tearDown()


class TestReadVersion(unittest.TestCase):
    """Tests for _read_version()."""

    def test_missing_pyproject_file_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "install.py").write_text("", encoding="utf-8")
            with patch("install.__file__", str(project_dir / "install.py")):
                with self.assertRaisesRegex(RuntimeError, "pyproject.toml not found"):
                    install._read_version()

    def test_missing_pyproject_version_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "install.py").write_text("", encoding="utf-8")
            (project_dir / "pyproject.toml").write_text(
                '[project]\nname = "complete-codebase-review"\n',
                encoding="utf-8",
            )
            with patch("install.__file__", str(project_dir / "install.py")):
                with self.assertRaisesRegex(RuntimeError, "version missing"):
                    install._read_version()


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

    def test_claude_code_uses_dot_claude_when_xdg_unset_on_linux(self):
        """Without XDG_CONFIG_HOME, Linux should use ~/.claude like other platforms."""
        env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
        with (
            patch("install.platform.system", return_value="Linux"),
            patch.dict(os.environ, env, clear=True),
        ):
            dirs = install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], Path.home() / ".claude" / "skills")

    def test_claude_code_uses_dot_claude_when_xdg_empty_on_linux(self):
        """Empty XDG_CONFIG_HOME is treated as unset — use ~/.claude."""
        env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
        env["XDG_CONFIG_HOME"] = ""
        with (
            patch("install.platform.system", return_value="Linux"),
            patch.dict(os.environ, env, clear=True),
        ):
            dirs = install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], Path.home() / ".claude" / "skills")

    def test_claude_code_uses_dot_claude_on_non_linux(self):
        with patch("install.platform.system", return_value="Darwin"):
            dirs = install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], Path.home() / ".claude" / "skills")


class TestCopySkill(unittest.TestCase):
    """Tests for copy_skill()."""

    def _make_src(self, tmpdir, extra_files=None):
        src = Path(tmpdir) / "src"
        src.mkdir()
        (src / "SKILL.md").write_text("name: test-skill")
        (src / "README.md").write_text("# Test")
        if extra_files:
            for name, content in extra_files.items():
                p = src / name
                if content is None:
                    p.mkdir(parents=True, exist_ok=True)
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(content)
        return src

    def test_creates_dest_dir_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            result = install.copy_skill(src, dest)
            self.assertEqual(result, dest / "complete-codebase-review")
            self.assertTrue(result.exists())
            self.assertTrue((result / "SKILL.md").exists())

    def test_removes_existing_skill_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            skill_dest = dest / "complete-codebase-review"
            skill_dest.mkdir(parents=True)
            (skill_dest / "old.txt").write_text("old")

            install.copy_skill(src, dest)

            self.assertTrue(skill_dest.exists())
            self.assertTrue((skill_dest / "SKILL.md").exists())
            self.assertFalse((skill_dest / "old.txt").exists())

    def test_removes_existing_skill_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            skill_dest = dest / "complete-codebase-review"
            skill_dest.parent.mkdir(parents=True)
            skill_dest.write_text("not-a-dir")

            install.copy_skill(src, dest)

            self.assertTrue(skill_dest.exists())
            self.assertTrue(skill_dest.is_dir())
            self.assertTrue((skill_dest / "SKILL.md").exists())

    def test_calls_copytree_with_ignore_patterns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            install.copy_skill(src, dest)
            skill_dest = dest / "complete-codebase-review"
            self.assertTrue(skill_dest.exists())
            self.assertTrue((skill_dest / "SKILL.md").exists())

    def test_copy_skill_includes_karpathy_guidelines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir, {
                "karpathy-guidelines.md": "# Guidelines",
            })
            dest = Path(tmpdir) / "dest"
            result = install.copy_skill(src, dest)

            self.assertTrue((result / "karpathy-guidelines.md").exists())

    def test_copy_skill_to_file_path_raises_oserror(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            file_target = Path(tmpdir) / "file.txt"
            file_target.write_text("not a directory")
            with self.assertRaises(OSError):
                install.copy_skill(src, file_target)

    def test_ignore_patterns_excludes_expected_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir, {
                ".git": None,
                "__pycache__": None,
                "install.py": "",
                "install.sh": "",
                "install.ps1": "",
                ".skills": None,
                ".env": "",
                ".secret": "",
                ".credentials": "",
                ".code-review-cache": None,
                "foo.pyc": "",
                "keep.py": "",
            })
            dest = Path(tmpdir) / "dest"
            result = install.copy_skill(src, dest)

            self.assertTrue((result / "keep.py").exists())
            self.assertTrue((result / "SKILL.md").exists())
            self.assertFalse((result / ".git").exists())
            self.assertFalse((result / "__pycache__").exists())
            self.assertFalse((result / "install.py").exists())
            self.assertFalse((result / "foo.pyc").exists())

    @patch("install.shutil.copytree", side_effect=PermissionError("denied"))
    @patch("install.print_error")
    def test_permission_error_is_raised(self, mock_print_error, mock_copytree):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            with self.assertRaises(PermissionError):
                install.copy_skill(src, dest)
        mock_print_error.assert_called_once()

    @patch("install.shutil.copytree", side_effect=OSError("disk full"))
    @patch("install.print_error")
    def test_os_error_is_raised(self, mock_print_error, mock_copytree):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            with self.assertRaises(OSError):
                install.copy_skill(src, dest)
        mock_print_error.assert_called_once()

    @patch("install.shutil.copytree", side_effect=PermissionError("denied"))
    @patch("install.print_error")
    def test_permission_error_does_not_call_mkdir_on_failure(
        self, mock_print_error, mock_copytree
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            with self.assertRaises(PermissionError):
                install.copy_skill(src, dest)
        mock_print_error.assert_called_once()


class TestPrintFunctions(unittest.TestCase):
    """Tests for print_* helper functions."""

    def setUp(self):
        self.patcher = patch("sys.stdout", new_callable=io.StringIO)
        self.mock_stdout = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_print_success_contains_green_code(self):
        with (
            patch.object(sys.stdout, "isatty", return_value=True),
            patch.dict(os.environ, {}, clear=True),
        ):
            install.print_success("done")
        output = self.mock_stdout.getvalue()
        self.assertIn("SUCCESS", output)
        self.assertIn("\x1b[92m", output)
        self.assertIn("\x1b[0m", output)
        self.assertIn("done", output)

    def test_print_info_contains_blue_code(self):
        with (
            patch.object(sys.stdout, "isatty", return_value=True),
            patch.dict(os.environ, {}, clear=True),
        ):
            install.print_info("hello")
        output = self.mock_stdout.getvalue()
        self.assertIn("INFO", output)
        self.assertIn("\x1b[94m", output)
        self.assertIn("\x1b[0m", output)
        self.assertIn("hello", output)

    def test_print_error_contains_red_code(self):
        with (
            patch.object(sys.stdout, "isatty", return_value=True),
            patch.dict(os.environ, {}, clear=True),
        ):
            install.print_error("fail")
        output = self.mock_stdout.getvalue()
        self.assertIn("ERROR", output)
        self.assertIn("\x1b[91m", output)
        self.assertIn("\x1b[0m", output)
        self.assertIn("fail", output)

    def test_multiple_calls_accumulate(self):
        with (
            patch.object(sys.stdout, "isatty", return_value=True),
            patch.dict(os.environ, {}, clear=True),
        ):
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


class TestMainArgparse(_BaseInstallTest):

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
            mock_copy.return_value = Path("/custom/dir/complete-codebase-review").resolve()
            install.main()
        mock_copy.assert_called_once()
        self.assertEqual(mock_copy.call_args[0][1], Path("/custom/dir").resolve())

    def test_dry_run_auto_detect_prints_dry_run_complete_not_installed(self):
        with (
            patch("sys.argv", ["install.py", "--dry-run"]),
            patch("install.get_target_dirs", return_value={
                "Claude Code": Path("/home/user/.claude/skills")
            }),
            patch("install.copy_skill") as mock_copy,
            patch.object(Path, "exists", return_value=True),
            patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
        ):
            install.main()
        mock_copy.assert_not_called()
        output = mock_stdout.getvalue()
        self.assertIn("Dry run complete", output)
        self.assertNotIn("Installation complete", output)


class TestMainFunction(_BaseInstallTestWithArgv):
    """Tests for main()."""

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


class TestGitignoreWarning(_BaseInstallTestWithArgv):
    """Tests for gitignore warning in main() local fallback."""

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


class TestValidateTargetPath(unittest.TestCase):
    """Tests for _validate_target_path()."""

    def test_valid_absolute_path(self):
        result = install._validate_target_path(Path("/home/user/skills"))
        self.assertEqual(result, Path("/home/user/skills").resolve())

    def test_valid_relative_path(self):
        result = install._validate_target_path(Path("skills"))
        self.assertEqual(result, Path("skills").resolve())

    def test_path_traversal_detected(self):
        with self.assertRaises(ValueError) as ctx:
            install._validate_target_path(Path("/home/user/../../etc"))
        self.assertIn("Path traversal", str(ctx.exception))

    def test_path_traversal_simple(self):
        with self.assertRaises(ValueError):
            install._validate_target_path(Path("../evil"))

    def test_path_traversal_encoded(self):
        with self.assertRaises(ValueError):
            install._validate_target_path(Path("safe/../../etc"))

    def test_path_traversal_in_middle(self):
        with self.assertRaises(ValueError):
            install._validate_target_path(Path("/home/user/../other/skills"))

    def test_dot_without_dotdot_is_valid(self):
        result = install._validate_target_path(Path("./skills"))
        self.assertIsNotNone(result)

    def test_dotdot_substring_in_path_component_is_valid(self):
        result = install._validate_target_path(Path("/home/user/..safe"))
        self.assertEqual(result, Path("/home/user/..safe").resolve())

    def test_normal_path_with_symlinks_resolves(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            real = Path(tmpdir) / "real"
            real.mkdir()
            link = Path(tmpdir) / "link"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported on this platform")
            result = install._validate_target_path(link)
            self.assertEqual(result, real.resolve())

    @patch("install.sys.exit")
    @patch("install.sys.stdout", new_callable=io.StringIO)
    def test_target_path_traversal_exits_with_error(self, mock_stdout, mock_exit):
        with (
            patch("sys.argv", ["install.py", "--target", "/safe/../../etc"]),
        ):
            install.main()
        mock_exit.assert_called_with(1)
        output = mock_stdout.getvalue()
        self.assertIn("Path traversal", output)


class TestMainEdgeCases(_BaseInstallTestWithArgv):
    """Edge-case tests for main()."""

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

"""Unit tests for install.py.

T-030 (deferred): Mock-heavy test pattern is a design concern. Would require
significant refactoring to reduce mock coupling — deferred.
"""
import importlib
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock


def _import_install():
    p = str(Path(__file__).resolve().parent.parent)
    old_path = list(sys.path)
    try:
        if p not in sys.path:
            sys.path.insert(0, p)
        module = importlib.import_module("install")
        importlib.reload(module)
        return module
    finally:
        sys.path[:] = old_path


_ARGV_PATCH = ("install.py",)


class _BaseInstallTest(unittest.TestCase):
    def setUp(self):
        self.install = _import_install()
        self.file_patch = patch.object(self.install, "__file__", "/fake/path/install.py")
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


class TestReadVersion(_BaseInstallTest):
    """Tests for _read_version()."""

    def test_missing_pyproject_file_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "install.py").write_text("", encoding="utf-8")
            with patch.object(self.install, "__file__", str(project_dir / "install.py")):
                with self.assertRaisesRegex(RuntimeError, "pyproject.toml not found"):
                    self.install._read_version()

    def test_missing_pyproject_version_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "install.py").write_text("", encoding="utf-8")
            (project_dir / "pyproject.toml").write_text(
                '[project]\nname = "complete-codebase-review"\n',
                encoding="utf-8",
            )
            with patch.object(self.install, "__file__", str(project_dir / "install.py")):
                with self.assertRaisesRegex(RuntimeError, "version missing"):
                    self.install._read_version()

    def test_read_version_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "install.py").write_text("", encoding="utf-8")
            (project_dir / "pyproject.toml").write_text(
                'version = "2.2.0"\n', encoding="utf-8"
            )
            with patch.object(self.install, "__file__", str(project_dir / "install.py")):
                result = self.install._read_version()
            self.assertEqual(result, "2.2.0")


class TestGetTargetDirs(_BaseInstallTest):
    """Tests for get_target_dirs()."""

    def test_returns_dict_with_expected_keys(self):
        dirs = self.install.get_target_dirs()
        expected_keys = {"Claude Code", "OpenCode", "Cursor", "Continue"}
        self.assertEqual(set(dirs.keys()), expected_keys)

    def test_values_are_path_instances(self):
        dirs = self.install.get_target_dirs()
        for name, path in dirs.items():
            with self.subTest(agent=name):
                self.assertIsInstance(path, Path)

    def test_paths_are_under_home(self):
        home = Path.home()
        with patch.object(self.install.platform, "system", return_value="Darwin"):
            dirs = self.install.get_target_dirs()
        expected = {
            "Claude Code": home / ".claude" / "skills",
            "OpenCode": home / ".opencode" / "skills",
            "Cursor": home / ".cursor" / "skills",
            "Continue": home / ".continue" / "skills",
        }
        self.assertEqual(dirs, expected)

    def test_claude_code_uses_xdg_on_linux(self):
        fake_home = Path('/home/user').resolve()
        fake_xdg = fake_home / '.config'
        with patch.object(self.install.platform, "system",
                                  return_value="Linux"), \
     patch.dict(os.environ, {"XDG_CONFIG_HOME": str(fake_xdg)}), \
     patch.object(Path, "home", return_value=fake_home):
            dirs = self.install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], fake_xdg / "claude" / "skills")

    def test_claude_code_uses_dot_claude_when_xdg_unset_on_linux(self):
        """Without XDG_CONFIG_HOME, Linux should use ~/.claude like other platforms."""
        env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
        with patch.object(self.install.platform, "system",
                          return_value="Linux"), \
             patch.dict(os.environ, env, clear=True):
            dirs = self.install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], Path.home() / ".claude" / "skills")

    def test_claude_code_uses_dot_claude_when_xdg_empty_on_linux(self):
        """Empty XDG_CONFIG_HOME is treated as unset — use ~/.claude."""
        env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
        env["XDG_CONFIG_HOME"] = ""
        with patch.object(self.install.platform, "system",
                          return_value="Linux"), \
             patch.dict(os.environ, env, clear=True):
            dirs = self.install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], Path.home() / ".claude" / "skills")

    def test_claude_code_uses_dot_claude_on_non_linux(self):
        with patch.object(self.install.platform, "system", return_value="Darwin"):
            dirs = self.install.get_target_dirs()
        self.assertEqual(dirs["Claude Code"], Path.home() / ".claude" / "skills")

    def test_windows_uses_dot_app_style_paths(self):
        with patch.object(self.install.platform, "system", return_value="Windows"):
            dirs = self.install.get_target_dirs()
        home = Path.home()
        self.assertEqual(dirs["Claude Code"], home / ".claude" / "skills")
        self.assertEqual(dirs["OpenCode"], home / ".opencode" / "skills")
        self.assertEqual(dirs["Cursor"], home / ".cursor" / "skills")
        self.assertEqual(dirs["Continue"], home / ".continue" / "skills")


class TestCopySkill(_BaseInstallTest):
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
            result = self.install.copy_skill(src, dest)
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

            self.install.copy_skill(src, dest)

            self.assertTrue(skill_dest.exists())
            self.assertTrue((skill_dest / "SKILL.md").exists())
            self.assertFalse((skill_dest / "old.txt").exists())

    def test_removes_readonly_skill_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            skill_dest = dest / "complete-codebase-review"
            skill_dest.mkdir(parents=True)
            ro_file = skill_dest / "readonly.txt"
            ro_file.write_text("read-only")
            os.chmod(str(ro_file), stat.S_IRUSR | stat.S_IXUSR)
            try:
                result = self.install.copy_skill(src, dest)
            except NameError:
                self.fail("copy_skill raised NameError (missing 'import stat')")
            self.assertTrue(result.exists())
            self.assertTrue((result / "SKILL.md").exists())

    def test_removes_existing_skill_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            skill_dest = dest / "complete-codebase-review"
            skill_dest.parent.mkdir(parents=True)
            skill_dest.write_text("not-a-dir")

            self.install.copy_skill(src, dest)

            self.assertTrue(skill_dest.exists())
            self.assertTrue(skill_dest.is_dir())
            self.assertTrue((skill_dest / "SKILL.md").exists())

    def test_calls_copytree_with_ignore_patterns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            self.install.copy_skill(src, dest)
            skill_dest = dest / "complete-codebase-review"
            self.assertTrue(skill_dest.exists())
            self.assertTrue((skill_dest / "SKILL.md").exists())

    def test_copy_skill_includes_karpathy_guidelines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir, {
                "karpathy-guidelines.md": "# Guidelines",
            })
            dest = Path(tmpdir) / "dest"
            result = self.install.copy_skill(src, dest)

            self.assertTrue((result / "karpathy-guidelines.md").exists())

    def test_copy_skill_to_file_path_raises_oserror(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            file_target = Path(tmpdir) / "file.txt"
            file_target.write_text("not a directory")
            with self.assertRaises(OSError):
                self.install.copy_skill(src, file_target)

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
                "orchestrator-rules.md": "",
                "keep.py": "",
            })
            dest = Path(tmpdir) / "dest"
            result = self.install.copy_skill(src, dest)

            self.assertTrue((result / "keep.py").exists())
            self.assertTrue((result / "SKILL.md").exists())
            self.assertFalse((result / ".git").exists())
            self.assertFalse((result / "__pycache__").exists())
            self.assertFalse((result / "install.py").exists())
            self.assertFalse((result / "foo.pyc").exists())
            self.assertFalse((result / "orchestrator-rules.md").exists())

    def test_permission_error_is_raised(self):
        with patch.object(self.install.shutil, "copytree",
                          side_effect=PermissionError("denied")), \
             patch.object(self.install, "print_error") as mock_print_error:
            with tempfile.TemporaryDirectory() as tmpdir:
                src = self._make_src(tmpdir)
                dest = Path(tmpdir) / "dest"
                with self.assertRaises(PermissionError):
                    self.install.copy_skill(src, dest)
            mock_print_error.assert_called_once()

    def test_os_error_is_raised(self):
        with patch.object(self.install.shutil, "copytree",
                          side_effect=OSError("disk full")), \
             patch.object(self.install, "print_error") as mock_print_error:
            with tempfile.TemporaryDirectory() as tmpdir:
                src = self._make_src(tmpdir)
                dest = Path(tmpdir) / "dest"
                with self.assertRaises(OSError):
                    self.install.copy_skill(src, dest)
            mock_print_error.assert_called_once()

class TestPrintFunctions(_BaseInstallTest):
    """Tests for print_* helper functions."""

    def setUp(self):
        super().setUp()
        self.patcher = patch("sys.stdout", new_callable=io.StringIO)
        self.mock_stdout = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        super().tearDown()

    def test_print_success_contains_green_code(self):
        with patch.object(sys.stdout, "isatty",
                          return_value=True), \
             patch.dict(os.environ, {}, clear=True):
            self.install.print_success("done")
        output = self.mock_stdout.getvalue()
        self.assertIn("SUCCESS", output)
        self.assertIn("\x1b[92m", output)
        self.assertIn("\x1b[0m", output)
        self.assertIn("done", output)

    def test_print_info_contains_blue_code(self):
        with patch.object(sys.stdout, "isatty",
                          return_value=True), \
             patch.dict(os.environ, {}, clear=True):
            self.install.print_info("hello")
        output = self.mock_stdout.getvalue()
        self.assertIn("INFO", output)
        self.assertIn("\x1b[94m", output)
        self.assertIn("\x1b[0m", output)
        self.assertIn("hello", output)

    def test_print_error_contains_red_code(self):
        with patch.object(sys.stdout, "isatty",
                          return_value=True), \
             patch.dict(os.environ, {}, clear=True):
            self.install.print_error("fail")
        output = self.mock_stdout.getvalue()
        self.assertIn("ERROR", output)
        self.assertIn("\x1b[91m", output)
        self.assertIn("\x1b[0m", output)
        self.assertIn("fail", output)

    def test_multiple_calls_accumulate(self):
        with patch.object(sys.stdout, "isatty",
                          return_value=True), \
             patch.dict(os.environ, {}, clear=True):
            self.install.print_info("first")
            self.install.print_success("second")
            self.install.print_error("third")
        output = self.mock_stdout.getvalue()
        self.assertIn("first", output)
        self.assertIn("second", output)
        self.assertIn("third", output)

    def test_output_ends_with_newline(self):
        self.install.print_info("line")
        output = self.mock_stdout.getvalue()
        self.assertTrue(output.endswith("\n"))


class TestMainArgparse(_BaseInstallTest):

    def test_dry_run_does_not_call_copy_skill(self):
        with patch("sys.argv", ["install.py", "--dry-run"]), \
             patch.object(self.install, "get_target_dirs",
                          return_value={"Claude Code":
                                        Path("/home/user/.claude/skills")}), \
             patch.object(self.install, "copy_skill") as mock_copy, \
             patch.object(Path, "exists", return_value=True), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.install.main()
        mock_copy.assert_not_called()

    def test_target_flag_installs_to_specified_dir(self):
        with patch("sys.argv",
                   ["install.py", "--target", "/custom/dir"]), \
             patch.object(self.install, "copy_skill") as mock_copy, \
             patch("sys.stdout", new_callable=io.StringIO):
            mock_copy.return_value = Path(
                "/custom/dir/complete-codebase-review").resolve()
            self.install.main()
        mock_copy.assert_called_once()
        self.assertEqual(mock_copy.call_args[0][1], Path("/custom/dir").resolve())

    def test_dry_run_auto_detect_prints_dry_run_complete_not_installed(self):
        with patch("sys.argv", ["install.py", "--dry-run"]), \
             patch.object(self.install, "get_target_dirs",
                          return_value={"Claude Code":
                                        Path("/home/user/.claude/skills")}), \
             patch.object(self.install, "copy_skill") as mock_copy, \
             patch.object(Path, "exists", return_value=True), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.install.main()
        mock_copy.assert_not_called()
        output = mock_stdout.getvalue()
        self.assertIn("Dry run complete", output)
        self.assertNotIn("Installation complete", output)

    def test_target_flag_dry_run(self):
        with patch("sys.argv", ["install.py", "--target", "/custom/dir", "--dry-run"]), \
             patch.object(self.install, "_validate_target_path",
                          return_value=Path("/custom/dir")), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.install.main()
        output = mock_stdout.getvalue()
        self.assertIn("[DRY-RUN] Would install to", output)
        self.assertIn("Dry run complete", output)


class TestMainFunction(_BaseInstallTestWithArgv):
    """Tests for main()."""

    def test_install_to_detected_agents(self):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
            "OpenCode": Path("/home/user/.opencode/skills"),
        }
        existing = {p.parent for p in fake_dirs.values()}
        fake_home = Path("/home/user").resolve()

        with patch.object(self.install, "get_target_dirs",
                          return_value=fake_dirs), \
             patch.object(self.install, "copy_skill",
                          return_value=Path(
                              "/installed/complete-codebase-review")) \
             as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout, \
             patch.object(Path, "home",
                          return_value=fake_home):
            with patch.object(Path, "exists", lambda p: p in existing):
                self.install.main()

        self.assertEqual(mock_copy.call_count, 2)
        output = mock_stdout.getvalue()
        self.assertIn("SUCCESS", output)
        self.assertIn("Installation complete!", output)

    def test_no_agent_configs_falls_back_to_local(self):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
            "OpenCode": Path("/home/user/.opencode/skills"),
        }

        with patch.object(self.install, "get_target_dirs",
                          return_value=fake_dirs), \
             patch.object(self.install, "copy_skill",
                          return_value=Path.cwd() / ".skills" /
                          "complete-codebase-review") as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=False):
                self.install.main()

        output = mock_stdout.getvalue()
        self.assertIn("No existing global tool configurations", output)
        self.assertIn("Installed to local directory", output)

    def test_local_fallback_when_parent_exists_but_target_missing(self):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
        }

        with patch.object(self.install, "get_target_dirs",
                          return_value=fake_dirs), \
             patch.object(self.install, "copy_skill",
                          return_value=Path.cwd() / ".skills" /
                          "complete-codebase-review") as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=False):
                self.install.main()

        output = mock_stdout.getvalue()
        self.assertIn("No existing global tool configurations", output)

    def test_copy_skill_failure_continues_to_next_agent(self):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
            "OpenCode": Path("/home/user/.opencode/skills"),
        }
        existing = {p.parent for p in fake_dirs.values()}

        with patch.object(self.install, "get_target_dirs",
                          return_value=fake_dirs), \
             patch.object(self.install, "copy_skill",
                          side_effect=[PermissionError("denied"),
                                       Path("/ok")]) as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout, \
             patch.object(Path, "home",
                          return_value=Path("/home/user").resolve()):
            with patch.object(Path, "exists", lambda p: p in existing):
                self.install.main()

        self.assertEqual(mock_copy.call_count, 2)
        output = mock_stdout.getvalue()
        self.assertIn("Failed to install to Claude Code", output)
        self.assertIn("Installed to OpenCode", output)
        self.assertIn("Installation complete!", output)

    def test_local_install_permission_error_exits(self):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
        }

        with patch.object(self.install, "get_target_dirs",
                          return_value=fake_dirs), \
             patch.object(self.install, "copy_skill",
                          side_effect=PermissionError("denied")) \
             as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=False):
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()

        self.assertEqual(ctx.exception.code, 1)

    def test_local_install_oserror_exits(self):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
        }

        with patch.object(self.install, "get_target_dirs",
                          return_value=fake_dirs), \
             patch.object(self.install, "copy_skill",
                          side_effect=OSError("disk full")) as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=False):
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()

        self.assertEqual(ctx.exception.code, 1)


class TestGitignoreWarning(_BaseInstallTestWithArgv):
    """Tests for gitignore warning in main() local fallback."""

    def test_gitignore_warning_shown_when_skills_present(self):
        gitignore_content = ".skills\n__pycache__\n"
        with patch.object(self.install, "get_target_dirs",
                          return_value={}), \
             patch.object(self.install, "copy_skill",
                          return_value=Path("/x")) as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=True), \
                 patch.object(Path, "read_text",
                              return_value=gitignore_content):
                self.install.main()
        output = mock_stdout.getvalue()
        self.assertIn("gitignore", output.lower())
        self.assertIn(".skills", output)

    def test_no_gitignore_warning_when_skills_absent(self):
        gitignore_content = "__pycache__\n*.pyc\n"
        with patch.object(self.install, "get_target_dirs",
                          return_value={}), \
             patch.object(self.install, "copy_skill",
                          return_value=Path("/x")) as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=True), \
                 patch.object(Path, "read_text",
                              return_value=gitignore_content):
                self.install.main()
        output = mock_stdout.getvalue()
        self.assertNotIn("gitignore", output.lower())

    def test_no_gitignore_warning_when_file_absent(self):
        with patch.object(self.install, "get_target_dirs",
                          return_value={}), \
             patch.object(self.install, "copy_skill",
                          return_value=Path("/x")) as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=False):
                self.install.main()
        output = mock_stdout.getvalue()
        self.assertNotIn("gitignore", output.lower())


class TestValidateTargetPath(_BaseInstallTest):
    """Tests for _validate_target_path()."""

    def test_valid_absolute_path(self):
        result = self.install._validate_target_path(Path("/home/user/skills"))
        self.assertEqual(result, Path("/home/user/skills").resolve())

    def test_valid_relative_path(self):
        result = self.install._validate_target_path(Path("skills"))
        self.assertEqual(result, Path("skills").resolve())

    def test_path_traversal_detected(self):
        with self.assertRaises(ValueError) as ctx:
            self.install._validate_target_path(Path("/home/user/../../etc"))
        self.assertIn("Path traversal", str(ctx.exception))

    def test_path_traversal_simple(self):
        with self.assertRaises(ValueError):
            self.install._validate_target_path(Path("../evil"))

    def test_path_traversal_encoded(self):
        with self.assertRaises(ValueError):
            self.install._validate_target_path(Path("safe/../../etc"))

    def test_path_traversal_in_middle(self):
        with self.assertRaises(ValueError):
            self.install._validate_target_path(Path("/home/user/../other/skills"))

    def test_dot_without_dotdot_is_valid(self):
        result = self.install._validate_target_path(Path("./skills"))
        self.assertIsNotNone(result)

    def test_dotdot_substring_in_path_component_is_valid(self):
        result = self.install._validate_target_path(Path("/home/user/..safe"))
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
            result = self.install._validate_target_path(link)
            self.assertEqual(result, real.resolve())

    def test_target_path_traversal_exits_with_error(self):
        with patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout, \
             patch("sys.argv", ["install.py", "--target", "/safe/../../etc"]):
            with self.assertRaises(SystemExit) as ctx:
                self.install.main()
        self.assertEqual(ctx.exception.code, 1)
        output = mock_stdout.getvalue()
        self.assertIn("Path traversal", output)

class TestMainEdgeCases(_BaseInstallTestWithArgv):
    """Edge-case tests for main()."""

    def test_target_install_permission_error_exits(self):
        with patch.object(self.install, "_validate_target_path",
                          return_value=Path("/resolved")), \
             patch.object(self.install, "copy_skill",
                           side_effect=PermissionError("denied")) \
             as mock_copy, \
             patch.object(self.install.sys, "stdout",
                           new_callable=io.StringIO) as mock_stdout:
            with patch("sys.argv", ["install.py", "--target", "/custom/dir"]):
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()
        self.assertEqual(ctx.exception.code, 1)
        output = mock_stdout.getvalue()
        self.assertIn("Install failed", output)

    def test_version_flag(self):
        with patch("sys.argv", ["install.py", "--version"]), \
             patch.object(self.install, "get_version",
                          return_value="9.9.9"), \
             patch.object(self.install, "copy_skill") as mock_copy, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.install.main()
        mock_copy.assert_not_called()
        output = mock_stdout.getvalue()
        self.assertIn("complete-codebase-review v9.9.9", output)

    def test_empty_target_dirs_uses_local_fallback(self):
        with patch.object(self.install, "get_target_dirs",
                          return_value={}), \
             patch.object(self.install, "copy_skill",
                          return_value=Path("/x")) as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=True), \
                 patch.object(Path, "read_text", return_value=""):
                self.install.main()

        mock_copy.assert_called_once()
        args, _ = mock_copy.call_args
        self.assertEqual(args[1], Path.cwd() / ".skills")

    def test_empty_target_dirs_dry_run(self):
        with patch.object(self.install, "get_target_dirs",
                          return_value={}), \
             patch.object(self.install, "copy_skill") as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=True), \
                 patch.object(Path, "read_text", return_value=""):
                with patch("sys.argv", ["install.py", "--dry-run"]):
                    self.install.main()
        mock_copy.assert_not_called()
        output = mock_stdout.getvalue()
        self.assertIn("[DRY-RUN] Would install to local directory", output)

    def test_auto_install_invalid_path(self):
        fake_dirs = {"Claude Code": Path("/home/user/../.claude/skills")}
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=True):
                result = self.install._run_auto_install(
                    Path("/src"), fake_dirs, dry_run=False
                )
        self.assertFalse(result)
        output = mock_stdout.getvalue()
        self.assertIn("Invalid target path", output)

    def test_one_agent_exists_one_missing_installs_partial(self):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
            "Cursor": Path("/home/user/.cursor/skills"),
        }
        existing_paths = {Path("/home/user/.claude")}
        fake_home = Path("/home/user").resolve()

        with patch.object(self.install, "get_target_dirs",
                          return_value=fake_dirs), \
             patch.object(self.install, "copy_skill",
                          return_value=Path("/installed")) as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout, \
             patch.object(Path, "home",
                          return_value=fake_home):
            with patch.object(Path, "exists", lambda p: p in existing_paths):
                self.install.main()

        self.assertEqual(mock_copy.call_count, 1)
        output = mock_stdout.getvalue()
        self.assertIn("Detected Claude Code", output)
        self.assertNotIn("Detected Cursor", output)
        self.assertNotIn("No existing global tool configurations", output)
        self.assertIn("Installation complete!", output)

    def test_all_agents_fail_and_local_fails_exits(self):
        fake_dirs = {
            "Claude Code": Path("/home/user/.claude/skills"),
        }

        with patch.object(self.install, "get_target_dirs",
                          return_value=fake_dirs), \
             patch.object(self.install, "copy_skill",
                          side_effect=PermissionError("no write")) \
             as mock_copy, \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", return_value=False):
                with self.assertRaises(SystemExit) as ctx:
                    self.install.main()

        self.assertEqual(ctx.exception.code, 1)
        output = mock_stdout.getvalue()
        self.assertIn("Local installation failed", output)


class TestInternalFunctions(_BaseInstallTest):
    """Tests for previously uncovered internal helper functions."""

    def test_onerror_retries_after_chmod(self):
        mock_func = MagicMock()
        mock_chmod = MagicMock()
        with patch("install.os.chmod", mock_chmod):
            self.install._onerror(mock_func, "/some/path", None)
        mock_chmod.assert_called_once()
        args, kwargs = mock_chmod.call_args
        self.assertEqual(args[0], "/some/path")
        self.assertFalse(kwargs.get("follow_symlinks", True))
        mock_func.assert_called_once_with("/some/path")

    def test_onerror_handles_os_error(self):
        mock_func = MagicMock()
        with patch("install.os.chmod", side_effect=OSError("denied")):
            self.install._onerror(mock_func, "/some/path", None)
        mock_func.assert_called_once_with("/some/path")

    def test_onerror_fallback_on_not_implemented(self):
        mock_func = MagicMock()
        mock_chmod = MagicMock(side_effect=[NotImplementedError, None])
        with patch("install.os.chmod", mock_chmod), \
             patch("install.os.path.islink", return_value=False):
            self.install._onerror(mock_func, "/some/path", None)
        second_call = mock_chmod.call_args_list[1]
        self.assertEqual(second_call.args[0], "/some/path")
        self.assertNotIn("follow_symlinks", second_call.kwargs)

    def test_use_color_returns_false_when_no_tty(self):
        with patch.object(sys.stdout, "isatty", return_value=False):
            result = self.install._use_color()
        self.assertFalse(result)

    def test_use_color_returns_false_when_no_color_set(self):
        with patch.object(sys.stdout, "isatty",
                          return_value=True), \
             patch.dict(os.environ, {"NO_COLOR": "1"}, clear=True):
            result = self.install._use_color()
        self.assertFalse(result)

    def test_use_color_returns_true_when_tty_and_no_no_color(self):
        with patch.object(sys.stdout, "isatty",
                          return_value=True), \
             patch.dict(os.environ, {}, clear=True):
            result = self.install._use_color()
        self.assertTrue(result)

    def test_xdg_or_home_dir_uses_xdg_on_linux(self):
        fake_home = Path('/home/user').resolve()
        fake_xdg = fake_home / '.config'
        with patch("install.platform.system",
                   return_value="Linux"), \
             patch.dict(os.environ, {"XDG_CONFIG_HOME": str(fake_xdg)}, clear=True), \
             patch.object(Path, "home", return_value=fake_home):
            result = self.install._xdg_or_home_dir(fake_home, "claude")
        self.assertEqual(result, fake_xdg / "claude" / "skills")

    def test_xdg_or_home_dir_uses_home_on_non_linux(self):
        with patch("install.platform.system", return_value="Windows"):
            result = self.install._xdg_or_home_dir(Path("/home/user"), "claude")
        self.assertEqual(result, Path("/home/user/.claude/skills"))

    def test_validate_xdg_path_resolves_any_absolute(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xdg = Path(tmpdir) / "xdg"
            result = self.install._validate_xdg_path(xdg)
            self.assertIsNotNone(result)
            self.assertEqual(result, xdg.resolve())

    def test_validate_xdg_path_rejects_relative(self):
        result = self.install._validate_xdg_path(Path("relative/path"))
        self.assertIsNone(result)

    def test_get_version_caches_result(self):
        self.install._VERSION_CACHE = None
        call_count = 0
        def _counting_read_version():
            nonlocal call_count
            call_count += 1
            return "1.0.0"
        with patch.object(self.install, "_read_version", side_effect=_counting_read_version):
            version1 = self.install.get_version()
            version2 = self.install.get_version()
        self.assertEqual(version1, version2)
        self.assertEqual(call_count, 1)
        self.install._VERSION_CACHE = None


class TestMainEntryPoint(unittest.TestCase):
    """Tests for the if __name__ == '__main__' guard."""

    def test_main_entry_point(self):
        import subprocess
        script = str(Path(__file__).resolve().parent.parent / "install.py")
        result = subprocess.run(
            [sys.executable, script, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("complete-codebase-review v", result.stdout)


if __name__ == "__main__":
    unittest.main()

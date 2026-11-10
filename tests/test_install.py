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
import time
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

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tests import create_directory_link  # noqa: E402


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

    def test_refuses_a_target_swapped_for_a_link_after_the_sweep(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            dest.mkdir()
            elsewhere = Path(tmpdir) / "elsewhere"
            elsewhere.mkdir()
            # The swap needs a link. A host that cannot create one skips the
            # test instead of failing it.
            probe = Path(tmpdir) / "probe"
            try:
                create_directory_link(probe, elsewhere)
            except OSError as exc:
                self.skipTest("cannot create a directory link: " + str(exc))
            self.install._remove_link_like(probe)
            real_sweep = self.install._sweep_leftovers

            def sweep_then_swap(target, *args, **kwargs):
                result = real_sweep(target, *args, **kwargs)
                # Another writer swaps the directory for a link between the
                # guard and the copy.
                target.rmdir()
                create_directory_link(target, elsewhere)
                return result

            with patch.object(
                    self.install, "_sweep_leftovers", sweep_then_swap):
                with patch.object(self.install.shutil, "copytree") as copytree:
                    with self.assertRaises(ValueError):
                        self.install.copy_skill(src, dest)
            # The copy must not have run through the link: the staging tree
            # would land inside the link's target.
            copytree.assert_not_called()
            self.assertEqual(list(elsewhere.iterdir()), [])

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

    def test_sweeps_stale_staging_and_backup_trees(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            dest.mkdir()
            stale_staging = dest / (self.install.STAGING_PREFIX + "999")
            stale_backup = dest / (self.install.PREVIOUS_PREFIX + "999")
            stale_staging.mkdir()
            stale_backup.mkdir()
            (stale_staging / "left.txt").write_text("left")
            # Age them past the liveness window: a young tree may belong to a
            # run that is still working, an old one is a crash.
            old = time.time() - self.install.LEFTOVER_MAX_AGE_SEC - 60
            os.utime(stale_staging, (old, old))
            os.utime(stale_backup, (old, old))

            self.install.copy_skill(src, dest)

            self.assertFalse(stale_staging.exists())
            self.assertFalse(stale_backup.exists())
            self.assertTrue((dest / "complete-codebase-review" / "SKILL.md").exists())

    def test_keeps_a_young_staging_tree(self):
        # A concurrent install owns its staging tree; age is the only liveness
        # signal available on Windows, so a fresh one must survive.
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            dest.mkdir()
            live = dest / (self.install.STAGING_PREFIX + str(os.getpid() + 1))
            live.mkdir()
            (live / "SKILL.md").write_text("in flight")

            self.install.copy_skill(src, dest)

            self.assertTrue((live / "SKILL.md").exists())

    def test_keeps_a_young_leftover_named_for_our_own_pid(self):
        # Pids are reused: a crashed run's backup can carry the pid this run
        # would use. Deleting it before the copy can destroy the only copy of
        # the previous install, so the backup name must be this run's alone.
        # The install has to be there for this run to park it: without one
        # nothing writes the name the leftover carries, and the leftover
        # survives for a reason that has nothing to do with the collision.
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            dest.mkdir()
            skill_dest = dest / "complete-codebase-review"
            skill_dest.mkdir()
            (skill_dest / "SKILL.md").write_text("installed")
            crashed = dest / (self.install.PREVIOUS_PREFIX + str(os.getpid()))
            crashed.mkdir()
            (crashed / "SKILL.md").write_text("survivor")

            self.install.copy_skill(src, dest)

            # The install went in, so this run did park the old tree under a
            # name of its own and never touched the crashed one.
            self.assertTrue((skill_dest / "SKILL.md").exists())
            self.assertEqual(
                (crashed / "SKILL.md").read_text(encoding="utf-8"),
                "survivor",
            )

    def test_keeps_a_link_like_leftover_the_age_rule_would_delete(self):
        # A parked link keeps the age of the link the user configured: a
        # link's own timestamp cannot be refreshed on every platform, so the
        # age rule would delete a rollback copy while the install that parked
        # it is still running.
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "dest"
            dest.mkdir()
            outside = Path(tmpdir) / "outside"
            outside.mkdir()
            parked = dest / (self.install.PREVIOUS_PREFIX + "123-abc")
            try:
                create_directory_link(parked, outside)
            except OSError as exc:
                self.skipTest("cannot create a directory link: " + str(exc))
            real_time = self.install.time.time
            # Push the clock past the liveness window so the age rule would
            # select the parked link.
            with patch.object(
                    self.install.time, "time",
                    lambda: real_time() + self.install.LEFTOVER_MAX_AGE_SEC + 60):
                self.install._sweep_leftovers(dest)

            self.assertTrue(parked.exists())
            # An explicit uninstall still removes it.
            self.install._sweep_leftovers(dest, max_age=0)
            self.assertFalse(parked.exists())

    def test_update_leaves_no_previous_tree_behind(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            self.install.copy_skill(src, dest)
            (src / "SKILL.md").write_text("name: updated")
            self.install.copy_skill(src, dest)

            self.assertEqual(
                [p.name for p in dest.iterdir() if p.name.startswith(".")],
                [],
            )
            self.assertEqual(
                (dest / "complete-codebase-review" / "SKILL.md").read_text(
                    encoding="utf-8"),
                "name: updated",
            )

    def test_failed_swap_restores_previous_install(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            skill_dest = dest / "complete-codebase-review"
            skill_dest.mkdir(parents=True)
            (skill_dest / "SKILL.md").write_text("old install")

            real_replace = self.install.os.replace

            def swap_refused(source, target):
                if self.install.STAGING_PREFIX in str(source):
                    raise OSError("swap refused")
                return real_replace(source, target)

            with patch.object(self.install.os, "replace", swap_refused):
                with self.assertRaises(OSError):
                    self.install.copy_skill(src, dest)

            self.assertEqual(
                (skill_dest / "SKILL.md").read_text(encoding="utf-8"),
                "old install",
            )

    def test_failed_swap_restores_a_link_like_install(self):
        # A link is parked rather than deleted, so a failed swap leaves the
        # user's configured path in place and the link's target untouched.
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            root = Path(tmpdir)
            dest = root / "dest"
            dest.mkdir()
            external = root / "external"
            external.mkdir()
            (external / "SKILL.md").write_text("external", encoding="utf-8")
            skill_dest = dest / "complete-codebase-review"
            try:
                create_directory_link(skill_dest, external)
            except OSError as exc:
                self.skipTest("directory links unavailable: " + str(exc))

            real_replace = self.install.os.replace

            def swap_refused(source, target):
                if self.install.STAGING_PREFIX in str(source):
                    raise OSError("swap refused")
                return real_replace(source, target)

            with patch.object(self.install.os, "replace", swap_refused):
                with self.assertRaises(OSError):
                    self.install.copy_skill(src, dest)

            self.assertTrue(self.install._is_link_like(skill_dest))
            self.assertEqual(
                (external / "SKILL.md").read_text(encoding="utf-8"),
                "external",
            )

    def test_parked_previous_tree_is_stamped(self):
        # A rename keeps the tree's old mtime, which makes the live backup
        # look like a crashed run's leftover to a concurrent age-based sweep.
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            self.install.copy_skill(src, dest)
            skill_dest = dest / "complete-codebase-review"
            old = time.time() - self.install.LEFTOVER_MAX_AGE_SEC - 60
            os.utime(str(skill_dest), (old, old))

            ages = []
            real_remove = self.install._remove_tree

            def spy(path):
                if Path(path).name.startswith(self.install.PREVIOUS_PREFIX):
                    ages.append(time.time() - Path(path).lstat().st_mtime)
                return real_remove(path)

            with patch.object(self.install, "_remove_tree", spy):
                self.install.copy_skill(src, dest)
            self.assertEqual(len(ages), 1)
            self.assertLess(ages[0], self.install.LEFTOVER_MAX_AGE_SEC)

    def test_previous_tree_is_stamped_before_the_rename(self):
        # A concurrent sweep judges age from the mtime the parked entry has
        # when it appears. Refreshing that mtime after the rename leaves a
        # window in which the backup still carries the old install's age and
        # can be swept away, so the stamp must happen while the tree is still
        # at its live name.
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            self.install.copy_skill(src, dest)
            old = time.time() - self.install.LEFTOVER_MAX_AGE_SEC - 60
            os.utime(str(dest / "complete-codebase-review"), (old, old))

            ages = []
            real_replace = os.replace

            def spy(src_path, dst_path):
                if Path(dst_path).name.startswith(
                    self.install.PREVIOUS_PREFIX
                ):
                    ages.append(
                        time.time() - Path(src_path).lstat().st_mtime
                    )
                return real_replace(src_path, dst_path)

            with patch.object(self.install.os, "replace", spy):
                self.install.copy_skill(src, dest)
            self.assertEqual(len(ages), 1)
            self.assertLess(ages[0], self.install.LEFTOVER_MAX_AGE_SEC)

    def test_failed_stamp_leaves_the_live_install_in_place(self):
        # Parking a tree with its old mtime lets a concurrent sweep delete the
        # only rollback copy, so a failed stamp must abort before the move.
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            self.install.copy_skill(src, dest)
            skill_dest = dest / "complete-codebase-review"
            real_utime = os.utime

            def refuse_park(path, *args, **kwargs):
                if Path(path) in (skill_dest, skill_dest.resolve()):
                    raise OSError("stamp denied")
                return real_utime(path, *args, **kwargs)

            with patch.object(self.install.os, "utime", refuse_park):
                with self.assertRaises(OSError) as caught:
                    self.install.copy_skill(src, dest)
            self.assertIn("mtime", str(caught.exception))
            self.assertTrue((skill_dest / "SKILL.md").exists())
            self.assertEqual(
                list(dest.glob(self.install.PREVIOUS_PREFIX + "*")), []
            )

    def test_a_long_copy_keeps_its_staging_tree_alive(self):
        # The sweep that clears a crashed run's leftovers judges a tree by
        # age: anything older than an hour is assumed to belong to a dead
        # run. A copy that takes over an hour leaves the staging tree
        # looking stale, so a concurrent install's sweep deletes it while
        # the copy is still writing, and the copy fails on a file that was
        # there a moment ago. The staging tree's mtime is refreshed as the
        # copy goes, so the sweep sees a live run.
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            dest.mkdir()
            real_copytree = self.install.shutil.copytree
            real_copy2 = self.install.shutil.copy2
            state = {"swept": False, "staging": None}

            def aging_copy2(src_file, dst_file, **copy_kwargs):
                result = real_copy2(src_file, dst_file, **copy_kwargs)
                # The copy of this file took over an hour, so the staging
                # tree looks stale by now.
                old = time.time() - self.install.LEFTOVER_MAX_AGE_SEC - 60
                os.utime(str(state["staging"]), (old, old))
                return result

            def slow_copytree(source, target, **kwargs):
                state["staging"] = Path(target)
                inner = kwargs.pop(
                    "copy_function", self.install.shutil.copy2
                )

                def copy_one(src_file, dst_file, **inner_kwargs):
                    result = inner(src_file, dst_file, **inner_kwargs)
                    # A concurrent install sweeps the leftovers while this
                    # copy is still running.
                    self.install._sweep_leftovers(dest)
                    state["swept"] = True
                    return result

                kwargs["copy_function"] = copy_one
                return real_copytree(source, target, **kwargs)

            with patch.object(self.install.shutil, "copytree", slow_copytree), \
                 patch.object(self.install.shutil, "copy2", aging_copy2):
                self.install.copy_skill(src, dest)

            # The sweep ran while the copy was in flight.
            self.assertTrue(state["swept"])
            # The install went in: the sweep did not delete the staging
            # tree out from under the copy.
            self.assertTrue(
                (dest / "complete-codebase-review" / "SKILL.md").exists()
            )

    def test_a_concurrent_park_leaves_the_older_backup_alone(self):
        # Two installs overlap. The second one parks the tree the first
        # one just put in place, so the live install is briefly missing.
        # The first run must not put its own older backup back in that
        # gap: the backup predates the tree the second run parked, and
        # restoring it leaves the stale version installed. The backup
        # stays a leftover for the next run's sweep instead.
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            dest = Path(tmpdir) / "dest"
            dest.mkdir()
            skill_dest = dest / "complete-codebase-review"
            skill_dest.mkdir()
            (skill_dest / "SKILL.md").write_text(
                "old install", encoding="utf-8"
            )
            real_replace = os.replace
            state = {"parked": False}

            def replacing(source, target):
                if (
                    Path(source).name.startswith(self.install.STAGING_PREFIX)
                    and Path(target) == skill_dest
                ):
                    # This run's swap lands, and a second install parks the
                    # live tree straight away: the live install is missing
                    # and the second run is about to put its own tree
                    # there.
                    real_replace(source, target)
                    real_replace(
                        str(skill_dest),
                        str(dest / (
                            self.install.PREVIOUS_PREFIX + "second-run"
                        )),
                    )
                    state["parked"] = True
                    return
                return real_replace(source, target)

            with patch.object(self.install.os, "replace", replacing):
                self.install.copy_skill(src, dest)

            self.assertTrue(state["parked"])
            # Nothing was put back over the gap the second install left.
            self.assertFalse(os.path.lexists(skill_dest))
            # The older backup is still there, as a leftover.
            old_backups = [
                path for path in dest.glob(self.install.PREVIOUS_PREFIX + "*")
                if (path / "SKILL.md").read_text(encoding="utf-8")
                == "old install"
            ]
            self.assertEqual(len(old_backups), 1)

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

    def test_copy_skill_skips_foreign_skills_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir, {
                ".skills-index.json": '{"skills": []}',
                "skills/review/SKILL.md": "name: review",
            })
            dest = Path(tmpdir) / "dest"
            result = self.install.copy_skill(src, dest)

            self.assertFalse((result / ".skills-index.json").exists())
            self.assertTrue((result / "SKILL.md").exists())
            self.assertTrue((result / "skills" / "review" / "SKILL.md").exists())

    def test_copy_skill_normal_tree_copies_nested_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir, {
                "ccr/pipeline.json": "{}",
                "skills/review/SKILL.md": "name: review",
                "helpers/note.md": "# Note",
            })
            dest = Path(tmpdir) / "dest"
            result = self.install.copy_skill(src, dest)

            self.assertTrue((result / "SKILL.md").exists())
            self.assertTrue((result / "README.md").exists())
            self.assertTrue((result / "ccr" / "pipeline.json").exists())
            self.assertTrue((result / "skills" / "review" / "SKILL.md").exists())
            self.assertTrue((result / "helpers" / "note.md").exists())

    def test_sweep_refuses_a_link_like_target(self):
        # A directory swapped for a link must not send the sweep through it
        # and delete same-named trees inside the link's target.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            real = root / "external"
            (real / (self.install.STAGING_PREFIX + "1")).mkdir(parents=True)
            link = root / "dest"
            try:
                create_directory_link(link, real)
            except OSError as exc:
                self.skipTest("directory links unavailable: " + str(exc))
            with patch.object(self.install.sys, "stdout",
                              new_callable=io.StringIO):
                self.assertFalse(
                    self.install._sweep_leftovers(link, max_age=0)
                )
            self.assertTrue(
                (real / (self.install.STAGING_PREFIX + "1")).exists()
            )

    def test_link_like_dest_dir_is_refused(self):
        # A link at the destination would move the containment root onto its
        # target, so the old install would be deleted from there.
        with tempfile.TemporaryDirectory() as tmpdir:
            src = self._make_src(tmpdir)
            root = Path(tmpdir)
            external = root / "external"
            (external / "complete-codebase-review").mkdir(parents=True)
            sentinel = external / "complete-codebase-review" / "SKILL.md"
            sentinel.write_text("external sentinel", encoding="utf-8")
            try:
                create_directory_link(root / "dest", external)
            except OSError as exc:
                self.skipTest("directory links unavailable: " + str(exc))
            with patch.object(self.install.sys, "stdout", new_callable=io.StringIO):
                with self.assertRaises(ValueError) as ctx:
                    self.install.copy_skill(src, root / "dest")
            self.assertIn("link-like target", str(ctx.exception))
            self.assertEqual(
                sentinel.read_text(encoding="utf-8"), "external sentinel")

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

    def test_detected_but_failed_reports_failure_message(self):
        fake_dirs = {"Claude Code": Path("/home/user/.claude/skills")}
        existing = {p.parent for p in fake_dirs.values()}

        with patch.object(self.install, "get_target_dirs",
                          return_value=fake_dirs), \
             patch.object(self.install, "copy_skill",
                          side_effect=OSError("boom")), \
             patch.object(self.install, "_run_local_fallback"), \
             patch.object(self.install.sys, "stdout",
                          new_callable=io.StringIO) as mock_stdout:
            with patch.object(Path, "exists", lambda p: p in existing):
                self.install.main()

        self.assertIn("No detected installations succeeded", mock_stdout.getvalue())

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

class TestInstallEscapedSymlinkValidation(unittest.TestCase):
    """A link resolving outside the skill dir aborts the install and cleanup.

    ``_ignore_skill_files`` keeps links out of the copy, but the validator is
    the last line of defence: a tree that already holds an escaping link must
    be refused, and the partial install must not survive the refusal.
    """

    def setUp(self):
        self.install = _import_install()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.outside = self.root / "outside"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text(
            "must not ship", encoding="utf-8"
        )

    def _tree_with_escaping_link(self):
        skill_dest = self.root / "complete-codebase-review"
        (skill_dest / "skills").mkdir(parents=True)
        (skill_dest / "SKILL.md").write_text("name: test", encoding="utf-8")
        try:
            create_directory_link(skill_dest / "skills" / "escape", self.outside)
        except OSError as exc:
            self.skipTest("directory links unavailable: " + str(exc))
        return skill_dest

    def test_link_pointing_outside_is_refused(self):
        skill_dest = self._tree_with_escaping_link()
        with self.assertRaises(ValueError) as ctx:
            self.install._validate_no_escaped_symlinks(skill_dest)
        message = str(ctx.exception)
        self.assertIn("points outside skill dir", message)
        self.assertIn("escape", message)

    def test_refused_tree_is_removed_but_link_target_survives(self):
        skill_dest = self._tree_with_escaping_link()
        with self.assertRaises(ValueError):
            self.install._validate_no_escaped_symlinks(skill_dest)
        self.assertFalse(skill_dest.exists())
        self.assertTrue((self.outside / "secret.txt").exists())


class TestUninstallLinkLikeSkills(_BaseInstallTest):
    """--uninstall must not follow a junctioned or symlinked .skills."""

    def test_link_like_skills_is_refused_and_target_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            installed = outside / "complete-codebase-review"
            installed.mkdir(parents=True)
            (installed / "SKILL.md").write_text("keep me", encoding="utf-8")
            cwd = root / "work"
            cwd.mkdir()
            try:
                create_directory_link(cwd / ".skills", outside)
            except OSError as exc:
                self.skipTest("directory links unavailable: " + str(exc))
            old = os.getcwd()
            try:
                os.chdir(str(cwd))
                with patch.object(self.install, "get_target_dirs",
                                  return_value={}), \
                     patch("sys.argv", ["install.py", "--uninstall"]), \
                     patch.object(self.install.sys, "stdout",
                                  new_callable=io.StringIO) as out:
                    code = self.install.main()
            finally:
                os.chdir(old)
            self.assertEqual(code, 1)
            self.assertIn("Uninstall incomplete", out.getvalue())
            self.assertTrue((installed / "SKILL.md").exists())


class TestUninstallSwappedTargetDirectory(_BaseInstallTest):
    """A target swapped for a link after validation must not be followed.

    ``_run_uninstall`` validates ``.skills`` and then ``remove_skill`` looks
    at it again; between the two the directory can be replaced by a link to
    an external tree. The containment root must not follow that link, and the
    recursive delete must be refused.
    """

    def test_swapped_skills_is_refused_and_external_tree_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "work"
            skills = work / ".skills"
            local = skills / "complete-codebase-review"
            local.mkdir(parents=True)
            (local / "SKILL.md").write_text("local", encoding="utf-8")
            external = root / "external"
            (external / "complete-codebase-review").mkdir(parents=True)
            sentinel = external / "complete-codebase-review" / "SKILL.md"
            sentinel.write_text("external sentinel", encoding="utf-8")
            install = self.install
            resolve = install._resolve_local_skills

            def resolve_then_swap():
                resolved = resolve()
                skills.rename(work / ".skills-moved")
                try:
                    create_directory_link(skills, external)
                except OSError as exc:
                    self.skipTest("directory links unavailable: " + str(exc))
                return resolved

            old = os.getcwd()
            try:
                os.chdir(str(work))
                with patch.object(install, "_resolve_local_skills",
                                  resolve_then_swap), \
                     patch.object(install, "get_target_dirs",
                                  return_value={}), \
                     patch.object(install.sys, "stdout",
                                  new_callable=io.StringIO) as out:
                    code = install._run_uninstall(None, False)
            finally:
                os.chdir(old)
            self.assertEqual(
                sentinel.read_text(encoding="utf-8"), "external sentinel")
            self.assertEqual(code, 1)
            self.assertIn("Uninstall incomplete", out.getvalue())


class TestLocalFallbackLinkLikeSkills(_BaseInstallTest):
    """_run_local_fallback must refuse a junctioned or symlinked .skills."""

    def test_link_like_skills_refused_before_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            src = root / "src"
            src.mkdir()
            (src / "SKILL.md").write_text("body", encoding="utf-8")
            work = root / "work"
            work.mkdir()
            try:
                create_directory_link(work / ".skills", outside)
            except OSError as exc:
                self.skipTest("directory links unavailable: " + str(exc))
            old = os.getcwd()
            try:
                os.chdir(str(work))
                with patch.object(self.install.sys, "stdout",
                                  new_callable=io.StringIO) as out:
                    with self.assertRaises(SystemExit) as ctx:
                        self.install._run_local_fallback(src, False)
            finally:
                os.chdir(old)
            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("Local installation failed", out.getvalue())
            self.assertEqual(list(outside.iterdir()), [])


class TestLocalSkillsPointingAtWorkingTree(_BaseInstallTest):
    """A .skills link to the working tree is refused by install and uninstall."""

    def _work_tree(self, tmp):
        work = Path(tmp) / "work"
        work.mkdir()
        (work / "SKILL.md").write_text("repo sentinel", encoding="utf-8")
        try:
            create_directory_link(work / ".skills", work)
        except OSError as exc:
            self.skipTest("directory links unavailable: " + str(exc))
        return work

    def test_install_refused_and_tree_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = self._work_tree(tmp)
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "SKILL.md").write_text("body", encoding="utf-8")
            old = os.getcwd()
            try:
                os.chdir(str(work))
                with patch.object(self.install.sys, "stdout",
                                  new_callable=io.StringIO) as out:
                    with self.assertRaises(SystemExit) as ctx:
                        self.install._run_local_fallback(src, False)
            finally:
                os.chdir(old)
            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("Local installation failed", out.getvalue())
            self.assertIn("link-like .skills", out.getvalue())
            self.assertFalse((work / "complete-codebase-review").exists())
            self.assertTrue((work / "SKILL.md").exists())

    def test_uninstall_refused_and_tree_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = self._work_tree(tmp)
            old = os.getcwd()
            try:
                os.chdir(str(work))
                with patch.object(self.install, "get_target_dirs",
                                  return_value={}), \
                     patch("sys.argv", ["install.py", "--uninstall"]), \
                     patch.object(self.install.sys, "stdout",
                                  new_callable=io.StringIO) as out:
                    code = self.install.main()
            finally:
                os.chdir(old)
            self.assertEqual(code, 1)
            self.assertIn("Uninstall incomplete", out.getvalue())
            self.assertIn("link-like .skills", out.getvalue())
            self.assertTrue((work / "SKILL.md").exists())
            self.assertFalse((work / "complete-codebase-review").exists())

    def test_ancestor_target_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            sentinel = Path(tmp) / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            try:
                create_directory_link(work / ".skills", Path(tmp))
            except OSError as exc:
                self.skipTest("directory links unavailable: " + str(exc))
            old = os.getcwd()
            try:
                os.chdir(str(work))
                # _validate_target_path rejects the escape on its own, so stub
                # it out (as the link-like check is stubbed) to keep the
                # resolved-ancestor guard the branch under test.
                with patch.object(self.install, "_is_link_like",
                                  return_value=False), \
                        patch.object(self.install, "_validate_target_path",
                                     side_effect=lambda path: path.resolve()):
                    with self.assertRaises(ValueError) as ctx:
                        self.install._resolve_local_skills()
            finally:
                os.chdir(old)
            self.assertIn("working directory or a parent", str(ctx.exception))
            self.assertTrue(sentinel.is_file())
            self.assertFalse((Path(tmp) / "complete-codebase-review").exists())

    def test_working_tree_target_is_refused_without_the_link_check(self):
        # The link-like rejection runs first; patch it off to keep the
        # cwd/ancestor guard exercised on its own.
        with tempfile.TemporaryDirectory() as tmp:
            work = self._work_tree(tmp)
            old = os.getcwd()
            try:
                os.chdir(str(work))
                with patch.object(self.install, "_is_link_like",
                                  return_value=False):
                    with self.assertRaises(ValueError) as ctx:
                        self.install._resolve_local_skills()
            finally:
                os.chdir(old)
            self.assertIn("working directory or a parent", str(ctx.exception))


class TestLocalSkillsPointingAtCheckoutChild(_BaseInstallTest):
    """A .skills link to a child of the checkout is refused, not followed."""

    def _work_tree(self, tmp):
        work = Path(tmp) / "work"
        child = work / "source"
        child.mkdir(parents=True)
        (child / "SKILL.md").write_text("source sentinel", encoding="utf-8")
        installed = child / "complete-codebase-review"
        installed.mkdir()
        (installed / "SKILL.md").write_text("installed sentinel",
                                            encoding="utf-8")
        try:
            create_directory_link(work / ".skills", child)
        except OSError as exc:
            self.skipTest("directory links unavailable: " + str(exc))
        return work, child

    def test_install_refused_and_tree_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, child = self._work_tree(tmp)
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "SKILL.md").write_text("body", encoding="utf-8")
            old = os.getcwd()
            try:
                os.chdir(str(work))
                with patch.object(self.install.sys, "stdout",
                                  new_callable=io.StringIO) as out:
                    with self.assertRaises(SystemExit) as ctx:
                        self.install._run_local_fallback(src, False)
            finally:
                os.chdir(old)
            self.assertEqual(ctx.exception.code, 1)
            self.assertIn("Local installation failed", out.getvalue())
            self.assertIn("link-like .skills", out.getvalue())
            self.assertTrue((child / "SKILL.md").exists())
            self.assertEqual(
                (child / "complete-codebase-review" / "SKILL.md").read_text(
                    encoding="utf-8"),
                "installed sentinel",
            )

    def test_uninstall_refused_and_tree_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, child = self._work_tree(tmp)
            old = os.getcwd()
            try:
                os.chdir(str(work))
                with patch.object(self.install, "get_target_dirs",
                                  return_value={}), \
                     patch("sys.argv", ["install.py", "--uninstall"]), \
                     patch.object(self.install.sys, "stdout",
                                  new_callable=io.StringIO) as out:
                    code = self.install.main()
            finally:
                os.chdir(old)
            self.assertEqual(code, 1)
            self.assertIn("Uninstall incomplete", out.getvalue())
            self.assertIn("link-like .skills", out.getvalue())
            self.assertTrue(
                (child / "complete-codebase-review" / "SKILL.md").exists())


class TestCredentialName(_BaseInstallTest):
    """Credential stores must never be copied into a skill directory."""

    MATCHES = (
        ".git-credentials", ".npmrc", ".pypirc", ".htpasswd",
        "foo.keystore", "bar.jks", "id_rsa", ".env.local", "server.pem",
    )
    NON_MATCHES = (".gitignore", "notes.txt", "README.md")

    def test_credential_names_match(self):
        for name in self.MATCHES:
            with self.subTest(name=name):
                self.assertTrue(self.install._is_credential_name(name))

    def test_ordinary_names_do_not_match(self):
        for name in self.NON_MATCHES:
            with self.subTest(name=name):
                self.assertFalse(self.install._is_credential_name(name))


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

    def test_remove_tree_removes_a_directory_link(self):
        # Windows refuses os.unlink on a junction or a directory symlink, so
        # the link must be removed through its reparse point and its target
        # left alone.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "target"
            target.mkdir()
            (target / "keep.txt").write_text("keep", encoding="utf-8")
            link = root / "link"
            try:
                create_directory_link(link, target)
            except OSError as exc:
                self.skipTest("directory links unavailable: " + str(exc))
            self.install._remove_tree(link)
            self.assertFalse(os.path.lexists(str(link)))
            self.assertTrue((target / "keep.txt").exists())

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


class TestChecksumFunctions(unittest.TestCase):
    """Tests for _compute_sha256 and _verify_checksum functions."""

    def setUp(self):
        self.install = _import_install()

    def test_compute_sha256_returns_hex_string(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            temp_path = f.name
        try:
            result = self.install._compute_sha256(Path(temp_path))
            self.assertEqual(len(result), 64)
            self.assertRegex(result, r'^[a-f0-9]+$')
        finally:
            Path(temp_path).unlink()

    def test_compute_sha256_consistent_hash(self):
        content = b"test content for hashing"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            temp_path = f.name
        try:
            hash1 = self.install._compute_sha256(Path(temp_path))
            hash2 = self.install._compute_sha256(Path(temp_path))
            self.assertEqual(hash1, hash2)
        finally:
            Path(temp_path).unlink()

    def test_verify_checksum_returns_true_for_valid_hash(self):
        content = b"test content"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            temp_path = f.name
        try:
            expected_hash = self.install._compute_sha256(Path(temp_path))
            result = self.install._verify_checksum(Path(temp_path), expected_hash)
            self.assertTrue(result)
        finally:
            Path(temp_path).unlink()

    def test_verify_checksum_returns_false_for_invalid_hash(self):
        content = b"test content"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            temp_path = f.name
        try:
            invalid_hash = "0" * 64
            result = self.install._verify_checksum(Path(temp_path), invalid_hash)
            self.assertFalse(result)
        finally:
            Path(temp_path).unlink()

    def test_verify_checksum_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.install._verify_checksum(Path("/nonexistent/file.txt"), "abc123")

    def test_verify_checksum_case_insensitive(self):
        content = b"test"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            temp_path = f.name
        try:
            expected_hash = self.install._compute_sha256(Path(temp_path))
            upper_hash = expected_hash.upper()
            result = self.install._verify_checksum(Path(temp_path), upper_hash)
            self.assertTrue(result)
        finally:
            Path(temp_path).unlink()


class TestIsSha256(_BaseInstallTest):
    """Tests for the shared 64-hex checksum validator."""

    def test_accepts_lowercase_and_uppercase_hex(self):
        self.assertTrue(self.install._is_sha256("0" * 64))
        self.assertTrue(self.install._is_sha256("aB" * 32))

    def test_rejects_wrong_length(self):
        self.assertFalse(self.install._is_sha256(""))
        self.assertFalse(self.install._is_sha256("0" * 63))
        self.assertFalse(self.install._is_sha256("0" * 65))

    def test_rejects_non_hex_characters(self):
        self.assertFalse(self.install._is_sha256("g" * 64))
        self.assertFalse(self.install._is_sha256("0" * 63 + " "))


class TestChecksumFormatValidation(_BaseInstallTest):
    """--checksum rejects malformed input before any file is verified."""

    def test_invalid_checksum_format_exits_with_unchanged_message(self):
        bad_inputs = ["", "short", "xyz" * 30, "g" * 64]
        for bad in bad_inputs:
            with self.subTest(input=bad):
                with patch("sys.argv", ["install.py", "--checksum", bad]), \
                     patch("sys.stdout", new_callable=io.StringIO) as mock_stdout, \
                     patch.object(self.install, "_verify_checksum") as mock_verify:
                    with self.assertRaises(SystemExit) as ctx:
                        self.install.main()
                self.assertEqual(ctx.exception.code, 1)
                self.assertIn(
                    "Invalid checksum format (expected 64 hexadecimal characters)",
                    mock_stdout.getvalue(),
                )
                mock_verify.assert_not_called()


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


class TestIgnoreSkillFiles(unittest.TestCase):
    """Installer copy filter drops artifacts and dev-only paths."""

    def test_skips_artifacts(self):
        install_mod = _import_install()
        names = [
            "SKILL.md", "install.py", "tools", "tests", "__pycache__",
            "x.pyc", "pkg.egg-info", ".coverage", ".git",
        ]
        kept = install_mod._ignore_skill_files(".", names)
        self.assertNotIn("SKILL.md", kept)
        for ignored in ("install.py", "tools", "tests", "__pycache__",
                        "x.pyc", "pkg.egg-info", ".coverage", ".git"):
            self.assertIn(ignored, kept)

    def test_keeps_runtime_content(self):
        install_mod = _import_install()
        names = ["SKILL.md", "karpathy-guidelines.md", "helpers", "skills", "ccr",
                 "LICENSE"]
        self.assertEqual(install_mod._ignore_skill_files(".", names), [])

    def test_skips_audit_and_coverage_artifacts(self):
        install_mod = _import_install()
        names = [
            "CCR_REPORT.md", "ARCH_QUALITY_FINDINGS.md", "coverage.json",
            "coverage_report.txt", "coverage_run.txt", ".gitmessage",
        ]
        kept = install_mod._ignore_skill_files(".", names)
        for name in names:
            self.assertIn(name, kept)

    def test_skips_foreign_skills_index(self):
        install_mod = _import_install()
        kept = install_mod._ignore_skill_files(
            ".", [".skills-index.json", "SKILL.md"]
        )
        self.assertIn(".skills-index.json", kept)
        self.assertNotIn("SKILL.md", kept)

    def test_skips_local_environments_and_build_output(self):
        install_mod = _import_install()
        names = [".venv", "venv", "node_modules", "build", "dist",
                 "htmlcov", ".mypy_cache", ".pytest_cache"]
        kept = install_mod._ignore_skill_files(".", names)
        for name in names:
            self.assertIn(name, kept)

    def test_skips_credential_variants(self):
        install_mod = _import_install()
        names = [".env.local", ".env.production", "credentials.json",
                 "credentials", ".aws", ".ssh",
                 "id_rsa", "id_rsa_work", "id_ed25519_personal",
                 "server.pem", "client.key", "SKILL.md"]
        kept = install_mod._ignore_skill_files(".", names)
        for name in names[:-1]:
            self.assertIn(name, kept)
        self.assertNotIn("SKILL.md", kept)

    def test_skips_installer_sidecar(self):
        install_mod = _import_install()
        kept = install_mod._ignore_skill_files(".", ["install.py.sha256"])
        self.assertIn("install.py.sha256", kept)

    def test_skips_symlinked_entries(self):
        install_mod = _import_install()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
            link = root / "deploy-notes.txt"
            try:
                link.symlink_to(root / ".env")
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation needs privilege here")
            kept = install_mod._ignore_skill_files(str(root), ["deploy-notes.txt"])
            self.assertIn("deploy-notes.txt", kept)


class TestCcrHint(unittest.TestCase):
    """The post-install hint explains how to run the bundled module."""

    def test_hint_covers_both_shells(self):
        install_mod = _import_install()
        buffer = io.StringIO()
        with patch("sys.stdout", buffer):
            install_mod._print_ccr_hint()
        text = buffer.getvalue()
        self.assertIn("PYTHONPATH", text)
        self.assertIn("PowerShell", text)
        self.assertIn("python -m ccr", text)


if __name__ == "__main__":
    unittest.main()

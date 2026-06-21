"""Smoke tests for install.py — subprocess CLI checks.

Runs install.py with various flags and asserts exit codes/output.
No mocking — tests the real entry point as a user would invoke it.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

INSTALL_PY = str(Path(__file__).resolve().parent.parent / "install.py")
PYTHON = sys.executable


class TestSmokeHelp(unittest.TestCase):
    """Tests for --help and -h flags."""

    @classmethod
    def setUpClass(cls):
        cls.help_result = subprocess.run(
            [PYTHON, INSTALL_PY, "--help"],
            capture_output=True, text=True
        )

    def test_help_exits_zero(self):
        self.assertEqual(self.help_result.returncode, 0)

    def test_help_contains_description(self):
        self.assertIn(
            "Install the Complete Codebase Review skill", self.help_result.stdout
        )

    def test_help_contains_examples(self):
        self.assertIn("Examples:", self.help_result.stdout)

    def test_short_help_equivalent(self):
        short_help = subprocess.run(
            [PYTHON, INSTALL_PY, "-h"],
            capture_output=True, text=True
        )
        self.assertEqual(self.help_result.stdout, short_help.stdout)

    def test_stderr_empty_on_help(self):
        self.assertEqual(self.help_result.stderr, "")


class TestSmokeVersion(unittest.TestCase):
    """Tests for --version and -V flags."""

    @classmethod
    def setUpClass(cls):
        cls.version_result = subprocess.run(
            [PYTHON, INSTALL_PY, "--version"],
            capture_output=True, text=True
        )

    def test_version_exits_zero(self):
        self.assertEqual(self.version_result.returncode, 0)

    def test_version_prints_version_string(self):
        self.assertIn(
            "complete-codebase-review v", self.version_result.stdout
        )

    def test_short_version_equivalent(self):
        short_v = subprocess.run(
            [PYTHON, INSTALL_PY, "-V"],
            capture_output=True, text=True
        )
        self.assertEqual(self.version_result.stdout, short_v.stdout)

    def test_stderr_empty_on_version(self):
        self.assertEqual(self.version_result.stderr, "")


class TestSmokeDryRun(unittest.TestCase):
    """Tests for --dry-run and -n flags."""

    @classmethod
    def setUpClass(cls):
        cls.dry_run_result = subprocess.run(
            [PYTHON, INSTALL_PY, "--dry-run"],
            capture_output=True, text=True
        )

    def test_dry_run_exits_zero(self):
        self.assertEqual(self.dry_run_result.returncode, 0)

    def test_dry_run_prints_message(self):
        self.assertIn("Dry run complete", self.dry_run_result.stdout)

    def test_dry_run_does_not_print_installation_complete(self):
        self.assertNotIn("Installation complete", self.dry_run_result.stdout)

    def test_short_dry_run_flag(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "-n"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_stderr_empty_on_dry_run(self):
        self.assertEqual(self.dry_run_result.stderr, "")


class TestSmokeTargetPath(unittest.TestCase):
    """Tests for --target path validation."""

    def test_target_traversal_rejected(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--target", "../evil"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 1)

    def test_target_traversal_prints_error(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--target", "../evil"],
            capture_output=True, text=True
        )
        self.assertIn("Path traversal", result.stdout)


class TestNoColorEnv(unittest.TestCase):
    """Tests for NO_COLOR env var suppressing ANSI codes."""

    def _no_color_env(self):
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        return env

    def test_no_color_suppresses_ansi(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--dry-run"],
            capture_output=True, text=True, env=self._no_color_env()
        )
        self.assertNotIn("\033[", result.stdout)

    def test_no_color_still_outputs_text(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--dry-run"],
            capture_output=True, text=True, env=self._no_color_env()
        )
        self.assertIn("Dry run complete", result.stdout)


if __name__ == "__main__":
    unittest.main()

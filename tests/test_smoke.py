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

    def test_help_exits_zero(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--help"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_help_contains_description(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--help"],
            capture_output=True, text=True
        )
        self.assertIn("Install the Complete Codebase Review skill", result.stdout)

    def test_help_contains_examples(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--help"],
            capture_output=True, text=True
        )
        self.assertIn("Examples:", result.stdout)

    def test_short_help_equivalent(self):
        long_help = subprocess.run(
            [PYTHON, INSTALL_PY, "--help"],
            capture_output=True, text=True
        )
        short_help = subprocess.run(
            [PYTHON, INSTALL_PY, "-h"],
            capture_output=True, text=True
        )
        self.assertEqual(long_help.stdout, short_help.stdout)

    def test_stderr_empty_on_help(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--help"],
            capture_output=True, text=True
        )
        self.assertEqual(result.stderr, "")


class TestSmokeVersion(unittest.TestCase):
    """Tests for --version and -V flags."""

    def test_version_exits_zero(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--version"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_version_prints_version_string(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--version"],
            capture_output=True, text=True
        )
        self.assertIn("complete-codebase-review v", result.stdout)

    def test_short_version_equivalent(self):
        long_v = subprocess.run(
            [PYTHON, INSTALL_PY, "--version"],
            capture_output=True, text=True
        )
        short_v = subprocess.run(
            [PYTHON, INSTALL_PY, "-V"],
            capture_output=True, text=True
        )
        self.assertEqual(long_v.stdout, short_v.stdout)

    def test_stderr_empty_on_version(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--version"],
            capture_output=True, text=True
        )
        self.assertEqual(result.stderr, "")


class TestSmokeDryRun(unittest.TestCase):
    """Tests for --dry-run and -n flags."""

    def test_dry_run_exits_zero(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--dry-run"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_dry_run_prints_message(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--dry-run"],
            capture_output=True, text=True
        )
        self.assertIn("Dry run complete", result.stdout)

    def test_dry_run_does_not_print_installation_complete(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--dry-run"],
            capture_output=True, text=True
        )
        self.assertNotIn("Installation complete", result.stdout)

    def test_short_dry_run_flag(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "-n"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_stderr_empty_on_dry_run(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--dry-run"],
            capture_output=True, text=True
        )
        self.assertEqual(result.stderr, "")


class TestSmokeTargetPath(unittest.TestCase):
    """Tests for --target path validation."""

    def test_target_traversal_rejected(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--target", "../evil"],
            capture_output=True, text=True
        )
        self.assertNotEqual(result.returncode, 0)

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

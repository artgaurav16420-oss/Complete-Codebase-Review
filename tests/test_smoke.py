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
        self.assertEqual(short_help.returncode, 0)
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
        self.assertEqual(short_v.returncode, 0)
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


class TestChecksumVerification(unittest.TestCase):
    """Tests for --checksum and --self-verify flags."""

    def test_self_verify_passes(self):
        """Verify --self-verify succeeds with valid checksum."""
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--self-verify"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Checksum verification passed", result.stdout)

    def test_self_verify_with_missing_checksum_file_fails(self):
        """Verify --self-verify fails when checksum file is missing."""
        import tempfile
        import shutil
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_install = Path(tmpdir) / "install.py"
            shutil.copy(INSTALL_PY, tmp_install)
            result = subprocess.run(
                [PYTHON, str(tmp_install), "--self-verify"],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("install.py.sha256 not found", result.stdout)

    def test_checksum_flag_passes(self):
        """Verify --checksum succeeds with valid hash."""
        hash_value = "8a7fa5446db4b6edb8d8f05d8b62deb1b941d51acbb4bc9453c80e653833463c"
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--checksum", hash_value],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Checksum verification passed", result.stdout)

    def test_checksum_flag_fails_with_invalid_hash(self):
        """Verify --checksum fails with invalid hash."""
        invalid_hash = "0" * 64
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--checksum", invalid_hash],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Checksum verification FAILED", result.stdout)

    def test_help_shows_checksum_options(self):
        """Verify --help mentions checksum flags."""
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--help"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--checksum", result.stdout)
        self.assertIn("--self-verify", result.stdout)


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

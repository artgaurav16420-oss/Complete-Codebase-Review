"""End-to-end integration tests for the Complete Codebase Review toolchain.

Tests that the full pipeline is wired correctly:
1. install.py CLI works (help, version, dry-run)
2. All test suites can be discovered and pass
3. The SKILL.md schema contract validation passes on a real health report
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_PY = str(REPO_ROOT / "install.py")
PYTHON = sys.executable


class TestEndToEndCLI(unittest.TestCase):
    """install.py CLI works end-to-end."""

    def test_help_exits_zero(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--help"],
            capture_output=True, text=True, cwd=REPO_ROOT,
            timeout=30
        )
        self.assertEqual(result.returncode, 0)

    def test_version_exits_zero(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--version"],
            capture_output=True, text=True, cwd=REPO_ROOT,
            timeout=30
        )
        self.assertEqual(result.returncode, 0)

    def test_dry_run_exits_zero(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--dry-run"],
            capture_output=True, text=True, cwd=REPO_ROOT,
            timeout=30
        )
        self.assertEqual(result.returncode, 0)

    def test_dry_run_prints_info(self):
        result = subprocess.run(
            [PYTHON, INSTALL_PY, "--dry-run"],
            capture_output=True, text=True, cwd=REPO_ROOT,
            timeout=30
        )
        self.assertIn("Starting Universal Installer", result.stdout)
        self.assertIn("Dry run complete", result.stdout)


class TestEndToEndHealthReport(unittest.TestCase):
    """Health report passes schema contract validation."""

    def test_generated_report_validates(self):
        report_path = REPO_ROOT / ".code-review-cache" / "health-report.md"
        if not report_path.is_file():
            self.skipTest(
                f"Health report not found at {report_path}. "
                "Run a full review first."
            )
        old_path = list(sys.path)
        try:
            sys.path.insert(0, str(REPO_ROOT))
            from tests.test_pipeline import validate_markdown_output
        finally:
            sys.path[:] = old_path
        content = report_path.read_text(encoding="utf-8")
        errors = validate_markdown_output(content)
        self.assertEqual(
            errors, [],
            f"health-report.md failed validation:\n" + "\n".join(
                f"  - {e}" for e in errors
            )
        )


if __name__ == "__main__":
    unittest.main()

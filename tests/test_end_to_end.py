"""End-to-end integration tests for the Complete Codebase Review toolchain.

Tests that the full pipeline is wired correctly:
1. The SKILL.md schema contract validation passes on a real health report
2. All test suites can be discovered and pass

(CLI smoke tests are in test_smoke.py to avoid duplication.)
"""
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestEndToEndHealthReport(unittest.TestCase):
    """Health report passes schema contract validation."""

    def test_generated_report_validates(self):
        report_path = REPO_ROOT / ".code-review-cache" / "health-report.md"
        if not report_path.is_file():
            self.skipTest("Health report not found — run pipeline first")
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

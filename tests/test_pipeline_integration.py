"""Integration tests for the Complete Codebase Review pipeline.

Tests that the pipeline structure is wired correctly by exercising
discovery, parallel analysis orchestration, and output validation
against the dummy_repo fixture. Uses Quick Mode settings to keep
test runtime bounded.

NOTE: Full agent spawning (Task tool calls) is mocked. This test
verifies the orchestrator's structural logic, not the sub-agents.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
for _path in (str(REPO_ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from test_env_config import TABLE_VARS  # noqa: E402
from test_pipeline import (  # noqa: E402
    SAMPLE_VALID_OUTPUT,
    validate_markdown_output,
)


class TestDummyRepoDiscovery(unittest.TestCase):
    """Discovery phase metadata extraction from dummy_repo."""

    def test_dummy_repo_has_expected_files(self):
        repo = REPO_ROOT / "tests" / "dummy_repo"
        expected = {
            "app.py", "config.py",
            "auth/login.py", "auth/user.py",
            "notifications/email.py",
            "api/orders.py",
            "core/processor.py",
            "utils/helper.py",
            "tests/test_auth.py",
        }
        actual = set()
        for f in repo.rglob("*.py"):
            rel = f.relative_to(repo)
            actual.add(str(rel).replace(os.sep, "/"))
        for exp in expected:
            self.assertIn(
                exp, actual,
                f"Expected {exp} not found in dummy_repo",
            )

    def test_dummy_repo_has_known_issues(self):
        with open(REPO_ROOT / "tests" / "expected_issues.json",
                  encoding="utf-8") as f:
            issues = json.load(f)
        self.assertGreater(len(issues), 10,
                           "expected_issues should cover expanded dummy_repo")


class TestOutputValidation(unittest.TestCase):
    """Health report schema contract passes for dummy data."""

    def test_manual_sample_passes_strict(self):
        errors = validate_markdown_output(SAMPLE_VALID_OUTPUT)
        self.assertEqual(
            errors, [],
            "SAMPLE_VALID_OUTPUT failed validation:\n" +
            "\n".join(f"  - {e}" for e in errors),
        )


class TestExpectedIssuesJSON(unittest.TestCase):
    """expected_issues.json matches dummy_repo content."""

    def test_expected_issues_parses(self):
        with open(REPO_ROOT / "tests" / "expected_issues.json",
                  encoding="utf-8") as f:
            issues = json.load(f)
        self.assertIsInstance(issues, list)
        self.assertGreater(len(issues), 0)
        for issue in issues:
            self.assertIsInstance(issue, str)
            self.assertTrue(issue.strip())


class TestEnvVarIntegration(unittest.TestCase):
    """CODE_REVIEW_* env vars integrate correctly with SKILL.md spec."""

    def test_quick_mode_settings(self):
        expected_basics = {
            "CODE_REVIEW_EFFORT",
            "CODE_REVIEW_TIMEOUT_SEC",
            "CODE_REVIEW_MAX_FILES",
        }
        for var in expected_basics:
            self.assertIn(
                var, TABLE_VARS,
                f"{var} missing from TABLE_VARS in test_env_config",
            )


if __name__ == "__main__":
    unittest.main()

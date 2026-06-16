"""Tests for CODE_REVIEW_* env-var configuration completeness.

Verifies that all env vars documented in the SKILL.md config table have
corresponding references in the document body, and that no orphan
env-var references exist outside the table.
"""
import os
import re
import unittest
from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parent.parent / "SKILL.md"

TABLE_VARS = [
    "CODE_REVIEW_EFFORT",
    "CODE_REVIEW_TIMEOUT_SEC",
    "CODE_REVIEW_MAX_FILES",
    "CODE_REVIEW_CACHE_DIR",
    "CODE_REVIEW_BASELINE",
    "CODE_REVIEW_AGENTS",
    "CODE_REVIEW_STATUS_INTERVAL",
    "CODE_REVIEW_FILTER",
]


class TestEnvVarTable(unittest.TestCase):
    """Env-var table in SKILL.md is complete and internally consistent."""

    @classmethod
    def setUpClass(cls):
        with open(SKILL_PATH, "r", encoding="utf-8") as f:
            cls.content = f.read()
        idx = cls.content.find("| `CODE_REVIEW_EFFORT`")
        cls.table_start = idx
        if idx >= 0:
            cls.body = cls.content[idx:]
        else:
            cls.body = cls.content

    def test_all_known_vars_present_in_table(self):
        for var in TABLE_VARS:
            with self.subTest(var=var):
                self.assertIn(
                    f"| `{var}`", self.content,
                    f"{var} missing from env-var table",
                )

    def test_unknown_vars_absent(self):
        """No CODE_REVIEW_* outside the known set appears in body."""
        body_refs = set(re.findall(r"CODE_REVIEW_\w+", self.body))
        unknown = body_refs - set(TABLE_VARS)
        self.assertEqual(unknown, set(), f"Unknown env vars referenced: {unknown}")

    def test_each_var_has_body_references(self):
        for var in TABLE_VARS:
            with self.subTest(var=var):
                count = self.body.count(var)
                self.assertGreaterEqual(
                    count, 2,
                    f"{var} has only {count} occurrence(s) — expected table row + body refs",
                )

    def test_each_var_has_default_documented(self):
        for var in TABLE_VARS:
            with self.subTest(var=var):
                self.assertRegex(
                    self.content,
                    rf"`{var}`.*\|",
                    f"{var} missing default-value column",
                )


class TestEnvVarExtraFiles(unittest.TestCase):
    """Other doc files reference only known env vars."""

    def setUp(self):
        self.repo_root = SKILL_PATH.parent

    def _check_file(self, rel_path):
        path = self.repo_root / rel_path
        if not path.exists():
            self.skipTest(f"{rel_path} not found")
        text = path.read_text(encoding="utf-8")
        refs = set(re.findall(r"CODE_REVIEW_\w+", text))
        unknown = refs - set(TABLE_VARS)
        self.assertEqual(
            unknown, set(),
            f"{rel_path}: unknown env vars {unknown}",
        )

    def test_help_md(self):
        self._check_file("help.md")

    def test_readme_md(self):
        self._check_file("README.md")

    def test_agents_md(self):
        self._check_file("AGENTS.md")


if __name__ == "__main__":
    unittest.main()

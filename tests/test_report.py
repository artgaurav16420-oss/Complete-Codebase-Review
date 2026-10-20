"""Tests for ccr.report: Markdown and JSON contracts."""

import sys
import unittest
from pathlib import Path

from ccr import pipeline
from ccr import report as report_mod

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_pipeline import (  # noqa: E402
    validate_json_output,
    validate_markdown_output,
)

GOOD = "[app.py:1] \u2014 hardcoded key in source \u2192 any reader gets the key"


def result(agent, findings):
    """Build an agent result dict."""
    return {"agent": agent, "findings": findings}


class TestMarkdown(unittest.TestCase):
    """Rendered Markdown passes the schema contract."""

    @classmethod
    def setUpClass(cls):
        cls.model = pipeline.synthesize(
            _manifest(),
            {
                "security": result("security", [
                    {"finding": GOOD, "severity": "CRITICAL", "est_hours": 2,
                     "da_verdict": "CONFIRMED"},
                ]),
                "code_quality": result("code_quality", [
                    {"finding": "[b.py:2] \u2014 flaw \u2192 failure",
                     "severity": "MEDIUM", "est_hours": 4,
                     "da_verdict": "PLAUSIBLE"},
                ]),
            },
            ["security", "code_quality"],
            target="demo",
            facts={"files": 12, "languages": {"Python": 12},
                   "top_dirs": {"src": 12}},
        )
        cls.md = report_mod.render_markdown(cls.model)

    def test_passes_validator(self):
        self.assertEqual(validate_markdown_output(self.md), [])

    def test_has_required_sections(self):
        for section in (
            "## Executive Summary", "## Per-Domain Scores",
            "## Detailed Findings", "## Improvement Roadmap",
            "## Tech Debt Summary", "## Agent Status",
        ):
            self.assertIn(section, self.md)

    def test_reports_health(self):
        self.assertIn("**Overall Health** | RED", self.md)

    def test_codebase_size_rendered(self):
        self.assertIn("12 files, 1 languages", self.md)

    def test_rejected_section_empty(self):
        self.assertIn("## Rejected Findings", self.md)

    def test_clean_report_still_valid(self):
        model = pipeline.synthesize(
            _manifest(), {}, [], target="clean",
        )
        md = report_mod.render_markdown(model)
        self.assertEqual(validate_markdown_output(md), [])
        self.assertIn("GREEN", md)


class TestJson(unittest.TestCase):
    """Rendered JSON passes the machine contract."""

    @classmethod
    def setUpClass(cls):
        cls.model = pipeline.synthesize(
            _manifest(),
            {"security": result("security", [
                {"finding": GOOD, "severity": "CRITICAL", "est_hours": 2,
                 "da_verdict": "CONFIRMED"},
                {"finding": "[x.py:9] \u2014 style issue \u2192 noise",
                 "severity": "INFO", "est_hours": 0.5,
                 "da_verdict": "CONFIRMED"},
            ])},
            ["security"], target="demo",
        )
        cls.data = report_mod.render_json(cls.model)

    def test_passes_validator(self):
        self.assertEqual(validate_json_output(self.data), [])

    def test_info_mapped_to_low(self):
        severities = [item["severity"] for item in self.data["findings"]]
        self.assertIn("LOW", severities)
        self.assertNotIn("INFO", severities)

    def test_roadmap_keys(self):
        self.assertEqual(
            sorted(self.data["roadmap"]), ["phase_1", "phase_2", "phase_3"]
        )

    def test_roadmap_phase_objects(self):
        phase = self.data["roadmap"]["phase_1"]
        self.assertIn("title", phase)
        self.assertIn("estimated_hours", phase)
        self.assertIsInstance(phase["tasks"], list)

    def test_finding_fields(self):
        for item in self.data["findings"]:
            for field in ("id", "finding", "severity", "domain",
                          "est_hours", "da_verdict"):
                self.assertIn(field, item)


class TestFormatting(unittest.TestCase):
    """Hour formatting helpers."""

    def test_short_format(self):
        self.assertEqual(report_mod.fmt_hours(2), "2h")
        self.assertEqual(report_mod.fmt_hours(2.5), "2.5h")

    def test_long_format(self):
        self.assertEqual(report_mod.fmt_hours_long(2), "2 hours")
        self.assertEqual(report_mod.fmt_hours_long(2.5), "2.5 hours")

    def test_pipe_escaped(self):
        model = pipeline.synthesize(
            _manifest(),
            {"security": result("security", [
                {"finding": "[a.py:1] \u2014 a|b \u2192 failure",
                 "severity": "LOW", "est_hours": 1,
                 "da_verdict": "CONFIRMED"},
            ])},
            ["security"],
        )
        md = report_mod.render_markdown(model)
        self.assertIn("a/b", md)
        self.assertEqual(validate_markdown_output(md), [])


def _manifest():
    """Load the real manifest."""
    from ccr import manifest as manifest_mod
    return manifest_mod.load()


if __name__ == "__main__":
    unittest.main()

"""Tests for ccr.report: Markdown and JSON contracts."""

import importlib
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Import the shared helpers from the bare module so discovery, direct runs
# and these tests all share one module object (no duplicate copies).
import test_pipeline  # noqa: E402
from ccr import pipeline  # noqa: E402
from ccr import report as report_mod  # noqa: E402
from test_pipeline import (  # noqa: E402
    validate_json_output,
    validate_markdown_output,
)

GOOD = "[app.py:1] \u2014 hardcoded key in source \u2192 any reader gets the key"


class TestSharedValidatorModule(unittest.TestCase):
    """Schema validators come from the one `test_pipeline` module object."""

    def test_helpers_are_attributes_of_the_shared_module(self):
        module = sys.modules["test_pipeline"]
        self.assertIs(module, test_pipeline)
        self.assertIs(validate_markdown_output, module.validate_markdown_output)
        self.assertIs(validate_json_output, module.validate_json_output)

    def test_patch_on_shared_module_is_visible_to_importers(self):
        module = sys.modules["test_pipeline"]
        with patch.object(
            module, "validate_markdown_output", return_value=["patched"],
        ):
            reimported = importlib.import_module("test_pipeline")
            self.assertIs(reimported, module)
            self.assertEqual(reimported.validate_markdown_output(""), ["patched"])
            self.assertIs(
                reimported.validate_markdown_output,
                module.validate_markdown_output,
            )


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

    def test_internal_validator_accepts(self):
        self.assertEqual(report_mod.validate_markdown(self.md), [])

    def test_rejects_non_enum_health(self):
        bad = dict(self.model)
        bad["overall_health"] = "PURPLE"
        md = report_mod.render_markdown(bad)
        errors = report_mod.validate_markdown(md)
        self.assertIn("invalid overall health: PURPLE", errors)

    def test_rejects_extra_cells_in_the_health_row(self):
        lines = self.md.splitlines()
        for index, line in enumerate(lines):
            if line.startswith("| **Overall Health** |"):
                lines[index] = line[:-1].rstrip() + " | PURPLE |"
                break
        errors = report_mod.validate_markdown("\n".join(lines))
        self.assertIn("missing overall health", errors)

    def test_finding_text_cannot_forge_tech_debt_marker(self):
        model = copy.deepcopy(self.model)
        model["findings"][0]["finding"] = (
            "[" + "x.py:1] \u2014 quotes **By domain**: Evil: 99h \u2192 "
            "synthesis aborts"
        )
        md = report_mod.render_markdown(model)
        self.assertEqual(report_mod.validate_markdown(md), [])

    def test_finding_text_cannot_forge_section_header(self):
        model = copy.deepcopy(self.model)
        model["findings"][0]["finding"] = (
            "[" + "x.py:1] \u2014 x \x0c## Tech Debt Summary\x0c"
            "**Total estimated**: 2 hours\x0c**By domain**: fake: 99h\x0c"
            "## X \u2192 failure"
        )
        md = report_mod.render_markdown(model)
        self.assertEqual(report_mod.validate_markdown(md), [])

    def test_target_cannot_forge_section_header(self):
        model = dict(self.model)
        model["target"] = "repo\x0c## Executive Summary"
        md = report_mod.render_markdown(model)
        self.assertEqual(report_mod.validate_markdown(md), [])

    def test_target_html_is_escaped_in_the_title(self):
        model = dict(self.model)
        model["target"] = "<img src=x onerror=alert(1)>"
        md = report_mod.render_markdown(model)
        self.assertNotIn("<img", md.splitlines()[0])
        self.assertIn("&lt;img", md.splitlines()[0])

    def test_target_markdown_image_is_escaped_in_the_title(self):
        model = dict(self.model)
        model["target"] = "![x](https://example.invalid/pixel.png)"
        md = report_mod.render_markdown(model)
        self.assertNotIn("![x](", md.splitlines()[0])
        self.assertIn("\\[x\\]", md.splitlines()[0])

    def test_internal_validator_rejects_missing_section(self):
        broken = self.md.replace("## Agent Status", "")
        self.assertTrue(report_mod.validate_markdown(broken))

    def test_internal_validator_rejects_non_numeric_score(self):
        broken = self.md.replace("| Security |", "| Security | N/A |", 1)
        self.assertTrue(report_mod.validate_markdown(broken))

    def test_na_in_finding_text_is_not_a_score(self):
        model = pipeline.synthesize(
            _manifest(),
            {"security": result("security", [
                {"finding": "[a.py:1] \u2014 value N/A in config \u2192 bad",
                 "severity": "LOW", "est_hours": 1,
                 "da_verdict": "CONFIRMED"},
            ])},
            ["security"], target="na",
        )
        md = report_mod.render_markdown(model)
        self.assertEqual(report_mod.validate_markdown(md), [])

    def test_half_hour_mismatch_is_rejected(self):
        import re
        broken = re.sub(
            r"\*\*Total estimated\*\*: ([0-9.]+) hours",
            lambda m: "**Total estimated**: {:.1f} hours".format(
                float(m.group(1)) + 0.5),
            self.md,
        )
        self.assertTrue(report_mod.validate_markdown(broken))

    def test_truncated_scan_is_surfaced(self):
        model = pipeline.synthesize(
            _manifest(), {}, [], target="sampled",
            facts={"files": 5, "truncated": True},
        )
        md = report_mod.render_markdown(model)
        self.assertIn("Sampled", md)
        js = report_mod.render_json(model)
        self.assertTrue(js["report"]["codebase_size"]["truncated"])

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

    def test_overlap_section_present(self):
        self.assertIn("## Overlap Candidates", self.md)

    def test_clean_report_still_valid(self):
        model = pipeline.synthesize(
            _manifest(), {}, [], target="clean",
        )
        md = report_mod.render_markdown(model)
        self.assertEqual(validate_markdown_output(md), [])
        self.assertIn("GREEN", md)


class TestOverlapCandidates(unittest.TestCase):
    """Non-empty overlap section: merged ids and the large-file advisory."""

    @classmethod
    def setUpClass(cls):
        cls.model = pipeline.synthesize(
            _manifest(),
            {
                "security": result("security", [
                    {"finding": "[svc/a.py:10] \u2014 session token cache shared "
                     "across tenants \u2192 cross-tenant credential leak",
                     "severity": "CRITICAL", "est_hours": 4,
                     "da_verdict": "CONFIRMED"},
                    {"finding": "[svc/b.py:20] \u2014 blocking call inside async "
                     "handler \u2192 request timeouts under load",
                     "severity": "HIGH", "est_hours": 9,
                     "da_verdict": "CONFIRMED"},
                ]),
                "code_quality": result("code_quality", [
                    {"finding": "[svc/a.py:11] \u2014 session token cache shared "
                     "across tenants \u2192 cross-tenant credential leak",
                     "severity": "HIGH", "est_hours": 12,
                     "da_verdict": "CONFIRMED"},
                    {"finding": "[svc/b.py:40] \u2014 duplicated mapper logic "
                     "\u2192 stale reads after schema change",
                     "severity": "MEDIUM", "est_hours": 10,
                     "da_verdict": "CONFIRMED"},
                ]),
            },
            ["security", "code_quality"],
            target="overlap",
        )
        cls.md = report_mod.render_markdown(cls.model)

    def test_model_records_merge_and_advisory(self):
        self.assertEqual(
            [
                (candidate["file"], candidate["kept"], candidate["merged"],
                 candidate["advisory"])
                for candidate in self.model["overlap_candidates"]
            ],
            [
                ("svc/a.py", "F-001", ["F-003"], False),
                ("svc/b.py", "F-002", ["F-004"], True),
            ],
        )

    def test_markdown_renders_merged_id(self):
        self.assertIn("- svc/a.py: kept F-001 (merged: F-003)", self.md)

    def test_markdown_renders_large_file_advisory(self):
        self.assertIn(
            "- [advisory] svc/b.py: 19.0h across F-002 + F-004", self.md,
        )
        self.assertIn("adjudicate whether this is one root cause", self.md)

    def test_overlap_report_still_passes_validators(self):
        self.assertEqual(validate_markdown_output(self.md), [])
        self.assertEqual(report_mod.validate_markdown(self.md), [])


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

    def test_design_note_is_marked_no_fix(self):
        model = pipeline.synthesize(
            _manifest(),
            {"security": result("security", [
                {"finding": "[a.py:1] \u2014 sync and async mirror \u2192 "
                 "deliberate design", "severity": "INFO", "est_hours": 0,
                 "finding_type": "design_note",
                 "da_verdict": "CONFIRMED"},
            ])},
            ["security"], target="design",
        )
        data = report_mod.render_json(model)
        item = data["findings"][0]
        self.assertTrue(item["no_fix"])
        self.assertEqual(item["finding_type"], "design_note")

    def test_overlap_candidates_in_json(self):
        self.assertIn("overlap_candidates", self.data)
        self.assertIsInstance(self.data["overlap_candidates"], list)

    def test_rejected_findings_are_serialized(self):
        model = pipeline.synthesize(
            _manifest(),
            {"security": result("security", [
                {"finding": "[a.py:1] \u2014 flaw \u2192 failure might occur",
                 "severity": "LOW", "est_hours": 1},
            ])},
            ["security"], target="rejected",
        )
        data = report_mod.render_json(model)
        self.assertEqual(len(data["rejected"]), 1)
        self.assertEqual(data["rejected"][0]["da_verdict"], "REJECTED")
        self.assertIn("reject_reason", data["rejected"][0])


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

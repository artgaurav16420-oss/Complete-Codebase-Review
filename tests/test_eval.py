"""End-to-end eval: recorded fixtures scored against expected issues."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Import the shared helpers from the bare module so discovery, direct runs
# and these tests all share one module object (no duplicate copies).
from ccr import manifest as manifest_mod  # noqa: E402
from ccr import pipeline  # noqa: E402
from test_pipeline import (  # noqa: E402
    validate_json_output,
    validate_markdown_output,
)

FIXTURES = ROOT / "tests" / "fixtures" / "agents"
EXPECTED = ROOT / "tests" / "expected_issues.json"


class TestEvalHarness(unittest.TestCase):
    """The pipeline finds every issue the fixture repository is known to have."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = manifest_mod.load()
        cls.model, cls.score = pipeline.run_eval(
            cls.manifest, FIXTURES, EXPECTED
        )
        with open(EXPECTED, encoding="utf-8") as f:
            cls.expected = json.load(f)

    def test_full_coverage(self):
        self.assertEqual(self.score["coverage"], 1.0)
        self.assertEqual(self.score["missing"], [])

    def test_all_expected_matched(self):
        self.assertEqual(self.score["matched"], len(self.expected))

    def test_precision_above_floor(self):
        self.assertGreaterEqual(self.score["precision"], 0.7)

    def test_markdown_contract(self):
        from ccr import report
        md = report.render_markdown(self.model)
        self.assertEqual(validate_markdown_output(md), [])

    def test_json_contract(self):
        from ccr import report
        self.assertEqual(validate_json_output(report.render_json(self.model)), [])

    def test_weasel_findings_rejected(self):
        reasons = [item["reject_reason"] for item in self.model["rejected"]]
        self.assertTrue(any("weasel" in reason for reason in reasons))
        self.assertTrue(any("anchor" in reason for reason in reasons))

    def test_rejected_absent_from_roadmap(self):
        bullets = []
        for items in self.model["roadmap"].values():
            bullets.extend(item["finding"] for item in items)
        for item in self.model["rejected"]:
            self.assertNotIn(item["finding"], bullets)

    def test_known_critical_issues(self):
        self.assertEqual(self.model["critical_issues"], 2)
        self.assertEqual(self.model["overall_health"], "RED")

    def test_duplicate_collapsed(self):
        unused = [
            item for item in self.model["findings"]
            if "unused-import" in item.get("tags", [])
        ]
        self.assertEqual(len(unused), 1)

    def test_every_expected_tag_appears(self):
        tags = set()
        for item in self.model["findings"]:
            tags |= set(item.get("tags", []))
        self.assertEqual(set(self.expected) - tags, set())

    def test_totals_reconcile(self):
        roadmap_total = sum(self.model["roadmap_hours"].values())
        self.assertAlmostEqual(
            roadmap_total, self.model["tech_debt"]["total_hours"]
        )


class TestEvalCliExit(unittest.TestCase):
    """Eval returns non-zero when an issue is missing."""

    def test_missing_fixture_raises(self):
        with self.assertRaises(ValueError):
            pipeline.run_eval(
                manifest_mod.load(), ROOT / "tests" / "fixtures" / "empty",
                EXPECTED,
            )

    def test_duplicate_expected_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "expected.json"
            path.write_text('["a", "a"]', encoding="utf-8")
            with self.assertRaises(ValueError):
                pipeline.run_eval(manifest_mod.load(), FIXTURES, path)

    def test_empty_expected_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "expected.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                pipeline.run_eval(manifest_mod.load(), FIXTURES, path)


class TestOrganizerBenchmark(unittest.TestCase):
    """Recorded real run against Organizer, human-verified for precision."""

    @classmethod
    def setUpClass(cls):
        root = ROOT / "tests" / "fixtures" / "organizer"
        cls.model, cls.score = pipeline.run_eval(
            manifest_mod.load(), root / "agents", root / "expected.json"
        )

    def test_full_coverage(self):
        self.assertEqual(self.score["coverage"], 1.0)
        self.assertEqual(self.score["missing"], [])
        self.assertEqual(self.score["matched"], 32)

    def test_findings_and_severity(self):
        self.assertEqual(len(self.model["findings"]), 18)
        highs = [
            item for item in self.model["findings"]
            if item["severity"] == "HIGH"
        ]
        self.assertEqual(len(highs), 2)

    def test_precision_encodes_false_positive(self):
        self.assertGreaterEqual(self.score["precision"], 0.94)

    def test_known_false_positive_detected(self):
        self.assertEqual(len(self.score["known_false_positives"]), 1)
        self.assertGreaterEqual(self.score["verified_precision"], 0.94)

    def test_false_positive_is_the_dry_run_finding(self):
        needle = self.score["known_false_positives"][0]
        matches = [
            item for item in self.model["findings"]
            if needle in item["finding"]
        ]
        self.assertEqual(len(matches), 1)
        self.assertIn("fsops.py:534", matches[0]["finding"])

    def test_markdown_contract(self):
        from ccr import report
        md = report.render_markdown(self.model)
        self.assertEqual(validate_markdown_output(md), [])

    def test_json_contract(self):
        from ccr import report
        self.assertEqual(
            validate_json_output(report.render_json(self.model)), []
        )


class TestSpecLoading(unittest.TestCase):
    """Benchmark spec validation."""

    def _write(self, tmp, payload):
        path = Path(tmp) / "spec.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_missing_expected_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, {"known_false_positives": []})
            with self.assertRaises(ValueError):
                pipeline.load_spec(path)

    def test_false_positives_must_be_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp, {"expected_issues": ["a"], "known_false_positives": "x"}
            )
            with self.assertRaises(ValueError):
                pipeline.load_spec(path)

    def test_non_list_spec_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "nope")
            with self.assertRaises(ValueError):
                pipeline.load_spec(path)

    def test_bare_list_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, ["a", "b"])
            expected, fps = pipeline.load_spec(path)
            self.assertEqual(expected, ["a", "b"])
            self.assertEqual(fps, [])


if __name__ == "__main__":
    unittest.main()

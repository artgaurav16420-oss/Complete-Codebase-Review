"""Tests for ccr.pipeline: gates, synthesis, rendering, scoring."""

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

from ccr import manifest as manifest_mod  # noqa: E402
from ccr import pipeline  # noqa: E402

GOOD = "[app.py:1] \u2014 hardcoded key in source \u2192 any reader gets the key"


def _manifest():
    return manifest_mod.load()


def _results():
    return {
        "security": {"findings": [
            {"finding": GOOD, "severity": "CRITICAL", "est_hours": 2,
             "da_verdict": "CONFIRMED", "tags": ["CWE-798"]},
        ]},
        "code_quality": {"findings": [
            {"finding": "[b.py:2] \u2014 flaw \u2192 failure", "severity": "HIGH",
             "est_hours": 5, "da_verdict": "CONFIRMED", "tags": ["dead-code"]},
        ]},
    }


class TestCompletion(unittest.TestCase):
    """Agent coverage thresholds."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = _manifest()

    def test_full_threshold_pass(self):
        ratio = pipeline.check_completion(
            self.manifest, "max", ["a", "b", "c", "d"], ["a", "b", "c"]
        )
        self.assertAlmostEqual(ratio, 0.75)

    def test_full_threshold_fail(self):
        with self.assertRaises(RuntimeError) as ctx:
            pipeline.check_completion(
                self.manifest, "max", ["a", "b", "c", "d"], ["a", "b"]
            )
        self.assertIn("insufficient", str(ctx.exception))

    def test_quick_threshold_pass(self):
        ratio = pipeline.check_completion(
            self.manifest, "min", ["a", "b", "c"], ["a", "b"]
        )
        self.assertAlmostEqual(ratio, 2 / 3)

    def test_quick_threshold_fail(self):
        with self.assertRaises(RuntimeError):
            pipeline.check_completion(
                self.manifest, "min", ["a", "b", "c"], ["a"]
            )

    def test_duplicate_ids_do_not_inflate(self):
        with self.assertRaises(RuntimeError):
            pipeline.check_completion(
                self.manifest, "max", ["a", "a", "b", "c"], ["a", "a"]
            )

    def test_empty_plan(self):
        self.assertEqual(
            pipeline.check_completion(self.manifest, "max", [], []), 0.0
        )


class TestSynthesize(unittest.TestCase):
    """Model assembly."""

    def test_domains_come_from_manifest(self):
        model = pipeline.synthesize(
            _manifest(), _results(), ["security", "code_quality"]
        )
        domains = {item["domain"] for item in model["findings"]}
        self.assertEqual(domains, {"Security", "Code Quality"})

    def test_ids_assigned(self):
        model = pipeline.synthesize(
            _manifest(), _results(), ["security", "code_quality"]
        )
        self.assertEqual(
            [item["id"] for item in model["findings"]], ["F-001", "F-002"]
        )

    def test_skips_missing_agents(self):
        model = pipeline.synthesize(
            _manifest(), _results(), ["security", "code_quality", "devops"]
        )
        self.assertEqual(model["agent_status"]["total"], 3)
        self.assertEqual(model["agent_status"]["completed"], 2)

    def test_plan_order_controls_finding_order(self):
        model = pipeline.synthesize(
            _manifest(), _results(), ["code_quality", "security"]
        )
        self.assertEqual(model["findings"][0]["domain"], "Code Quality")

    def test_rejected_kept_separate(self):
        results = {"security": {"findings": [
            {"finding": "no anchor", "severity": "HIGH", "da_verdict": "CONFIRMED"},
        ]}}
        model = pipeline.synthesize(_manifest(), results, ["security"])
        self.assertEqual(model["findings"], [])
        self.assertEqual(len(model["rejected"]), 1)

    def test_baseline_re_review_count_defaults_to_zero(self):
        model = pipeline.synthesize(_manifest(), _results(), ["security"])
        self.assertEqual(model["baseline"]["re_review_count"], 0)

    def test_baseline_carries_re_review_count(self):
        model = pipeline.synthesize(
            _manifest(), _results(), ["security"], re_review_count=2
        )
        self.assertEqual(model["baseline"]["re_review_count"], 2)


class TestRenderAndWrite(unittest.TestCase):
    """Output rendering and file writing."""

    def test_unknown_format_raises(self):
        model = pipeline.synthesize(_manifest(), _results(), ["security"])
        with self.assertRaises(ValueError):
            pipeline.render(model, "xml")

    def test_render_both(self):
        model = pipeline.synthesize(_manifest(), _results(), ["security"])
        output = pipeline.render(model, "both")
        self.assertEqual(set(output), {"markdown", "json"})

    def test_write_outputs(self):
        model = pipeline.synthesize(_manifest(), _results(), ["security"])
        with tempfile.TemporaryDirectory() as tmp:
            paths = pipeline.write_outputs(model, Path(tmp) / "report", "both")
            self.assertEqual(len(paths), 2)
            for path in paths:
                self.assertTrue(path.exists())
            payload = json.loads(
                (Path(tmp) / "report.json").read_text(encoding="utf-8")
            )
            self.assertIn("report", payload)


class TestEvaluate(unittest.TestCase):
    """Coverage scoring."""

    def _model(self, results=None):
        return pipeline.synthesize(
            _manifest(),
            _results() if results is None else results,
            ["security", "code_quality"],
        )

    def test_full_coverage(self):
        score = pipeline.evaluate(self._model(), ["CWE-798", "dead-code"])
        self.assertEqual(score["matched"], 2)
        self.assertEqual(score["coverage"], 1.0)
        self.assertEqual(score["missing"], [])

    def test_missing_issue(self):
        score = pipeline.evaluate(self._model(), ["CWE-798", "n-plus-one-query"])
        self.assertEqual(score["missing"], ["n-plus-one-query"])
        self.assertAlmostEqual(score["coverage"], 0.5)

    def test_empty_expected(self):
        score = pipeline.evaluate(self._model(), [])
        self.assertEqual(score["coverage"], 1.0)

    def test_no_findings(self):
        model = pipeline.synthesize(_manifest(), {}, [])
        score = pipeline.evaluate(model, ["x"])
        self.assertEqual(score["precision"], 0.0)
        self.assertEqual(score["coverage"], 0.0)


class TestMalformedResultGuard(unittest.TestCase):
    def _malformed(self, count, finding="no anchor here"):
        return {"security": {"findings": [
            {"finding": finding, "severity": "MEDIUM", "est_hours": 1}
            for _ in range(count)
        ]}}

    def test_many_missing_anchors_raise(self):
        with self.assertRaises(ValueError) as ctx:
            pipeline.synthesize(
                _manifest(), self._malformed(5), ["security"],
            )
        self.assertIn("malformed", str(ctx.exception))

    def test_blank_findings_raise(self):
        with self.assertRaises(ValueError) as ctx:
            pipeline.synthesize(
                _manifest(), self._malformed(5, finding="   "), ["security"],
            )
        self.assertIn("malformed", str(ctx.exception))

    def test_small_malformed_set_is_tolerated(self):
        model = pipeline.synthesize(
            _manifest(), self._malformed(3), ["security"],
        )
        self.assertEqual(model["findings"], [])

    def test_weasel_rejections_do_not_trigger_guard(self):
        results = {"security": {"findings": [
            {"finding": "[a.py:1] \u2014 flaw \u2192 failure might occur",
             "severity": "LOW", "est_hours": 1}
            for _ in range(5)
        ]}}
        model = pipeline.synthesize(_manifest(), results, ["security"])
        self.assertEqual(model["findings"], [])


class TestBaselineDomainIds(unittest.TestCase):
    def test_baseline_uses_canonical_ids(self):
        model = pipeline.synthesize(
            _manifest(), _results(), ["security", "code_quality"],
        )
        keys = set(model["baseline"]["per_domain_open_findings"])
        self.assertIn("security", keys)
        self.assertIn("code_quality", keys)
        self.assertNotIn("Security", keys)


if __name__ == "__main__":
    unittest.main()

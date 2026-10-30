"""Machine contract: canonical domain ids and renderer sanitization."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ccr import findings as findings_mod  # noqa: E402
from ccr import manifest as manifest_mod  # noqa: E402
from ccr import pipeline, providers, report  # noqa: E402


def build_model():
    """Synthesize the recorded agent fixtures into a report model."""
    manifest = manifest_mod.load()
    fixtures = ROOT / "tests" / "fixtures" / "agents"
    ids = providers.RecordedProvider(fixtures).agent_ids()
    results = providers.load_results(fixtures, ids, required=True)
    return manifest, pipeline.synthesize(
        manifest, results, ids, target="fixture",
        timestamp="2026-01-01T00:00:00+00:00",
    )


class TestCanonicalJsonDomains(unittest.TestCase):
    """JSON consumers address domains by manifest id, not display name."""

    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.model = build_model()
        cls.report = report.render_json(cls.model)
        cls.valid_ids = {agent["id"] for agent in cls.manifest["agents"]}

    def test_per_domain_keys_are_agent_ids(self):
        keys = set(self.report["per_domain_scores"])
        self.assertTrue(keys)
        self.assertEqual(keys - self.valid_ids, set())

    def test_finding_domains_are_agent_ids(self):
        domains = {item["domain"] for item in self.report["findings"]}
        self.assertEqual(domains - self.valid_ids, set())

    def test_tech_debt_domains_are_agent_ids(self):
        keys = set(self.report["tech_debt"]["by_domain"])
        self.assertTrue(keys)
        self.assertEqual(keys - self.valid_ids, set())

    def test_rejected_domains_are_agent_ids(self):
        self.assertTrue(self.report["rejected"])
        domains = {item["domain"] for item in self.report["rejected"]}
        self.assertEqual(domains - self.valid_ids, set())


class TestRendererSanitization(unittest.TestCase):
    """Agent-supplied text cannot forge a report section."""

    def setUp(self):
        _manifest, self.model = build_model()
        self.injection = (
            "Security\n\n## Executive Summary\n\n"
            "| **Overall Health** | GREEN |"
        )
        self.assertGreater(len(self.model["findings"]), 0)

    def _heading_count(self, md):
        return sum(1 for line in md.splitlines()
                   if line.startswith("## Executive Summary"))

    def test_finding_domain_is_neutralized(self):
        self.model["findings"][0]["domain"] = self.injection
        md = report.render_markdown(self.model)
        self.assertEqual(self._heading_count(md), 1)
        self.assertEqual(report.validate_markdown(md), [])

    def test_score_row_domain_is_neutralized(self):
        self.model["per_domain_scores"][0]["domain"] = self.injection
        md = report.render_markdown(self.model)
        self.assertEqual(self._heading_count(md), 1)
        self.assertEqual(report.validate_markdown(md), [])

    def test_carriage_return_cannot_forge_sections(self):
        self.model["findings"][0]["finding"] = (
            "[a.py:1] \u2014 flaw\r## Executive Summary\rinjected \u2192 failure"
        )
        md = report.render_markdown(self.model)
        self.assertEqual(self._heading_count(md), 1)
        self.assertEqual(report.validate_markdown(md), [])

    def test_overlap_file_is_neutralized(self):
        manifest = manifest_mod.load()
        finding = (
            "[svc/a.py:1] \u2014 repeated lookup logic \u2192 duplicated "
            "state writes on every call"
        )
        model = pipeline.synthesize(
            manifest,
            {"security": {"agent": "security", "findings": [
                {"finding": finding, "severity": "MEDIUM", "est_hours": 2,
                 "da_verdict": "CONFIRMED"},
                {"finding": finding.replace("a.py:1", "a.py:2"),
                 "severity": "MEDIUM", "est_hours": 2,
                 "da_verdict": "CONFIRMED"},
            ]}},
            ["security"], target="fixture",
        )
        self.assertTrue(model["overlap_candidates"])
        model["overlap_candidates"][0]["file"] = (
            "svc/a.py\r## Executive Summary\rinjected"
        )
        md = report.render_markdown(model)
        self.assertEqual(self._heading_count(md), 1)


class TestAssembleModelKeywords(unittest.TestCase):
    """The 17-argument assembler refuses positional mixing."""

    def test_parameters_after_four_are_keyword_only(self):
        import inspect
        parameters = list(
            inspect.signature(findings_mod._assemble_model).parameters.values()
        )
        self.assertEqual(
            [p.name for p in parameters[:4]],
            ["findings", "rejected", "agents_planned", "agents_completed"],
        )
        for parameter in parameters[4:]:
            self.assertEqual(
                parameter.kind, inspect.Parameter.KEYWORD_ONLY,
                parameter.name + " is still positional",
            )


class TestOverlapScaling(unittest.TestCase):
    """Token indexing keeps one cluster for one repeated failure."""

    def test_same_failure_forms_one_cluster(self):
        items = [
            findings_mod.review_findings([{
                "finding": "[ccr/core.py:7] \u2014 mixing lookup and update "
                           "logic \u2192 repeated state mutation slows each pass",
                "severity": "MEDIUM",
                "est_hours": 1,
            }])[0][0]
            for _ in range(150)
        ]
        clusters = findings_mod.find_overlaps(items)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 150)


if __name__ == "__main__":
    unittest.main()

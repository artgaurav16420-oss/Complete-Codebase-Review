"""Tests for ccr.findings: normalization, DA checks, dedup, aggregation."""

import unittest

from ccr import findings as f


def make(finding, severity="HIGH", domain="Security", hours=2.0,
         verdict="CONFIRMED", tags=None):
    """Build a finding dict for tests."""
    return {
        "finding": finding,
        "severity": severity,
        "domain": domain,
        "est_hours": hours,
        "da_verdict": verdict,
        "tags": tags or [],
    }


GOOD = "[app.py:1] \u2014 hardcoded key in source \u2192 any reader gets the key"


class TestNormalization(unittest.TestCase):
    """Severity, verdict, and anchor parsing."""

    def test_severity_case(self):
        self.assertEqual(f.normalize_severity("high"), "HIGH")

    def test_severity_unknown_falls_back(self):
        self.assertEqual(f.normalize_severity("bogus"), "LOW")
        self.assertEqual(f.normalize_severity(None), "LOW")

    def test_verdict_case(self):
        self.assertEqual(f.normalize_verdict("confirmed"), "CONFIRMED")

    def test_verdict_default(self):
        self.assertEqual(f.normalize_verdict(None), "QUESTIONABLE")

    def test_verdict_alias(self):
        self.assertEqual(f.normalize_verdict("da escalation"), "DA-ESCALATION")

    def test_anchor_parts(self):
        parts = f.anchor_parts(GOOD)
        self.assertEqual(parts[0], "app.py")
        self.assertEqual(parts[1], 1)

    def test_anchor_parts_invalid(self):
        self.assertIsNone(f.anchor_parts("no anchor here"))

    def test_weasel_hits(self):
        self.assertEqual(f.weasel_hits("this might fail"), ["might"])
        self.assertEqual(f.weasel_hits("clean text"), [])


class TestReviewFindings(unittest.TestCase):
    """Mechanical DA checks."""

    def test_keeps_anchored_finding(self):
        kept, rejected = f.review_findings([make(GOOD)])
        self.assertEqual(len(kept), 1)
        self.assertEqual(rejected, [])

    def test_rejects_weasel(self):
        bad = "[app.py:2] \u2014 this might fail \u2192 outage"
        kept, rejected = f.review_findings([make(bad)])
        self.assertEqual(kept, [])
        self.assertEqual(rejected[0]["da_verdict"], "REJECTED")
        self.assertIn("weasel", rejected[0]["reject_reason"])

    def test_rejects_missing_anchor(self):
        kept, rejected = f.review_findings([make("hardcoded key")])
        self.assertEqual(kept, [])
        self.assertIn("anchor", rejected[0]["reject_reason"])

    def test_rejects_empty(self):
        kept, rejected = f.review_findings([make("")])
        self.assertEqual(kept, [])
        self.assertIn("empty", rejected[0]["reject_reason"])

    def test_normalizes_in_place(self):
        kept, _ = f.review_findings([make(GOOD, severity="critical")])
        self.assertEqual(kept[0]["severity"], "CRITICAL")
        self.assertEqual(kept[0]["est_hours"], 2.0)

    def test_negative_hours_become_zero(self):
        kept, _ = f.review_findings([make(GOOD, hours=-5)])
        self.assertEqual(kept[0]["est_hours"], 0.0)


class TestDedup(unittest.TestCase):
    """Findings on the same domain and line collapse."""

    def test_keeps_higher_severity(self):
        low = make(GOOD, severity="LOW")
        high = make(GOOD, severity="HIGH")
        result = f.dedup([low, high])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["severity"], "HIGH")

    def test_same_severity_keeps_larger_estimate(self):
        small = make(GOOD, hours=1)
        large = make(GOOD, hours=5)
        result = f.dedup([small, large])
        self.assertEqual(result[0]["est_hours"], 5)

    def test_different_domain_not_merged(self):
        a = make(GOOD, domain="Security")
        b = make(GOOD, domain="Quality")
        self.assertEqual(len(f.dedup([a, b])), 2)

    def test_assign_ids(self):
        result = f.assign_ids([make(GOOD), make(GOOD, domain="Other")])
        self.assertEqual([item["id"] for item in result], ["F-001", "F-002"])


class TestRoadmap(unittest.TestCase):
    """Phase placement and eligibility."""

    def test_critical_goes_phase_1(self):
        phases = f.place_roadmap([make(GOOD, severity="CRITICAL", hours=20)])
        self.assertEqual(len(phases[1]), 1)

    def test_quick_win_goes_phase_1(self):
        phases = f.place_roadmap([make(GOOD, severity="LOW", hours=1)])
        self.assertEqual(len(phases[1]), 1)

    def test_high_goes_phase_2(self):
        phases = f.place_roadmap([make(GOOD, severity="HIGH", hours=5)])
        self.assertEqual(len(phases[2]), 1)

    def test_large_medium_goes_phase_3(self):
        phases = f.place_roadmap([make(GOOD, severity="MEDIUM", hours=10)])
        self.assertEqual(len(phases[3]), 1)

    def test_rejected_excluded(self):
        phases = f.place_roadmap([make(GOOD, verdict="REJECTED")])
        self.assertEqual(sum(len(items) for items in phases.values()), 0)

    def test_questionable_excluded(self):
        phases = f.place_roadmap([make(GOOD, verdict="QUESTIONABLE")])
        self.assertEqual(sum(len(items) for items in phases.values()), 0)

    def test_da_escalation_included(self):
        phases = f.place_roadmap([make(GOOD, verdict="DA-ESCALATION")])
        self.assertEqual(sum(len(items) for items in phases.values()), 1)


class TestAggregate(unittest.TestCase):
    """Report model aggregation."""

    def _model(self, items, rejected=None):
        kept = f.assign_ids(f.dedup(items))
        return f.aggregate(
            kept, rejected or [], ["security"], ["security"],
            target="demo",
        )

    def test_red_health_on_critical(self):
        model = self._model([make(GOOD, severity="CRITICAL")])
        self.assertEqual(model["overall_health"], "RED")
        self.assertEqual(model["critical_issues"], 1)

    def test_yellow_health_on_high(self):
        model = self._model([make(GOOD, severity="HIGH")])
        self.assertEqual(model["overall_health"], "YELLOW")

    def test_green_health_on_low(self):
        model = self._model([make(GOOD, severity="LOW")])
        self.assertEqual(model["overall_health"], "GREEN")

    def test_totals_reconcile(self):
        model = self._model([
            make(GOOD, severity="CRITICAL", hours=3),
            make("[b.py:2] \u2014 flaw \u2192 failure", hours=5),
            make("[c.py:3] \u2014 flaw \u2192 failure", domain="Quality", hours=1),
        ])
        roadmap_total = sum(model["roadmap_hours"].values())
        self.assertAlmostEqual(roadmap_total, model["tech_debt"]["total_hours"])
        self.assertAlmostEqual(
            sum(model["tech_debt"]["by_domain"].values()),
            model["tech_debt"]["total_hours"],
        )

    def test_rejected_not_counted(self):
        rejected = [dict(make(GOOD, verdict="REJECTED"), reject_reason="test")]
        model = self._model([], rejected)
        self.assertEqual(model["tech_debt"]["total_hours"], 0)
        self.assertEqual(model["agent_status"]["da_verdict_summary"]["REJECTED"], 1)
        self.assertEqual(model["per_domain_scores"], [])

    def test_overall_score_is_domain_average(self):
        model = self._model([make(GOOD, severity="HIGH", hours=5)])
        scores = [row["score"] for row in model["per_domain_scores"]]
        self.assertAlmostEqual(model["overall_score"], sum(scores) / len(scores), 1)

    def test_baseline_fields(self):
        model = self._model([make(GOOD)])
        baseline = model["baseline"]
        for key in ("timestamp", "target", "health_score", "tech_debt_hours",
                    "critical_count", "per_domain_scores",
                    "per_domain_open_findings", "task_count", "re_review_count"):
            self.assertIn(key, baseline)

    def test_trend_with_baseline(self):
        kept = f.assign_ids([make(GOOD, hours=5)])
        model = f.aggregate(
            kept, [], ["security"], ["security"],
            baseline={"tech_debt_hours": 10},
        )
        self.assertIn("10", model["tech_debt"]["trend"])
        self.assertIn("5", model["tech_debt"]["trend"])

    def test_priority_areas_sorted_by_severity(self):
        model = self._model([
            make(GOOD, severity="CRITICAL", domain="Security"),
            make("[b.py:1] \u2014 flaw \u2192 failure", severity="LOW",
                 domain="Docs"),
        ])
        self.assertEqual(model["priority_areas"][0], "Security")


if __name__ == "__main__":
    unittest.main()

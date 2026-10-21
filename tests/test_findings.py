"""Tests for ccr.findings: normalization, DA checks, dedup, aggregation."""

import unittest

from ccr import findings as f


def make(finding, severity="HIGH", domain="Security", hours=2.0,
         verdict="CONFIRMED", tags=None, finding_type=None):
    """Build a finding dict for tests."""
    data = {
        "finding": finding,
        "severity": severity,
        "domain": domain,
        "est_hours": hours,
        "da_verdict": verdict,
        "tags": tags or [],
    }
    if finding_type:
        data["finding_type"] = finding_type
    return data


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
        self.assertEqual(f.normalize_verdict(None), "PLAUSIBLE")

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

    def test_floor_fills_missing_estimate(self):
        kept, _ = f.review_findings(
            [make(GOOD, hours=0, finding_type="hardcoded_secret")],
            floors={"hardcoded_secret": 2},
        )
        self.assertEqual(kept[0]["est_hours"], 2.0)

    def test_floor_respects_half_multiplier(self):
        kept, _ = f.review_findings(
            [make(GOOD, hours=1, finding_type="circular_dependency")],
            floors={"circular_dependency": 8},
        )
        self.assertEqual(kept[0]["est_hours"], 4.0)


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

    def test_low_five_hours_goes_phase_3(self):
        phases = f.place_roadmap([make(GOOD, severity="LOW", hours=5)])
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

    def test_high_never_quick_win(self):
        phases = f.place_roadmap([make(GOOD, severity="HIGH", hours=1)])
        self.assertEqual(len(phases[1]), 0)
        self.assertEqual(len(phases[2]), 1)

    def test_info_excluded(self):
        phases = f.place_roadmap([make(GOOD, severity="INFO", hours=0)])
        self.assertEqual(sum(len(items) for items in phases.values()), 0)

    def test_quick_win_cap_prefers_medium(self):
        medium = [
            make(f"[m{i}.py:{i}] \u2014 flaw \u2192 failure", severity="MEDIUM",
                 hours=2, domain="M")
            for i in range(15)
        ]
        low = [
            make(f"[l{i}.py:{i}] \u2014 flaw \u2192 failure", severity="LOW",
                 hours=1, domain="L")
            for i in range(20)
        ]
        phases = f.place_roadmap(medium + low)
        phase1_severities = {
            f.normalize_severity(item["severity"]) for item in phases[1]
        }
        self.assertIn("MEDIUM", phase1_severities)
        self.assertEqual(
            sum(1 for item in phases[1]
                if f.normalize_severity(item["severity"]) == "LOW"), 10
        )

    def test_quick_wins_capped(self):
        items = [
            make(f"[f{i}.py:{i}] \u2014 flaw \u2192 failure", severity="MEDIUM",
                 hours=2, domain=f"D{i}")
            for i in range(25)
        ]
        phases = f.place_roadmap(items)
        self.assertLessEqual(len(phases[1]), 20)
        self.assertGreater(len(phases[2]), 0)


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


class TestScoreDomains(unittest.TestCase):
    def test_empty(self):
        scores, totals = f._score_domains([])
        self.assertEqual(scores, [])
        self.assertEqual(totals["CRITICAL"], 0)

    def test_counts_and_unknown_domain(self):
        items = [
            {"severity": "CRITICAL", "domain": None},
            {"severity": "HIGH", "domain": "Security"},
        ]
        scores, totals = f._score_domains(items)
        self.assertEqual(totals["CRITICAL"], 1)
        self.assertEqual(totals["HIGH"], 1)

    def test_severity_normalization(self):
        items = [{"severity": "bogus", "domain": "X"}]
        _, totals = f._score_domains(items)
        self.assertEqual(totals["LOW"], 1)


class TestRoadmapSummary(unittest.TestCase):
    def test_empty(self):
        rh, total, by = f._roadmap_summary({})
        self.assertEqual(rh, {})
        self.assertEqual(total, 0)
        self.assertEqual(by, {})

    def test_hours(self):
        phases = {"Phase 1": [{"domain": "Sec", "est_hours": 2},
                               {"domain": "Sec", "est_hours": 1.5}]}
        rh, total, by = f._roadmap_summary(phases)
        self.assertEqual(rh["Phase 1"], 3.5)
        self.assertEqual(total, 3.5)
        self.assertEqual(by["Sec"], 3.5)


class TestVerdictSummary(unittest.TestCase):
    def test_counts(self):
        items = [{"da_verdict": "CONFIRMED"}, {"da_verdict": "BOGUS"}]
        vs = f._verdict_summary(items)
        self.assertEqual(vs["CONFIRMED"], 1)
        self.assertEqual(vs["QUESTIONABLE"], 1)


class TestPriorityAreas(unittest.TestCase):
    def test_order_and_limit(self):
        scores = [
            {"domain": "A", "critical": 1, "high": 0, "medium": 0},
            {"domain": "B", "critical": 0, "high": 2, "medium": 0},
            {"domain": "C", "critical": 0, "high": 0, "medium": 1},
            {"domain": "D", "critical": 0, "high": 0, "medium": 0},
        ]
        self.assertEqual(f._priority_areas(scores), ["A", "B", "C"])


class TestHealth(unittest.TestCase):
    def test_red_yellow_green(self):
        self.assertEqual(f._health({"CRITICAL": 1, "HIGH": 0}), "RED")
        self.assertEqual(f._health({"CRITICAL": 0, "HIGH": 1}), "YELLOW")
        self.assertEqual(f._health({"CRITICAL": 0, "HIGH": 0}), "GREEN")


class TestOverallScore(unittest.TestCase):
    def test_empty_and_rounding(self):
        self.assertEqual(f._overall_score([]), 10.0)
        scores = [{"score": 7.0}, {"score": 8.0}]
        self.assertEqual(f._overall_score(scores), 7.5)


class TestTrend(unittest.TestCase):
    def test_no_baseline(self):
        self.assertEqual(f._trend(None, 10.0), "no previous baseline")

    def test_previous_none(self):
        self.assertEqual(f._trend({}, 10.0), "no previous baseline")

    def test_previous_zero(self):
        self.assertEqual(f._trend({"tech_debt_hours": 0}, 10.0), "0h -> 10.0h")

    def test_positive_change(self):
        t = f._trend({"tech_debt_hours": 10}, 8.0)
        self.assertIn("10h -> 8.0h", t)
        self.assertIn("-20%", t)


class TestAnchorParsing(unittest.TestCase):
    def test_windows_absolute_path(self):
        parts = f.anchor_parts(
            "[D:\\src\\a.py:42] \u2014 flaw \u2192 failure"
        )
        self.assertEqual(parts[0], "D:\\src\\a.py")
        self.assertEqual(parts[1], 42)

    def test_line_range(self):
        parts = f.anchor_parts("[a.py:42-48] \u2014 flaw \u2192 failure")
        self.assertEqual(parts[0], "a.py")
        self.assertEqual(parts[1], 42)

    def test_relative_path(self):
        self.assertTrue(f.ANCHOR_RE.match("[src/a.py:1] \u2014 flaw \u2192 failure"))


class TestDedupSeparators(unittest.TestCase):
    def test_backslash_and_slash_collapse(self):
        items = [
            make("[src\\a.py:1] \u2014 flaw \u2192 failure"),
            make("[src/a.py:1] \u2014 flaw \u2192 failure"),
        ]
        self.assertEqual(len(f.dedup(items)), 1)

    def test_case_sensitive_paths_stay_distinct(self):
        items = [
            make("[src/Foo.py:1] \u2014 flaw \u2192 failure"),
            make("[src/foo.py:1] \u2014 flaw \u2192 failure"),
        ]
        self.assertEqual(len(f.dedup(items)), 2)


class TestPromptShapeRegression(unittest.TestCase):
    """A finding shaped like the prompt output must reach the roadmap."""

    def test_missing_verdict_keeps_debt_and_roadmap(self):
        raw = [{
            "finding": "[a.py:1] \u2014 flaw \u2192 failure",
            "severity": "CRITICAL",
            "domain": "Security",
            "est_hours": 6,
        }]
        kept, rejected = f.review_findings(raw)
        kept = f.assign_ids(f.dedup(kept))
        model = f.aggregate(kept, rejected, ["security"], ["security"])
        self.assertEqual(model["critical_issues"], 1)
        self.assertGreater(model["tech_debt_hours"], 0)
        self.assertTrue(model["roadmap"][1])


class TestOverlaps(unittest.TestCase):
    def test_same_failure_clusters(self):
        items = f.assign_ids(f.dedup([
            make("[client.py:10] \u2014 sync and async clients mirror each "
                 "other \u2192 duplicate maintenance cost", domain="Arch"),
            make("[client.py:20] \u2014 async client mirrors sync client "
                 "implementation \u2192 duplicate maintenance", domain="Quality"),
        ]))
        clusters = f.find_overlaps(items)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 2)

    def test_negation_is_not_merged(self):
        items = f.assign_ids([
            make("[a.py:1] \u2014 anchor \u2192 request rejected by handler"),
            make("[a.py:2] \u2014 anchor \u2192 request not rejected by handler"),
        ])
        self.assertEqual(f.find_overlaps(items), [])

    def test_representative_prefers_eligible_verdict(self):
        items = f.assign_ids([
            make("[a.py:1] \u2014 flaw \u2192 failure mode", verdict="QUESTIONABLE",
                 severity="CRITICAL", hours=20),
            make("[a.py:2] \u2014 flaw \u2192 failure mode", verdict="CONFIRMED",
                 severity="MEDIUM", hours=2),
        ])
        rep = f._overlap_representative(items)
        self.assertEqual(rep["da_verdict"], "CONFIRMED")

    def test_different_failures_stay_separate(self):
        items = f.assign_ids(f.dedup([
            make("[a.py:1] \u2014 unbounded dependency range \u2192 stale "
                 "bundle risk"),
            make("[b.py:2] \u2014 missing test coverage \u2192 silent "
                 "regression"),
        ]))
        self.assertEqual(f.find_overlaps(items), [])

    def test_large_same_file_is_advisory_not_merged(self):
        items = f.assign_ids(f.dedup([
            make("[client.py:10] \u2014 aaa bbb ccc \u2192 first failure mode",
                 domain="Arch", hours=10),
            make("[client.py:20] \u2014 ddd eee fff \u2192 second unrelated "
                 "failure", domain="Quality", hours=10),
        ]))
        model = f.aggregate(items, [], ["arch"], ["arch"])
        self.assertEqual(model["tech_debt_hours"], 20.0)
        advisory = [c for c in model["overlap_candidates"]
                    if c.get("advisory")]
        self.assertEqual(len(advisory), 1)
        self.assertEqual(advisory[0]["hours"], 20.0)

    def test_aggregate_counts_cluster_once(self):
        items = f.assign_ids(f.dedup([
            make("[client.py:10] \u2014 sync and async clients mirror each "
                 "other \u2192 duplicate maintenance cost", domain="Arch",
                 hours=16),
            make("[client.py:20] \u2014 async client mirrors sync client "
                 "implementation \u2192 duplicate maintenance", domain="Quality",
                 hours=16),
        ]))
        model = f.aggregate(items, [], ["arch"], ["arch"])
        self.assertEqual(model["tech_debt_hours"], 16.0)
        self.assertEqual(len(model["overlap_candidates"]), 1)
        self.assertEqual(len(model["overlap_candidates"][0]["merged"]), 1)


class TestRoadmapEligible(unittest.TestCase):
    def test_rejected_excluded(self):
        self.assertFalse(f.roadmap_eligible({"da_verdict": "REJECTED"}))

    def test_confirmed_included(self):
        self.assertTrue(f.roadmap_eligible({"da_verdict": "CONFIRMED"}))


if __name__ == "__main__":
    unittest.main()

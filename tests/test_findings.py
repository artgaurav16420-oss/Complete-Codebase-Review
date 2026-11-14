"""Tests for ccr.findings: normalization, DA checks, dedup, aggregation."""

import unittest

from ccr import findings as f


def make(finding, severity="HIGH", domain="Security", hours=2.0,
         verdict="CONFIRMED", tags=None, finding_type=None, agent=None):
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
    if agent:
        data["agent"] = agent
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

    def test_demotes_weasel_to_questionable(self):
        hedged = "[app.py:2] \u2014 this might fail \u2192 outage"
        kept, rejected = f.review_findings([make(hedged)])
        self.assertEqual(rejected, [])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["da_verdict"], "QUESTIONABLE")
        self.assertEqual(kept[0]["weasel_word"], "weasel word: might")
        self.assertNotIn("reject_reason", kept[0])

    def test_weasel_keeps_an_existing_rejected_verdict(self):
        hedged = "[app.py:2] \u2014 this might fail \u2192 outage"
        kept, rejected = f.review_findings([
            make(hedged, verdict="REJECTED"),
        ])
        self.assertEqual(rejected, [])
        self.assertEqual(kept[0]["da_verdict"], "REJECTED")
        self.assertEqual(kept[0]["weasel_word"], "weasel word: might")

    def test_weasel_does_not_hide_an_anchor_rejection(self):
        kept, rejected = f.review_findings([make("might fail")])
        self.assertEqual(kept, [])
        self.assertIn("anchor", rejected[0]["reject_reason"])

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

    def test_floor_ignores_non_string_finding_type(self):
        for bad in (["hardcoded_secret"], {"name": "hardcoded_secret"}):
            kept, _ = f.review_findings(
                [make(GOOD, hours=1, finding_type=bad)],
                floors={"hardcoded_secret": 2},
            )
            self.assertEqual(kept[0]["est_hours"], 1.0)

    def test_overflowing_estimate_becomes_zero(self):
        kept, _ = f.review_findings([make(GOOD, hours=10 ** 400)])
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

    def test_distinct_flaws_on_one_line_survive(self):
        injection = make(
            "[x.py:10] \u2014 SQL injection in query \u2192 data exfiltration",
            severity="CRITICAL", hours=4,
        )
        missing_index = make(
            "[x.py:10] \u2014 missing index on join key \u2192 full table scan",
            severity="MEDIUM", hours=2,
        )
        result = f.dedup([injection, missing_index])
        self.assertEqual(len(result), 2)
        self.assertEqual(
            {item["finding"] for item in result},
            {injection["finding"], missing_index["finding"]},
        )

    def test_identical_flaws_still_collapse(self):
        first = make(
            "[x.py:10] \u2014 SQL injection in query \u2192 data exfiltration",
            severity="CRITICAL", hours=4,
        )
        duplicate = make(
            "[x.py:10] \u2014 SQL injection in query \u2192 data exfiltration",
            severity="MEDIUM", hours=2,
        )
        result = f.dedup([first, duplicate])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["severity"], "CRITICAL")

    def test_opposite_negations_stay_separate(self):
        # Shared token "input" is not enough when one finding says the input
        # is validated and the other says it is not.
        positive = make("[x.py:10] \u2014 validates input \u2192 missing guard")
        negative = make(
            "[x.py:10] \u2014 does not validate input \u2192 injection"
        )
        self.assertEqual(len(f.dedup([positive, negative])), 2)

    def test_same_negation_still_merges(self):
        a = make(
            "[x.py:10] \u2014 does not validate input \u2192 injection"
        )
        b = make(
            "[x.py:10] \u2014 does not validate input \u2192 injection"
        )
        self.assertEqual(len(f.dedup([a, b])), 1)

    def test_intersecting_flaws_merge_transitively(self):
        # a-b share alpha, b-c share gamma; a and c share nothing. The groups
        # are connected through b, so all three collapse.
        a = make("[x.py:10] \u2014 alpha \u2192 failure one")
        b = make("[x.py:10] \u2014 gamma \u2192 failure two")
        c = make("[x.py:10] \u2014 alpha gamma \u2192 failure three")
        self.assertEqual(len(f.dedup([a, b, c])), 1)

    def test_empty_token_findings_stay_separate(self):
        # The find_overlaps tokenizer drops one-character tokens; two findings
        # with no usable tokens cannot be shown to describe the same flaw.
        a = make("[x.py:10] \u2014 x \u2192 failure one")
        b = make("[x.py:10] \u2014 y \u2192 failure two")
        self.assertEqual(len(f.dedup([a, b])), 2)

    def test_first_seen_group_order_is_preserved(self):
        a = make("[x.py:10] \u2014 alpha \u2192 failure one")
        b = make("[y.py:20] \u2014 beta \u2192 failure two")
        c = make("[x.py:10] \u2014 gamma \u2192 failure three")
        result = f.dedup([a, b, c])
        self.assertEqual(
            [item["finding"] for item in result],
            [a["finding"], b["finding"], c["finding"]],
        )

    def test_group_winner_keeps_worst_severity(self):
        low = make("[x.py:10] \u2014 flaw \u2192 alpha",
                   severity="LOW", hours=10)
        critical = make("[x.py:10] \u2014 same flaw \u2192 alpha",
                        severity="CRITICAL", hours=1)
        result = f.dedup([low, critical])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["severity"], "CRITICAL")

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
        phases = f.place_roadmap([
            make(GOOD, severity="HIGH", hours=5, domain="Architecture")
        ])
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

    def test_high_security_keys_on_agent_id(self):
        phases = f.place_roadmap([
            make(GOOD, severity="HIGH", hours=5,
                 domain="AppSec", agent="security")
        ])
        self.assertEqual(len(phases[1]), 1)

    def test_non_security_agent_with_security_label_is_not_phase_1(self):
        phases = f.place_roadmap([
            make(GOOD, severity="HIGH", hours=5,
                 domain="Security", agent="code_quality")
        ])
        self.assertEqual(len(phases[1]), 0)
        self.assertEqual(len(phases[2]), 1)

    def test_questionable_excluded(self):
        phases = f.place_roadmap([make(GOOD, verdict="QUESTIONABLE")])
        self.assertEqual(sum(len(items) for items in phases.values()), 0)

    def test_da_escalation_included(self):
        phases = f.place_roadmap([make(GOOD, verdict="DA-ESCALATION")])
        self.assertEqual(sum(len(items) for items in phases.values()), 1)

    def test_security_high_goes_phase_1(self):
        phases = f.place_roadmap([
            make(GOOD, severity="HIGH", domain="Security", hours=4)
        ])
        self.assertEqual(len(phases[1]), 1)
        self.assertEqual(len(phases[2]), 0)

    def test_renamed_security_label_comes_from_the_roster(self):
        phases = f.place_roadmap([
            make(GOOD, severity="HIGH", hours=5,
                 domain="AppSec", agent="security"),
            make("[b.py:2] \u2014 flaw \u2192 failure", severity="HIGH",
                 hours=5, domain="AppSec"),
        ])
        self.assertEqual(len(phases[1]), 2)

    def test_renamed_roster_keeps_literal_security_fallback(self):
        # The roster contributes "AppSec"; the union must still keep the
        # manifest default so an id-less finding labelled "Security" stays in
        # phase 1 after a rename.
        phases = f.place_roadmap([
            make(GOOD, severity="HIGH", hours=5,
                 domain="AppSec", agent="security"),
            make("[b.py:2] \u2014 flaw \u2192 failure", severity="HIGH",
                 hours=5, domain="Security"),
        ])
        self.assertEqual(len(phases[1]), 2)
        self.assertEqual(len(phases[2]), 0)
        self.assertIn(
            "[b.py:2] \u2014 flaw \u2192 failure",
            [item["finding"] for item in phases[1]],
        )

    def test_non_security_high_stays_phase_2(self):
        phases = f.place_roadmap([
            make(GOOD, severity="HIGH", domain="Architecture", hours=4)
        ])
        self.assertEqual(len(phases[1]), 0)
        self.assertEqual(len(phases[2]), 1)

    def test_high_never_quick_win(self):
        phases = f.place_roadmap([
            make(GOOD, severity="HIGH", hours=1, domain="Architecture")
        ])
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

    def test_baseline_domain_keys_use_agent_ids(self):
        model = self._model([
            make(GOOD, domain="AppSec", agent="security"),
        ])
        baseline = model["baseline"]
        self.assertEqual(set(baseline["per_domain_scores"]), {"security"})
        self.assertEqual(set(baseline["per_domain_open_findings"]),
                         {"security"})

    def test_re_review_count_reaches_the_baseline(self):
        kept = f.assign_ids([make(GOOD)])
        model = f.aggregate(
            kept, [], ["security"], ["security"], re_review_count=4,
        )
        self.assertEqual(model["baseline"]["re_review_count"], 4)

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

    def test_ascii_separators_are_normalized(self):
        expected = "[a.py:42] \u2014 flaw \u2192 failure"
        for text in (
            "[a.py:42] - flaw -> failure",
            "[a.py:42] -- flaw => failure",
            "[a.py:42] flaw -> failure",
            "[a.py:42] \u2013 flaw \u2192 failure",
        ):
            self.assertEqual(f.normalize_anchor(text), expected, text)
            self.assertEqual(
                f.anchor_parts(text), ("a.py", 42, "flaw", "failure"), text
            )

    def test_bracketed_path_is_normalized(self):
        # Next.js style routes: `app/[id]/page.tsx` contains a `]`.
        self.assertEqual(
            f.anchor_parts("[app/[id]/page.tsx:12] - flaw -> failure"),
            ("app/[id]/page.tsx", 12, "flaw", "failure"),
        )

    def test_arrow_inside_the_flaw_is_not_the_separator(self):
        # `=>` is a source token; the documented `->` separator comes later.
        self.assertEqual(
            f.anchor_parts("[js/a.js:5] - handler => promise is dropped -> crash"),
            ("js/a.js", 5, "handler => promise is dropped", "crash"),
        )

    def test_rocket_is_used_when_no_other_arrow_exists(self):
        self.assertEqual(
            f.anchor_parts("[a.rb:9] -- opts => nil is dereferenced"),
            ("a.rb", 9, "opts", "nil is dereferenced"),
        )

    def test_later_rocket_wins_over_an_earlier_arrow(self):
        # A lambdas `->` sits in the flaw; the separator is the following `=>`.
        self.assertEqual(
            f.anchor_parts("[a.rb:3] -- lambda -> returns a proc => nil is dereferenced"),
            ("a.rb", 3, "lambda -> returns a proc", "nil is dereferenced"),
        )

    def test_canonical_arrow_wins_over_ascii(self):
        self.assertEqual(
            f.anchor_parts("[a.py:1] - flaw \u2192 failure -> detail"),
            ("a.py", 1, "flaw", "failure -> detail"),
        )

    def test_normalize_anchor_is_idempotent(self):
        canon = "[a.py:42] \u2014 flaw \u2192 failure"
        self.assertEqual(f.normalize_anchor(canon), canon)

    def test_ascii_anchor_survives_the_gate(self):
        kept, rejected = f.review_findings([
            {"finding": "[a.py:1] - flaw -> failure mode", "severity": "LOW"},
        ])
        self.assertEqual(rejected, [])
        self.assertEqual(
            kept[0]["finding"],
            "[a.py:1] \u2014 flaw \u2192 failure mode",
        )

    def test_anchor_without_arrow_is_still_rejected(self):
        kept, rejected = f.review_findings([
            {"finding": "[a.py:1] - no failure mode here", "severity": "LOW"},
        ])
        self.assertEqual(kept, [])
        self.assertIn("anchor", rejected[0]["reject_reason"])


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

    def test_security_high_survives_a_costlier_non_security_high(self):
        # Merging the security finding away would drop the Phase 1 promotion
        # place_roadmap gives a HIGH security finding.
        items = f.assign_ids([
            make("[app.py:7] \u2014 unsanitised input in query \u2192 injection",
                 severity="HIGH", domain="Security", agent="security", hours=2),
            make("[app.py:7] \u2014 unsanitised input in query \u2192 injection",
                 severity="HIGH", domain="Architecture",
                 agent="architecture", hours=40),
        ])
        model = f.aggregate(
            items, [], ["security", "architecture"],
            ["security", "architecture"],
        )
        candidate = model["overlap_candidates"][0]
        self.assertEqual(candidate["kept"], items[0]["id"])
        self.assertEqual(candidate["merged"], [items[1]["id"]])
        phase_one = [item.get("id") for item in model["roadmap"][1]]
        self.assertIn(items[0]["id"], phase_one)

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


class TestSecurityAgentId(unittest.TestCase):
    """The security-agent id follows the same reset rule as calibration."""

    def tearDown(self):
        f.set_security_agent_id(None)

    def test_none_restores_the_default(self):
        f.set_security_agent_id("sec_team")
        self.assertEqual(f.SECURITY_AGENT_ID, "sec_team")
        f.set_security_agent_id(None)
        self.assertEqual(f.SECURITY_AGENT_ID, f._DEFAULT_SECURITY_AGENT_ID)


class TestSettingsArePerThread(unittest.TestCase):
    """Two runs in one process must not see each other's settings."""

    def test_a_thread_keeps_its_own_identity_and_calibration(self):
        import threading

        barrier = threading.Barrier(2)
        seen = {}

        def worker(key, agent_id, threshold):
            f.set_security_agent_id(agent_id)
            f.set_calibration({"overlap_threshold": threshold})
            # Both threads have set their values before either reads, so a
            # process-wide setting would hand both the same answer.
            barrier.wait(timeout=5)
            seen[key] = (f.SECURITY_AGENT_ID, f.OVERLAP_THRESHOLD)

        threads = [
            threading.Thread(target=worker, args=("a", "sec_a", 0.9)),
            threading.Thread(target=worker, args=("b", "sec_b", 0.3)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(seen["a"], ("sec_a", 0.9))
        self.assertEqual(seen["b"], ("sec_b", 0.3))
        # The reading thread keeps its own settings.
        self.assertEqual(
            f.SECURITY_AGENT_ID, f._DEFAULT_SECURITY_AGENT_ID
        )


class TestCalibration(unittest.TestCase):
    """The tunables come from the manifest (ADR-007)."""

    @classmethod
    def setUpClass(cls):
        cls.defaults = {
            "overlap_threshold": f.OVERLAP_THRESHOLD,
            "large_fix_hours": f.LARGE_FIX_HOURS,
            "quick_win_cap_hours": f.QUICK_WIN_CAP_HOURS,
        }

    def tearDown(self):
        f.set_calibration(self.defaults)

    def test_sets_all_three(self):
        f.set_calibration({
            "overlap_threshold": 0.9,
            "large_fix_hours": 2.0,
            "quick_win_cap_hours": 10.0,
        })
        self.assertEqual(
            (f.OVERLAP_THRESHOLD, f.LARGE_FIX_HOURS, f.QUICK_WIN_CAP_HOURS),
            (0.9, 2.0, 10.0),
        )

    def test_non_object_resets_to_engine_defaults(self):
        # The engine defaults, not the manifest's: ccr imports the manifest,
        # so cls.defaults may themselves have been tuned (ADR-007).
        f.set_calibration(None)
        self.assertEqual(
            (f.OVERLAP_THRESHOLD, f.LARGE_FIX_HOURS, f.QUICK_WIN_CAP_HOURS),
            (f._DEFAULT_OVERLAP_THRESHOLD, f._DEFAULT_LARGE_FIX_HOURS,
             f._DEFAULT_QUICK_WIN_CAP_HOURS),
        )

    def test_invalid_values_fall_back_to_defaults(self):
        f.set_calibration({
            "overlap_threshold": True,
            "large_fix_hours": float("nan"),
            "quick_win_cap_hours": float("inf"),
        })
        self.assertEqual(
            (f.OVERLAP_THRESHOLD, f.LARGE_FIX_HOURS, f.QUICK_WIN_CAP_HOURS),
            (f._DEFAULT_OVERLAP_THRESHOLD, f._DEFAULT_LARGE_FIX_HOURS,
             f._DEFAULT_QUICK_WIN_CAP_HOURS),
        )

    def test_out_of_range_values_fall_back_to_defaults(self):
        f.set_calibration({"overlap_threshold": 0})
        self.assertEqual(f.OVERLAP_THRESHOLD, f._DEFAULT_OVERLAP_THRESHOLD)
        f.set_calibration({"large_fix_hours": -1, "quick_win_cap_hours": 0})
        self.assertEqual(
            (f.LARGE_FIX_HOURS, f.QUICK_WIN_CAP_HOURS),
            (f._DEFAULT_LARGE_FIX_HOURS, f._DEFAULT_QUICK_WIN_CAP_HOURS),
        )

    def test_huge_int_falls_back_to_default(self):
        f.set_calibration({"large_fix_hours": 10 ** 400})
        self.assertEqual(f.LARGE_FIX_HOURS, f._DEFAULT_LARGE_FIX_HOURS)

    def test_omitted_key_restores_default(self):
        f.set_calibration({"quick_win_cap_hours": 5.0})
        f.set_calibration({"overlap_threshold": 0.5})
        self.assertEqual(
            (f.QUICK_WIN_CAP_HOURS, f.OVERLAP_THRESHOLD),
            (f._DEFAULT_QUICK_WIN_CAP_HOURS, 0.5),
        )

    def test_overlap_threshold_controls_merging(self):
        near = [
            make("[app.py:1] — a → alpha beta gamma delta"),
            make("[app.py:2] — b → alpha beta gamma delta epsilon"),
        ]
        f.set_calibration({"overlap_threshold": 0.7})
        self.assertEqual(len(f.find_overlaps(near)), 1)
        f.set_calibration({"overlap_threshold": 0.9})
        self.assertEqual(f.find_overlaps(near), [])

    def test_large_fix_default_follows_calibration(self):
        items = [
            make("[app.py:1] — a → x", hours=3),
            make("[app.py:2] — b → y", hours=3),
        ]
        f.set_calibration({"large_fix_hours": 2.0})
        self.assertEqual(len(f.find_large_file_clusters(items)), 1)
        f.set_calibration({"large_fix_hours": 8.0})
        self.assertEqual(f.find_large_file_clusters(items), [])

    def test_quick_win_cap_follows_calibration(self):
        items = [make(GOOD, severity="LOW", hours=2)]
        f.set_calibration({"quick_win_cap_hours": 1.0})
        self.assertEqual(len(f.place_roadmap(items)[2]), 1)
        f.set_calibration({"quick_win_cap_hours": 40.0})
        self.assertEqual(len(f.place_roadmap(items)[1]), 1)


if __name__ == "__main__":
    unittest.main()

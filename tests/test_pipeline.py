"""Functional pipeline test: validate review output schema per SKILL.md.

Defines the expected output schema for a completed review (Phases 1-4)
and validates that sample/reference outputs conform.
"""
import json
import unittest
from pathlib import Path

REQUIRED_SECTIONS = [
    "executive_summary",
    "per_domain_scores",
    "detailed_findings",
    "improvement_roadmap",
]

VALID_SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
VALID_DA_VERDICTS = ["CONFIRMED", "PLAUSIBLE", "QUESTIONABLE", "REJECTED"]

# Schema-validation helpers --------------------------------------------------

def validate_executive_summary(es):
    """Validate executive summary structure. Returns list of error strings."""
    errors = []
    required = {"health_score", "total_files", "total_loc", "total_findings"}
    for field in required:
        if field not in es:
            errors.append(f"executive_summary missing '{field}'")
    return errors


def validate_scores(scores):
    """Validate per-domain scores. Returns list of error strings."""
    errors = []
    if len(scores) < 14:
        errors.append(f"per_domain_scores has {len(scores)} domains, expected >= 14")
    for domain, score in scores.items():
        if not isinstance(score, (int, float)):
            errors.append(f"domain '{domain}' score not numeric: {type(score).__name__}")
        elif score < 0 or score > 10:
            errors.append(f"domain '{domain}' score {score} out of range [0, 10]")
    return errors


def validate_findings(findings):
    """Validate detailed findings list. Returns list of error strings."""
    errors = []
    required = {"finding", "severity", "domain", "est_hours", "da_verdict"}
    for idx, f in enumerate(findings):
        for field in required:
            if field not in f:
                errors.append(f"finding[{idx}] missing '{field}'")
        sev = f.get("severity", "")
        if sev and sev not in VALID_SEVERITIES:
            errors.append(f"finding[{idx}] invalid severity '{sev}'")
        dv = f.get("da_verdict", "")
        if dv and dv not in VALID_DA_VERDICTS:
            errors.append(f"finding[{idx}] invalid DA verdict '{dv}'")
        hours = f.get("est_hours", -1)
        if hours is not None and isinstance(hours, (int, float)) and hours < 0:
            errors.append(f"finding[{idx}] negative est_hours {hours}")
    return errors


def validate_roadmap(roadmap, findings=None):
    """Validate improvement roadmap structure. Returns list of error strings."""
    errors = []
    for phase in ["phase_1", "phase_2", "phase_3"]:
        if phase not in roadmap:
            errors.append(f"improvement_roadmap missing '{phase}'")
        elif not isinstance(roadmap[phase], list) or len(roadmap[phase]) == 0:
            errors.append(f"improvement_roadmap.{phase} must be a non-empty list")
    if findings:
        roadmap_items = [
            item
            for phase in roadmap.values()
            if isinstance(phase, list)
            for item in phase
        ]
        for idx, finding in enumerate(findings):
            if finding.get("da_verdict") != "REJECTED":
                continue
            title = finding.get("finding")
            if title in roadmap_items:
                errors.append(
                    f"finding[{idx}] rejected DA verdict must be excluded from roadmap"
                )
    return errors


def validate_review_output(output):
    """Validate a complete review output dict. Returns list of error strings."""
    errors = []
    for section in REQUIRED_SECTIONS:
        if section not in output:
            errors.append(f"Missing top-level section '{section}'")
            return errors
    errors.extend(validate_executive_summary(output["executive_summary"]))
    errors.extend(validate_scores(output["per_domain_scores"]))
    errors.extend(validate_findings(output["detailed_findings"]))
    errors.extend(validate_roadmap(
        output["improvement_roadmap"], output["detailed_findings"]
    ))
    return errors


# Sample valid output for testing --------------------------------------------

SAMPLE_VALID_OUTPUT = {
    "executive_summary": {
        "health_score": 6.7,
        "total_files": 23,
        "total_loc": 2802,
        "total_findings": 25,
    },
    "per_domain_scores": {
        "Architecture": 7.0,
        "Code Quality": 6.5,
        "Security": 6.0,
        "Tech Debt": 5.5,
        "Test Health": 4.0,
        "Dependencies": 7.5,
        "Documentation": 5.5,
        "Build & CI": 7.0,
        "Performance": 7.0,
        "Database & Schema": 7.0,
        "UI/UX": 6.0,
        "DevOps": 7.0,
        "Standards": 7.0,
        "Process Quality": 6.5,
    },
    "detailed_findings": [
        {
            "finding": "Hardcoded credential in git history",
            "severity": "CRITICAL",
            "domain": "Security",
            "est_hours": 2,
            "da_verdict": "CONFIRMED",
            "files": ["tests/dummy_repo/app.py"],
        },
        {
            "finding": "Command injection via shell=True",
            "severity": "CRITICAL",
            "domain": "Security",
            "est_hours": 4,
            "da_verdict": "CONFIRMED",
            "files": ["tests/dummy_repo/deploy.sh"],
        },
        {
            "finding": "No CI concurrency block",
            "severity": "HIGH",
            "domain": "Build & CI",
            "est_hours": 0.5,
            "da_verdict": "CONFIRMED",
            "files": [".github/workflows/ci.yml"],
        },
        {
            "finding": "Unused import in test_compliance.py",
            "severity": "LOW",
            "domain": "Code Quality",
            "est_hours": 0.25,
            "da_verdict": "REJECTED",
            "files": ["tests/test_compliance.py"],
        },
    ],
    "improvement_roadmap": {
        "phase_1": ["Fix hardcoded credential", "Add CI concurrency"],
        "phase_2": ["Add env-var config tests", "Add smoke tests", "Create CONTRIBUTING.md"],
        "phase_3": ["Pipeline functional test", "Coverage measurement"],
    },
}

# Tests -----------------------------------------------------------------------


class TestOutputSchemas(unittest.TestCase):
    """Schema validation helpers reject invalid and accept valid outputs."""

    def test_minimal_valid_passes(self):
        errors = validate_review_output(SAMPLE_VALID_OUTPUT)
        self.assertEqual(errors, [])

    def test_missing_section_returns_error(self):
        errors = validate_review_output({})
        self.assertGreater(len(errors), 0)
        self.assertIn("executive_summary", errors[0])

    def test_invalid_severity_detected(self):
        bad = dict(SAMPLE_VALID_OUTPUT)
        bad_findings = list(bad["detailed_findings"])
        bad_findings[0] = dict(bad_findings[0], severity="CATASTROPHIC")
        bad["detailed_findings"] = bad_findings
        errors = validate_review_output(bad)
        self.assertTrue(any("CATASTROPHIC" in e for e in errors))

    def test_invalid_da_verdict_detected(self):
        bad = dict(SAMPLE_VALID_OUTPUT)
        bad_findings = list(bad["detailed_findings"])
        bad_findings[0] = dict(bad_findings[0], da_verdict="MAYBE")
        bad["detailed_findings"] = bad_findings
        errors = validate_review_output(bad)
        self.assertTrue(any("MAYBE" in e for e in errors))

    def test_negative_est_hours_detected(self):
        bad = dict(SAMPLE_VALID_OUTPUT)
        bad_findings = list(bad["detailed_findings"])
        bad_findings[0] = dict(bad_findings[0], est_hours=-1)
        bad["detailed_findings"] = bad_findings
        errors = validate_review_output(bad)
        self.assertTrue(any("negative" in e.lower() for e in errors))

    def test_roadmap_missing_phase(self):
        bad = dict(SAMPLE_VALID_OUTPUT)
        bad["improvement_roadmap"] = {"phase_1": ["fix"], "phase_2": []}
        errors = validate_review_output(bad)
        self.assertTrue(any("phase_3" in e for e in errors))

    def test_finding_missing_field(self):
        bad = dict(SAMPLE_VALID_OUTPUT)
        bad_findings = [{"finding": "incomplete"}]
        bad["detailed_findings"] = bad_findings
        errors = validate_review_output(bad)
        self.assertTrue(any("severity" in e for e in errors))

    def test_rejected_findings_are_excluded_from_roadmap(self):
        bad = dict(SAMPLE_VALID_OUTPUT)
        rejected_title = bad["detailed_findings"][3]["finding"]
        roadmap = {
            phase: list(items)
            for phase, items in bad["improvement_roadmap"].items()
        }
        roadmap["phase_1"].append(rejected_title)
        bad["improvement_roadmap"] = roadmap
        errors = validate_review_output(bad)
        self.assertTrue(any("rejected DA verdict" in e for e in errors))

    def test_scores_out_of_range(self):
        bad = dict(SAMPLE_VALID_OUTPUT)
        scores = dict(bad["per_domain_scores"])
        scores["Security"] = 11
        bad["per_domain_scores"] = scores
        errors = validate_review_output(bad)
        self.assertTrue(any("11" in e for e in errors))

    def test_executive_summary_missing_field(self):
        bad = dict(SAMPLE_VALID_OUTPUT)
        bad["executive_summary"] = {"health_score": 6.0}
        errors = validate_review_output(bad)
        self.assertTrue(any("total_files" in e for e in errors))

    def test_fewer_than_14_scores_detected(self):
        bad = dict(SAMPLE_VALID_OUTPUT)
        scores = dict(bad["per_domain_scores"])
        bad["per_domain_scores"] = dict(list(scores.items())[:5])
        errors = validate_review_output(bad)
        self.assertTrue(any("5 domains" in e for e in errors))


class TestSampleOutputValidation(unittest.TestCase):
    """The sample output is the reference — must always pass strict validation."""

    def test_sample_passes_strict_validation(self):
        errors = validate_review_output(SAMPLE_VALID_OUTPUT)
        self.assertEqual(errors, [],
                         f"Sample output failed validation: {errors}")

    def test_sample_can_be_serialized_to_json(self):
        dumped = json.dumps(SAMPLE_VALID_OUTPUT, indent=2)
        loaded = json.loads(dumped)
        self.assertEqual(loaded, SAMPLE_VALID_OUTPUT)

    def test_sample_has_all_scores_between_0_and_10(self):
        for domain, score in SAMPLE_VALID_OUTPUT["per_domain_scores"].items():
            with self.subTest(domain=domain):
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 10)


if __name__ == "__main__":
    unittest.main()

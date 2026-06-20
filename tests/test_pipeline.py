"""Schema contract tests: validate review output structure per SKILL.md Output Format.
AKA test_output_schema.py in spirit — this is a schema-contract test, not a pipeline
integration test.

Defines the expected Markdown output structure (Executive Summary, Per-Domain
Scores, Detailed Findings, Improvement Roadmap, Tech Debt Summary, Agent
Status) and validates that sample outputs conform.
"""
import re
import unittest

VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
VALID_DA_VERDICTS = {"CONFIRMED", "PLAUSIBLE", "QUESTIONABLE", "REJECTED"}
VALID_HEALTH = {"GREEN", "YELLOW", "RED"}

REQUIRED_ES_FIELDS = [
    "Overall Health", "Codebase Size", "Critical Issues",
    "Tech Debt", "Priority Areas",
]

REQUIRED_SECTIONS = [
    "## Executive Summary",
    "## Per-Domain Scores",
    "## Detailed Findings",
    "## Improvement Roadmap",
    "## Tech Debt Summary",
    "## Agent Status",
]


def _section_text(md, header):
    """Return text of a section by its ## header, or empty string."""
    pattern = rf"(^{re.escape(header)}\s*\n.*?)(?=^## |\Z)"
    m = re.search(pattern, md, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _table_rows(text):
    """Return list of data rows from a markdown table (skips header/separator)."""
    lines = [l.strip() for l in text.split("\n") if l.startswith("|")]
    if len(lines) < 3:
        return []
    return lines[2:]


def _parse_table_row(row_text):
    """Split a markdown table row into cell values, stripped."""
    return [c.strip() for c in row_text.strip("|").split("|")]


# Markdown validators ---------------------------------------------------------


def validate_executive_summary(md):
    """Validate Executive Summary section. Returns list of error strings."""
    errors = []
    text = _section_text(md, "## Executive Summary")
    if not text:
        errors.append("Missing Executive Summary section")
        return errors
    for field in REQUIRED_ES_FIELDS:
        if f"**{field}**" not in text:
            errors.append(f"Executive Summary missing field: '{field}'")
    m = re.search(r'\*\*Overall Health\*\*:\s*(\S+)', text)
    if m and m.group(1) not in VALID_HEALTH:
        errors.append(f"Invalid Overall Health value: '{m.group(1)}'")
    return errors


def validate_per_domain_scores(md):
    """Validate Per-Domain Scores table. Returns list of error strings."""
    errors = []
    text = _section_text(md, "## Per-Domain Scores")
    if not text:
        errors.append("Missing Per-Domain Scores section")
        return errors
    lines = text.strip().split("\n")
    header_found = any(
        "| Domain | Score (/10) | Critical | High | Medium | Low |" in l
        for l in lines
    )
    if not header_found:
        errors.append("Per-Domain Scores table missing or has wrong columns")
        return errors
    rows = _table_rows(text)
    data_rows = [r for r in rows if "**Overall**" not in r]
    if not data_rows:
        errors.append("Per-Domain Scores table has no data rows")
    for row in data_rows:
        cells = _parse_table_row(row)
        if len(cells) < 6:
            errors.append(f"Per-Domain row has {len(cells)} columns: {row}")
            continue
        try:
            score = float(cells[1])
            if score < 0 or score > 10:
                errors.append(f"Domain '{cells[0]}' score {score} out of range [0, 10]")
        except ValueError:
            errors.append(f"Domain '{cells[0]}' score not numeric: '{cells[1]}'")
    overall_rows = [r for r in rows if "**Overall**" in r]
    if not overall_rows:
        errors.append("Missing Overall row in Per-Domain Scores")
    return errors


def validate_detailed_findings(md):
    """Validate Detailed Findings table. Returns list of error strings."""
    errors = []
    text = _section_text(md, "## Detailed Findings")
    if not text:
        errors.append("Missing Detailed Findings section")
        return errors
    lines = text.strip().split("\n")
    header_found = any(
        "| Finding | Severity | Domain | Est. Hours | DA Verdict |" in l
        for l in lines
    )
    if not header_found:
        errors.append("Detailed Findings table missing or has wrong columns")
        return errors
    rows = _table_rows(text)
    if not rows:
        errors.append("Detailed Findings table has no data rows")
    for idx, row in enumerate(rows):
        cells = _parse_table_row(row)
        if len(cells) < 5:
            errors.append(f"Finding[{idx}] has {len(cells)} columns: {row}")
            continue
        sev = cells[1].strip()
        if sev not in VALID_SEVERITIES:
            errors.append(f"Finding[{idx}] invalid severity '{sev}'")
        dv = cells[4].strip()
        if dv not in VALID_DA_VERDICTS:
            errors.append(f"Finding[{idx}] invalid DA verdict '{dv}'")
    return errors


def _extract_findings_from_md(md):
    """Parse findings from markdown table into list of dicts for roadmap check."""
    text = _section_text(md, "## Detailed Findings")
    if not text:
        return []
    rows = _table_rows(text)
    findings = []
    for idx, row in enumerate(rows):
        cells = _parse_table_row(row)
        if len(cells) >= 5:
            findings.append({
                "finding": cells[0],
                "severity": cells[1],
                "domain": cells[2],
                "est_hours": cells[3],
                "da_verdict": cells[4],
            })
    return findings


def _extract_roadmap_items(md):
    """Parse roadmap phase bullet items into flat list of strings."""
    text = _section_text(md, "## Improvement Roadmap")
    if not text:
        return []
    items = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            items.append(line[2:].strip())
    return items


def validate_improvement_roadmap(md, findings=None):
    """Validate Improvement Roadmap. Returns list of error strings."""
    errors = []
    text = _section_text(md, "## Improvement Roadmap")
    if not text:
        errors.append("Missing Improvement Roadmap section")
        return errors
    for phase in ["Phase 1", "Phase 2", "Phase 3"]:
        if f"### {phase}" not in text and f"**{phase}**" not in text:
            errors.append(f"Improvement Roadmap missing {phase}")
    if findings:
        roadmap_items = [item.strip().casefold() for item in _extract_roadmap_items(md)]
        for idx, f in enumerate(findings):
            if f.get("da_verdict") != "REJECTED":
                continue
            title = f.get("finding", "").strip().casefold()
            if not title:
                continue
            if any(title == ri for ri in roadmap_items):
                errors.append(
                    f"Finding[{idx}] rejected DA verdict must be excluded from roadmap"
                )
    return errors


def validate_tech_debt_summary(md):
    """Validate Tech Debt Summary section. Returns list of error strings."""
    errors = []
    text = _section_text(md, "## Tech Debt Summary")
    if not text:
        errors.append("Missing Tech Debt Summary section")
        return errors
    for field in ["Total estimated", "By domain", "Trend"]:
        if f"**{field}**" not in text:
            errors.append(f"Tech Debt Summary missing field: '{field}'")
    return errors


def validate_tech_debt_reconciliation(md):
    """Reconcile Roadmap phase totals, Tech Debt Summary total, and domain
    breakdown sum. All three must agree. Returns list of error strings."""
    errors = []
    roadmap_text = _section_text(md, "## Improvement Roadmap")
    debt_text = _section_text(md, "## Tech Debt Summary")
    if not roadmap_text or not debt_text:
        return errors  # individual validators cover missing sections

    # Extract sum of roadmap phase estimates
    roadmap_total = 0.0
    for m in re.finditer(
        r'(?mi)^#+\s+Phase\s+\d+.*estimated:\s*(\d+(?:\.\d+)?)\s*hours?', roadmap_text
    ):
        roadmap_total += float(m.group(1))

    # Extract Tech Debt Summary total
    total_m = re.search(
        r'(?i)\*\*Total estimated\*\*:\s*(\d+(?:\.\d+)?)\s*hours?', debt_text
    )
    summary_total = float(total_m.group(1)) if total_m else None

    # Extract and sum domain breakdown (handles single-line, multi-line, and table formats)
    domain_m = re.search(
        r'(?si)\*\*By domain\*\*:\s*(.*?)(?=\n\s*[-*+]\s+|\n\s*\d+\.\s+|\Z)', debt_text
    )
    domain_total = None
    if domain_m:
        values = re.findall(r'(?i)\b(\d+(?:\.\d+)?)h\b', domain_m.group(1))
        if values:
            domain_total = round(sum(float(h) for h in values), 2)
        else:
            domain_total = 0.0

    roadmap_total = round(roadmap_total, 2)
    if summary_total is not None:
        summary_total = round(summary_total, 2)

    if summary_total is None:
        errors.append(
            "Tech Debt Summary total field not found or unparseable"
        )
    if domain_total is None:
        errors.append(
            "Domain breakdown field not found or unparseable"
        )
    if summary_total is not None and roadmap_total != summary_total:
        errors.append(
            f"Roadmap phase total ({roadmap_total}h) != "
            f"Tech Debt Summary total ({summary_total}h)"
        )
    if domain_total is not None and summary_total is not None and domain_total != summary_total:
        errors.append(
            f"Domain breakdown sum ({domain_total}h) != "
            f"Tech Debt Summary total ({summary_total}h)"
        )
    return errors


def validate_agent_status(md):
    """Validate Agent Status section. Returns list of error strings."""
    errors = []
    text = _section_text(md, "## Agent Status")
    if not text:
        errors.append("Missing Agent Status section")
        return errors
    if "Completed:" not in text:
        errors.append("Agent Status missing Completed count")
    return errors


def validate_markdown_output(md):
    """Validate a complete review output Markdown document. Returns list of errors."""
    errors = []
    for section in REQUIRED_SECTIONS:
        if section not in md:
            errors.append(f"Missing section '{section}'")
    errors.extend(validate_executive_summary(md))
    errors.extend(validate_per_domain_scores(md))
    errors.extend(validate_detailed_findings(md))
    errors.extend(validate_improvement_roadmap(md, _extract_findings_from_md(md)))
    errors.extend(validate_tech_debt_summary(md))
    errors.extend(validate_tech_debt_reconciliation(md))
    errors.extend(validate_agent_status(md))
    return errors


# Sample valid markdown output -------------------------------------------------

SAMPLE_VALID_OUTPUT = r"""# Codebase Health Report — my-web-app (src/)

## Executive Summary
- **Overall Health**: YELLOW
- **Codebase Size**: 47,320 LOC, 312 files, 8 modules
- **Critical Issues**: 3
- **Tech Debt**: 200 engineering hours
- **Priority Areas**: Security (hardcoded secrets), Architecture (circular deps), Process Quality (Karpathy compliance)

## Per-Domain Scores
| Domain | Score (/10) | Critical | High | Medium | Low |
|--------|------------|----------|------|--------|-----|
| Architecture | 6 | 1 | 2 | 3 | 1 |
| Security | 4 | 2 | 3 | 1 | 0 |
| Process Quality | 8 | 0 | 1 | 1 | 2 |
| Code Quality | 7 | 0 | 1 | 4 | 2 |
| Test Health | 5 | 0 | 2 | 2 | 1 |
| Dependencies | 8 | 0 | 0 | 2 | 3 |
| Documentation | 6 | 0 | 1 | 1 | 4 |
| Build & CI | 9 | 0 | 0 | 1 | 1 |
| Database | 7 | 0 | 1 | 1 | 1 |
| **Overall** | **6.5** | **3** | **11** | **16** | **15** |

## Detailed Findings

| Finding | Severity | Domain | Est. Hours | DA Verdict |
|---------|----------|--------|------------|------------|
| Hardcoded DB password in config/database.php | CRITICAL | Security | 2h | CONFIRMED |
| Circular dep: auth -> user -> notification -> auth | CRITICAL | Architecture | 8h | CONFIRMED |
| Hardcoded API key in tests/fixtures/auth.json | CRITICAL | Security | 2h | CONFIRMED |
| Vibe coding: no behavior-driven tests found | HIGH | Process Quality | 4h | CONFIRMED |
| Module user/service.go: cyclomatic complexity 34 | HIGH | Code Quality | 4h | CONFIRMED |
| Test coverage <20% in 3 of 8 modules | HIGH | Test Health | 12h | PLAUSIBLE |
| Deprecated lodash.set used in 17 call sites | HIGH | Dependencies | 3h | CONFIRMED |
| Missing API docs for /admin/* endpoints (9 endpoints) | HIGH | Documentation | 4.5h | CONFIRMED |
| N+1 query in /orders endpoint | HIGH | Database | 3h | CONFIRMED |
| Mixed snake_case and camelCase in src/models | MEDIUM | Standards | 2h | QUESTIONABLE |
| Unused import in test_compliance.py | LOW | Code Quality | 0.25h | REJECTED |

## Improvement Roadmap

### Phase 1 — Now (estimated: 35 hours)
- T-001: Rotate hardcoded secrets -> env vars -> 4h
- T-002: Break auth->user->notification cycle via event bus -> 8h
- T-003: Implement behavior-driven tests for core auth logic -> 4h
- T-004: Add unit tests for 3 uncovered modules -> 12h
- T-005: Replace lodash.set with native optional chaining -> 3h
- T-006: Add rate limiting to auth endpoints -> 4h

### Phase 2 — Next Quarter (estimated: 47 hours)
- T-007: Refactor high-complexity functions (17 functions >15 cyclomatic) -> 14h
- T-008: Document all undocumented API endpoints -> 10h
- T-009: Fix N+1 queries (3 instances) -> 9h
- T-010: Migrate from Moment.js to date-fns -> 8h
- T-011: Add E2E tests for critical paths -> 6h

### Phase 3 — Backlog (estimated: 118 hours)
- T-012: Implement design system component library -> 40h
- T-013: Add performance benchmarking pipeline -> 16h
- T-014: Full OWASP Top 10 hardening audit -> 24h
- ... (remaining 8 tasks)

## Tech Debt Summary
- **Total estimated**: 200 hours
- **By domain**: Security 18h, Architecture 24h, Code Quality 32h, Test Health 48h, Process Quality 12h, Dependencies 12h, Documentation 20h, Standards 16h, Database 18h
- **Trend**: First baseline -- no trend data

## Agent Status
- Completed: 12/14 agents
- Failed (timeout): Performance Baseline, UI/UX Auditor (noted in findings)
- Report verified by devil's advocate
- **DA Verdict**: 24 CONFIRMED, 8 PLAUSIBLE, 3 QUESTIONABLE, 1 REJECTED
"""


# Mutation helpers for test inputs --------------------------------------------


def _replace_in_table(md, header, old_cell, new_cell, col_index):
    """Replace a cell value in the first matching table row under a ## header."""
    text = _section_text(md, header)
    if not text:
        return md
    rows = _table_rows(text)
    target_line = None
    for row in rows:
        cells = _parse_table_row(row)
        if len(cells) > col_index and cells[col_index].strip() == old_cell:
            target_line = row
            break
    if not target_line:
        return md
    new_line = target_line.replace(old_cell, new_cell, 1)
    return md.replace(target_line, new_line)


def _replace_in_section(md, header, old, new):
    """Replace text within a section."""
    text = _section_text(md, header)
    if not text:
        return md
    new_text = text.replace(old, new)
    return md.replace(text, new_text)


def _remove_section(md, header):
    """Remove a ## section and its content from markdown."""
    pattern = rf"(^{re.escape(header)}\s*\n.*?)(?=^## |\Z)"
    return re.sub(pattern, "", md, count=1, flags=re.MULTILINE | re.DOTALL).strip()


# Tests -----------------------------------------------------------------------


class TestMarkdownValidation(unittest.TestCase):
    """Markdown validators reject invalid and accept valid outputs."""

    def test_minimal_valid_passes(self):
        errors = validate_markdown_output(SAMPLE_VALID_OUTPUT)
        self.assertEqual(errors, [])

    def test_missing_section_returns_error(self):
        md = _remove_section(SAMPLE_VALID_OUTPUT, "## Executive Summary")
        errors = validate_markdown_output(md)
        self.assertTrue(any("Executive Summary" in e for e in errors))

    def test_invalid_severity_detected(self):
        md = _replace_in_table(
            SAMPLE_VALID_OUTPUT, "## Detailed Findings",
            "CRITICAL", "CATASTROPHIC", 1,
        )
        errors = validate_markdown_output(md)
        self.assertTrue(any("CATASTROPHIC" in e for e in errors))

    def test_invalid_da_verdict_detected(self):
        md = _replace_in_table(
            SAMPLE_VALID_OUTPUT, "## Detailed Findings",
            "CONFIRMED", "MAYBE", 4,
        )
        errors = validate_markdown_output(md)
        self.assertTrue(any("MAYBE" in e for e in errors))

    def test_invalid_health_value_detected(self):
        md = _replace_in_section(
            SAMPLE_VALID_OUTPUT, "## Executive Summary",
            "YELLOW", "PURPLE",
        )
        errors = validate_markdown_output(md)
        self.assertTrue(any("PURPLE" in e for e in errors))

    def test_roadmap_missing_phase(self):
        md = _replace_in_section(
            SAMPLE_VALID_OUTPUT, "## Improvement Roadmap",
            "### Phase 3", "### Phase X",
        )
        errors = validate_markdown_output(md)
        self.assertTrue(any("Phase 3" in e for e in errors))

    def test_executive_summary_missing_field(self):
        md = _replace_in_section(
            SAMPLE_VALID_OUTPUT, "## Executive Summary",
            "**Priority Areas**", "**MissingField**",
        )
        errors = validate_markdown_output(md)
        self.assertTrue(any("Priority Areas" in e for e in errors))

    def test_score_out_of_range(self):
        md = _replace_in_table(
            SAMPLE_VALID_OUTPUT, "## Per-Domain Scores",
            "4", "11", 1,
        )
        errors = validate_markdown_output(md)
        self.assertTrue(any("11" in e for e in errors))

    def test_rejected_findings_are_excluded_from_roadmap(self):
        md = SAMPLE_VALID_OUTPUT.replace(
            "- ... (remaining 8 tasks)",
            "- Unused import in test_compliance.py\n- ... (remaining 8 tasks)",
        )
        errors = validate_markdown_output(md)
        self.assertTrue(any("rejected DA verdict" in e for e in errors))

    def test_rejected_findings_exact_title_matching(self):
        md = SAMPLE_VALID_OUTPUT.replace(
            "Unused import in test_compliance.py",
            "Different title altogether",
        )
        errors = validate_markdown_output(md)
        self.assertFalse(any("rejected DA verdict" in e for e in errors))

    def test_missing_overall_row_detected(self):
        md = _replace_in_section(
            SAMPLE_VALID_OUTPUT, "## Per-Domain Scores",
            "| **Overall** | **6.5** | **3** | **11** | **16** | **15** |",
            "",
        )
        errors = validate_markdown_output(md)
        self.assertTrue(any("Overall" in e for e in errors))

    def test_tech_debt_missing_field(self):
        md = _replace_in_section(
            SAMPLE_VALID_OUTPUT, "## Tech Debt Summary",
            "**Trend**", "**TrendX**",
        )
        errors = validate_markdown_output(md)
        self.assertTrue(any("Trend" in e for e in errors))


class TestSampleOutputValidation(unittest.TestCase):
    """The sample output is the reference -- must always pass strict validation."""

    def test_sample_passes_strict_validation(self):
        errors = validate_markdown_output(SAMPLE_VALID_OUTPUT)
        self.assertEqual(errors,
                         [],
                         f"Sample output failed validation: {errors}")

    def test_sample_has_all_required_sections(self):
        for section in REQUIRED_SECTIONS:
            with self.subTest(section=section):
                self.assertIn(section, SAMPLE_VALID_OUTPUT,
                              f"Missing section: {section}")

    def test_sample_es_fields_present(self):
        text = _section_text(SAMPLE_VALID_OUTPUT, "## Executive Summary")
        for field in REQUIRED_ES_FIELDS:
            with self.subTest(field=field):
                self.assertIn(f"**{field}**", text)

    def test_sample_has_findings_with_valid_severities(self):
        findings = _extract_findings_from_md(SAMPLE_VALID_OUTPUT)
        self.assertGreater(len(findings), 0)
        for f in findings:
            with self.subTest(finding=f["finding"][:30]):
                self.assertIn(f["severity"], VALID_SEVERITIES)
                self.assertIn(f["da_verdict"], VALID_DA_VERDICTS)

    def test_sample_rejected_excluded_from_roadmap(self):
        findings = _extract_findings_from_md(SAMPLE_VALID_OUTPUT)
        rejected = [f for f in findings if f["da_verdict"] == "REJECTED"]
        roadmap_items = _extract_roadmap_items(SAMPLE_VALID_OUTPUT)
        for f in rejected:
            title = f["finding"].strip().casefold()
            self.assertFalse(
                any(title == item.strip().casefold() for item in roadmap_items),
                f"REJECTED finding '{f['finding']}' found in roadmap",
            )

    def test_sample_tech_debt_reconciliation_passes(self):
        errors = validate_tech_debt_reconciliation(SAMPLE_VALID_OUTPUT)
        self.assertEqual(errors, [],
                         f"Sample tech debt reconciliation failed: {errors}")

    def test_sample_roadmap_phase_totals_match(self):
        text = _section_text(SAMPLE_VALID_OUTPUT, "## Improvement Roadmap")
        totals = [float(m.group(1)) for m in
                  re.finditer(r'(?mi)^#+\s+Phase\s+\d+.*estimated:\s*(\d+(?:\.\d+)?)\s*hours?', text)]
        self.assertEqual(sum(totals), 200,
                         f"Roadmap phases {totals} sum to {sum(totals)}h, expected 200h")

    def test_actual_health_report_passes_validation(self):
        import os
        report_path = os.path.join(
            os.path.dirname(__file__), os.pardir, ".code-review-cache", "health-report.md"
        )
        if not os.path.isfile(report_path):
            self.skipTest(f"Health report not found at {report_path}")
        with open(report_path, encoding="utf-8") as f:
            content = f.read()
        errors = validate_markdown_output(content)
        self.assertEqual(
            errors,
            [],
            f"Actual health-report.md failed validation:\n" + "\n".join(f"  - {e}" for e in errors),
        )


if __name__ == "__main__":
    unittest.main()

"""Schema contract tests: validate review output structure per SKILL.md Output Format.
AKA test_output_schema.py in spirit — this is a schema-contract test, not a pipeline
integration test.

Defines the expected Markdown output structure (Executive Summary, Per-Domain
Scores, Detailed Findings, Improvement Roadmap, Tech Debt Summary, Agent
Status) and validates that sample outputs conform.
"""
import re
import unittest
from pathlib import Path

VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
VALID_DA_VERDICTS = {
    "CONFIRMED", "PLAUSIBLE", "QUESTIONABLE", "REJECTED", "DA-ESCALATION",
}
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
        r'(?mi)^(?:\#+\s+|\*\*)?Phase\s+\d+.*estimated:\s*(\d+(?:\.\d+)?)\s*hours?', roadmap_text
    ):
        roadmap_total += float(m.group(1))

    # Extract Tech Debt Summary total
    total_m = re.search(
        r'(?i)\*\*Total estimated\*\*:\s*(\d+(?:\.\d+)?)\s*hours?', debt_text
    )
    summary_total = float(total_m.group(1)) if total_m else None

    # Extract and sum domain breakdown (handles single-line, multi-line, and table formats)
    domain_m = re.search(
        r'(?si)\*\*By domain\*\*:\s*(.*?)(?=\n\s{0,1}[-*+]\s+|\n\s*#|\n\s*\d+\.\s+|\Z)', debt_text
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
    if summary_total is not None and abs(roadmap_total - summary_total) >= 0.5:
        errors.append(
            f"Roadmap phase total ({roadmap_total}h) != "
            f"Tech Debt Summary total ({summary_total}h)"
        )
    if (
        domain_total is not None
        and summary_total is not None
        and abs(domain_total - summary_total) >= 0.5
    ):
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


WEASEL_PATTERNS = [
    r'\bmight\b', r'\blikely\b', r'\bcould\s+potentially\b',
    r'\bit\s+is\s+recommended\b', r'\bconsider\s+refactoring\b',
    r'\bbest\s+practice\s+suggests\b', r'\bgenerally\s+speaking\b',
    r'\bin\s+most\s+cases\b',
]


def validate_findings_have_evidence(md):
    """Check findings contain file:line anchors and no weasel words."""
    errors = []
    findings_text = _section_text(md, "## Detailed Findings")
    for line in _table_rows(findings_text):
        cells = _parse_table_row(line)
        if len(cells) < 1:
            continue
        finding = cells[0]
        if not re.match(r'^\[[^:]+:\d+\]\s+—\s+.+?\s+→\s+.+$', finding):
            errors.append(
                f"Finding missing [file:line] — flaw → failure_mode: "
                f"{finding[:60]}"
            )
        finding_desc = re.sub(r'^\[[^\]]+\]\s*—\s*', '', finding)
        for pattern in WEASEL_PATTERNS:
            if re.search(pattern, finding_desc, re.IGNORECASE):
                errors.append(f"Finding contains weasel word: {finding[:60]}")
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
    errors.extend(validate_findings_have_evidence(md))
    return errors


# JSON output format ------------------------------------------------------------

VALID_HEALTH_JSON = {"GREEN", "YELLOW", "RED"}
VALID_SEVERITIES_JSON = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_DA_VERDICTS_JSON = {
    "CONFIRMED", "PLAUSIBLE", "QUESTIONABLE", "REJECTED", "DA-ESCALATION",
}
REQUIRED_REPORT_FIELDS = [
    "report", "per_domain_scores", "findings", "roadmap",
    "tech_debt", "agent_status", "baseline",
]
REQUIRED_REPORT_SUBFIELDS = [
    "title", "overall_health", "critical_issues", "tech_debt_hours",
]
REQUIRED_FINDING_FIELDS = [
    "id", "finding", "severity", "domain", "est_hours", "da_verdict",
]
REQUIRED_AGENT_STATUS_FIELDS = [
    "completed", "total", "da_verdict_summary",
]
REQUIRED_TECH_DEBT_FIELDS = [
    "total_hours", "by_domain", "trend",
]


def validate_json_output(data):
    """Validate a JSON health report object. Returns list of error strings."""
    errors = []
    if not isinstance(data, dict):
        errors.append("JSON root must be a dict")
        return errors
    for field in REQUIRED_REPORT_FIELDS:
        if field not in data:
            errors.append(f"Missing top-level field: '{field}'")
    report = data.get("report")
    if not isinstance(report, dict):
        errors.append("report must be a dict")
    else:
        for field in REQUIRED_REPORT_SUBFIELDS:
            if field not in report:
                errors.append(f"Missing report field: '{field}'")
        health = report.get("overall_health")
        if health and health not in VALID_HEALTH_JSON:
            errors.append(f"Invalid overall_health: '{health}'")
    scores = data.get("per_domain_scores")
    if not isinstance(scores, dict):
        errors.append("per_domain_scores must be a dict")
    else:
        for domain, scores_obj in scores.items():
            if not isinstance(scores_obj, dict):
                errors.append(f"per_domain_scores.{domain} must be a dict")
                continue
            s = scores_obj.get("score")
            if s is not None and (
                not isinstance(s, (int, float)) or s < 0 or s > 10
            ):
                errors.append(
                    f"per_domain_scores.{domain} score {s} out of range [0, 10]"
                )
    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
    else:
        for idx, f in enumerate(findings):
            if not isinstance(f, dict):
                errors.append(f"findings[{idx}] must be a dict")
                continue
            for field in REQUIRED_FINDING_FIELDS:
                if field not in f:
                    errors.append(f"findings[{idx}] missing field '{field}'")
            sev = f.get("severity")
            if sev and sev not in VALID_SEVERITIES_JSON:
                errors.append(f"findings[{idx}] invalid severity '{sev}'")
            dv = f.get("da_verdict")
            if dv and dv not in VALID_DA_VERDICTS_JSON:
                errors.append(f"findings[{idx}] invalid da_verdict '{dv}'")
    roadmap = data.get("roadmap")
    if not isinstance(roadmap, dict):
        errors.append("roadmap must be a dict")
    else:
        for phase_key in ["phase_1", "phase_2", "phase_3"]:
            if phase_key not in roadmap:
                errors.append(f"roadmap missing '{phase_key}'")
    tech_debt = data.get("tech_debt")
    if not isinstance(tech_debt, dict):
        errors.append("tech_debt must be a dict")
    else:
        for field in REQUIRED_TECH_DEBT_FIELDS:
            if field not in tech_debt:
                errors.append(f"tech_debt missing field: '{field}'")
    status = data.get("agent_status")
    if not isinstance(status, dict):
        errors.append("agent_status must be a dict")
    else:
        for field in REQUIRED_AGENT_STATUS_FIELDS:
            if field not in status:
                errors.append(f"agent_status missing field: '{field}'")
    baseline = data.get("baseline")
    if not isinstance(baseline, dict):
        errors.append("baseline must be a dict")
    elif "timestamp" not in baseline:
        errors.append("baseline missing field: 'timestamp'")
    return errors


# Sample valid JSON output -----------------------------------------------------

SAMPLE_VALID_JSON = {
    "report": {
        "title": "Codebase Health Report",
        "overall_health": "YELLOW",
        "codebase_size": {"loc": 47320, "files": 312, "modules": 8},
        "critical_issues": 3,
        "tech_debt_hours": 200,
        "priority_areas": ["Security", "Architecture", "Process Quality"],
    },
    "per_domain_scores": {
        "architecture": {
            "score": 6.0, "critical": 1, "high": 2, "medium": 3, "low": 1
        },
        "security": {
            "score": 4.0, "critical": 2, "high": 3, "medium": 1, "low": 0
        },
        "process_quality": {
            "score": 8.0, "critical": 0, "high": 1, "medium": 1, "low": 2
        },
        "code_quality": {
            "score": 7.0, "critical": 0, "high": 1, "medium": 4, "low": 2
        },
        "test_health": {
            "score": 5.0, "critical": 0, "high": 2, "medium": 2, "low": 1
        },
        "dependencies": {
            "score": 8.0, "critical": 0, "high": 0, "medium": 2, "low": 3
        },
        "documentation": {
            "score": 6.0, "critical": 0, "high": 1, "medium": 1, "low": 4
        },
        "build_ci": {
            "score": 9.0, "critical": 0, "high": 0, "medium": 1, "low": 1
        },
        "database": {
            "score": 7.0, "critical": 0, "high": 1, "medium": 1, "low": 1
        },
    },
    "findings": [
        {
            "id": "F-001",
            "finding": (
                "[config/database.php:42] - Hardcoded DB password"
                " -> credential leak on source exposure"
            ),
            "severity": "CRITICAL",
            "domain": "security",
            "est_hours": 2.0,
            "da_verdict": "CONFIRMED",
        },
        {
            "id": "F-002",
            "finding": (
                "[src/auth/cycle.go:15] - Circular dep"
                " auth->user->notification->auth"
                " -> startup deadlock risk"
            ),
            "severity": "CRITICAL",
            "domain": "architecture",
            "est_hours": 8.0,
            "da_verdict": "CONFIRMED",
        },
        {
            "id": "F-003",
            "finding": (
                "[tests/fixtures/auth.json:3] - Hardcoded API key"
                " -> credential leak in test artifacts"
            ),
            "severity": "CRITICAL",
            "domain": "security",
            "est_hours": 2.0,
            "da_verdict": "CONFIRMED",
        },
    ],
    "roadmap": {
        "phase_1": {
            "title": "Now",
            "estimated_hours": 35.0,
            "tasks": [
                {
                    "id": "T-001",
                    "description": "Rotate hardcoded secrets -> env vars",
                    "hours": 4,
                }
            ],
        },
        "phase_2": {
            "title": "Next Quarter",
            "estimated_hours": 47.0,
            "tasks": [
                {
                    "id": "T-007",
                    "description": "Refactor high-complexity functions",
                    "hours": 14,
                }
            ],
        },
        "phase_3": {
            "title": "Backlog",
            "estimated_hours": 118.0,
            "tasks": [
                {
                    "id": "T-012",
                    "description": "Implement design system component library",
                    "hours": 40,
                }
            ],
        },
    },
    "tech_debt": {
        "total_hours": 200.0,
        "by_domain": {
            "security": 18, "architecture": 24, "code_quality": 32,
            "test_health": 48, "process_quality": 12, "dependencies": 12,
            "documentation": 20, "standards": 16, "database": 18,
        },
        "trend": "First baseline -- no trend data",
    },
    "agent_status": {
        "completed": 12,
        "total": 14,
        "failed": ["Performance Baseline", "UI/UX Auditor"],
        "da_verdict_summary": {"confirmed": 24, "plausible": 8, "questionable": 3, "rejected": 1},
    },
    "baseline": {
        "timestamp": "2026-07-30T12:00:00Z",
        "target": "src/",
        "trend_vs_previous": "none",
    },
}



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
| [config/database.php:42] — Hardcoded DB password → credential leak on source exposure | CRITICAL | Security | 2h | CONFIRMED |
| [src/auth/cycle.go:15] — Circular dep auth→user→notification→auth → startup deadlock risk | CRITICAL | Architecture | 8h | CONFIRMED |
| [tests/fixtures/auth.json:3] — Hardcoded API key → credential leak in test artifacts | CRITICAL | Security | 2h | CONFIRMED |
| [src/auth/handler.go:1] — No behavior-driven tests → unverified auth logic regressions | HIGH | Process Quality | 4h | CONFIRMED |
| [src/user/service.go:67] — Cyclomatic complexity 34 → unmaintainable, error-prone changes | HIGH | Code Quality | 4h | CONFIRMED |
| [src/modules/*/test.py:1] — Test coverage <20% in 3 of 8 modules → silent regressions undetected | HIGH | Test Health | 12h | PLAUSIBLE |
| [src/utils/lodash.js:12] — Deprecated lodash.set in 17 call sites → prototype pollution risk | HIGH | Dependencies | 3h | CONFIRMED |
| [docs/api/admin.md:1] — Missing API docs for /admin/* endpoints (9 endpoints) → integration failures | HIGH | Documentation | 4.5h | CONFIRMED |
| [src/api/orders.py:89] — N+1 query in /orders endpoint → O(n) DB calls, timeout on scale | HIGH | Database | 3h | CONFIRMED |
| [src/models/index.ts:1] — Mixed snake_case and camelCase → inconsistent API contracts | MEDIUM | Standards | 2h | QUESTIONABLE |
| [tests/test_compliance.py:5] — Unused import → minor dead code, no runtime impact | LOW | Code Quality | 0.25h | REJECTED |

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
        replacement = (
            "- [tests/test_compliance.py:5] — Unused import"
            " → minor dead code, no runtime impact\n"
            "- ... (remaining 8 tasks)"
        )
        md = SAMPLE_VALID_OUTPUT.replace(
            "- ... (remaining 8 tasks)", replacement,
        )
        errors = validate_markdown_output(md)
        self.assertTrue(any("rejected DA verdict" in e for e in errors))

    def test_rejected_findings_exact_title_matching(self):
        md = SAMPLE_VALID_OUTPUT.replace(
            "[tests/test_compliance.py:5] — Unused import → minor dead code, no runtime impact",
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
        totals = [
            float(m.group(1)) for m in
            re.finditer(
                r'(?mi)^#+\s+Phase\s+\d+.*estimated:\s*(\d+(?:\.\d+)?)\s*hours?',
                text,
            )
        ]
        self.assertEqual(sum(totals), 200,
                         f"Roadmap phases {totals} sum to {sum(totals)}h, expected 200h")

    def test_actual_health_report_passes_validation(self):
        import os
        cache_dir = os.environ.get("CODE_REVIEW_CACHE_DIR", ".code-review-cache")
        report_path = Path(__file__).resolve().parent.parent / cache_dir / "health-report.md"
        if not report_path.exists():
            self.skipTest("health-report.md not found on disk")
        md = report_path.read_text(encoding="utf-8")
        errors = validate_markdown_output(md)
        self.assertEqual(
            errors, [],
            "health-report.md does not conform to schema:\n" + "\n".join(
                f"  - {e}" for e in errors
            )
        )


class TestJsonOutputValidation(unittest.TestCase):
    """JSON output validators reject invalid and accept valid outputs."""

    def test_valid_json_passes(self):
        errors = validate_json_output(SAMPLE_VALID_JSON)
        self.assertEqual(errors, [])

    def test_missing_top_level_field(self):
        data = dict(SAMPLE_VALID_JSON)
        del data["report"]
        errors = validate_json_output(data)
        self.assertTrue(any("report" in e for e in errors))

    def test_invalid_health_value(self):
        data = dict(SAMPLE_VALID_JSON)
        data["report"] = dict(data["report"], overall_health="PURPLE")
        errors = validate_json_output(data)
        self.assertTrue(any("PURPLE" in e for e in errors))

    def test_invalid_severity(self):
        data = dict(SAMPLE_VALID_JSON)
        f = dict(data["findings"][0], severity="CATASTROPHIC")
        data["findings"] = [f]
        errors = validate_json_output(data)
        self.assertTrue(any("CATASTROPHIC" in e for e in errors))

    def test_invalid_da_verdict(self):
        data = dict(SAMPLE_VALID_JSON)
        f = dict(data["findings"][0], da_verdict="MAYBE")
        data["findings"] = [f]
        errors = validate_json_output(data)
        self.assertTrue(any("MAYBE" in e for e in errors))

    def test_score_out_of_range(self):
        data = dict(SAMPLE_VALID_JSON)
        data["per_domain_scores"] = {
            "security": {"score": 11, "critical": 0, "high": 0, "medium": 0, "low": 0},
        }
        errors = validate_json_output(data)
        self.assertTrue(any("11" in e for e in errors))

    def test_roadmap_missing_phase(self):
        data = dict(SAMPLE_VALID_JSON)
        data["roadmap"] = {"phase_1": {"title": "Now", "estimated_hours": 10}}
        errors = validate_json_output(data)
        self.assertTrue(any("phase_2" in e for e in errors))

    def test_findings_not_a_list(self):
        data = dict(SAMPLE_VALID_JSON)
        data["findings"] = "not-a-list"
        errors = validate_json_output(data)
        self.assertTrue(any("must be a list" in e for e in errors))

    def test_not_a_dict(self):
        errors = validate_json_output("not-a-dict")
        self.assertTrue(any("must be a dict" in e for e in errors))


class TestJsonSampleOutputValidation(unittest.TestCase):
    """The sample JSON output must always pass strict validation."""

    def test_sample_passes_strict_validation(self):
        errors = validate_json_output(SAMPLE_VALID_JSON)
        self.assertEqual(errors, [],
                         f"Sample JSON failed validation: {errors}")

    def test_sample_has_all_required_report_fields(self):
        for field in REQUIRED_REPORT_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, SAMPLE_VALID_JSON)

    def test_sample_has_valid_health(self):
        self.assertIn(
            SAMPLE_VALID_JSON["report"]["overall_health"],
            VALID_HEALTH_JSON,
        )

    def test_sample_findings_have_required_fields(self):
        for idx, f in enumerate(SAMPLE_VALID_JSON["findings"]):
            for field in REQUIRED_FINDING_FIELDS:
                with self.subTest(finding=idx, field=field):
                    self.assertIn(field, f)

    def test_sample_tech_debt_reconciliation(self):
        by_domain = SAMPLE_VALID_JSON["tech_debt"]["by_domain"]
        domain_sum = round(sum(by_domain.values()), 2)
        total = round(SAMPLE_VALID_JSON["tech_debt"]["total_hours"], 2)
        self.assertAlmostEqual(domain_sum, total, delta=0.5)

    def test_sample_roadmap_phase_totals_match(self):
        phases = SAMPLE_VALID_JSON["roadmap"]
        total = sum(
            phases[k]["estimated_hours"]
            for k in ["phase_1", "phase_2", "phase_3"]
        )
        self.assertAlmostEqual(
            total, SAMPLE_VALID_JSON["tech_debt"]["total_hours"], delta=0.5,
        )

    def test_sample_agent_status_counts_match(self):
        ds = SAMPLE_VALID_JSON["agent_status"]["da_verdict_summary"]
        total_verdicts = sum(ds.values())
        self.assertGreater(total_verdicts, 0)


if __name__ == "__main__":
    unittest.main()

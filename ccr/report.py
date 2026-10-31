"""Render the review model as Markdown or JSON.

The Markdown contract is validated by tests/test_pipeline.py; keep the
section names and table headers exactly as written here.
"""

import math


def _fmt_number(value):
    """Format a number without trailing zeros: 2.0 -> '2', 2.5 -> '2.5'."""
    try:
        number = round(float(value), 2)
    except OverflowError:
        # An integer beyond float range is still finite; render it as given.
        return str(value)
    if not math.isfinite(number):
        # Finite estimates can sum past the float range, and int(inf) raises.
        # The float repr ("inf"/"-inf") is the honest value here.
        return str(number)
    if number == int(number):
        return str(int(number))
    return str(number)


def fmt_hours(value):
    """Format hours without trailing zeros: 2 -> '2h', 2.5 -> '2.5h'."""
    return _fmt_number(value) + "h"


def fmt_hours_long(value):
    """Format hours as words: 2 -> '2 hours', 2.5 -> '2.5 hours'."""
    return _fmt_number(value) + " hours"


def _cell(text):
    """Make text safe inside a Markdown table cell or section body.

    Uses ``splitlines`` so every separator it honours (including ``\\x0b``,
    ``\\x0c`` and ``\\x85``) collapses, not just CR/LF.
    """
    cleaned = str(text).replace("|", "/")
    return " ".join(cleaned.splitlines()).strip()


def _executive_summary(model):
    """Render the Executive Summary section."""
    size = model.get("codebase_size") or {}
    files = size.get("files", 0)
    languages = size.get("languages", 0)
    modules = size.get("modules", 0)
    priority = ", ".join(_cell(name) for name in model["priority_areas"])
    if not priority:
        priority = "none"
    debt_hours = fmt_hours(model["tech_debt_hours"])
    lines = [
        "## Executive Summary",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Overall Health** | {model['overall_health']} |",
        f"| **Codebase Size** | {files} files, {languages} languages, "
        f"{modules} top-level modules |",
    ]
    if size.get("truncated"):
        lines.append(
            "| **Scope** | Sampled \u2014 file cap reached; findings cover a "
            "subset of the codebase |"
        )
    lines.extend([
        f"| **Critical Issues** | {model['critical_issues']} |",
        f"| **Tech Debt** | {debt_hours} |",
        f"| **Priority Areas** | {priority} |",
        "",
    ])
    return "\n".join(lines)


def _per_domain(model):
    """Render the Per-Domain Scores section."""
    lines = [
        "## Per-Domain Scores",
        "",
        "| Domain | Score (/10) | Critical | High | Medium | Low |",
        "|--------|-------------|----------|------|--------|-----|",
    ]
    for row in model["per_domain_scores"]:
        domain = _cell(row["domain"])
        lines.append(
            f"| {domain} | {row['score']} | {row['critical']} | "
            f"{row['high']} | {row['medium']} | {row['low']} |"
        )
    if not model["per_domain_scores"]:
        lines.append("| none | 10.0 | 0 | 0 | 0 | 0 |")
    counts = model["counts"]
    lines.append(
        f"| **Overall** | {model['overall_score']} | {counts['CRITICAL']} | "
        f"{counts['HIGH']} | {counts['MEDIUM']} | {counts['LOW']} |"
    )
    lines.append("")
    return "\n".join(lines)


def _findings(model):
    """Render the Detailed Findings section."""
    lines = [
        "## Detailed Findings",
        "",
        "| Finding | Severity | Domain | Est. Hours | DA Verdict |",
        "|---------|----------|--------|------------|------------|",
    ]
    for item in model["findings"]:
        finding = _cell(item["finding"])
        domain = _cell(item.get("domain", ""))
        hours = fmt_hours(item.get("est_hours", 0))
        lines.append(
            f"| {finding} | {item['severity']} | "
            f"{domain} | "
            f"{hours} | "
            f"{item['da_verdict']} |"
        )
    if not model["findings"]:
        lines.append(
            "| [none:0] \u2014 no findings were reported by any agent "
            "\u2192 nothing to fix | INFO | - | 0h | CONFIRMED |"
        )
    lines.append("")
    return "\n".join(lines)


def _roadmap(model):
    """Render the Improvement Roadmap section."""
    titles = {
        1: "Phase 1 - Now",
        2: "Phase 2 - Next Quarter",
        3: "Phase 3 - Backlog",
    }
    lines = ["## Improvement Roadmap", ""]
    for phase in (1, 2, 3):
        hours = model["roadmap_hours"][phase]
        lines.append(
            f"### {titles[phase]} (estimated: {hours} hours)"
        )
        lines.append("")
        items = model["roadmap"][phase]
        if not items:
            lines.append("- (none)")
        for item in items:
            lines.append("- " + _cell(item["finding"]))
        lines.append("")
    return "\n".join(lines)


def _tech_debt(model):
    """Render the Tech Debt Summary section."""
    debt = model["tech_debt"]
    total_hours = fmt_hours_long(debt["total_hours"])
    parts = []
    for domain, hours in debt["by_domain"].items():
        label = _cell(domain)
        amount = fmt_hours(hours)
        parts.append(f"{label}: {amount}")
    lines = [
        "## Tech Debt Summary",
        "",
        f"**Total estimated**: {total_hours}",
        "",
        f"**Trend**: {debt['trend']}",
        "",
        "**By domain**: " + ("; ".join(parts) if parts else "none"),
        "",
    ]
    return "\n".join(lines)


def _agent_status(model):
    """Render the Agent Status section."""
    status = model["agent_status"]
    tally = ", ".join(
        f"{count} {verdict}"
        for verdict, count in status["da_verdict_summary"].items()
    )
    lines = [
        "## Agent Status",
        "",
        f"Completed: {status['completed']}/{status['total']} agents",
        "",
        "DA verdicts: " + (tally if tally else "none"),
        "",
    ]
    return "\n".join(lines)


def _rejected(model):
    """Render rejected findings after the required sections."""
    lines = ["## Rejected Findings", ""]
    if not model["rejected"]:
        lines.append("None.")
    for item in model["rejected"]:
        finding = _cell(item.get("finding", ""))
        lines.append(
            f"- {finding} "
            f"(reason: {item.get('reject_reason', '')})"
        )
    lines.append("")
    return "\n".join(lines)


def _overlap_candidates(model):
    """Render cross-domain overlap candidates for DA adjudication."""
    lines = ["## Overlap Candidates", ""]
    candidates = model.get("overlap_candidates") or []
    if not candidates:
        lines.append("None.")
        lines.append("")
        return "\n".join(lines)
    for candidate in candidates:
        merged = ", ".join(candidate.get("merged", []))
        filename = _cell(candidate.get("file", ""))
        if candidate.get("advisory"):
            lines.append(
                f"- [advisory] {filename}: "
                f"{candidate.get('hours', 0)}h across "
                f"{candidate.get('kept', '')} + {merged} \u2014 adjudicate "
                "whether this is one root cause"
            )
        else:
            lines.append(
                f"- {filename}: kept "
                f"{candidate.get('kept', '')} (merged: {merged})"
            )
    lines.append("")
    return "\n".join(lines)


def _title(text):
    """Escape the heading text so a path cannot inject HTML or a link."""
    return (
        _cell(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def render_markdown(model):
    """Render the full health report as Markdown."""
    title = _title(model.get("target") or ".")
    sections = [
        f"# Codebase Health Report - {title}",
        "",
        _executive_summary(model),
        _per_domain(model),
        _findings(model),
        _roadmap(model),
        _tech_debt(model),
        _agent_status(model),
        _overlap_candidates(model),
        _rejected(model),
    ]
    return "\n".join(sections).rstrip() + "\n"


REQUIRED_SECTIONS = (
    "## Executive Summary",
    "## Per-Domain Scores",
    "## Detailed Findings",
    "## Improvement Roadmap",
    "## Tech Debt Summary",
    "## Agent Status",
)


def _num(text):
    """Parse a number from text; return None when not numeric."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _section_text(md, header):
    """Return the text of one '## ' section, excluding later sections.

    Matches the header as a whole line, so a finding that quotes the heading
    cannot move the section boundary.
    """
    lines = md.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == header:
            start = index + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


HEALTH_VALUES = ("GREEN", "YELLOW", "RED")


def validate_markdown(md):
    """Return a list of contract violations in a rendered report.

    Enforces the section contract, numeric domain scores, the health enum, and
    the tech-debt reconciliation the orchestrator rules require.
    """
    errors = []
    for section in REQUIRED_SECTIONS:
        if section not in md:
            errors.append("missing section: " + section)

    health = None
    for line in _section_text(md, "## Executive Summary").splitlines():
        cells = line.split("|")
        # A well-formed row is "| **Overall Health** | VALUE |" -> 4 parts.
        if len(cells) == 4 and cells[1].strip() == "**Overall Health**":
            health = cells[2].strip()
            break
    if health is None:
        errors.append("missing overall health")
    elif health not in HEALTH_VALUES:
        errors.append("invalid overall health: " + health)

    scores_text = _section_text(md, "## Per-Domain Scores")
    for line in scores_text.splitlines():
        if line.startswith("|") and (" N/A " in line or " n/a " in line):
            errors.append("non-numeric domain score: " + line.strip())

    total = None
    domain_sum = 0.0
    found_domain = False
    debt_text = _section_text(md, "## Tech Debt Summary")
    for line in debt_text.splitlines():
        if line.startswith("**Total estimated**") and ":" in line:
            total = _num(line.split(":", 1)[1].strip().split(" ")[0])
        if "**By domain**" in line and ":" in line:
            for part in line.split(":", 1)[1].split(";"):
                if ":" not in part:
                    continue
                value = _num(part.rsplit(":", 1)[1].strip().rstrip("h"))
                if value is None:
                    errors.append("non-numeric domain hours: " + part.strip())
                else:
                    domain_sum += value
                    found_domain = True
    if total is None:
        # Require a total: even a zero-finding report renders
        # "**Total estimated**: 0 hours", so there is no legitimate gap.
        errors.append("tech-debt total missing")
    elif found_domain and abs(domain_sum - total) >= 0.5:
        errors.append(
            "tech-debt mismatch: by-domain {:.2f}h != total {:.2f}h".format(
                domain_sum, total
            )
        )
    return errors


def render_json(model):
    """Render the machine-readable report contract."""
    domain_ids = {}
    for item in model["findings"]:
        display = item.get("domain")
        agent_id = item.get("agent")
        if display and agent_id:
            domain_ids.setdefault(display, agent_id)
    findings = []
    for item in model["findings"]:
        raw_severity = item["severity"]
        severity = "LOW" if raw_severity == "INFO" else raw_severity
        findings.append({
            "id": item["id"],
            "finding": item["finding"],
            "severity": severity,
            "domain": item.get("agent") or item.get("domain", ""),
            "est_hours": item.get("est_hours", 0),
            "da_verdict": item["da_verdict"],
            "finding_type": item.get("finding_type", ""),
            "no_fix": raw_severity == "INFO",
        })
    titles = {1: "Now", 2: "Next Quarter", 3: "Backlog"}
    roadmap = {}
    for phase in (1, 2, 3):
        items = model["roadmap"][phase]
        roadmap[f"phase_{phase}"] = {
            "title": titles[phase],
            "estimated_hours": model["roadmap_hours"][phase],
            "tasks": [
                {
                    "id": item["id"],
                    "finding": item["finding"],
                    "est_hours": item.get("est_hours", 0),
                }
                for item in items
            ],
        }
    size = model.get("codebase_size") or {}
    return {
        "report": {
            "title": "Codebase Health Report",
            "overall_health": model["overall_health"],
            "codebase_size": {
                "files": size.get("files", 0),
                "languages": size.get("languages", 0),
                "modules": size.get("modules", 0),
                "truncated": bool(size.get("truncated", False)),
            },
            "critical_issues": model["critical_issues"],
            "tech_debt_hours": model["tech_debt_hours"],
            "priority_areas": model["priority_areas"],
        },
        "per_domain_scores": {
            domain_ids.get(row["domain"], row["domain"]): {
                "score": row["score"],
                "critical": row["critical"],
                "high": row["high"],
                "medium": row["medium"],
                "low": row["low"],
            }
            for row in model["per_domain_scores"]
        },
        "findings": findings,
        "rejected": [
            dict(
                item,
                domain=item.get("agent") or item.get("domain", ""),
            )
            for item in model["rejected"]
        ],
        "overlap_candidates": model.get("overlap_candidates", []),
        "roadmap": roadmap,
        "tech_debt": {
            "total_hours": model["tech_debt"]["total_hours"],
            "by_domain": {
                domain_ids.get(name, name): hours
                for name, hours in model["tech_debt"]["by_domain"].items()
            },
            "trend": model["tech_debt"]["trend"],
        },
        "agent_status": model["agent_status"],
        "baseline": model["baseline"],
    }

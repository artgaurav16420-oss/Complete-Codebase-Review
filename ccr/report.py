"""Render the review model as Markdown or JSON.

The Markdown contract is validated by tests/test_pipeline.py; keep the
section names and table headers exactly as written here.
"""


def _fmt_number(value):
    number = round(float(value), 2)
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
    """Make text safe inside a Markdown table cell."""
    return str(text).replace("|", "/").replace("\n", " ").strip()


def _executive_summary(model):
    """Render the Executive Summary section."""
    size = model.get("codebase_size") or {}
    files = size.get("files", 0)
    languages = size.get("languages", 0)
    modules = size.get("modules", 0)
    priority = ", ".join(model["priority_areas"]) or "none"
    lines = [
        "## Executive Summary",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Overall Health** | {model['overall_health']} |",
        "| **Codebase Size** | {} files, {} languages, {} top-level modules |".format(
            files, languages, modules
        ),
        f"| **Critical Issues** | {model['critical_issues']} |",
        f"| **Tech Debt** | {fmt_hours(model['tech_debt_hours'])} |",
        f"| **Priority Areas** | {priority} |",
        "",
    ]
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
        lines.append(
            "| {domain} | {score} | {critical} | {high} | {medium} | {low} |".format(
                **row
            )
        )
    if not model["per_domain_scores"]:
        lines.append("| none | 10.0 | 0 | 0 | 0 | 0 |")
    counts = model["counts"]
    lines.append(
        "| **Overall** | {} | {} | {} | {} | {} |".format(
            model["overall_score"], counts["CRITICAL"], counts["HIGH"],
            counts["MEDIUM"], counts["LOW"],
        )
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
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                _cell(item["finding"]),
                item["severity"],
                item.get("domain", ""),
                fmt_hours(item.get("est_hours", 0)),
                item["da_verdict"],
            )
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
            "### {} (estimated: {} hours)".format(titles[phase], hours)
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
    parts = [
        f"{domain}: {fmt_hours(hours)}"
        for domain, hours in debt["by_domain"].items()
    ]
    lines = [
        "## Tech Debt Summary",
        "",
        f"**Total estimated**: {fmt_hours_long(debt['total_hours'])}",
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
        "{} {}".format(count, verdict)
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
        lines.append(
            "- {} (reason: {})".format(
                _cell(item.get("finding", "")), item.get("reject_reason", "")
            )
        )
    lines.append("")
    return "\n".join(lines)


def render_markdown(model):
    """Render the full health report as Markdown."""
    sections = [
        f"# Codebase Health Report - {model.get('target') or '.'}",
        "",
        _executive_summary(model),
        _per_domain(model),
        _findings(model),
        _roadmap(model),
        _tech_debt(model),
        _agent_status(model),
        _rejected(model),
    ]
    return "\n".join(sections).rstrip() + "\n"


def render_json(model):
    """Render the machine-readable report contract."""
    findings = []
    for item in model["findings"]:
        severity = item["severity"]
        if severity == "INFO":
            severity = "LOW"
        findings.append({
            "id": item["id"],
            "finding": item["finding"],
            "severity": severity,
            "domain": item.get("domain", ""),
            "est_hours": item.get("est_hours", 0),
            "da_verdict": item["da_verdict"],
        })
    titles = {1: "Now", 2: "Next Quarter", 3: "Backlog"}
    roadmap = {}
    for phase in (1, 2, 3):
        items = model["roadmap"][phase]
        roadmap["phase_{}".format(phase)] = {
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
            },
            "critical_issues": model["critical_issues"],
            "tech_debt_hours": model["tech_debt_hours"],
            "priority_areas": model["priority_areas"],
        },
        "per_domain_scores": {
            row["domain"]: {
                "score": row["score"],
                "critical": row["critical"],
                "high": row["high"],
                "medium": row["medium"],
                "low": row["low"],
            }
            for row in model["per_domain_scores"]
        },
        "findings": findings,
        "roadmap": roadmap,
        "tech_debt": model["tech_debt"],
        "agent_status": model["agent_status"],
        "baseline": model["baseline"],
    }

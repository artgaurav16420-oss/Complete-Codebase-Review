"""Render the review model as Markdown or JSON.

The Markdown contract is validated by tests/test_pipeline.py; keep the
section names and table headers exactly as written here.
"""


def _fmt_number(value):
    """Format a number without trailing zeros: 2.0 -> '2', 2.5 -> '2.5'."""
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
    """Make text safe inside a Markdown table cell or section body."""
    cleaned = str(text).replace("|", "/")
    for sep in ("\r\n", "\r", "\n", "\u2028", "\u2029"):
        cleaned = cleaned.replace(sep, " ")
    return cleaned.strip()


def _executive_summary(model):
    """Render the Executive Summary section."""
    size = model.get("codebase_size") or {}
    files = size.get("files", 0)
    languages = size.get("languages", 0)
    modules = size.get("modules", 0)
    priority = ", ".join(_cell(name) for name in model["priority_areas"])
    if not priority:
        priority = "none"
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
        f"| **Tech Debt** | {fmt_hours(model['tech_debt_hours'])} |",
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
        lines.append(
            f"| {_cell(row['domain'])} | {row['score']} | {row['critical']} | "
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
        lines.append(
            f"| {_cell(item['finding'])} | {item['severity']} | "
            f"{_cell(item.get('domain', ''))} | "
            f"{fmt_hours(item.get('est_hours', 0))} | "
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
    parts = [
        f"{_cell(domain)}: {fmt_hours(hours)}"
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
        lines.append(
            f"- {_cell(item.get('finding', ''))} "
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
        if candidate.get("advisory"):
            lines.append(
                f"- [advisory] {_cell(candidate.get('file', ''))}: "
                f"{candidate.get('hours', 0)}h across "
                f"{candidate.get('kept', '')} + {merged} \u2014 adjudicate "
                "whether this is one root cause"
            )
        else:
            lines.append(
                f"- {_cell(candidate.get('file', ''))}: kept "
                f"{candidate.get('kept', '')} (merged: {merged})"
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
    """Return the text of one '## ' section, excluding later sections."""
    start = md.find(header)
    if start == -1:
        return ""
    start += len(header)
    end = md.find("\n## ", start)
    return md[start:end if end != -1 else len(md)]


def validate_markdown(md):
    """Return a list of contract violations in a rendered report.

    Enforces the section contract, numeric domain scores, and the tech-debt
    reconciliation the orchestrator rules require.
    """
    errors = []
    for section in REQUIRED_SECTIONS:
        if section not in md:
            errors.append("missing section: " + section)

    scores_text = _section_text(md, "## Per-Domain Scores")
    for line in scores_text.splitlines():
        if line.startswith("|") and (" N/A " in line or " n/a " in line):
            errors.append("non-numeric domain score: " + line.strip())

    total = None
    domain_sum = 0.0
    found_domain = False
    for line in md.splitlines():
        if line.startswith("**Total estimated**"):
            total = _num(line.split(":", 1)[1].strip().split(" ")[0])
        if "**By domain**" in line:
            for part in line.split(":", 1)[1].split(";"):
                if ":" not in part:
                    continue
                value = _num(part.rsplit(":", 1)[1].strip().rstrip("h"))
                if value is None:
                    errors.append("non-numeric domain hours: " + part.strip())
                else:
                    domain_sum += value
                    found_domain = True
    if total is not None and found_domain and abs(domain_sum - total) >= 0.5:
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

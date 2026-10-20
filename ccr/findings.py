"""Finding normalization, mechanical DA checks, and aggregation.

This module implements the deterministic parts of Phase 3: severity and
verdict normalization, the Three-Strike rejections that can be decided
without judgment, deduplication, tech-debt totals, roadmap placement, and
per-domain scoring.
"""

import re

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
VERDICTS = (
    "CONFIRMED", "PLAUSIBLE", "QUESTIONABLE", "REJECTED", "DA-ESCALATION",
)
ROADMAP_VERDICTS = frozenset({"CONFIRMED", "PLAUSIBLE", "DA-ESCALATION"})
SEVERITY_WEIGHT = {
    "CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4,
}

ANCHOR_RE = re.compile(r"^\[[^:]+:\d+\]\s+\u2014\s+.+?\s+\u2192\s+.+$")
ANCHOR_PARTS_RE = re.compile(r"^\[([^:]+):(\d+)\]\s+\u2014\s+(.+?)\s+\u2192\s+(.+)$")

WEASEL_PATTERNS = [
    r"\bmight\b", r"\blikely\b", r"\bcould\s+potentially\b",
    r"\bit\s+is\s+recommended\b", r"\bconsider\s+refactoring\b",
    r"\bbest\s+practice\s+suggests\b", r"\bgenerally\s+speaking\b",
    r"\bin\s+most\s+cases\b",
]


def normalize_severity(value):
    """Return an uppercase severity, defaulting to LOW when unrecognized."""
    if not value:
        return "LOW"
    cleaned = str(value).strip().upper()
    return cleaned if cleaned in SEVERITIES else "LOW"


def normalize_verdict(value):
    """Return an uppercase verdict, defaulting to QUESTIONABLE."""
    if not value:
        return "QUESTIONABLE"
    cleaned = str(value).strip().upper().replace("_", "-")
    aliases = {"ESCALATION": "DA-ESCALATION", "DA ESCALATION": "DA-ESCALATION"}
    cleaned = aliases.get(cleaned, cleaned)
    return cleaned if cleaned in VERDICTS else "QUESTIONABLE"


def weasel_hits(text):
    """Return the weasel phrases present in text."""
    hits = []
    for pattern in WEASEL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            hits.append(match.group(0))
    return hits


def anchor_parts(finding_text):
    """Return (file, line, flaw, failure_mode) or None."""
    match = ANCHOR_PARTS_RE.match(finding_text or "")
    if not match:
        return None
    return match.group(1), int(match.group(2)), match.group(3), match.group(4)


def _as_hours(value):
    """Coerce an estimate to a non-negative float."""
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, hours)


def review_findings(raw_findings, floors=None):
    """Apply mechanical DA checks and calibrate missing estimates.

    Args:
        raw_findings: Findings from agent reports.
        floors: Optional tech-debt floors keyed by `finding_type`.

    Returns:
        tuple: (kept, rejected). Rejected findings carry `reject_reason`
        and a REJECTED DA verdict.
    """
    kept = []
    rejected = []
    for raw in raw_findings:
        item = dict(raw)
        item["severity"] = normalize_severity(item.get("severity"))
        item["da_verdict"] = normalize_verdict(item.get("da_verdict"))
        item["est_hours"] = _as_hours(item.get("est_hours"))
        floor = (floors or {}).get(item.get("finding_type", ""))
        if floor:
            floor = float(floor)
            if item["est_hours"] <= 0:
                item["est_hours"] = floor
            else:
                item["est_hours"] = max(item["est_hours"], floor * 0.5)

        text = str(item.get("finding", "")).strip()
        item["finding"] = text
        reason = None
        if not text:
            reason = "empty finding"
        elif not ANCHOR_RE.match(text):
            reason = "missing [file:line] anchor or missing arrow"
        else:
            hits = weasel_hits(text)
            if hits:
                reason = "weasel word: " + hits[0]
        if reason:
            item["da_verdict"] = "REJECTED"
            item["reject_reason"] = reason
            rejected.append(item)
        else:
            kept.append(item)
    return kept, rejected


def dedup(findings):
    """Collapse findings sharing domain and file:line, keeping the worst.

    Args:
        findings: Findings that already carry a parseable anchor.

    Returns:
        list: Deduplicated findings in stable order.
    """
    chosen = {}
    order = []
    for item in findings:
        parts = anchor_parts(item.get("finding", ""))
        if parts is None:
            continue
        key = (item.get("domain", ""), parts[0], parts[1])
        existing = chosen.get(key)
        if existing is None:
            chosen[key] = item
            order.append(key)
            continue
        old_rank = SEVERITY_WEIGHT[normalize_severity(existing.get("severity"))]
        new_rank = SEVERITY_WEIGHT[normalize_severity(item.get("severity"))]
        if new_rank < old_rank:
            chosen[key] = item
        elif new_rank == old_rank:
            if item.get("est_hours", 0) > existing.get("est_hours", 0):
                chosen[key] = item
    return [chosen[key] for key in order]


def assign_ids(findings):
    """Assign stable F-001 style identifiers in place and return the list."""
    for index, item in enumerate(findings, start=1):
        item["id"] = "F-{:03d}".format(index)
    return findings


def roadmap_eligible(finding):
    """Return True when a finding may enter the roadmap."""
    return (
        finding.get("da_verdict") in ROADMAP_VERDICTS
        and finding.get("da_verdict") != "REJECTED"
    )


def place_roadmap(findings):
    """Split eligible findings into three phases.

    Phase 1: CRITICAL plus quick wins (<= 2h).
    Phase 2: HIGH, or MEDIUM at <= 8h.
    Phase 3: everything else eligible.
    """
    phases = {1: [], 2: [], 3: []}
    for item in findings:
        if not roadmap_eligible(item):
            continue
        severity = normalize_severity(item.get("severity"))
        hours = _as_hours(item.get("est_hours"))
        if severity == "CRITICAL" or hours <= 2:
            phases[1].append(item)
        elif severity == "HIGH" or (severity == "MEDIUM" and hours <= 8):
            phases[2].append(item)
        else:
            phases[3].append(item)
    return phases


def _score(counts):
    """Convert severity counts into a 0-10 domain score."""
    score = (
        10
        - 2.0 * counts.get("CRITICAL", 0)
        - 1.0 * counts.get("HIGH", 0)
        - 0.5 * counts.get("MEDIUM", 0)
        - 0.25 * counts.get("LOW", 0)
    )
    return round(max(0.0, score), 1)


def _empty_counts():
    """Return a zeroed severity count dict."""
    return {severity: 0 for severity in SEVERITIES}


def aggregate(findings, rejected, agents_planned, agents_completed,
              target="", baseline=None):
    """Build the report model consumed by the renderers.

    Args:
        findings: Kept findings (post-dedup, post-id).
        rejected: Findings rejected by mechanical DA checks.
        agents_planned: Agent ids that were planned.
        agents_completed: Agent ids that reported.
        target: Target directory string.
        baseline: Optional previous baseline dict for trend text.

    Returns:
        dict: Report model.
    """
    all_findings = list(findings) + list(rejected)
    open_findings = [f for f in findings if f.get("da_verdict") != "REJECTED"]

    per_domain = {}
    for item in open_findings:
        domain = item.get("domain") or "Unknown"
        counts = per_domain.setdefault(domain, _empty_counts())
        severity = normalize_severity(item.get("severity"))
        counts[severity] += 1

    domains = sorted(per_domain)
    scores = []
    for domain in domains:
        counts = per_domain[domain]
        scores.append({
            "domain": domain,
            "score": _score(counts),
            "critical": counts["CRITICAL"],
            "high": counts["HIGH"],
            "medium": counts["MEDIUM"],
            "low": counts["LOW"],
        })

    total_counts = _empty_counts()
    for item in open_findings:
        total_counts[normalize_severity(item.get("severity"))] += 1

    phases = place_roadmap(findings)
    roadmap_hours = {
        phase: round(sum(_as_hours(f.get("est_hours")) for f in items), 2)
        for phase, items in phases.items()
    }
    total_hours = round(sum(roadmap_hours.values()), 2)

    by_domain = {}
    for items in phases.values():
        for item in items:
            domain = item.get("domain") or "Unknown"
            by_domain[domain] = round(
                by_domain.get(domain, 0.0) + _as_hours(item.get("est_hours")), 2
            )

    verdict_summary = {}
    for item in all_findings:
        verdict = normalize_verdict(item.get("da_verdict"))
        verdict_summary[verdict] = verdict_summary.get(verdict, 0) + 1

    priority = sorted(
        scores,
        key=lambda row: (
            -row["critical"], -row["high"], -row["medium"], row["domain"]
        ),
    )
    priority_areas = [row["domain"] for row in priority[:3]]

    if total_counts["CRITICAL"]:
        health = "RED"
    elif total_counts["HIGH"]:
        health = "YELLOW"
    else:
        health = "GREEN"

    if scores:
        overall_score = round(
            sum(row["score"] for row in scores) / len(scores), 1
        )
    else:
        overall_score = 10.0

    trend = "no previous baseline"
    if baseline:
        previous = baseline.get("tech_debt_hours")
        if previous is not None:
            if previous > 0:
                change = round((total_hours - previous) / previous * 100)
                trend = "{}h -> {}h ({}%)".format(
                    previous, total_hours, "{:+d}".format(change)
                )
            else:
                trend = "{}h -> {}h".format(previous, total_hours)

    return {
        "target": target,
        "overall_health": health,
        "critical_issues": total_counts["CRITICAL"],
        "tech_debt_hours": total_hours,
        "priority_areas": priority_areas,
        "per_domain_scores": scores,
        "overall_score": overall_score,
        "counts": total_counts,
        "findings": findings,
        "rejected": rejected,
        "roadmap": phases,
        "roadmap_hours": roadmap_hours,
        "tech_debt": {
            "total_hours": total_hours,
            "by_domain": dict(sorted(by_domain.items())),
            "trend": trend,
        },
        "agent_status": {
            "completed": len(agents_completed),
            "total": len(agents_planned),
            "da_verdict_summary": dict(sorted(verdict_summary.items())),
        },
        "baseline": {
            "timestamp": "",
            "target": target,
            "health_score": health,
            "tech_debt_hours": total_hours,
            "critical_count": total_counts["CRITICAL"],
            "per_domain_scores": {
                row["domain"]: row["score"] for row in scores
            },
            "per_domain_open_findings": {
                row["domain"]: {
                    "critical": row["critical"], "high": row["high"],
                }
                for row in scores
            },
            "task_count": sum(len(items) for items in phases.values()),
            "re_review_count": 0,
        },
    }

"""Finding normalization, mechanical DA checks, and aggregation.

This module implements the deterministic parts of Phase 3: severity and
verdict normalization, the Three-Strike rejections that can be decided
without judgment, deduplication, tech-debt totals, roadmap placement, and
per-domain scoring.
"""

import math
import re
import threading

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
VERDICTS = (
    "CONFIRMED", "PLAUSIBLE", "QUESTIONABLE", "REJECTED", "DA-ESCALATION",
)
ROADMAP_VERDICTS = frozenset({"CONFIRMED", "PLAUSIBLE", "DA-ESCALATION"})
SEVERITY_WEIGHT = {
    "CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4,
}

ANCHOR_RE = re.compile(
    r"^\[(.+):(\d+)(?:-\d+)?\]\s+\u2014\s+.+?\s+\u2192\s+.+$"
)
ANCHOR_PARTS_RE = re.compile(
    r"^\[(.+):(\d+)(?:-\d+)?\]\s+\u2014\s+(.+?)\s+\u2192\s+(.+)$"
)

WEASEL_PATTERNS = [
    re.compile(r"\bmight\b", re.IGNORECASE),
    re.compile(r"\blikely\b", re.IGNORECASE),
    re.compile(r"\bcould\s+potentially\b", re.IGNORECASE),
    re.compile(r"\bit\s+is\s+recommended\b", re.IGNORECASE),
    re.compile(r"\bconsider\s+refactoring\b", re.IGNORECASE),
    re.compile(r"\bbest\s+practice\s+suggests\b", re.IGNORECASE),
    re.compile(r"\bgenerally\s+speaking\b", re.IGNORECASE),
    re.compile(r"\bin\s+most\s+cases\b", re.IGNORECASE),
]

# The prompts show the canonical em dash + arrow pair, but providers (and
# humans writing fixtures) reliably emit ASCII. Rejecting a sound finding for
# punctuation costs a whole finding, so the separators are normalised before
# the anchor gate looks at them. The prefix consumes a whole run of dashes so
# `-- flaw` does not leave a stray hyphen behind.
# The file part may contain one level of brackets (`app/[id]/page.tsx`); a
# plain [^\]]+ stopped at the first `]`, so those findings were never
# normalised and the gate then rejected an anchor the canonical regex accepts.
_ANCHOR_PREFIX_RE = re.compile(
    r"^(\[(?:[^\[\]\n]|\[[^\]\n]*\])+:\d+(?:-\d+)?\])\s*"
    r"(?:(?:[\u2014\u2013]{1,2}|-{1,3}|:)\s*)?"
)
# ASCII arrows are ambiguous inside code (`->` lambdas, `=>` rockets). The
# separator is the *last* one in the finding: incidental arrows live in the
# flaw text, which precedes it. A canonical arrow is never ambiguous and always
# wins, so it is not searched positionally.
_CANONICAL_ARROW_RE = re.compile(r"\s\u2192\s")
_ASCII_ARROW_RE = re.compile(r"\s(?:->|=>|[\u2013\u2014]>)\s")


def normalize_anchor(finding_text):
    """Rewrite ASCII separators into the canonical em dash and arrow.

    ``[a.py:1] - flaw -> failure``, ``[a.py:1] -- flaw => failure`` and
    ``[a.py:1] flaw -> failure`` all become
    ``[a.py:1] \u2014 flaw \u2192 failure``. Text without a ``[file:line]``
    anchor or without an arrow is returned unchanged, so the gate still
    rejects findings that carry no failure mode. Idempotent on canonical text.
    """
    text = finding_text or ""
    match = _ANCHOR_PREFIX_RE.match(text)
    if not match:
        return text
    rest = text[match.end():]
    if _CANONICAL_ARROW_RE.search(rest):
        return match.group(1) + " \u2014 " + rest
    matches = list(_ASCII_ARROW_RE.finditer(rest))
    if not matches:
        return text
    last = matches[-1]
    rest = rest[:last.start()] + " \u2192 " + rest[last.end():]
    return match.group(1) + " \u2014 " + rest


MALFORMED_REASONS = ("anchor", "empty finding")


def malformed_rejections(rejected):
    """Return rejections caused by empty text or a missing anchor."""
    return [
        item for item in rejected
        if any(
            reason in str(item.get("reject_reason", ""))
            for reason in MALFORMED_REASONS
        )
    ]


def normalize_severity(value):
    """Return an uppercase severity, defaulting to LOW when unrecognized."""
    if not value:
        return "LOW"
    cleaned = str(value).strip().upper()
    return cleaned if cleaned in SEVERITIES else "LOW"


def normalize_verdict(value):
    """Return an uppercase verdict, defaulting missing values to PLAUSIBLE.

    A missing verdict means the finding has not been challenged, not that it
    is dubious. Defaulting to QUESTIONABLE silently removed every prompt-shaped
    finding from the roadmap and zeroed tech debt.
    """
    if not value:
        return "PLAUSIBLE"
    cleaned = str(value).strip().upper().replace("_", "-")
    aliases = {"ESCALATION": "DA-ESCALATION", "DA ESCALATION": "DA-ESCALATION"}
    cleaned = aliases.get(cleaned, cleaned)
    return cleaned if cleaned in VERDICTS else "QUESTIONABLE"


def weasel_hits(text):
    """Return the weasel phrases present in text."""
    hits = []
    for pattern in WEASEL_PATTERNS:
        match = pattern.search(text)
        if match:
            hits.append(match.group(0))
    return hits


def anchor_parts(finding_text):
    """Return (file, line, flaw, failure_mode) or None."""
    match = ANCHOR_PARTS_RE.match(normalize_anchor(finding_text))
    if not match:
        return None
    return match.group(1), int(match.group(2)), match.group(3), match.group(4)


def _as_hours(value):
    """Coerce an estimate to a non-negative float."""
    try:
        hours = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(hours):
        return 0.0
    return max(0.0, hours)


def review_findings(raw_findings, floors=None):
    """Apply mechanical DA checks and calibrate missing estimates.

    Args:
        raw_findings: Findings from agent reports.
        floors: Optional tech-debt floors keyed by `finding_type`.

    Returns:
        tuple: (kept, rejected). Rejected findings carry `reject_reason`
        and a REJECTED DA verdict. A hedged finding stays in ``kept`` with
        a QUESTIONABLE verdict and a ``weasel_word`` marker; only empty or
        anchorless findings are rejected mechanically.

    Assumes:
        ``raw_findings`` are normalised dicts from agent reports. Mutates
        copies, never the caller's list. Severity/verdict values outside
        the enums are coerced (LOW / QUESTIONABLE) rather than rejected.
    """
    kept = []
    rejected = []
    for raw in raw_findings:
        item = dict(raw)
        item["severity"] = normalize_severity(item.get("severity"))
        item["da_verdict"] = normalize_verdict(item.get("da_verdict"))
        item["est_hours"] = _as_hours(item.get("est_hours"))
        finding_type = item.get("finding_type")
        if not isinstance(finding_type, str):
            finding_type = ""
        floor = (floors or {}).get(finding_type)
        if floor:
            floor = float(floor)
            if item["est_hours"] <= 0:
                item["est_hours"] = floor
            else:
                item["est_hours"] = max(item["est_hours"], floor * 0.5)

        text = normalize_anchor(str(item.get("finding", "")).strip())
        item["finding"] = text
        reason = None
        if not text:
            reason = "empty finding"
        elif not ANCHOR_RE.match(text):
            reason = "missing [file:line] anchor or missing arrow"
        else:
            hits = weasel_hits(text)
            if hits:
                # Hedged language routes a finding to the DA instead of
                # rejecting it: the failure-mode clause may legitimately
                # describe what might happen, and a mechanical REJECTED
                # verdict would deny the DA its adjudication.
                item["weasel_word"] = "weasel word: " + hits[0]
                if item["da_verdict"] != "REJECTED":
                    item["da_verdict"] = "QUESTIONABLE"
        if reason:
            item["da_verdict"] = "REJECTED"
            item["reject_reason"] = reason
            rejected.append(item)
        else:
            kept.append(item)
    return kept, rejected


def _dedup_winner(members):
    """Return the member dedup keeps: worst severity, then largest estimate."""
    winner = members[0]
    for item in members[1:]:
        old_rank = SEVERITY_WEIGHT[normalize_severity(winner.get("severity"))]
        new_rank = SEVERITY_WEIGHT[normalize_severity(item.get("severity"))]
        if new_rank < old_rank:
            winner = item
        elif new_rank == old_rank:
            if _as_hours(item.get("est_hours")) > _as_hours(
                winner.get("est_hours")
            ):
                winner = item
    return winner


def dedup(findings):
    """Collapse findings sharing domain, file:line and flaw, keeping the worst.

    Findings at one file:line are grouped by the flaw they describe: two
    findings join the same group only when their flaw-token sets intersect,
    using the same tokenizer as ``find_overlaps``. Distinct defects on one
    line (a SQL injection and a missing index, say) survive; true duplicates
    still collapse. A finding with no usable tokens joins no group, so it
    cannot swallow an unrelated finding on the same line.

    Args:
        findings: Findings that already carry a parseable anchor.

    Returns:
        list: Deduplicated findings in first-seen group order.
    """
    groups = []
    for index, item in enumerate(findings):
        parts = anchor_parts(item.get("finding", ""))
        if parts is None:
            continue
        path = parts[0].replace("\\", "/")
        key = (item.get("domain", ""), path, parts[1])
        tokens, _negations = _flaw_tokens(item)
        matches = [
            position for position, group in enumerate(groups)
            if group["key"] == key
            and tokens
            and group["tokens"]
            and (tokens & group["tokens"])
        ]
        if not matches:
            groups.append({
                "key": key, "members": [item], "tokens": tokens,
                "position": index,
            })
            continue
        target = groups[matches[0]]
        target["members"].append(item)
        target["tokens"] = target["tokens"] | tokens
        for position in reversed(matches[1:]):
            extra = groups.pop(position)
            target["members"].extend(extra["members"])
            target["tokens"] = target["tokens"] | extra["tokens"]
    groups.sort(key=lambda group: group["position"])
    return [_dedup_winner(group["members"]) for group in groups]


def assign_ids(findings):
    """Assign stable F-001 style identifiers in place and return the list."""
    for index, item in enumerate(findings, start=1):
        item["id"] = f"F-{index:03d}"
    return findings


def roadmap_eligible(finding):
    """Return True when a finding may enter the roadmap.

    INFO findings are observations (including deliberate design trade-offs)
    and carry no fix cost, so they stay out of the roadmap and tech debt.
    """
    if normalize_severity(finding.get("severity")) == "INFO":
        return False
    return finding.get("da_verdict") in ROADMAP_VERDICTS


# Calibration defaults (ADR-007). manifest.load() overrides them from
# pipeline.json via set_calibration, which keeps tuning out of the engine.
_DEFAULT_OVERLAP_THRESHOLD = 0.6
OVERLAP_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "into", "when",
    "then", "than", "are", "was", "were", "has", "have", "its",
})


NEGATIONS = frozenset({"not", "no", "never", "without"})


def _tokens_for_text(text):
    """Tokenize text with the same rules find_overlaps uses."""
    words = re.findall(r"[a-z0-9_]+", text.lower())
    negations = frozenset(
        words[index + 1]
        for index, word in enumerate(words[:-1])
        if word in NEGATIONS
    )
    tokens = frozenset(
        token for token in words
        if token not in OVERLAP_STOPWORDS and token not in NEGATIONS
        and len(token) > 2
    )
    return tokens, negations


def _failure_tokens(finding):
    """Return (tokens, negations) for the failure-mode text."""
    parts = anchor_parts(finding.get("finding", ""))
    text = parts[3] if parts else str(finding.get("finding", ""))
    return _tokens_for_text(text)


def _flaw_tokens(finding):
    """Return (tokens, negations) for the flaw text."""
    parts = anchor_parts(finding.get("finding", ""))
    text = parts[2] if parts else str(finding.get("finding", ""))
    return _tokens_for_text(text)


def find_overlaps(findings):
    """Cluster findings that describe the same failure in the same file.

    Deterministic: same-file findings whose failure-mode token sets have a
    Jaccard similarity >= OVERLAP_THRESHOLD join one cluster. Clusters with
    one member are dropped. Returns a list of member lists.

    Groups are indexed by failure token, so a group that shares no token with
    the current finding is skipped: its Jaccard score would be zero.
    """
    by_file = {}
    for item in findings:
        parts = anchor_parts(item.get("finding", ""))
        if parts is None:
            continue
        by_file.setdefault(parts[0].replace("\\", "/"), []).append(item)
    clusters = []
    for _file, items in sorted(by_file.items()):
        groups = []
        index = {}
        for item in items:
            tokens, negations = _failure_tokens(item)
            candidates = set()
            for token in tokens:
                candidates.update(index.get(token, ()))
            joined = False
            for position in sorted(candidates):
                group = groups[position]
                if negations != group["negations"]:
                    continue
                inter = len(tokens & group["tokens"])
                union = len(tokens | group["tokens"])
                if union and inter / union >= _overlap_threshold():
                    group["members"].append(item)
                    added = tokens - group["tokens"]
                    group["tokens"] = group["tokens"] | tokens
                    for token in added:
                        index.setdefault(token, set()).add(position)
                    joined = True
                    break
            if not joined:
                groups.append({
                    "members": [item], "tokens": tokens,
                    "negations": negations,
                })
                position = len(groups) - 1
                for token in tokens:
                    index.setdefault(token, set()).add(position)
        clusters.extend(
            group["members"] for group in groups if len(group["members"]) > 1
        )
    return clusters


def _phase_one_promoted(item, security_domains=frozenset()):
    """True when place_roadmap would promote this finding to Phase 1.

    CRITICAL always reaches Phase 1; HIGH only when the security agent raised
    it. An ineligible finding is never placed, so it cannot be promoted.
    """
    if not roadmap_eligible(item):
        return False
    severity = normalize_severity(item.get("severity"))
    return severity == "CRITICAL" or (
        severity == "HIGH" and _is_security(item, security_domains)
    )


def _overlap_representative(members, security_domains=frozenset()):
    """Pick the member whose roadmap placement the cluster keeps.

    Eligible first, then a finding place_roadmap promotes to Phase 1: merging
    a HIGH security finding under a costlier non-security HIGH would lose the
    Phase 1 promotion the security finding earned.
    """
    return sorted(
        members,
        key=lambda item: (
            0 if roadmap_eligible(item) else 1,
            0 if _phase_one_promoted(item, security_domains) else 1,
            SEVERITY_WEIGHT[normalize_severity(item.get("severity"))],
            -_as_hours(item.get("est_hours")),
            item.get("id", ""),
        ),
    )[0]


_DEFAULT_LARGE_FIX_HOURS = 8.0


def find_large_file_clusters(findings, min_hours=None):
    """Flag files where several expensive findings may be one root cause.

    Advisory only: same file, at least two eligible findings at or above
    ``min_hours``. The DA adjudicates; nothing is removed from tech debt. The
    default is resolved at call time so a manifest override applies.
    """
    if min_hours is None:
        min_hours = _large_fix_hours()
    by_file = {}
    for item in findings:
        parts = anchor_parts(item.get("finding", ""))
        if parts is None:
            continue
        if _as_hours(item.get("est_hours")) < min_hours:
            continue
        by_file.setdefault(parts[0].replace("\\", "/"), []).append(item)
    return [
        members for _file, members in sorted(by_file.items())
        if len(members) > 1
    ]


_DEFAULT_QUICK_WIN_CAP_HOURS = 40.0


_DEFAULT_SECURITY_AGENT_ID = "security"


# The engine's identity and calibration belong to a run, not to the process.
# Two syntheses that run at the same time must not see each other's values,
# so the overrides live on the calling thread: a thread that sets them gets
# its own copy, and the next thread starts from the defaults. Module-level
# reads stay available through __getattr__ below, which reports the calling
# thread's value.
_SETTINGS = threading.local()

_ENGINE_DEFAULTS = {
    "SECURITY_AGENT_ID": _DEFAULT_SECURITY_AGENT_ID,
    "OVERLAP_THRESHOLD": _DEFAULT_OVERLAP_THRESHOLD,
    "LARGE_FIX_HOURS": _DEFAULT_LARGE_FIX_HOURS,
    "QUICK_WIN_CAP_HOURS": _DEFAULT_QUICK_WIN_CAP_HOURS,
}


def _setting(name):
    """Return this thread's override for a setting, or its default."""
    return getattr(_SETTINGS, name, _ENGINE_DEFAULTS[name])


def __getattr__(name):
    """Expose the thread's settings as module attributes.

    Callers that read ``findings.SECURITY_AGENT_ID`` see the value their own
    thread set. A module global cannot do that: the last writer would win for
    every reader.
    """
    if name in _ENGINE_DEFAULTS:
        return _setting(name)
    raise AttributeError(
        "module 'ccr.findings' has no attribute " + repr(name)
    )


def _security_agent_id():
    return _setting("SECURITY_AGENT_ID")


def _overlap_threshold():
    return _setting("OVERLAP_THRESHOLD")


def _large_fix_hours():
    return _setting("LARGE_FIX_HOURS")


def _quick_win_cap_hours():
    return _setting("QUICK_WIN_CAP_HOURS")


def set_security_agent_id(agent_id):
    """Point the security-agent check at the manifest's id.

    ADR-005 makes pipeline.json the source of truth for agent identity, so the
    loader overrides this default. Direct callers of this module keep the
    default, which also keeps unit tests independent of the manifest. The
    override belongs to the calling thread, so a second run in another thread
    cannot change what this one sees.
    """
    _SETTINGS.SECURITY_AGENT_ID = (
        agent_id if isinstance(agent_id, str) and agent_id
        else _DEFAULT_SECURITY_AGENT_ID
    )


# Calibration key -> (exclusive lower bound, inclusive upper bound or None).
# The manifest schema enforces the same ranges; the engine repeats them so a
# direct caller of set_calibration cannot install a value that merges every
# pair, detects no cluster, or caps every quick win.
CALIBRATION_RANGES = {
    "overlap_threshold": (0.0, 1.0),
    "large_fix_hours": (0.0, None),
    "quick_win_cap_hours": (0.0, None),
}


def _calibration_value(settings, key, default):
    """Return a usable override for key, or the default.

    NaN and infinity are refused here as well as by the manifest schema: NaN
    compares false against everything, so it would silently empty every
    cluster, and an enormous int would overflow the float conversion. An
    out-of-range number is ignored for the same reason.
    """
    low, high = CALIBRATION_RANGES[key]
    value = settings.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        if not math.isfinite(value):
            return default
    except OverflowError:
        return default
    if value <= low or (high is not None and value > high):
        return default
    return float(value)


def set_calibration(calibration):
    """Point the calibration constants at the manifest's values.

    ADR-005 makes pipeline.json the source of truth for the numbers that
    decide report output (ADR-007 records the policy), so the loader overrides
    these defaults. A key the manifest omits restores the engine default, so
    loading one manifest cannot leave a previous manifest's numbers live.
    Direct callers of this module keep the defaults, which also keeps unit
    tests independent of the manifest. The overrides belong to the calling
    thread, so a concurrent run in another thread cannot change them.
    """
    settings = calibration if isinstance(calibration, dict) else {}
    _SETTINGS.OVERLAP_THRESHOLD = _calibration_value(
        settings, "overlap_threshold", _DEFAULT_OVERLAP_THRESHOLD
    )
    _SETTINGS.LARGE_FIX_HOURS = _calibration_value(
        settings, "large_fix_hours", _DEFAULT_LARGE_FIX_HOURS
    )
    _SETTINGS.QUICK_WIN_CAP_HOURS = _calibration_value(
        settings, "quick_win_cap_hours", _DEFAULT_QUICK_WIN_CAP_HOURS
    )


def _domain_agent_ids(findings):
    """Map report names to the agent ids that produced them."""
    mapping = {}
    for item in findings:
        display = item.get("domain")
        agent_id = item.get("agent")
        if not isinstance(display, str) or not display:
            continue
        if not isinstance(agent_id, str) or not agent_id:
            continue
        mapping.setdefault(display, agent_id)
    return mapping


def _is_security(item, security_domains=frozenset()):
    """True when a finding came from the security agent.

    Keys on the stable agent id first: the display label is editable in the
    manifest. Findings without an id fall back to the labels this run attached
    to that id, so a rename cannot silently demote a HIGH finding.
    """
    if item.get("agent"):
        return item.get("agent") == _security_agent_id()
    return item.get("domain") in security_domains


def place_roadmap(findings, security_domains=None):
    """Split eligible findings into three phases.

    Phase 1: CRITICAL plus MEDIUM/LOW quick wins (<= 2h), capped at
    QUICK_WIN_CAP_HOURS so the phase stays discriminating.
    Phase 2: HIGH, MEDIUM at <= 8h, and quick wins beyond the cap.
    Phase 3: everything else eligible. INFO is never eligible.

    Args:
        findings: Eligible findings.
        security_domains: Report names the manifest assigned to the security
            agent. Defaults to the names the findings carry, plus the literal
            "Security".
    """
    findings = list(findings)
    if security_domains is None:
        roster = _domain_agent_ids(findings)
        security_domains = {
            display for display, agent_id in roster.items()
            if agent_id == _security_agent_id()
        }
    # Always keep the manifest default: a renamed label must not drop findings
    # that carry only the literal "Security" domain and no agent key.
    security_domains = set(security_domains or ()) | {"Security"}
    phases = {1: [], 2: [], 3: []}
    quick_wins = []
    for item in findings:
        if not roadmap_eligible(item):
            continue
        severity = normalize_severity(item.get("severity"))
        hours = _as_hours(item.get("est_hours"))
        if severity == "CRITICAL":
            phases[1].append(item)
        elif severity == "HIGH" and _is_security(item, security_domains):
            phases[1].append(item)
        elif severity in ("MEDIUM", "LOW") and hours <= 2:
            quick_wins.append(item)
        elif severity == "HIGH" or (severity == "MEDIUM" and hours <= 8):
            phases[2].append(item)
        else:
            phases[3].append(item)
    quick_wins.sort(key=lambda item: (
        SEVERITY_WEIGHT[normalize_severity(item.get("severity"))],
        _as_hours(item.get("est_hours")),
        item.get("id", ""),
    ))
    used = 0.0
    for item in quick_wins:
        hours = _as_hours(item.get("est_hours"))
        if used + hours <= _quick_win_cap_hours():
            phases[1].append(item)
            used += hours
        else:
            phases[2].append(item)
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


def _score_domains(open_findings):
    """Score each domain from open findings; also return total counts."""
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
    return scores, total_counts


def _roadmap_summary(phases):
    """Sum roadmap hours per phase, total, and per domain."""
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
    return roadmap_hours, total_hours, by_domain


def _verdict_summary(all_findings):
    """Count findings per DA verdict."""
    verdict_summary = {}
    for item in all_findings:
        verdict = normalize_verdict(item.get("da_verdict"))
        verdict_summary[verdict] = verdict_summary.get(verdict, 0) + 1
    return verdict_summary


def _priority_areas(scores):
    """Return the three domains needing attention first."""
    priority = sorted(
        scores,
        key=lambda row: (
            -row["critical"], -row["high"], -row["medium"], row["domain"]
        ),
    )
    return [row["domain"] for row in priority[:3]]


def _health(total_counts):
    """Map severity counts to RED/YELLOW/GREEN."""
    if total_counts["CRITICAL"]:
        return "RED"
    if total_counts["HIGH"]:
        return "YELLOW"
    return "GREEN"


def _overall_score(scores):
    """Average domain scores; 10.0 when there are no domains."""
    if scores:
        return round(sum(row["score"] for row in scores) / len(scores), 1)
    return 10.0


def _trend(baseline, total_hours):
    """Describe tech-debt movement against the previous baseline."""
    trend = "no previous baseline"
    if baseline:
        previous = baseline.get("tech_debt_hours")
        invalid = isinstance(previous, bool) or not isinstance(
            previous, (int, float)
        )
        if not invalid:
            try:
                invalid = not math.isfinite(previous)
            except OverflowError:
                invalid = True
        if invalid:
            previous = None
        if previous is not None:
            if previous > 0:
                change = round((total_hours - previous) / previous * 100)
                trend = f"{previous}h -> {total_hours}h ({change:+d}%)"
            else:
                trend = f"{previous}h -> {total_hours}h"
    return trend


def _assemble_model(findings, rejected, agents_planned, agents_completed, *,
                    target, health, total_counts, total_hours, scores,
                    priority_areas, overall_score, roadmap_hours, by_domain,
                    phases, verdict_summary, trend, overlap_candidates=None,
                    domain_agents=None, re_review_count=0):
    """Build the report model dict consumed by the renderers."""
    domain_agents = domain_agents or {}
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
        "overlap_candidates": overlap_candidates or [],
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
                domain_agents.get(row["domain"], row["domain"]): row["score"]
                for row in scores
            },
            "per_domain_open_findings": {
                domain_agents.get(row["domain"], row["domain"]): {
                    "critical": row["critical"], "high": row["high"],
                }
                for row in scores
            },
            "task_count": sum(len(items) for items in phases.values()),
            "re_review_count": re_review_count,
        },
    }


def aggregate(findings, rejected, agents_planned, agents_completed,
              target="", baseline=None, re_review_count=0):
    """Build the report model consumed by the renderers.

    Args:
        findings: Kept findings (post-dedup, post-id).
        rejected: Findings rejected by mechanical DA checks.
        agents_planned: Agent ids that were planned.
        agents_completed: Agent ids that reported.
        target: Target directory string.
        baseline: Optional previous baseline dict for trend text.
        re_review_count: Completed re-reviews, carried into the baseline so
            Phase 4f can force a full rescan every third re-review.

    Returns:
        dict: Report model.

    Assumes:
        ``findings`` already passed through ``review_findings``, ``dedup``,
        and ``assign_ids``. Calling this on raw agent output will include
        mechanically rejected items in the roadmap hours.

    The caller's dicts are copied on entry: ``overlap_of`` is annotated below,
    and building a report must not mutate the results it was given.
    """
    findings = [dict(item) for item in findings]
    rejected = [dict(item) for item in rejected]
    all_findings = list(findings) + list(rejected)
    open_findings = [f for f in findings if f.get("da_verdict") != "REJECTED"]
    domain_agents = _domain_agent_ids(all_findings)

    scores, total_counts = _score_domains(open_findings)

    # Same set place_roadmap applies (it always adds the literal "Security").
    security_domains = {
        display for display, agent_id in domain_agents.items()
        if agent_id == _security_agent_id()
    } | {"Security"}

    overlap_candidates = []
    merged_ids = set()
    for members in find_overlaps(findings):
        rep = _overlap_representative(members, security_domains)
        merged = [item for item in members if item is not rep]
        for item in merged:
            item["overlap_of"] = rep.get("id", "")
            merged_ids.add(id(item))
        overlap_candidates.append({
            "file": anchor_parts(rep.get("finding", ""))[0],
            "kept": rep.get("id", ""),
            "merged": [item.get("id", "") for item in merged],
            "advisory": False,
            "hours": round(sum(_as_hours(m.get("est_hours")) for m in members), 2),
        })
    for members in find_large_file_clusters(findings):
        remaining = [item for item in members if id(item) not in merged_ids]
        if len(remaining) < 2:
            continue
        members = remaining
        rep = _overlap_representative(members, security_domains)
        overlap_candidates.append({
            "file": anchor_parts(rep.get("finding", ""))[0],
            "kept": rep.get("id", ""),
            "merged": [item.get("id", "") for item in members
                       if item is not rep],
            "advisory": True,
            "hours": round(sum(_as_hours(m.get("est_hours")) for m in members), 2),
        })
    roadmap_source = [f for f in findings if id(f) not in merged_ids]

    phases = place_roadmap(
        roadmap_source,
        security_domains=security_domains,
    )
    roadmap_hours, total_hours, by_domain = _roadmap_summary(phases)

    verdict_summary = _verdict_summary(all_findings)
    priority_areas = _priority_areas(scores)
    health = _health(total_counts)
    overall_score = _overall_score(scores)
    trend = _trend(baseline, total_hours)

    return _assemble_model(
        findings, rejected, agents_planned, agents_completed,
        target=target, health=health, total_counts=total_counts,
        total_hours=total_hours, scores=scores,
        priority_areas=priority_areas, overall_score=overall_score,
        roadmap_hours=roadmap_hours, by_domain=by_domain,
        phases=phases, verdict_summary=verdict_summary, trend=trend,
        overlap_candidates=overlap_candidates, domain_agents=domain_agents,
        re_review_count=re_review_count,
    )

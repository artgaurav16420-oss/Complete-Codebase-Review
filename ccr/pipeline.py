"""Pipeline glue: completion gates, synthesis, and eval scoring."""

import json
from datetime import datetime, timezone
from pathlib import Path

from . import findings as findings_mod
from . import report as report_mod
from .fileio import write_text
from .providers import RecordedProvider


def check_completion(manifest, effort, planned, completed):
    """Raise when too few agents completed to trust the result.

    Args:
        manifest: Pipeline manifest.
        effort: "max" or "min".
        planned: Planned agent ids.
        completed: Agent ids that returned.

    Returns:
        float: Completion ratio.

    Raises:
        RuntimeError: When the ratio is below the configured threshold.

    Assumes:
        ``planned`` contains active domains only; callers must exclude
        LOW-ACTIVITY domains before invoking the gate.
    """
    if not planned:
        return 0.0
    planned = list(dict.fromkeys(planned))
    completed = list(dict.fromkeys(completed))
    completed = [agent_id for agent_id in completed if agent_id in planned]
    ratio = len(completed) / len(planned)
    key = "quick_completion" if effort == "min" else "full_completion"
    threshold = manifest["thresholds"][key]
    if ratio < threshold:
        raise RuntimeError(
            f"insufficient agent coverage: {len(completed)}/{len(planned)} "
            f"({ratio:.0%}) below {threshold:.0%}"
        )
    return ratio


def _collect_raw(manifest, results, planned):
    """Flatten agent results into normalised finding dicts."""
    agents_by_id = {a["id"]: a for a in manifest["agents"]}
    raw = []
    for agent_id in planned:
        if agent_id not in results:
            continue
        agent = agents_by_id.get(agent_id)
        if agent is None:
            raise ValueError("unknown agent id: " + str(agent_id))
        domain = agent["report"]
        for item in results[agent_id].get("findings", []):
            copy = dict(item)
            copy["domain"] = domain
            copy["agent"] = agent_id
            raw.append(copy)
    return raw


def _codebase_size(facts):
    """Map discovery facts to the report's codebase-size block."""
    return {
        "files": (facts or {}).get("files", 0),
        "languages": len((facts or {}).get("languages", {})),
        "modules": len((facts or {}).get("top_dirs", {})),
        "truncated": bool((facts or {}).get("truncated", False)),
    }


def _canonicalize_baseline(model, manifest):
    """Remap baseline domain keys from report names to agent ids.

    ``aggregate`` already keys the baseline by agent id; the remap only exists
    for a baseline read from an older report. A key that is itself a known
    agent id is an id, not a label, so it passes through unchanged even when
    some other agent's report name happens to match it. Without that, one
    agent's score would be redirected onto another's and overwritten.
    """
    agent_ids = {a["id"] for a in manifest["agents"]}
    display_to_id = {
        a["report"]: a["id"]
        for a in manifest["agents"]
        if a["report"] not in agent_ids
    }
    baseline = model["baseline"]
    baseline["per_domain_scores"] = {
        display_to_id.get(name, name): value
        for name, value in baseline["per_domain_scores"].items()
    }
    baseline["per_domain_open_findings"] = {
        display_to_id.get(name, name): value
        for name, value in baseline["per_domain_open_findings"].items()
    }


MALFORMED_MAX = 3
MALFORMED_RATIO = 0.2


def malformed_exceeded(raw_count, malformed_count):
    """True when malformed findings are too many and too large a share.

    Single source of the rule: synthesize and validate-results must agree on
    the same cache, otherwise the gate blocks a report the producer accepts.
    """
    return (
        malformed_count > MALFORMED_MAX
        and malformed_count / max(raw_count, 1) > MALFORMED_RATIO
    )


def synthesize(manifest, results, planned, completed=None, target="",
               facts=None, baseline=None, timestamp=None, re_review_count=0):
    """Merge agent results into a report model.

    Applies mechanical DA checks, deduplicates, assigns ids, and aggregates.

    Args:
        manifest: Pipeline manifest.
        results: agent id -> result dict.
        planned: Planned agent ids (sets iteration order).
        completed: Agent ids that returned. Defaults to results keys.
        target: Target directory string.
        facts: Discovery facts, used for codebase size.
        baseline: Previous baseline for trend text.
        timestamp: ISO timestamp for the baseline snapshot.
        re_review_count: Re-reviews performed so far, carried into the
            baseline snapshot so the periodic full rescan can fire.

    Returns:
        dict: Report model.
    """
    completed = list(completed if completed is not None else results.keys())
    raw = _collect_raw(manifest, results, planned)
    kept, rejected = findings_mod.review_findings(
        raw, floors=manifest.get("tech_debt_floors")
    )
    malformed = findings_mod.malformed_rejections(rejected)
    if malformed_exceeded(len(raw), len(malformed)):
        raise ValueError(
            "agent results malformed: {}/{} findings are empty or have no "
            "[file:line] anchor; re-run the agents with the CLI result shape "
            "([path:line] \u2014 flaw \u2192 failure)".format(
                len(malformed), len(raw)
            )
        )
    kept = findings_mod.assign_ids(findings_mod.dedup(kept))

    model = findings_mod.aggregate(
        kept, rejected, planned, completed,
        target=target, baseline=baseline,
        re_review_count=re_review_count,
    )
    model["codebase_size"] = _codebase_size(facts)
    _canonicalize_baseline(model, manifest)
    model["baseline"]["timestamp"] = timestamp or datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")
    return model


def render(model, fmt="markdown"):
    """Render a model. Returns a dict of format name to text."""
    output = {}
    if fmt in ("markdown", "both"):
        output["markdown"] = report_mod.render_markdown(model)
    if fmt in ("json", "both"):
        output["json"] = report_mod.render_json(model)
    if not output:
        raise ValueError("unknown format: " + fmt)
    return output


def write_outputs(model, out_path, fmt="markdown"):
    """Write rendered output next to out_path. Returns written paths."""
    written = []
    base = Path(out_path)
    base.parent.mkdir(parents=True, exist_ok=True)

    def _target(suffix):
        if base.suffix in ("", ".md", ".json"):
            return base.with_suffix(suffix)
        return Path(str(base) + suffix)

    for name, text in render(model, fmt).items():
        if name == "json":
            target = _target(".json")
            payload = json.dumps(text, indent=2, sort_keys=True) + "\n"
            write_text(target, payload, root=target.parent)
        else:
            errors = report_mod.validate_markdown(text)
            if errors:
                raise ValueError(
                    "report failed validation: " + "; ".join(errors)
                )
            target = _target(".md")
            write_text(target, text, root=target.parent)
        written.append(target)
    return written


def evaluate(model, expected_issues):
    """Score a report against expected issue identifiers.

    A finding matches when one of its tags equals an expected identifier.

    Returns:
        dict: coverage, precision, matched, missing, unmatched counts.
    """
    expected = [str(item) for item in expected_issues]
    expected_set = set(expected)
    matched = set()
    matched_findings = 0
    for item in model["findings"]:
        tags = {str(tag) for tag in item.get("tags", [])}
        hits = tags & expected_set
        if hits:
            matched |= hits
            matched_findings += 1
    total = len(model["findings"])
    coverage = len(matched) / len(expected) if expected else 1.0
    precision = matched_findings / total if total else 0.0
    return {
        "expected": len(expected),
        "matched": len(matched),
        "missing": sorted(expected_set - matched),
        "coverage": round(coverage, 4),
        "precision": round(precision, 4),
        "findings_total": total,
        "findings_matched": matched_findings,
        "rejected": len(model["rejected"]),
    }


def load_spec(path):
    """Load an expected-issues file.

    Accepts either a bare list (legacy fixtures) or a benchmark object with
    `expected_issues` and optional `known_false_positives` substrings.

    Returns:
        tuple: (expected_issues, known_false_positives)
    """
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    if isinstance(spec, list):
        return spec, []
    if not isinstance(spec, dict):
        raise ValueError("expected file must be a list or an object")
    expected = spec.get("expected_issues")
    if not isinstance(expected, list):
        raise ValueError("benchmark spec missing expected_issues list")
    false_positives = spec.get("known_false_positives", [])
    if not isinstance(false_positives, list):
        raise ValueError("known_false_positives must be a list")
    return expected, false_positives


def _validate_expected(expected):
    """Reject empty or duplicated expected-issue lists."""
    if not expected:
        raise ValueError("expected issues must be a non-empty list")
    if len(expected) != len(set(expected)):
        raise ValueError("duplicate expected issues")


def run_eval(manifest, fixtures_dir, expected_path):
    """Replay recorded fixtures through synthesis and score the result."""
    provider = RecordedProvider(fixtures_dir)
    agent_ids = provider.agent_ids()
    if not agent_ids:
        raise ValueError("no fixture results in " + str(fixtures_dir))
    results = {agent_id: provider.get(agent_id) for agent_id in agent_ids}
    model = synthesize(
        manifest, results, agent_ids, target="fixture",
        timestamp="1970-01-01T00:00:00+00:00",
    )
    expected, false_positives = load_spec(expected_path)
    _validate_expected(expected)
    score = evaluate(model, expected)
    if false_positives:
        hits = []
        for needle in false_positives:
            if any(needle in item["finding"] for item in model["findings"]):
                hits.append(needle)
        total = score["findings_total"]
        score["known_false_positives"] = hits
        score["verified_precision"] = (
            round((total - len(hits)) / total, 4) if total else 0.0
        )
    return model, score

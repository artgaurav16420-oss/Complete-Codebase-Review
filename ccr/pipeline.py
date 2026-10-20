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
            "insufficient agent coverage: {}/{} ({:.0%}) below {:.0%}".format(
                len(completed), len(planned), ratio, threshold
            )
        )
    return ratio


def synthesize(manifest, results, planned, completed=None, target="",
               facts=None, baseline=None, timestamp=None):
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

    Returns:
        dict: Report model.
    """
    completed = list(completed if completed is not None else results.keys())
    raw = []
    for agent_id in planned:
        if agent_id not in results:
            continue
        agent = next(a for a in manifest["agents"] if a["id"] == agent_id)
        domain = agent["report"]
        for item in results[agent_id].get("findings", []):
            copy = dict(item)
            copy.setdefault("domain", domain)
            copy["agent"] = agent_id
            raw.append(copy)

    kept, rejected = findings_mod.review_findings(
        raw, floors=manifest.get("tech_debt_floors")
    )
    kept = findings_mod.assign_ids(findings_mod.dedup(kept))

    model = findings_mod.aggregate(
        kept, rejected, planned, completed,
        target=target, baseline=baseline,
    )
    size = {
        "files": (facts or {}).get("files", 0),
        "languages": len((facts or {}).get("languages", {})),
        "modules": len((facts or {}).get("top_dirs", {})),
    }
    model["codebase_size"] = size
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
    for name, text in render(model, fmt).items():
        if name == "json":
            target = base.with_suffix(".json")
            payload = json.dumps(text, indent=2, sort_keys=True) + "\n"
            write_text(target, payload)
        else:
            target = base.with_suffix(".md")
            write_text(target, text)
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

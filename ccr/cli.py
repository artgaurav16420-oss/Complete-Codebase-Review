"""Command-line interface for the review pipeline."""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from . import __version__, manifest as manifest_mod
from . import discovery, pipeline, providers, state


def _manifest():
    """Load the manifest or exit with a clear error."""
    try:
        return manifest_mod.load()
    except (OSError, ValueError) as exc:
        print("[ERROR] " + str(exc))
        sys.exit(2)


def cmd_plan(args):
    """Print the Phase 1 + Phase 2 plan."""
    data = _manifest()
    target = args.target or args.target_opt or "."
    try:
        plan = discovery.plan(
            data, target, effort=args.effort,
            override=args.agents, max_files=args.max_files,
        )
    except ValueError as exc:
        print("[ERROR] " + str(exc))
        return 2
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    facts = plan["facts"]
    print(
        f"[PLAN] {plan['target']} - {facts['files']} files, "
        f"{len(facts['languages'])} languages, {facts['test_files']} test files"
    )
    mode = "quick" if plan["quick_mode"] else "full"
    print(f"[PLAN] effort={args.effort} ({mode}) timeout={plan['timeout_sec']}s")
    print(
        f"[PLAN] agents ({len(plan['agents'])}): "
        f"{', '.join(plan['agents'])}"
    )
    if facts["truncated"]:
        print(
            "[WARN] file cap reached; results cover a sample only",
            file=sys.stderr,
        )
    return 0


def _archive_results(cache):
    """Move previous agent results aside so they cannot be counted again."""
    stale = sorted(Path(cache).glob("phase_*.json"))
    if not stale:
        return 0
    dest = Path(cache) / "previous-results" / datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )
    dest.mkdir(parents=True, exist_ok=True)
    for path in stale:
        shutil.move(str(path), str(dest / path.name))
    return len(stale)


def cmd_record(args):
    """Write agent prompts and initialize pipeline state."""
    data = _manifest()
    target = args.target or args.target_opt or "."
    try:
        plan = discovery.plan(
            data, target, effort=args.effort,
            override=args.agents, max_files=args.max_files,
        )
    except ValueError as exc:
        print("[ERROR] " + str(exc))
        return 2
    cache = Path(args.out)
    state_path = cache / "ccr-state.json"
    try:
        current = state.State.load(state_path)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] invalid state in {cache}: {exc}")
        return 2
    archived = _archive_results(args.out)
    paths = providers.write_prompts(
        data, plan, args.out, skill_dir=args.skill_dir
    )
    if current is None or current.data["target_dir"] != plan["target"]:
        current = state.State.create(
            state_path, plan["target"], args.skill_dir, args.effort
        )
    current.data["effort"] = args.effort
    current.data["skill_dir"] = args.skill_dir
    current.data["facts"] = plan["facts"]
    current.save()
    current.set_gate("p1_discovery", True)
    current.plan_agents(plan["agents"])
    current.set_step("phase2:awaiting_agent_results")
    if archived:
        print(f"[RECORD] archived {archived} stale result file(s)")
    print(f"[RECORD] wrote {len(paths)} prompts to {cache}")
    print(f"[RECORD] run them, then: python -m ccr synthesize --in {cache}")
    return 0


def _planned_from_cache(cache):
    """Infer planned agent ids from phase_*.json files in the cache."""
    ids = []
    for path in sorted(Path(cache).glob("*.json")):
        stem = path.stem
        if stem in ("ccr-state", "ccr-baseline"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or not isinstance(
                data.get("findings"), list):
            continue
        if stem.startswith("phase_"):
            stem = stem[len("phase_"):]
        if stem and stem not in ids:
            ids.append(stem)
    return ids


def _cache_state(cache):
    """Return the pipeline state for a cache directory, or None."""
    return state.State.load(Path(cache) / "ccr-state.json")


def _resolve_planned(args, cached):
    if args.agents:
        return [
            token.strip() for token in args.agents.split(",") if token.strip()
        ]
    if cached is not None and cached.data["agents_planned"]:
        return cached.data["agents_planned"]
    return _planned_from_cache(args.cache)


def _check_completion_gate(data, effort, planned, completed, gate_known, args):
    if args.allow_partial or not gate_known:
        return None
    try:
        pipeline.check_completion(data, effort, planned, completed)
    except RuntimeError as exc:
        return exc
    return None


def _load_synthesis_results(args, planned):
    results = providers.load_results(args.cache, planned, required=False)
    completed = [agent_id for agent_id in planned if agent_id in results]
    if not completed:
        raise ValueError("no agent results found in " + args.cache)
    return results, completed


def _emit_synthesis_output(model, args):
    if not args.out:
        rendered = pipeline.render(model, args.format)
        if "markdown" in rendered:
            sys.stdout.write(rendered["markdown"])
        if "json" in rendered:
            if "markdown" in rendered:
                print("---CCR_JSON_START---")
            print(json.dumps(rendered["json"], indent=2, sort_keys=True))
        return 0
    written = pipeline.write_outputs(model, args.out, fmt=args.format)
    for path in written:
        print("[SYNTHESIZE] wrote " + str(path))
    print(
        f"[SYNTHESIZE] health={model['overall_health']} "
        f"critical={model['critical_issues']} "
        f"debt={model['tech_debt_hours']}h "
        f"agents={model['agent_status']['completed']}/"
        f"{model['agent_status']['total']}"
    )
    return 0


def cmd_synthesize(args):
    """Merge agent results into a report, enforcing the completion gate."""
    data = _manifest()
    try:
        cached = _cache_state(args.cache)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] invalid state in {args.cache}: {exc}")
        return 2
    planned = _resolve_planned(args, cached)
    if not planned:
        print("[ERROR] no agent results found in " + args.cache)
        return 2

    effort = args.effort
    if effort is None:
        effort = cached.data.get("effort", "max") if cached is not None else "max"
    target = args.target or (cached.data["target_dir"] if cached else args.cache)
    facts = cached.data.get("facts") if cached is not None else None
    gate_known = bool(args.agents) or (
        cached is not None and bool(cached.data["agents_planned"])
    )
    if not gate_known:
        print(
            "[WARN] planned agent set unknown (no state, no --agents); "
            "completion gate skipped",
            file=sys.stderr,
        )

    try:
        results, completed = _load_synthesis_results(args, planned)
    except (OSError, ValueError) as exc:
        print("[ERROR] " + str(exc))
        return 2
    gate_error = _check_completion_gate(
        data, effort, planned, completed, gate_known, args
    )
    if gate_error is not None:
        print("[ERROR] " + str(gate_error))
        print("[ERROR] report blocked; rerun with --allow-partial only if "
              "you accept the missing domains")
        return 1

    try:
        model = pipeline.synthesize(
            data, results, planned, completed=completed, target=target,
            facts=facts,
        )
    except ValueError as exc:
        print("[ERROR] " + str(exc))
        return 2
    return _emit_synthesis_output(model, args)


def cmd_eval(args):
    """Score recorded fixtures against expected issues."""
    data = _manifest()
    fixtures = args.fixtures or "tests/fixtures/agents"
    expected = args.expected or "tests/expected_issues.json"
    if not Path(fixtures).is_dir() or not Path(expected).is_file():
        print("[ERROR] eval defaults require a source checkout; "
              "pass --fixtures and --expected")
        return 2
    try:
        model, score = pipeline.run_eval(data, fixtures, expected)
    except (OSError, ValueError) as exc:
        print("[ERROR] " + str(exc))
        return 2
    if args.json:
        print(json.dumps(score, indent=2, sort_keys=True))
    else:
        print(
            f"[EVAL] coverage={score['coverage']:.0%} "
            f"precision={score['precision']:.0%} "
            f"matched={score['matched']}/{score['expected']} "
            f"findings={score['findings_total']}"
        )
        if "verified_precision" in score:
            print(
                f"[EVAL] verified_precision={score['verified_precision']:.0%} "
                f"known_false_positives="
                f"{len(score['known_false_positives'])}"
            )
        if score["missing"]:
            print("[EVAL] missing: " + ", ".join(score["missing"]))
    if score["missing"]:
        return 1
    return 0


def _positive_int(value):
    """argparse type: reject zero and negative counts."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return number


def build_parser():
    """Build the argparse parser."""
    parser = argparse.ArgumentParser(
        prog="ccr",
        description="Deterministic core for the Complete Codebase Review pipeline.",
    )
    parser.add_argument(
        "--version", action="version", version="ccr " + __version__
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="show discovery and agent selection")
    plan.add_argument("target", nargs="?", default=None,
                      help="Target directory (default: current directory).")
    plan.add_argument("--target", dest="target_opt", default=None,
                      help="Target directory (alternative to positional).")
    plan.add_argument("--effort", choices=["max", "min"], default="max")
    plan.add_argument("--agents", default=None)
    plan.add_argument("--max-files", type=_positive_int, default=None)
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(func=cmd_plan)

    record = sub.add_parser("record", help="write agent prompts and state")
    record.add_argument("target", nargs="?", default=None,
                        help="Target directory (default: current directory).")
    record.add_argument("--target", dest="target_opt", default=None,
                        help="Target directory (alternative to positional).")
    record.add_argument("--out", default=".code-review-cache")
    record.add_argument("--effort", choices=["max", "min"], default="max")
    record.add_argument("--agents", default=None)
    record.add_argument("--max-files", type=_positive_int, default=None)
    record.add_argument("--skill-dir", default="")
    record.set_defaults(func=cmd_record)

    synth = sub.add_parser("synthesize", help="merge agent results into a report")
    synth.add_argument("--in", dest="cache", default=".code-review-cache")
    synth.add_argument("--out", default=None)
    synth.add_argument("--target", default="")
    synth.add_argument("--agents", default=None)
    synth.add_argument(
        "--effort", choices=["max", "min"], default=None,
        help="Defaults to the effort recorded in ccr-state.json, else max.",
    )
    synth.add_argument(
        "--allow-partial", action="store_true",
        help="Emit a report even when the agent completion gate fails.",
    )
    synth.add_argument(
        "--format", choices=["markdown", "json", "both"], default="markdown"
    )
    synth.set_defaults(func=cmd_synthesize)

    ev = sub.add_parser("eval", help="score fixtures against expected issues")
    ev.add_argument(
        "--fixtures", default=None,
        help="Default: tests/fixtures/agents (source checkout only).",
    )
    ev.add_argument(
        "--expected", default=None,
        help="Default: tests/expected_issues.json (source checkout only).",
    )
    ev.add_argument("--json", action="store_true")
    ev.set_defaults(func=cmd_eval)
    return parser


def main(argv=None):
    """CLI entry point."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

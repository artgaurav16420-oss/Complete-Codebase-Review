"""Command-line interface for the review pipeline."""

import argparse
import json
import sys
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
    print("[PLAN] {} - {} files, {} languages, {} test files".format(
        plan["target"], facts["files"], len(facts["languages"]),
        facts["test_files"],
    ))
    mode = "quick" if plan["quick_mode"] else "full"
    print("[PLAN] effort={} ({}) timeout={}s".format(
        args.effort, mode, plan["timeout_sec"]
    ))
    print("[PLAN] agents ({}): {}".format(
        len(plan["agents"]), ", ".join(plan["agents"])
    ))
    if facts["truncated"]:
        print("[WARN] file cap reached; results cover a sample only")
    return 0


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
    paths = providers.write_prompts(
        data, plan, args.out, skill_dir=args.skill_dir
    )
    cache = Path(args.out)
    state_path = cache / "ccr-state.json"
    current = state.State.load(state_path)
    if current is None or current.data["target_dir"] != plan["target"]:
        current = state.State.create(
            state_path, plan["target"], args.skill_dir, args.effort
        )
    current.set_gate("p1_discovery", True)
    current.plan_agents(plan["agents"])
    current.set_step("phase2:awaiting_agent_results")
    print("[RECORD] wrote {} prompts to {}".format(len(paths), cache))
    print("[RECORD] run them, then: python -m ccr synthesize --in {}".format(cache))
    return 0


def _planned_from_cache(cache):
    """Infer planned agent ids from phase_*.json files in the cache."""
    ids = []
    for path in sorted(Path(cache).glob("phase_*.json")):
        stem = path.stem
        if stem.startswith("phase_"):
            stem = stem[len("phase_"):]
        ids.append(stem)
    return ids


def _cache_state(cache):
    """Return the pipeline state for a cache directory, or None."""
    return state.State.load(Path(cache) / "ccr-state.json")


def cmd_synthesize(args):
    """Merge agent results into a report, enforcing the completion gate."""
    data = _manifest()
    cached = _cache_state(args.cache)
    if args.agents:
        planned = args.agents.split(",")
    elif cached is not None and cached.data["agents_planned"]:
        planned = cached.data["agents_planned"]
    else:
        planned = _planned_from_cache(args.cache)
    if not planned:
        print("[ERROR] no agent results found in " + args.cache)
        return 2

    effort = args.effort
    if effort is None:
        effort = cached.data["effort"] if cached is not None else "max"
    target = args.target or (cached.data["target_dir"] if cached else args.cache)

    try:
        results = providers.load_results(args.cache, planned, required=False)
    except (OSError, ValueError) as exc:
        print("[ERROR] " + str(exc))
        return 2
    completed = [agent_id for agent_id in planned if agent_id in results]
    if not completed:
        print("[ERROR] no agent results found in " + args.cache)
        return 2
    if not args.allow_partial:
        try:
            pipeline.check_completion(data, effort, planned, completed)
        except RuntimeError as exc:
            print("[ERROR] " + str(exc))
            print("[ERROR] report blocked; rerun with --allow-partial only if "
                  "you accept the missing domains")
            return 1

    model = pipeline.synthesize(
        data, results, planned, completed=completed, target=target
    )
    if not args.out:
        rendered = pipeline.render(model, args.format)
        if "markdown" in rendered:
            sys.stdout.write(rendered["markdown"])
        if "json" in rendered:
            print(json.dumps(rendered["json"], indent=2, sort_keys=True))
        return 0
    written = pipeline.write_outputs(model, args.out, fmt=args.format)
    for path in written:
        print("[SYNTHESIZE] wrote " + str(path))
    print("[SYNTHESIZE] health={} critical={} debt={}h agents={}/{}".format(
        model["overall_health"], model["critical_issues"],
        model["tech_debt_hours"], model["agent_status"]["completed"],
        model["agent_status"]["total"],
    ))
    return 0


def cmd_eval(args):
    """Score recorded fixtures against expected issues."""
    data = _manifest()
    try:
        model, score = pipeline.run_eval(data, args.fixtures, args.expected)
    except (OSError, ValueError) as exc:
        print("[ERROR] " + str(exc))
        return 2
    if args.json:
        print(json.dumps(score, indent=2, sort_keys=True))
    else:
        print("[EVAL] coverage={:.0%} precision={:.0%} matched={}/{} findings={}".format(
            score["coverage"], score["precision"], score["matched"],
            score["expected"], score["findings_total"],
        ))
        if "verified_precision" in score:
            print("[EVAL] verified_precision={:.0%} known_false_positives={}".format(
                score["verified_precision"],
                len(score["known_false_positives"]),
            ))
        if score["missing"]:
            print("[EVAL] missing: " + ", ".join(score["missing"]))
    if score["missing"]:
        return 1
    return 0


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
    plan.add_argument("--max-files", type=int, default=None)
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
    record.add_argument("--max-files", type=int, default=None)
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
    ev.add_argument("--fixtures", default="tests/fixtures/agents")
    ev.add_argument("--expected", default="tests/expected_issues.json")
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

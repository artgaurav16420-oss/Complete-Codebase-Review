# ccr - Deterministic Core

The `ccr` package is the part of the review that runs without a model:
discovery, agent planning, state, finding normalization, DA checks, tech-debt
aggregation, roadmap, and report rendering. Zero runtime dependencies.

## Source of truth

`ccr/pipeline.json` defines agents, env vars, enums, thresholds, tech-debt
floors, and the version. Documentation tables and `install.py.sha256` are
generated from it:

```bash
python tools/generate.py
python tools/generate.py --check   # CI mode
```

## Modules

| Module | Responsibility |
|--------|----------------|
| `ccr.manifest` | Load and validate `pipeline.json` |
| `ccr.discovery` | Deterministic file/tooling scan; agent selection (override > Quick Mode > dimensions) |
| `ccr.state` | Atomic `ccr-state.json`; phase gates, agent accounting, resume drift detection |
| `ccr.findings` | Severity/verdict normalization, mechanical DA rejection, dedup, roadmap, aggregation |
| `ccr.report` | Markdown and JSON renderers; both validated by `tests/test_pipeline.py` |
| `ccr.providers` | Prompt generation, result ingestion, fixture replay |
| `ccr.pipeline` | Completion gates, synthesis, eval scoring |
| `ccr.cli` | `plan`, `record`, `synthesize`, `eval` |

## Integration boundary

`ccr` cannot spawn sub-agents. `record` writes `phase_<agent>.prompt.md` for the
host agent to execute; `synthesize` reads `phase_<agent>.json` back. Agent
result shape:

```json
{
  "agent": "security",
  "score": 4,
  "findings": [
    {
      "finding": "[src/db.py:12] — password literal in source → any reader gets it",
      "severity": "CRITICAL",
      "est_hours": 2,
      "finding_type": "hardcoded_secret",
      "tags": ["CWE-798"],
      "da_verdict": "CONFIRMED",
      "evidence": "literal assignment"
    }
  ]
}
```

`tags` are what the eval harness scores against `tests/expected_issues.json`.
`finding_type` optionally names a `tech_debt_floors` key; a missing estimate
takes the floor, and an explicit estimate is raised to at least half the floor
(the documented 0.5x multiplier).

## CLI

| Command | Purpose |
|---------|---------|
| `python -m ccr plan <dir>` | Discovery facts and selected agents (`--json` for machine output) |
| `python -m ccr record <dir> --out <cache>` | Prompts plus initial `ccr-state.json` |
| `python -m ccr synthesize --in <cache> --out <report>` | Report model to Markdown/JSON; refuses below the completion gate |
| `python -m ccr eval` | Fixture coverage and precision (list or benchmark spec) |

`synthesize` flags: `--effort max|min` (defaults to the state file),
`--allow-partial` to emit a report below the gate. Exit codes: `0` success,
`1` completion gate or eval miss, `2` usage or manifest error.

## Benchmarks

`ccr eval` accepts either a bare list of issue identifiers
(`tests/expected_issues.json`) or a benchmark object:

```json
{
  "expected_issues": ["tag-a", "CWE-798"],
  "known_false_positives": ["substring identifying a known-bad finding"]
}
```

The Organizer benchmark in `tests/fixtures/organizer/` is a real recorded run
with human-verified precision; see its README.

## Function reference

Signatures below are the public (non-underscore) functions of each module.
All return values are plain dicts/lists unless stated otherwise.

### `ccr.manifest`

| Function | Signature | Returns |
|----------|-----------|---------|
| `load` | `load(path=None)` | Manifest dict; raises `ValueError` on missing/invalid JSON |
| `validate` | `validate(data)` | `None`; raises `ValueError` with the first schema problem |
| `agent_ids` | `agent_ids(manifest)` | List of agent ids in manifest order |
| `agent_by_id` | `agent_by_id(manifest, agent_id)` | Agent dict or `None` |
| `report_name` | `report_name(manifest, agent_id)` | Report label; raises `ValueError` for unknown ids |
| `env_var_names` | `env_var_names(manifest)` | List of env-var names |
| `floor_for` | `floor_for(manifest, key)` | Float hours; defaults to `1.0` when no floor is defined |

### `ccr.discovery`

| Function | Signature | Returns |
|----------|-----------|---------|
| `discover` | `discover(target_dir, max_files=None)` | Facts dict (`files`, `bytes`, `languages`, `top_dirs`, `ci`, `truncated`, ...) |
| `active_agents` | `active_agents(manifest, facts)` | Agent ids whose dimensions apply; test health only when tests exist |
| `select_agents` | `select_agents(manifest, facts, effort='max', override=None)` | Planned ids; precedence is override > Quick Mode > dimensions |
| `plan` | `plan(manifest, target_dir, effort='max', override=None, max_files=None)` | `{target, effort, quick_mode, timeout_sec, agents, agent_names, facts}` |

`discover` raises `ValueError` when the target is not a directory or
`max_files < 1`.

### `ccr.state`

| Function | Signature | Returns |
|----------|-----------|---------|
| `new_state` | `new_state(target_dir, skill_dir='', effort='max')` | Fresh state dict |
| `merge_resume` | `merge_resume(state, cache_dir)` | Agent ids present on disk but not recorded as completed |
| `State.load` | `State.load(path)` | `State` or `None` when absent |
| `State.create` | `State.create(path, target_dir, skill_dir, effort)` | New `State`, persisted |
| `State.save` | `state.save()` | `None`; atomic write via temp file + `os.replace` |
| `State.record_agent` | `state.record_agent(agent_id, status='completed')` | `None` |
| `State.threshold_passed` | `state.threshold_passed(manifest)` | `bool`; enforces the 75%/66% completion gate |

### `ccr.findings`

| Function | Signature | Returns |
|----------|-----------|---------|
| `normalize_severity` | `normalize_severity(value)` | One of `CRITICAL/HIGH/MEDIUM/LOW/INFO`; unknown -> `LOW` |
| `normalize_verdict` | `normalize_verdict(value)` | One of `CONFIRMED/PLAUSIBLE/QUESTIONABLE/REJECTED/DA-ESCALATION`; unknown -> `QUESTIONABLE` |
| `anchor_parts` | `anchor_parts(finding_text)` | `(file, line, flaw, failure_mode)` or `None` |
| `weasel_hits` | `weasel_hits(text)` | Matched weasel phrases |
| `review_findings` | `review_findings(raw_findings, floors=None)` | `(kept, rejected)` after mechanical DA checks |
| `dedup` | `dedup(findings)` | Deduplicated list |
| `assign_ids` | `assign_ids(findings)` | Same list with `F-001` style ids |
| `roadmap_eligible` | `roadmap_eligible(finding)` | `bool`; `REJECTED` and `INFO` are never eligible |
| `place_roadmap` | `place_roadmap(findings)` | `{1, 2, 3}` phases; quick wins capped at 40h, HIGH never quick-win |
| `find_overlaps` | `find_overlaps(findings)` | Near-identical same-file clusters (auto-merged once) |
| `find_large_file_clusters` | `find_large_file_clusters(findings, min_hours=8.0)` | Advisory same-file clusters of expensive findings |
| `aggregate` | `aggregate(findings, rejected, agents_planned, agents_completed, target='', baseline=None)` | Report model consumed by the renderers |

### `ccr.report`

| Function | Signature | Returns |
|----------|-----------|---------|
| `fmt_hours` | `fmt_hours(value)` | `2` -> `"2h"`, `2.5` -> `"2.5h"` |
| `fmt_hours_long` | `fmt_hours_long(value)` | `2` -> `"2 hours"` |
| `render_markdown` | `render_markdown(model)` | Markdown string |
| `render_json` | `render_json(model)` | JSON-ready dict; `INFO` is mapped to `LOW` |

### `ccr.providers`

| Function | Signature | Returns |
|----------|-----------|---------|
| `build_prompt` | `build_prompt(agent, target, skill_dir, manifest_version='')` | Prompt text |
| `prompt_path` | `prompt_path(out_dir, agent_id)` | `Path` to `phase_<id>.prompt.md` |
| `result_path` | `result_path(out_dir, agent_id)` | `Path` to `phase_<id>.json` |
| `write_prompts` | `write_prompts(manifest, plan, out_dir, skill_dir='')` | Written paths |
| `load_result` | `load_result(path, agent_id)` | Validated result dict; raises `ValueError` |
| `load_results` | `load_results(out_dir, agent_ids, required=True)` | `{agent_id: result}`; `phase_<id>.json` wins over `<id>.json` |

### `ccr.pipeline`

| Function | Signature | Returns |
|----------|-----------|---------|
| `check_completion` | `check_completion(manifest, effort, planned, completed)` | Float completion ratio; raises `RuntimeError` below the gate |
| `synthesize` | `synthesize(manifest, results, planned, completed=None, target='', facts=None, baseline=None, timestamp=None)` | Report model |
| `render` | `render(model, fmt='markdown')` | `{"markdown": ...}`, `{"json": ...}`, or both |
| `write_outputs` | `write_outputs(model, out_path, fmt='markdown')` | Written paths |
| `load_spec` | `load_spec(path)` | Benchmark spec (list or object) |
| `evaluate` | `evaluate(model, expected_issues)` | Dict: `expected`, `matched`, `missing`, `coverage`, `precision`, `findings_total`, `findings_matched`, `rejected` |
| `run_eval` | `run_eval(manifest, fixtures_dir, expected_path)` | Tuple `(model, score)` |

### `ccr.cli` and `ccr.fileio`

| Function | Signature | Purpose |
|----------|-----------|---------|
| `main` | `main(argv=None)` | CLI entry; returns exit code |
| `build_parser` | `build_parser()` | `argparse` parser for `plan/record/synthesize/eval` |
| `write_text` | `write_text(path, text, newline='\n')` | UTF-8 write with explicit newline (3.9-compatible) |

## Tests

`tests/test_manifest.py`, `test_discovery.py`, `test_state.py`,
`test_findings.py`, `test_report.py`, `test_providers.py`,
`test_pipeline_core.py`, `test_cli.py`, `test_eval.py`, and `test_generated.py`
cover this package.

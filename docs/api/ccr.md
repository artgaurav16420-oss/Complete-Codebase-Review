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
      "tags": ["CWE-798"],
      "da_verdict": "CONFIRMED",
      "evidence": "literal assignment"
    }
  ]
}
```

`tags` are what the eval harness scores against `tests/expected_issues.json`.

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

## Tests

`tests/test_manifest.py`, `test_discovery.py`, `test_state.py`,
`test_findings.py`, `test_report.py`, `test_providers.py`,
`test_pipeline_core.py`, `test_cli.py`, `test_eval.py`, and `test_generated.py`
cover this package.

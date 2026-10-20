# ADR-005: Executable Core and Single-Source Manifest

## Status

Accepted (v2.4.0)

## Context

The pipeline was a 63KB prompt plus an installer. Every test validated the
document rather than behaviour: `test.sh` compared `expected_issues.json` with a
hardcoded copy of itself, and the "integration" suite validated a hand-written
sample report. Drift was structural — env vars lived in three files, test counts
in four, version in three plus a checksum, and the issue list in three.

## Decision

1. `ccr/pipeline.json` is the single source of truth for agents, env vars,
   enums, thresholds, tech-debt floors, and the version.
2. `tools/generate.py` renders the doc tables and `install.py.sha256` from that
   manifest. CI runs `--check` and fails on drift.
3. `ccr/` is a zero-dependency package implementing the deterministic half of
   the pipeline: discovery, agent selection, state, DA checks, dedup, roadmap,
   aggregation, Markdown/JSON rendering, and eval scoring.
4. `ccr` never calls a model. `record` writes prompts; the host executes them;
   `synthesize` ingests results. This boundary is what makes the core testable.
5. `tests/fixtures/agents/*.json` are recorded reports for `tests/dummy_repo`;
   `ccr eval` scores them against `tests/expected_issues.json`. `test.sh` and
   `Test-Windows.ps1` call the eval instead of duplicating the list.

## Consequences

- Adding an agent or env var is a one-line manifest edit plus regeneration.
- Report schema regressions fail unit tests, not a prose review.
- The eval is only as good as its fixtures; fixture coverage must be reviewed
  when `dummy_repo` changes.
- `ccr` is packaged as a console script, so the deterministic half can be used
  outside an agent runtime.
- `install.py` remains a standalone script (deliberately) and is excluded from
  the package.

## Alternatives considered

- **JSON Schema library**: rejected; runtime must stay zero-dependency.
  Structural validation lives in `ccr.manifest.validate`.
- **Generating the whole of SKILL.md**: rejected; prose sections need human
  editing. Only tables, version strings, and the checksum are generated.
- **Having `ccr` call an LLM**: rejected; it would make CI non-deterministic and
  couple the core to a provider.

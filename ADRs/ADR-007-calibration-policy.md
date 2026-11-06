# ADR-007: Report Calibration Policy

## Status

Accepted (unreleased; current release is v2.4.0)

## Context

Four decisions, five numbers, decide what a report says, and until now three of
them lived where the code that first needed them happened to sit:

| Decision | Value | Where it lived |
|---|---|---|
| Same-file findings merge into one | Jaccard similarity >= 0.6 | `ccr/findings.py:OVERLAP_THRESHOLD` |
| A finding is "expensive" for cluster detection | >= 8h | `ccr/findings.py:LARGE_FIX_HOURS` |
| Phase 1 quick wins stop accumulating | 40h | `ccr/findings.py:QUICK_WIN_CAP_HOURS` |
| A run is complete enough to report | 75% full / 66% quick | `ccr/pipeline.json:thresholds` |

These are product decisions, not implementation details: raising the overlap
threshold changes which findings a reader sees at all, and moving the quick-win
cap reorders the roadmap. ADR-005 declares `pipeline.json` the single source of
truth for manifest data, yet three of the four sat outside it, so
`tools/generate.py` could not see them and a tuning change contradicted the
documented manifest without any record of why the old value was chosen.

## Decision

The five numbers are the **calibration policy**. Their values live in
`ccr/pipeline.json`:

- `thresholds.full_completion` (0.75) and `thresholds.quick_completion` (0.66)
- `calibration.overlap_threshold` (0.6)
- `calibration.large_fix_hours` (8.0)
- `calibration.quick_win_cap_hours` (40.0)

`ccr.manifest.load()` validates the calibration block (`0 < overlap <= 1`, the
hour values finite and positive) and pushes the values into `ccr.findings`
through `set_calibration`, the boundary this change also introduces for
`security_agent_id`. `ccr.findings` keeps the literals as defaults, so a caller
that imports the module without loading the manifest still gets working numbers.

The policy itself, recorded here so a later change is argued against intent:

1. **Overlap merge.** Two findings in the same file whose failure-mode token
   sets (after stopword and negation filtering) reach a Jaccard similarity of
   0.6 are one finding. The threshold is deliberately conservative: a false
   merge hides a real finding, while a missed merge only repeats one. Negation
   sets must match, so "does not retry" never merges with "retries".
2. **Survivor selection.** The merged cluster is represented by the member that
   is promoted first (CRITICAL before HIGH; security domain before others; then
   severity weight, then larger estimate, then id). Security-first is a product
   choice: a duplicated security finding should never be represented by the
   softer wording of its duplicate.
3. **Quick-win cap.** MEDIUM/LOW findings at <= 2h fill Phase 1 until 40h is
   reached; the rest move to Phase 2. Without a cap, a codebase with heavy
   lint-style debt produces a "quick win" phase that is neither quick nor
   discriminating.
4. **Completion gates.** A full run reports at 75% of planned agents, a quick
   run at 66%. Below that the report would silently narrow its coverage, so
   `synthesize` blocks unless `--allow-partial` says the gap is intentional.

Changing any value is a policy change: edit `pipeline.json`, update the test
that pins the behaviour, and amend this ADR with the reason.

## Consequences

- Tuning no longer requires an engine edit, and the generated documentation
  tables and `tools/generate.py --check` see the same values the engine runs
  with.
- `ccr.findings` gains module state, like `SECURITY_AGENT_ID`. It is set by
  `manifest.load()`, which `ccr` runs at import, so tests that need a different
  value must restore it when they finish rather than assume the default.
- The values remain plain numbers, not configurable per run: a per-run knob
  would let two reports quote different tech debt for the same codebase.

# Organizer Benchmark (recorded real run)

This is the first benchmark built from an actual review run rather than
hand-authored findings.

- **Target**: Organizer 0.2.0 (`artgaurav16420-oss/Organizer`), run against a
  local checkout.
- **Recorded**: 2026-10-21, Quick Mode (`architecture`, `code_quality`,
  `security`); the host executed the prompts, `ccr` synthesized the report.
- **Verification**: every cited `file:line` was read by hand. 17 of 18 findings
  were valid; `F-012` (unused `dry_run` parameter) is a known false positive,
  contradicted by the comment at `fsops.py:559`.

`expected.json` lists the tags of the 17 verified findings as
`expected_issues`. The false positive's tag (`unused-parameter`) is deliberately
excluded, so `ccr eval` reports 94% precision and flags the known FP by text.

To refresh after a new run: re-record the agent JSON, re-verify each finding,
then update `expected.json`. Never edit the agent JSON to make the eval pass —
that turns the benchmark back into a tautology.

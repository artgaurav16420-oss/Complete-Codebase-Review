## Summary

Fixes the aggregation and rubric problems the httpx validation surfaced. No target-repo changes.

### Changes
- **Overlap candidates** — `aggregate` now detects same-file clusters. Near-identical failure text (Jaccard >= 0.6) is merged once and excluded from roadmap hours; expensive same-file clusters (>= 8h) are emitted as advisory candidates for DA adjudication, not auto-merged. Both appear in Markdown (`## Overlap Candidates`) and JSON (`overlap_candidates`).
- **Roadmap cap** — `place_roadmap`: HIGH is never a quick win, INFO is never eligible, quick wins are capped at 40h so Phase 1 stays discriminating.
- **Prompt contract** — scope-exclusion clause ("Focus ONLY on {domain}"), `est_hours` is the cost of the fix, `design_note` type (INFO, 0h), and CRITICAL/HIGH require a reproduction path.
- **Dimension selection** — docs/site/theme markup no longer activates the UI/UX dimension.

### Evidence (re-synthesized from the httpx cache)
- Overlap candidate: `httpx/_client.py`, 52h across F-002 + F-013 + F-021 — the triple-count is now surfaced.
- Phase 1 dropped from 73 tasks / 83.95h to 36 tasks / 40.0h.

### Verification
- 435 tests pass, 1 skip; coverage 91%; per-file floor, eval, generate check, self-verify green.

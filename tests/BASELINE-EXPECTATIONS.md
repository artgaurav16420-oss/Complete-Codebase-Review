# Baseline Expectations (RED Phase)

Known failure modes when an agent does a codebase review without this skill:

## Failure 1: Shallow Surface Scan
Agent reads file tree, maybe a few configs, declares "looks good."
**Misses:** architecture issues, tech debt patterns, dependency risks.
**Guarded by:** 13 specialist agents each with domain-specific methodology + web verification.

## Failure 2: Single-Pass Bias
Agent does one sequential pass and covers only what's visible from entry points.
**Misses:** deep nested modules, rarely-touched legacy code, background services.
**Guarded by:** ALL 13 agents must return; parallel spawn prevents sequential drift.

## Failure 3: No Structured Domains
Agent mixes architecture comments with style nits with security concerns.
**Result:** report is a brain dump, not actionable. No severity, no prioritization.
**Guarded by:** per-domain scores, severity-grouped findings, cross-agent conflict log.

## Failure 4: Inconsistent Depth
Agent dives deep into the first few files it sees, then runs out of context/time.
**Result:** some modules get thorough review, others get "looks good" — uneven.
**Guarded by:** large codebase scaling strategy (core modules + noted gaps).

## Failure 5: No Tech Debt Quantification
Agent says "there's some tech debt" but doesn't measure it.
**Result:** no basis for prioritization or sprint planning.
**Guarded by:** mandatory tech debt quantification (estimated hours per finding).

## Failure 6: No Actionable Roadmap
Report lists problems but doesn't prioritize or suggest order of fixes.
**Result:** developer doesn't know where to start.
**Guarded by:** mandatory 3-phase roadmap (now / next quarter / backlog).

## Failure 7: False Positives Waste Team Time
Report flags issues that don't exist or are misattributed.
**Result:** team chases ghosts, loses trust in the review output.
**Guarded by:** mandatory devil's advocate agent (CONFIRMED/PLAUSIBLE/QUESTIONABLE/REJECTED).

## Failure 8: Windows-Only Commands Fail Cross-Platform
Discovery commands written for one OS break on team members' machines.
**Result:** review only works on the author's OS.
**Guarded by:** OS detection + cross-platform command table.

## Failure 9: Agents Don't Use Domain Expertise
Agents review outside their expertise, miss domain-specific patterns.
**Result:** shallow findings in every domain.
**Guarded by:** mandatory skill loading per agent (accessibility, security-review, ui-ux-pro-max, etc.).

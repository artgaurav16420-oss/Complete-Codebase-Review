# ADR-002: Devil's Advocate Workflow

**Status:** Accepted  
**Date:** 2026-06-16  
**Deciders:** Project maintainers

## Context

Review findings from parallel agents may contain false positives, exaggerated severity, or claims that cannot be reproduced. Without adversarial review, the final report inherits every agent's bias.

## Decision

Phase 3 includes a Devil's Advocate (DA) step that independently re-reads code and web-verifies each finding before synthesis. DA assigns one of four verdicts:

| Verdict | Meaning |
|---------|---------|
| CONFIRMED | Finding is reproducible and accurate |
| PLAUSIBLE | Likely correct but cannot fully verify |
| QUESTIONABLE | Weak evidence — needs human review |
| REJECTED | False positive — suppressed from output |

Findings tagged DA-ESCALATION are flagged separately for explicit user attention.

## Consequences

- **Positive:** Significantly reduces false positives in final output.
- **Positive:** The 4-verdict rubric gives users clear confidence levels.
- **Negative:** Adds ~30% to Phase 3 execution time.
- **Negative:** Requires DA to have code-read access (already read-only).
- **Mitigation:** DA runs as a single Task sub-agent, not 14×.

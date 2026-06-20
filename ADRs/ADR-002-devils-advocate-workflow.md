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

## Accepted Risk — Single-Agent Coverage Gap

DA is one generalist agent re-verifying findings across all 14 domains.
This is structurally equivalent to the single-pass review the pipeline
exists to prevent (see ADR-001 and SKILL.md Anti-Rationalization table).

Accepted because:
1. **Different mandate:** DA challenges specific claims from specialist
   agents — it does not discover new domains. The 14 specialists already
   ran their analysis; DA is a verification pass, not a discovery pass.
2. **DA-ESCALATION mechanism:** If DA independently discovers a material
   issue within an active domain, it tags it `DA-ESCALATION` for explicit
   inclusion in roadmap prioritization. This catches cross-domain blind
   spots without full re-analysis.
3. **Cost proportionality:** 14× DA agents would double total Phase 2+3
   token cost while producing diminishing returns — each DA would verify
   findings from a single domain, which is already the output of the
   specialist agent for that domain.

This tradeoff is documented, not silent. If coverage gaps from single-agent
DA become a recurring concern, the fix is to cluster DA per domain-group
(e.g., Security+Dependencies, Architecture+Performance) rather than per
individual domain.

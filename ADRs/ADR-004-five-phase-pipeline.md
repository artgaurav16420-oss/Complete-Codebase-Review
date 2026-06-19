# ADR-004: Five-Phase Pipeline Structure

## Status
Accepted

## Context
The Complete Codebase Review skill needs a structured workflow for reviewing codebases. Early versions had an ad-hoc "scan → report" flow that lacked verification gates, user approval checkpoints, and independent review.

Key requirements:
- Read-only analysis to prevent accidental modifications
- User must approve fixes before they are applied
- Independent review to catch regressions from automated fixes
- Extensible — new analysis domains should be addable without restructuring

## Decision
Adopt a five-phase pipeline:

| Phase | Name | Description |
|-------|------|-------------|
| 1 | Discovery | Map codebase structure, stack, modules, env check |
| 2 | Parallel Analysis | N specialist agents analyze in parallel |
| 3 | Synthesis + Roadmap | Deduplicate, DA-verify, prioritize findings |
| 4 | Fix Plan | Generate structured tasks, user approval gate |
| 5 | Independent Review | Audit fixes, run tests, create PR |

### Key design decisions:
1. **Read-only boundary (Phases 1-3):** No code modifications during analysis. Prevents findings from being invalidated by mid-review changes.
2. **User approval gate (Phase 4c):** Tasks are presented for approval before any fix is applied. Supports selective fix application.
3. **Devil's Advocate (Phase 3b):** A dedicated agent challenges every finding to reduce false positives before they reach the roadmap.
4. **Independent reviewer (Phase 5a):** A fresh agent (not involved in Phase 4 fixes) reviews changes, preventing confirmation bias.
5. **14-agent parallel split (ADR-001):** Analysis domains are independent agents running in parallel, not sequential phases within Phase 2.

### Rejected alternatives:
- **3-phase (discover → fix → verify):** Missing user approval gate and independent review.
- **7-phase:** Added complexity without clear benefit. The DA and roadmap are sub-phases of Phase 3 rather than standalone phases.
- **Sequential agent analysis:** Would increase wall-clock time linearly with agent count; parallel is required for practical use.

## Consequences
- **Positive:** Clear separation of concerns, user control over fixes, reduced false positives via DA, regression protection via independent review.
- **Negative:** More complex orchestration than a flat script; requires tool support for parallel agent spawning; longer total review time.
- **Neutral:** Adding new analysis domains requires updating the agent table in Phase 2 but doesn't change the pipeline structure.

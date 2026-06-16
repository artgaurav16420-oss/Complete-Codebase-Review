# ADR-001: 14-Agent Parallel Split

**Status:** Accepted  
**Date:** 2026-06-16  
**Deciders:** Project maintainers

## Context

A single-pass review agent consistently misses cross-cutting issues — e.g., a security flaw hidden in a test file, or tech debt that spans build config and source code. The SKILL.md Anti-Rationalization table documents this failure mode.

## Decision

Phase 2 spawns 14 specialist agents in parallel, each covering a distinct domain:

1. Architecture Analyzer
2. Code Quality Auditor
3. Security Posture
4. Tech Debt Tracker
5. Test Health Auditor
6. Dependency Auditor
7. Documentation Auditor
8. Build & CI Auditor
9. Performance Baseline
10. Database & Schema
11. UI/UX Auditor
12. DevOps & Infra
13. Standards Compliance
14. Process Quality (Karpathy Compliance)

Each agent receives the full discovery manifest but applies its own domain lens. Findings are deduplicated and normalized in Phase 3.

## Consequences

- **Positive:** Cross-cutting issues are caught where domains intersect.
- **Positive:** Single-pass false positive rate drops (demonstrated: 9.0 → 6.7 score correction).
- **Negative:** 14× the token cost of single-pass for Phase 2.
- **Negative:** Orchestration complexity requires a `do nothing else` passive-wait pattern.
- **Mitigation:** `CODE_REVIEW_EFFORT=min` reduces to 3 agents. Agent threshold halt prevents wasted output.

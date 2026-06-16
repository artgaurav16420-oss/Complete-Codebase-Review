Karpathy Guidelines v3.7 MANDATORY: For all AI operations in this project, you MUST follow karpathy-guidelines.md as the primary behavioral ruleset.

# AGENTS.md — Complete Codebase Review

**This is a skill repo for AI coding agents.** The primary artifact is `SKILL.md` (a 720-line markdown skill definition), not a library or app. `karpathy-guidelines.md` and `install.py` are supporting files.

## Key Commands

| Command | What |
|---------|------|
| `python tests/test_compliance.py` | Main test suite — 60+ assertions across 17 test fns |
| `python tests/test_install.py` | Unit tests for install.py — 35 tests, 7 classes (unittest) |
| `./test.sh` | Bash integration tests (**Unix only** — skipped on Windows in CI) |
| `make test` | Runs test_compliance.py then test.sh |
| `python install.py` | Install skill to detected AI agent dirs |
| `python install.py --target DIR` | Install to custom dir |
| `python install.py --dry-run` | Preview install without copying |

## Architecture

4-phase review pipeline (all in `SKILL.md`):

```
Phase 1: Discovery      → map codebase, env check, health dimensions, manifest
Phase 2: Parallel       → 14 specialist agents spawned as Task sub-agents
Phase 3: Synthesis+DA   → dedup, normalize, Devil's Advocate challenges every finding
Phase 4: Fix Plan       → user-approved fix tasks + post-fix verification
```

14 specialist agents: Architecture, Code Quality, Security, Tech Debt, Test Health, Dependencies, Documentation, Build & CI, Performance, Database, UI/UX, DevOps, Standards, Process Quality (Karpathy).

**Read-only** (Phases 1-3). Phase 4 waits for explicit user approval.

## Config via Env Vars

| Var | Default | Note |
|-----|---------|------|
| `CODE_REVIEW_EFFORT` | `max` | `min` = Quick Mode (3 agents, 120s timeout) |
| `CODE_REVIEW_TIMEOUT_SEC` | `900` | Per-agent timeout |
| `CODE_REVIEW_AGENTS` | all 14 | Comma-separated subset |
| `CODE_REVIEW_MAX_FILES` | unlimited | Cap for large repos |
| `CODE_REVIEW_FILTER` | `all` | `critical-high` = omit MEDIUM/LOW from itemized lists |
| `CODE_REVIEW_CACHE_DIR` | `.code-review-cache` | Cache dir (falls back to OS temp) |

## CI

Matrix: 3 OS × 5 Python versions (3.9-3.13). Bash tests skipped on Windows. PowerShell test suite **deprecated** — all checks in Python now.

## Gotchas

- **SKILL_DIR injection**: Orchestrator resolves absolute path to skill dir and injects into sub-agent prompts. Never resolve via `realpath SKILL.md` — wrong CWD.
- **PowerShell compliance tests** (`tests/run-compliance-tests.ps1`) are deprecated — do not update.
- **`CODE_REVIEW_EFFORT=min`** reduces agents to 3 (Security, Code Quality, Architecture), timeout to 120s, sample ~10%.
- **Agent failure threshold**: <75% agents complete in full mode → halt. <66% in Quick Mode → halt. LOW-ACTIVITY domains excluded from denominator.
- **Cross-platform**: SKILL.md has command tables for Windows (`Get-ChildItem`) and Unix (`find`).
- **Phased roadmap**: Phase 1 = now (critical + quick wins), Phase 2 = next quarter, Phase 3 = backlog.
- **DA verdicts**: CONFIRMED / PLAUSIBLE / QUESTIONABLE / REJECTED. DA-ESCALATION findings tagged separately.
- **Post-fix verification** (Phase 4g): lint → typecheck → test affected area. No auto-retry on failure.
- **Tech debt floor estimates**: Calibration table in SKILL.md (e.g., circular dep = 8h, hardcoded secret = 2h).
- **.gitignore**: excludes `.skills/`, `.code-review-cache/`, `__pycache__/`.
- **.gitattributes**: `* text=auto eol=lf`.
- **PRs**: Conventional Commits encouraged. Checklist includes `make test` passing.
- **Config env var `CODE_REVIEW_BASELINE`**: Points to `ccr-baseline.json` by default for trend tracking across sessions.

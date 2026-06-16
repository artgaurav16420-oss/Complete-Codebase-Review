Karpathy Guidelines v3.7 MANDATORY: For all AI operations in this project, you MUST follow karpathy-guidelines.md as the primary behavioral ruleset.

# AGENTS.md — Complete Codebase Review

**Skill repo for AI coding agents.** Primary artifact is `SKILL.md` (562-line skill definition), not a library or app. `karpathy-guidelines.md` and `install.py` are supporting files. `help.md` and `SECURITY.md` are documentation — rarely needed.

## Key Commands

| Command | What |
|---------|------|
| `python tests/test_compliance.py` | Main test suite — 60+ assertions, 17 fns, plain Python (no pytest) |
| `python tests/test_install.py` | Unit tests for install.py — 35 tests, 7 classes (unittest) |
| `./test.sh` | Bash integration tests (**Unix only** — skipped on Windows in CI). Creates/destroys `tests/dummy_repo/` |
| `make test` | Runs test_compliance.py then test.sh |
| `make test-py` | Python compliance tests only |
| `make clean` | Unix: Remove `.code-review-cache/`, `__pycache__/`, `*.pyc` |
| `make clean-windows` | Windows equivalent of clean |
| `python install.py --help` | Installer CLI help |
| `python install.py` | Install skill to detected AI agent dirs |
| `python install.py --target DIR` | Install to custom dir |
| `python install.py --dry-run` | Preview install without copying |

**No Python dependencies.** Zero `requirements.txt` or `pip install` needed. All tests use stdlib only.

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
| `CODE_REVIEW_BASELINE` | `ccr-baseline.json` | Baseline snapshot for trend tracking |
| `CODE_REVIEW_STATUS_INTERVAL` | `300` | Min secs between event-driven status logs |

## CI

Matrix: 3 OS × 5 Python versions (3.9-3.13). Bash tests skipped on Windows.

## Gotchas

- **SKILL_DIR injection**: Orchestrator resolves absolute path to skill dir and injects into sub-agent prompts. Never resolve via `realpath SKILL.md` — wrong CWD.
- **PowerShell test suites removed** — all compliance checks migrated to Python.
- **`CODE_REVIEW_EFFORT=min`** reduces agents to 3 (Security, Code Quality, Architecture), timeout to 120s, sample ~10%.
- **Agent failure threshold**: <75% agents complete in full mode → halt. <66% in Quick Mode → halt. LOW-ACTIVITY domains excluded from denominator.
- **Cross-platform**: SKILL.md has command tables for Windows (`Get-ChildItem`) and Unix (`find`).
- **Phased roadmap**: Phase 1 = now (critical + quick wins), Phase 2 = next quarter, Phase 3 = backlog.
- **DA verdicts**: CONFIRMED / PLAUSIBLE / QUESTIONABLE / REJECTED. DA-ESCALATION findings tagged separately.
- **Post-fix verification** (Phase 4g): lint → typecheck → test affected area. No auto-retry on failure.
- **Tech debt floor estimates**: Calibration table in SKILL.md (e.g., circular dep = 8h, hardcoded secret = 2h).
- **.gitignore**: excludes `.skills`, `.code-review-cache/`, `__pycache__/`, `*.pyc`, `.DS_Store`, `*.egg-info/`.
- **.gitattributes**: `* text=auto eol=lf`.
- **PRs**: Conventional Commits encouraged. Checklist includes `make test` passing. Template at `.github/PULL_REQUEST_TEMPLATE.md`.
- **`test.sh` mock evaluation**: driven by `tests/expected_issues.json` (currently 3 issues: CWE-798, CWE-78, unused-import).
- **GitHub badges** in `README.md` point to `artgaurav16420-oss/Complete-Codebase-Review` — the upstream fork.

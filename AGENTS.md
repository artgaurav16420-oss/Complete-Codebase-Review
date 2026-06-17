Karpathy Guidelines v3.7 MANDATORY. Follow `karpathy-guidelines.md` as primary behavioral ruleset.

# AGENTS.md — Complete Codebase Review

**Skill repo.** `SKILL.md` (multi-phase skill). Not a library/app. Tests: `tests/`. Docs: `help.md`, `SECURITY.md`. Architecture references: `ADRs/` (3 docs). Zero deps, stdlib only, Python >= 3.9.

## Commands

| Command | What |
|---------|------|
| `python tests/test_compliance.py` | 130+ SKILL.md compliance assertions (custom DSL, not pytest) |
| `python tests/test_install.py` | install.py unit tests (unittest, 7 classes) |
| `python tests/test_pipeline.py` | Review output schema validation (REQUIRED_SECTIONS, VALID_DA_VERDICTS, etc.) |
| `python tests/test_env_config.py` | Env-var config table completeness checks |
| `python tests/test_smoke.py` | install.py subprocess smoke tests |
| `python -m unittest discover -s tests -p "test_*.py" -v` | All unittest suites |
| `./test.sh` | Bash integration tests (**Unix only** — uses `mktemp -d`, skipped on Windows CI) |
| `make test` | test_compliance.py + test.sh |
| `make test-py` | test_compliance.py only |
| `make test-bash` | test.sh only |
| `make test-windows` | Test on Windows (skips bash suite) |
| `make clean` / `make clean-windows` | Remove `.code-review-cache/`, `__pycache__/`, `*.pyc` |
| `python install.py [--help \| --target DIR \| --dry-run \| --version]` | Installer CLI |

## Key Architecture

5-phase pipeline defined in `SKILL.md`:
```
Phase 1: Discovery    → map codebase, env check, health dimensions, manifest
Phase 2: Parallel     → 14 specialist agents (Task sub-agents)
Phase 3: Synthesis+DA → dedup, normalize, Devil's Advocate (CONFIRMED/PLAUSIBLE/QUESTIONABLE/REJECTED)
Phase 4: Fix Plan     → user-approved tasks → apply fixes → verify (lint → typecheck → test)
Phase 5: Review+Test   → independent review → user-approved corrections → full suite
```

Read-only (Phases 1-3). Phase 4 and Phase 5 corrections wait for explicit user approval (by task ID or "all"). No auto-retry on post-fix verification.

Key env vars: `CODE_REVIEW_EFFORT` (max/min), `CODE_REVIEW_AGENTS`, `CODE_REVIEW_TIMEOUT_SEC`, `CODE_REVIEW_FILTER`, `CODE_REVIEW_MAX_FILES`, `CODE_REVIEW_CACHE_DIR`, `CODE_REVIEW_BASELINE`, `CODE_REVIEW_STATUS_INTERVAL`.

## CI

`.github/workflows/ci.yml`: 3 OS (ubuntu, windows, macos) × 5 Python (3.9-3.13). Steps: compliance.py → `coverage run -m unittest discover` → coverage report → test.sh (non-Windows only). Only dep: `coverage`.

## Gotchas

- **SKILL_DIR injection**: Orchestrator injects absolute path of skill dir into sub-agent prompts. Never resolve via `realpath SKILL.md` from target CWD.
- **`CODE_REVIEW_EFFORT=min`**: 3 agents (Security, Code Quality, Architecture), 120s timeout, ~10% sample.
- **Agent failure threshold**: <75% agents complete (full mode) or <66% (Quick Mode) → halt. LOW-ACTIVITY domains excluded from denominator.
- **DA verdicts**: REJECTED findings excluded from roadmap (enforced by test_pipeline.py).
- **Tech debt floor estimates**: Table in SKILL.md (circular dep = 8h, hardcoded secret = 2h, missing coverage = 4h, etc.). Documented multipliers allowed (2×, 0.5×).
- **Cross-platform**: SKILL.md has separate command tables for Windows (`Get-ChildItem`) and Unix (`find`).
- **`install.py` version**: Read from `pyproject.toml` via `_read_version()` — raises if file missing. Sync enforced by compliance test.
- **`CHANGELOG.md`**: Extracted from SKILL.md. SKILL.md no longer carries version history; avoid hardcoded SKILL.md line-count claims because they drift.
- **`test.sh` mock evaluation**: Hardcoded mock output matching `tests/expected_issues.json` (3 issues: CWE-798, CWE-78, unused-import). Brittle — adding an issue requires updating both.
- **.gitignore**: Excludes `.skills`, `.code-review-cache/`, `__pycache__/`, `*.pyc`, `.DS_Store`, `*.egg-info/`, `.env`, `.secret`, `.credentials`, `ccr-baseline.json`.
- **.gitattributes**: `* text=auto eol=lf`.
- **PRs**: Conventional Commits. Checklist: `make test` passing. Template at `.github/PULL_REQUEST_TEMPLATE.md`.
- **Badges** in `README.md` point to `artgaurav16420-oss/Complete-Codebase-Review` fork.
- **Phased roadmap** in SKILL.md: Phase 1 = now (critical + quick wins), Phase 2 = next quarter, Phase 3 = backlog.

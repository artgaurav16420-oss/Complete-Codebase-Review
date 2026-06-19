Karpathy Guidelines v3.7 MANDATORY: For all AI operations in this project, you MUST follow karpathy-guidelines.md as the primary behavioral ruleset.

# AGENTS.md — Complete Codebase Review

**Skill repo.** `SKILL.md` (5-phase skill). Not a library/app. Not on PyPI. Tests: `tests/`. Zero deps, stdlib only, Python >= 3.9.

## Commands

| Command | What |
|---------|------|
| `python tests/test_compliance.py` | 130+ SKILL.md compliance assertions (`make_checker()` DSL, not pytest) |
| `python tests/test_install.py` | install.py unit tests (unittest, 11 classes — 2 base, 9 concrete) |
| `python tests/test_pipeline.py` | Review output schema validation (REJECTED excluded from roadmap) |
| `python tests/test_env_config.py` | Env-var config table completeness checks |
| `python tests/test_smoke.py` | install.py subprocess smoke tests (18 tests) |
| `python -m unittest discover -s tests -p "test_*.py" -v` | All unittest suites |
| `./test.sh` | Bash integration tests (**Unix only** — requires `mktemp -d`) |
| `make test` | test_compliance.py + test.sh |
| `make test-py` | test_compliance.py only |
| `make test-bash` | test.sh only |
| `make test-windows` | **Windows devs**: test-py + `tests/Test-Windows.ps1` (skips bash suite) |
| `make clean` / `make clean-windows` | Remove `.code-review-cache/`, `__pycache__/`, `*.pyc` |
| `python install.py [--help \| --target DIR \| --dry-run \| --version]` | Installer CLI (`--dry-run` safe first step) |
| `review [commit\|branch\|pr]` | Code review of changes — severity-graded, approve/block decision. Defaults to uncommitted. Used in Phase 5e |
| `gh pr create` | Create PR from Phase 4+5 fix commits. Used in Phase 5d |

## Architecture

5-phase pipeline in `SKILL.md`:
```
Phase 1: Discovery      → map codebase, env check, health dimensions, manifest
Phase 2: Parallel       → 14 specialist agents (Task sub-agents)
Phase 3: Synthesis+DA   → dedup, normalize, Devil's Advocate (CONFIRMED/PLAUSIBLE/QUESTIONABLE/REJECTED)
Phase 4: Fix Plan       → user-approved tasks → apply fixes → verify (lint → typecheck → test)
Phase 5: Independent    → reviewer audits fixes → corrections → test suite → PR → review → fix comments → re-test → report
```

Read-only (Phases 1-3). Phase 4/5 wait for explicit user approval (by task ID or "all"). No auto-retry on post-fix verification.

Env vars: `CODE_REVIEW_EFFORT` (max/min), `CODE_REVIEW_AGENTS`, `CODE_REVIEW_TIMEOUT_SEC`, `CODE_REVIEW_FILTER` (all/critical-high), `CODE_REVIEW_MAX_FILES`, `CODE_REVIEW_CACHE_DIR`, `CODE_REVIEW_BASELINE`, `CODE_REVIEW_STATUS_INTERVAL`.

## CI

`.github/workflows/ci.yml`: 3 OS (ubuntu, windows, macos) × 5 Python (3.9-3.13). Steps: syntax check → compliance.py → `coverage run -m unittest discover` → coverage report → test.sh (non-Windows only). Only dep: `coverage`. Coverage threshold 85% (`.coveragerc`).

## Key Files / Directories

| Path | Notes |
|------|-------|
| `SKILL.md` | Main skill definition — 5-phase pipeline. Source of truth for phases, env vars, tech debt table |
| `install.py` | User-facing installer CLI. Version read from `pyproject.toml` via `_read_version()` |
| `karpathy-guidelines.md` | Behavioral ruleset (398 lines). Injected into sub-agents via SKILL_DIR |
| `help.md` | Companion doc: env var reference, quick mode, exit codes, usage examples |
| `ADRs/` | Architecture Decision Records (3: 14-agent split, DA workflow, plain-Python test framework) |
| `tests/BASELINE-EXPECTATIONS.md` | Describes expected mock review output for test.sh |
| `tests/expected_issues.json` | Mock output (4 issues: CWE-798, CWE-78, CWE-200, unused-import). Brittle — adding issues requires syncing both |
| `tests/Test-Windows.ps1` | Windows counterpart of test.sh — compliance + unittest + mock checks |
| `.skills-index.json` | Skills index for agent-discovery systems. Regenerate via `skill-matcher.js --index` |
| `.gitmessage` | Commit message template (Conventional Commits) |
| `skills/review/SKILL.md` | Portable code review skill. Loaded in Phase 5e to post severity-graded review on PR |

## Gotchas

- **SKILL_DIR injection**: Orchestrator injects absolute path of skill dir into sub-agent prompts. Never resolve `karpathy-guidelines.md` via `realpath` from target CWD.
- **`CODE_REVIEW_EFFORT=min`**: 3 agents (Security, Code Quality, Architecture), 120s timeout, ~10% sample.
- **Agent failure threshold**: <75% agents complete (full mode) or <66% (Quick Mode) → halt. LOW-ACTIVITY domains excluded from denominator.
- **DA verdicts**: REJECTED findings excluded from roadmap (enforced by test_pipeline.py).
- **Tech debt floor estimates**: Table in SKILL.md (circular dep = 8h, hardcoded secret = 2h, missing coverage = 4h, etc.). Documented multipliers allowed (2×, 0.5×).
- **Cross-platform**: SKILL.md has separate command tables for Windows (`Get-ChildItem`) and Unix (`find`).
- **`install.py` version**: Read from `pyproject.toml` via `_read_version()` — raises if file missing. Sync enforced by compliance test.
- **`CHANGELOG.md`**: Extracted from SKILL.md. SKILL.md no longer carries version history (v2.1.0 added Phase 5). Avoid hardcoded line-count claims — they drift.
- **`test.sh` mock evaluation**: Hardcoded mock output matching `tests/expected_issues.json` (4 issues). Adding an issue requires updating both.
- **Contribution conventions**: See `CONTRIBUTING.md`. Zero-dependency rule (stdlib only), no type hints, no expression f-strings, 100-char line limit. Conventional Commits enforced.
- **.gitignore**: Excludes `.skills`, `.code-review-cache/`, `__pycache__/`, `*.pyc`, `.DS_Store`, `*.egg-info/`, `.env`, `.secret`, `.credentials`, `ccr-baseline.json`.
- **.gitattributes**: `* text=auto eol=lf`.
- **PRs**: Conventional Commits. Checklist: `make test` passing.
- **Phase 5d-5f requires `gh` CLI**: PR creation, review posting, and comment fetching depend on `gh` CLI authenticated with push access. If `gh` is unavailable or remote is not GitHub, Phase 5d-5f skip gracefully and 5h reports the gap.
- **`skills/review/SKILL.md`**: Loaded in Phase 5e from `$SKILL_DIR/skills/review/` — not from a system-installed `/review` command. This keeps it platform-independent.
- **Badges** in `README.md` point to `artgaurav16420-oss/Complete-Codebase-Review` fork.
- **Phased roadmap** in SKILL.md: Phase 1 = now (critical + quick wins), Phase 2 = next quarter, Phase 3 = backlog.

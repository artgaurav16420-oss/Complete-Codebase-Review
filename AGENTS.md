Karpathy Guidelines v3.7 MANDATORY: For all AI operations in this project, you MUST follow karpathy-guidelines.md as the primary behavioral ruleset.

# AGENTS.md — Complete Codebase Review

**Skill repo.** `SKILL.md` (5-phase pipeline). Not a library/app. Not on PyPI. Zero deps, stdlib only, Python >= 3.9.

## Commands

| Command | What |
|---------|------|
| `make test` | Compliance + bash integration (Unix) |
| `make test-py` | `python tests/test_compliance.py` only |
| `make test-windows` | Windows: test-py + `tests/Test-Windows.ps1` |
| `python tests/test_compliance.py` | 139 assertions, 63 test methods |
| `python -m unittest discover -s tests -p "test_*.py" -v` | All 5 unittest suites |
| `python tests/test_install.py` | install.py unit tests (10 classes) |
| `python tests/test_pipeline.py` | Review output schema validation |
| `python tests/test_smoke.py` | install.py subprocess smoke tests (18 tests) |
| `python tests/test_env_config.py` | Env-var config table completeness |
| `python install.py [--help \| --target DIR \| --dry-run \| --version]` | Installer CLI. Use `--dry-run` first |
| `review [commit\|branch\|pr]` | Phase 5e — severity-graded review of changes |
| `gh pr create` | Phase 5d — PR from fix commits |

## Architecture

5-phase pipeline defined in `SKILL.md`:
```text
Phase 1: Discovery      → map codebase, env check, health dimensions
Phase 2: Parallel       → 14 specialist agents (Task sub-agents)
Phase 3: Synthesis+DA   → dedup, normalize, Devil's Advocate
Phase 4: Fix Plan       → user-approved tasks → apply fixes → verify
Phase 5: Independent    → reviewer audits → corrections → test → PR → re-test → report
```
Read-only (Phases 1-3). Phase 4/5 wait for explicit user approval (by task ID or "all"). No auto-retry on post-fix verification.

Env vars: `CODE_REVIEW_EFFORT` (max/min), `CODE_REVIEW_AGENTS`, `CODE_REVIEW_TIMEOUT_SEC` (default 900), `CODE_REVIEW_FILTER` (all/critical-high), `CODE_REVIEW_MAX_FILES`, `CODE_REVIEW_CACHE_DIR`, `CODE_REVIEW_BASELINE`, `CODE_REVIEW_STATUS_INTERVAL`.

## CI

`.github/workflows/ci.yml`: 3 OS × 5 Python (3.9-3.13). Syntax check → compliance → `coverage run -m unittest discover` → coverage report (≥85%) → test.sh (non-Windows) / Test-Windows.ps1 (Windows). Only dep: `coverage`.

## Code Conventions (from CONTRIBUTING.md)

- **Zero deps** — stdlib only. No `requirements.txt`, no `pip install`.
- **No type hints** — targets 3.9+ but zero-dep means no external typing deps (stdlib `typing` is fine).
- **100-char line limit**, no complex f-string expressions.
- **Conventional Commits** (`.gitmessage` template): `feat|fix|test|docs|refactor|ci|chore`.
- New tests use `unittest.TestCase`.
- No expression f-strings.

## Key Files / Directories

| Path | Notes |
|------|-------|
| `SKILL.md` | Source of truth for phases, env vars, and the tech debt table |
| `install.py` | User-facing installer. Version from `pyproject.toml` via `_read_version()` — raises if missing |
| `karpathy-guidelines.md` | Behavioral ruleset. Injected into sub-agents via SKILL_DIR |
| `help.md` | Env var reference, quick mode, exit codes, usage |
| `ADRs/` | 4 Architecture Decision Records |
| `skills/review/SKILL.md` | Portable review skill for Phase 5e — loaded from `$SKILL_DIR/skills/review/`, not system `/review` |
| `tests/BASELINE-EXPECTATIONS.md` | Expected mock review output (used by test.sh) |
| `tests/expected_issues.json` | Mock output (4 issues: CWE-798, CWE-78, CWE-200, unused-import). Brittle — adding issues requires syncing both |
| `.coveragerc` | Coverage threshold 85%. Omit `.skills/`, `.code-review-cache/`, `__pycache__/`, `ADRs/`, `tests/` |

## Gotchas

- **SKILL_DIR injection**: Orchestrator injects absolute skill dir path into sub-agent prompts. Never resolve `karpathy-guidelines.md` via `realpath` from target CWD.
- **`CODE_REVIEW_EFFORT=min`**: 3 agents (Security, Code Quality, Architecture), 120s timeout, ~10% sample.
- **Agent failure threshold**: <75% agents complete (full) or <66% (Quick Mode) → halt. LOW-ACTIVITY domains excluded from denominator.
- **DA verdicts**: REJECTED findings excluded from roadmap (enforced by test_pipeline.py).
- **Tech debt floor estimates**: Table in SKILL.md (circular dep = 8h, hardcoded secret = 2h, missing coverage = 4h, etc.). 2×/0.5× multipliers allowed.
- **Cross-platform**: SKILL.md has separate command tables for Windows (`Get-ChildItem`) and Unix (`find`).
- **`CHANGELOG.md`** is extracted from SKILL.md (v2.1.0 added Phase 5). Avoid hardcoded line-count claims.
- **`test.sh` mock evaluation**: Hardcoded mock output matching `tests/expected_issues.json` (4 issues). Adding an issue requires updating both.
- **Phase 5d-5g requires `gh` CLI**: PR creation, review loop, and comment
  posting depend on `gh` authenticated with push access. If `gh` unavailable or
  remote not GitHub, steps skip gracefully (reported in 5g).
- **PRs**: Conventional Commits. Checklist: `make test` passing.

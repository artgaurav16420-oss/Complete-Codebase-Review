Karpathy Guidelines v3.7 MANDATORY: For all AI operations in this project, you MUST follow karpathy-guidelines.md as the primary behavioral ruleset.

# AGENTS.md — Complete Codebase Review

**Skill repo** (`SKILL.md` defines a 5-phase pipeline). Zero deps, stdlib only, Python >= 3.9. Not a library/app. Not on PyPI.

## Key Commands

| Command | Purpose |
|---------|---------|
| `make test` | Compliance + bash integration (Unix) |
| `make test-py` / `make test-windows` | Compliance-only on Windows |
| `python tests/test_compliance.py` | 139 assertions, 63 tests (SKILL.md compliance) |
| `python -m unittest discover -s tests -p "test_*.py" -v` | All 5 suites (157 tests) |
| `python install.py --dry-run` | Always dry-run first before installing |
| `review [hash\|branch\|pr]` | Phase 5e — review skill (internal, not user-facing) |

## Architecture

```text
Phase 1: Discovery      → map codebase, env check, health dimensions
Phase 2: Parallel       → 14 specialist agents (Task sub-agents)
Phase 3: Synthesis+DA   → dedup, normalize, Devil's Advocate
Phase 4: Fix Plan       → user-approved tasks → apply fixes → verify
Phase 5: Independent    → reviewer audits → corrections → test → PR → [review → autofix → re-review] → re-test → report
```
Read-only (Phases 1-3). Phase 4/5 wait for explicit user approval (by task ID or "all"). No auto-retry on post-fix verification.

## Env Vars

| Variable | Default | Notes |
|----------|---------|-------|
| `CODE_REVIEW_EFFORT` | `max` | `min` = Quick Mode (3 agents, 120s) |
| `CODE_REVIEW_TIMEOUT_SEC` | `900` | Per-agent timeout |
| `CODE_REVIEW_CACHE_DIR` | `.code-review-cache` | Checkpoint/cache directory |
| `CODE_REVIEW_BASELINE` | `ccr-baseline.json` | Trend-tracking snapshot |
| `CODE_REVIEW_FILTER` | `all` | `critical-high` to filter output |
| `CODE_REVIEW_AGENTS` | all 14 | Comma-separated subset |
| `CODE_REVIEW_MAX_FILES` | unlimited | Cap file scan count |
| `CODE_REVIEW_STATUS_INTERVAL` | `300` | Status log throttle (seconds) |
| `REVIEW_MAX_ITERATIONS` | `3` | Phase 5 review-fix loop cap |

**Source of truth:** `SKILL.md` lines 17-27. This table may drift.

## CI

`.github/workflows/ci.yml`: 3 OS × 5 Python (3.9-3.13). Only CI dep is `coverage`. Steps: syntax check (py_compile) → `coverage run -m unittest discover` → coverage report (≥85%) → test.sh (non-Windows) / Test-Windows.ps1 (Windows).

## Code Conventions

- **Zero deps** — stdlib only. No `requirements.txt`, no `pip install`.
- **No type hints** — targets 3.9+ but zero-dep means no external typing deps.
- **100-char line limit**, no complex f-string expressions.
- **Conventional Commits**: `feat|fix|test|docs|refactor|ci|chore`.
- New tests use `unittest.TestCase`.
- `.coveragerc` omits `.skills/`, `.code-review-cache/`, `__pycache__/`, `ADRs/`, `tests/`.

## Gotchas (agents commonly miss these)

- **SKILL_DIR injection**: Orchestrator injects absolute skill dir path into sub-agent prompts. Never resolve `karpathy-guidelines.md` via `realpath` from target CWD.
- **Phase 5d-5g requires `gh` CLI**: PR creation, review loop, and comment posting depend on `gh` authenticated with push access. If unavailable, steps skip gracefully (reported in 5g).
- **`CHANGELOG.md`** version must stay in sync with `pyproject.toml` and SKILL.md frontmatter (`test_version_sources_stay_in_sync` enforces this).
- **`test.sh` mock**: Hardcoded to match `tests/expected_issues.json` (4 issues). Adding an issue requires syncing both.
- **Compliance tests are brittle**: `test_compliance.py` has hardcoded env-var names and descriptions. Adding/renaming vars requires updating the test.
- **DA verdicts**: REJECTED findings excluded from roadmap (enforced by `test_pipeline.py`).
- **Agent failure threshold**: <75% agents complete (full) or <66% (Quick Mode) → halt.
- **Cross-platform**: SKILL.md has separate command tables for Windows (`Get-ChildItem`) and Unix (`find`).
- **Tech debt floor estimates**: Circular dep = 8h, hardcoded secret = 2h, missing coverage = 4h, etc. 2×/0.5× multipliers allowed.
- **`install.py` version**: Reads from `pyproject.toml` via `_read_version()` — raises `RuntimeError` if missing.
- **`install.py --dry-run`** before any actual install. The `--dry-run` flag previews paths without copying.
- **`test.sh` is Unix-only; `Test-Windows.ps1` is Windows-only**. CI matrix uses `if: runner.os != 'Windows'` / `== 'Windows'`. Don't run `test.sh` on Windows.
- **`skills/review/SKILL.md`** is a separate internal skill loaded in Phase 5e from SKILL_DIR. Not part of the main pipeline, but must be kept in sync.

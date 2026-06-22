Karpathy Guidelines v3.7 MANDATORY: For all AI operations in this project, you MUST follow karpathy-guidelines.md as the primary behavioral ruleset.

# AGENTS.md — Complete Codebase Review

**Skill repo** (`SKILL.md` defines a 5-phase pipeline). Zero deps, stdlib only, Python >= 3.9. Not a library/app. Not on PyPI.

## Key Commands

| Command | Purpose |
|---------|---------|
| `make test` | Compliance + bash integration (Unix) |
| `make test-py` / `make test-windows` | Compliance-only on Windows |
| `python -m unittest discover -s tests -p "test_*.py"` | All 6 suites (169 tests) |
| `python tests/test_compliance.py` | 62 tests (SKILL.md compliance) |
| `python install.py --dry-run` | Always dry-run first before installing |
| `review [hash\|branch\|pr]` | Internal review skill (`skills/review/SKILL.md`), loaded in Phase 5a/5c. Also invocable as `/review` when installed. |
| `python -m coverage run --source=. -m unittest discover -s tests -p "test_*.py" && python -m coverage report` | Full coverage run (threshold ≥85%) |

## Architecture

```text
Phase 1: Discovery      → map codebase, env check, health dimensions
Phase 2: Parallel       → 14 specialist agents (Task sub-agents)
Phase 3: Synthesis+DA   → dedup, normalize, Devil's Advocate
Phase 4: Fix Plan       → user-approved tasks → apply fixes → verify
Phase 5: Independent    → reviewer audits → corrections → test → PR → review loop → re-test → report
```
Read-only (Phases 1-3). Phase 4/5 wait for explicit user approval (by task ID or "all"). No auto-retry on post-fix verification.

## CI

`.github/workflows/ci.yml`: 3 OS × 5 Python (3.9-3.13). Only CI dep is `coverage`. Steps: syntax check (py_compile) → `coverage run -m unittest discover` → coverage report (≥85%) → `./test.sh` (non-Windows) / `tests/Test-Windows.ps1` (Windows).

## Code Conventions

- **Zero deps** — stdlib only. No `requirements.txt`, no `pip install`.
- **No type hints** — targets 3.9+ but zero-dep means no external typing deps.
- **100-char line limit**, no complex f-string expressions.
- **Conventional Commits**: `feat|fix|test|docs|refactor|ci|chore`.
- New tests use `unittest.TestCase`.
- `.coveragerc` omits `.skills/`, `.code-review-cache/`, `__pycache__/`, `ADRs/`, `tests/`; threshold ≥85%.

## Gotchas (agents commonly miss these)

- **SKILL_DIR injection**: Orchestrator injects absolute skill dir path into sub-agent prompts. Never resolve `karpathy-guidelines.md` via `realpath` from target CWD.
- **Phase 5d-5g requires `gh` CLI**: PR creation, review loop, and comment posting depend on `gh` authenticated with push access. If unavailable, steps skip gracefully (reported in 5g).
- **Phase 5a/5c review is done by the orchestrator itself** — load `skills/review/SKILL.md` and execute its phases (Gather → Checklist → Grade → Emit JSON). Do not rely on external review bots. The `--json` flag in the review skill is a behavioral instruction to emit findings as structured JSON, not a script argument.
- **`gh pr review --approve` fails on your own PR** — use `gh pr comment --body-file` or `gh api repos/:owner/:repo/issues/:number/comments` for self-review.
- **Coverage must run from repo root**: `.coverage` file lives there. Running `coverage run` from another directory produces "No data to report".
- **Windows Python PATH race**: Windows Store Python stub (`WindowsApps\python.exe`) resolves before Anaconda/system Python. If `python --version` shows unexpected version, `Get-Command python.exe` reveals which one wins.
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
- **`skills/review/SKILL.md`** is a separate internal skill loaded by the orchestrator in Phase 5a (from SKILL_DIR). Not part of the main pipeline, but must be kept in sync.

## Key References

- Pipeline spec + env var docs: `SKILL.md`
- Internal review skill: `skills/review/SKILL.md`
- Quick reference + troubleshooting + CI examples: `help.md`
- install.py API docs: `docs/api/install.md`
- CI config: `.github/workflows/ci.yml`
- Design decisions: `ADRs/` (4 records: agent split, DA workflow, plain-Python tests, 5-phase pipeline)
- Test suites: `tests/test_*.py`
- Orchestrator execution rules: `orchestrator-rules.md`

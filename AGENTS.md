Karpathy Guidelines v3.7 MANDATORY: For all AI operations in this project, you MUST follow karpathy-guidelines.md as the primary behavioral ruleset.

# AGENTS.md — Complete Codebase Review

**Two halves.** `SKILL.md` is the prompt pipeline the host agent executes.
`ccr/` is the executable core: discovery, state, DA checks, aggregation,
report rendering, eval. `install.py` installs the skill; `tools/generate.py`
keeps generated docs in sync. Zero runtime deps, stdlib only, Python >= 3.9.

## Commands (verified)

| Command | Purpose |
|---------|---------|
| `python -m unittest discover -s tests -p "test_*.py"` | Full suite (prints its own count, <2s). Run after **any** change. |
| `python tests/test_compliance.py` | SKILL.md compliance only |
| `python tests/test_review_compliance.py` | `skills/review/SKILL.md` compliance only |
| `python -m ccr eval` | Score fixtures; defaults to the synthetic dummy_repo set. Organizer benchmark: `--fixtures tests/fixtures/organizer/agents --expected tests/fixtures/organizer/expected.json` |
| `python -m ccr plan .` | Discovery facts + selected agents (`--json`, `--effort min`) |
| `python tools/generate.py` / `--check` | Rewrite / verify generated docs and checksum |
| `make test` / `make test-py` / `make test-bash` | Unix wrappers |
| `make test-windows` | Windows: `tests/Test-Windows.ps1` |
| `make lint` | **Only** `py_compile` syntax check — there is no linter/formatter |
| `python -m coverage run --source=. -m unittest discover -s tests -p "test_*.py" && python -m coverage report` | From **repo root**; threshold 85% |
| `python install.py --dry-run` / `--self-verify` / `--uninstall` | Preview / verify / remove |

Never run a subset to "save time": the whole suite is seconds.

## Architecture

```text
SKILL.md          5-phase prompt pipeline (the product for agents)
ccr/              executable core
  pipeline.json   single source of truth: agents, env vars, enums, version
  discovery.py    deterministic scan + agent selection
  state.py        atomic ccr-state.json, phase gates, resume drift
  findings.py     normalization, mechanical DA rejection, dedup, roadmap
  report.py       Markdown + JSON renderers (validated by tests/test_pipeline.py)
  providers.py    prompt generation, result ingestion, fixture replay
  pipeline.py     completion gates, synthesis, eval scoring
  cli.py          plan | record | synthesize | eval
tools/generate.py regenerates doc tables + install.py.sha256 from pipeline.json
install.py        installer (the only legacy standalone script)
```

`record` writes one prompt per agent; the host executes them; `synthesize`
ingests the JSON. `ccr` never calls a model — that is why it is testable.

## Editing rules

- **Never hand-edit generated blocks** in `SKILL.md`, `README.md`, `help.md`,
  `orchestrator-rules.md`, `pyproject.toml`'s version, or `install.py.sha256`.
  Edit `ccr/pipeline.json`, run `python tools/generate.py`, commit all files.
  CI runs `--check` and fails on drift.
- **Version** is generated into `SKILL.md` and `pyproject.toml` from the
  manifest; `CHANGELOG.md`'s top `## vX.Y.Z` is manual and enforced by
  `test_version_sources_stay_in_sync`. `skills/review/SKILL.md` has its own
  independent version — do not sync it.
- **Tests assert exact substrings** in SKILL.md: emoji section headers
  (`## 🔧 Environment Variables`, `## 💾 Checkpointing`, `## ⚡ Quick Mode`),
  `effort: ${CODE_REVIEW_EFFORT:-max}`, table headers, phase names, enums.
  Renaming or rewording these breaks the suite.
- Never add `^model: ` to the frontmatter — `test.sh` and `Test-Windows.ps1`
  both fail on it.
- Env-var set is locked by `tests/test_env_config.py:TABLE_VARS` (12 vars);
  each needs >=2 body references. `AGENTS.md`, `README.md`, and `help.md` are
  scanned for unknown `CODE_REVIEW_*` names.
- Severity / DA verdict / health values are closed enums validated by
  `tests/test_pipeline.py`.

## Gotchas

- **Do not "fix" the eval fixtures to match the code.** `tests/fixtures/agents/*.json`
  are recorded agent reports; `tests/dummy_repo` deliberately contains the
  vulnerabilities they describe (hardcoded creds, `shell=True`, N+1, cycle).
  `ccr eval` must stay at 100% coverage; a miss means the pipeline regressed.
- **Two eval fixtures.** `tests/fixtures/agents` is synthetic (dummy_repo).
  `tests/fixtures/organizer` is a real recorded Quick Mode run with
  human-verified precision; its `expected.json` excludes the known false
  positive's tag and pins it as text. Never edit the agent JSON to make the
  numbers pass.
- **`synthesize` enforces the completion gate.** Planned agents come from
  `--agents`, then `ccr-state.json:agents_planned`, then the cache files. A
  partial run exits 1 unless `--allow-partial`. Do not bypass it in code.
- **`expected_issues.json` is scored, not self-compared.** `test.sh` and
  `Test-Windows.ps1` no longer hardcode copies of the list — they call
  `python -m ccr eval`. Do not reintroduce a duplicated list.
- **`install.py.sha256` is generated.** After editing `install.py`, run
  `python tools/generate.py`; `--self-verify` must pass.
- **`install.py:_SKILL_EXCLUDED`** decides what ships. `tools/`, `tests/`,
  `AGENTS.md`, `orchestrator-rules.md`, `Makefile`, `help.md`, `pyproject.toml`
  are deliberately excluded. Runtime needs (`SKILL.md`, `ccr/`,
  `karpathy-guidelines.md`, `helpers/`, `skills/`) must never be added.
- **Coverage spans `install.py`, `ccr/`, and `tools/`.** Doc-only changes cannot
  lower it; new Python without tests will.
- **`test.sh` is Unix-only** (bash + `grep`), **`Test-Windows.ps1` is
  Windows-only**; CI gates them with `if: runner.os != 'Windows'` / `== 'Windows'`.
  `make` may not exist on Windows — run `python -m unittest ...` directly.
- **SKILL_DIR injection**: the orchestrator passes the absolute installed skill
  dir into every sub-agent prompt. Never resolve `karpathy-guidelines.md` via
  `realpath` from the target CWD.
- **Phase 5a/5c review is done by the orchestrator itself** — load
  `skills/review/SKILL.md` and execute its phases; there is no review bot.
  `--json` is a behavioral instruction, not a script argument.
- **`gh pr review --approve` fails on your own PR** — use `gh pr comment
  --body-file` or `gh api repos/:owner/:repo/issues/:number/comments`.
- **Phase 5d-5g need `gh`** authenticated with push access; without it, PR
  steps skip and the branch stays on disk.
- **Agent failure threshold**: <75% of active agents (full) or <66% (Quick
  Mode) → halt; LOW-ACTIVITY domains are excluded from the denominator.
  `ccr.pipeline.check_completion` implements this.
- **DA `REJECTED` findings never reach the roadmap** — enforced both in
  `ccr.findings.place_roadmap` and `tests/test_pipeline.py`.
- **Tech debt floors**: circular dep 8h, hardcoded secret 2h, missing coverage
  4h per module (`pipeline.json:tech_debt_floors`). 2x/0.5x multipliers allowed.
- **Packaging**: `ccr` is a console script (`pipx install .`). Build backend is
  setuptools; runtime deps remain zero.

## Conventions

- Zero runtime deps. A PR adding one is rejected. Only CI installs (`coverage`,
  `build` for releases).
- No type hints; 100-char soft line limit; simple f-strings only.
- New tests use `unittest.TestCase`; `Test<Module><Scenario>` classes;
  filesystem tests use `tempfile.TemporaryDirectory()`, never the repo root.
- Add an ADR in `ADRs/` for significant design decisions.
- Conventional Commits: `feat|fix|test|docs|refactor|ci|chore`.

## Key References

- Pipeline spec, env vars, output schema: `SKILL.md`
- Orchestrator protocol (state, gates, tripwires): `orchestrator-rules.md`
- Internal review skill: `skills/review/SKILL.md`
- CLI and module reference: `docs/api/ccr.md`
- Installer API: `docs/api/install.md`
- Quick reference, exit codes, troubleshooting: `help.md`
- CI (pinned actions, drift check, eval): `.github/workflows/ci.yml`
- Release (sdist/wheel, checksums, provenance): `.github/workflows/release.yml`
- Design rationale: `ADRs/` (agent split, DA workflow, plain-Python tests,
  5-phase pipeline)

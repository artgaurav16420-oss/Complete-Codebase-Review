Karpathy Guidelines v3.7 MANDATORY: For all AI operations in this project, you MUST follow karpathy-guidelines.md as the primary behavioral ruleset.

# AGENTS.md — Complete Codebase Review

**Two halves.** `SKILL.md` is the prompt pipeline the host agent executes.
`ccr/` is the executable core: discovery, state, DA checks, aggregation,
report rendering, eval. `install.py` installs the skill; `tools/generate.py`
keeps generated docs in sync. Zero runtime deps, stdlib only, Python >= 3.9.

Nothing needs installing to work here: `python -m ccr ...` and the whole test
suite run from the repo root. `pip install .` only adds the `ccr` console
script. `ccr` exits 2 on usage/manifest errors, 1 on gate or eval failures.

## Commands (verified)

| Command | Purpose |
|---------|---------|
| `python -m unittest discover -s tests -p "test_*.py"` | Full suite (prints its own count, <2s). Run after **any** change. |
| `python tests/compliance_test.py` | SKILL.md contract only |
| `python tests/review_compliance_test.py` | `skills/review/SKILL.md` contract only |
| `python -m ccr eval` | Score fixtures; defaults to the synthetic dummy_repo set. Organizer benchmark: `--fixtures tests/fixtures/organizer/agents --expected tests/fixtures/organizer/expected.json` |
| `python -m ccr plan .` | Discovery facts + selected agents (`--json`, `--effort min`) |
| `python tools/generate.py` / `--check` | Rewrite / verify generated docs and checksum |
| `make test` | `./test.sh`: eval + both compliance suites + unittest under coverage. Unix only |
| `make test-py` | unittest + both compliance suites, no eval |
| `make test-windows` | `tests/Test-Windows.ps1` (Windows) |
| `make lint` | **Only** `py_compile` syntax check — there is no linter/formatter |
| `coverage run -m unittest discover -s tests -p "test_*.py"` then `coverage report`, `coverage json -o coverage.json`, `python tools/coverage_floor.py coverage.json` | Coverage gate: 85% total **and** 80% per module |
| `python tools/metrics.py ccr` | Per-function cyclomatic complexity / LOC, ad hoc |
| `python install.py --dry-run` / `--self-verify` / `--uninstall` | Preview / verify / remove |

Never run a subset to "save time": the whole suite is seconds. `make test-bash`
is the same full run as `make test`, not a bash-only check.

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
  cli.py          plan | record | synthesize | validate-results | eval
  manifest.py     manifest load + schema validation
  fileio.py       UTF-8 write helper used by pipeline and providers
tools/generate.py  regenerates doc tables + install.py.sha256 from pipeline.json
tools/coverage_floor.py  per-file coverage gate (CI only)
tools/metrics.py         ad hoc complexity/LOC report
install.py        installer (standalone; not a ccr subcommand)
```

`record` writes one prompt per agent; the host executes them; `synthesize`
ingests the JSON. `ccr` never calls a model — that is why it is testable.
Cache dir defaults to `.code-review-cache/`; `ccr-state.json` and
`previous-results/` live inside it.

## Editing rules

- **Never hand-edit generated blocks** in `SKILL.md`, `README.md`, `help.md`,
  `orchestrator-rules.md`, `pyproject.toml`'s version, or `install.py.sha256`.
  Edit `ccr/pipeline.json`, run `python tools/generate.py`, commit all files.
  CI runs `--check` and fails on drift. The `<!-- BEGIN/END GENERATED: key -->`
  markers themselves must survive — `generate.py` raises on a missing marker.
- **Version** is generated into `SKILL.md`, `pyproject.toml`, and `help.md` from
  the manifest; `CHANGELOG.md`'s top `## vX.Y.Z` is manual and enforced by
  `tests/compliance_test.py:test_version_sources_stay_in_sync`.
  `skills/review/SKILL.md` has its own independent version — do not sync it.
- **Tests assert exact substrings in SKILL.md.** `tests/compliance_test.py`
  pins phrases such as `effort: ${CODE_REVIEW_EFFORT:-max}`,
  `NEVER modify the codebase during Phases 1-3`, `python -m ccr synthesize`,
  `EST-CONFLICT`, `## Phase 4` / `## Phase 5`, and all 14 specialist agent
  names. Rewording a pinned phrase fails the suite even when it reads better.
- Never add `^model: ` to the frontmatter — `test.sh` and `Test-Windows.ps1`
  both fail on it.
- Env-var set is locked by `tests/test_env_config.py:TABLE_VARS` (12 vars);
  each needs >=2 body references. `AGENTS.md`, `README.md`, and `help.md` are
  scanned for unknown `CODE_REVIEW_*` names.
- Severity / DA verdict / health values are closed enums validated by
  `tests/test_pipeline.py`.
- **3.9 syntax floor.** CI covers 3.9-3.15 on Linux, Windows, macOS. No
  `match`, no `X | Y` unions, no `dict | dict` — newer local Pythons accept
  them, then CI fails.
- **LF only.** `.gitattributes` is `* text=auto eol=lf`; write new files LF.

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
- **Golden snapshots.** `tests/fixtures/golden/{agents,organizer}.json` are
  byte-exact `synthesize` output (`sort_keys=True, indent=2`, timestamp
  `2026-01-01T00:00:00`). Changing report or model shape breaks
  `tests/test_characterization.py`; regenerate the golden deliberately with the
  call in that file — never hand-edit it to fit.
- **Per-file coverage floor.** `tools/coverage_floor.py` fails CI when any
  single module is below 80%, even if the 85% total is green. It skips `tests/`
  and `tools/`, so `ccr/` and `install.py` are the files that must be tested.
- **`synthesize` enforces the completion gate.** Planned agents come from
  `--agents`, then `ccr-state.json:agents_planned`, then the cache files. A
  partial run exits 1 unless `--allow-partial`. Do not bypass it in code.
- **`record` archives previous results** to `previous-results/<timestamp>/` and
  refreshes effort/facts in state. `synthesize` carries those facts into the
  report; without state or `--agents` it warns and skips the gate.
- **`expected_issues.json` is scored, not self-compared.** `test.sh` and
  `Test-Windows.ps1` call `python -m ccr eval`. Do not reintroduce a duplicated
  issue list.
- **`install.py.sha256` is generated.** After editing `install.py`, run
  `python tools/generate.py`; `--self-verify` must pass.
- **`install.py:_SKILL_EXCLUDED`** decides what ships. `tools/`, `tests/`,
  `AGENTS.md`, `orchestrator-rules.md`, `Makefile`, `help.md`, `pyproject.toml`
  are deliberately excluded. Runtime needs (`SKILL.md`, `ccr/`,
  `karpathy-guidelines.md`, `helpers/`, `skills/`) must never be added.
- **`test.sh` is Unix-only** (bash + `grep`), **`Test-Windows.ps1` is
  Windows-only**; CI gates them with `if: runner.os != 'Windows'` / `== 'Windows'`.
  `make` may not exist on Windows — run `python -m unittest ...` directly.
- **SKILL_DIR injection**: the orchestrator passes the absolute installed skill
  dir into every sub-agent prompt. Never resolve `karpathy-guidelines.md` via
  `realpath` from the target CWD.
- **`skills/review/SKILL.md` is a separate product**, not part of Phase 5:
  Phase 5a spawns a fresh reviewer Task agent with inline instructions, and the
  orchestrator applies 5b corrections itself. The review skill has its own
  contract (`tests/review_compliance_test.py`, 75 assertions) and its own
  argument grammar (`--json`, `--base`, `-t`); editing it does not touch
  `SKILL.md`, and nothing in `SKILL.md` loads it.
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
- Conventional Commits: `feat|fix|test|docs|refactor|ci|chore`; PRs target
  `main`, releases are cut from `v*` tags by `.github/workflows/release.yml`.

## Key References

- Pipeline spec, env vars, output schema: `SKILL.md`
- Orchestrator protocol (state, gates, tripwires): `orchestrator-rules.md`
- Internal review skill: `skills/review/SKILL.md`
- CLI and module reference: `docs/api/ccr.md`
- Installer API: `docs/api/install.md`
- Quick reference, exit codes, troubleshooting: `help.md`
- CI (pinned actions, drift check, eval, coverage floor): `.github/workflows/ci.yml`
- Release (sdist/wheel, checksums, provenance): `.github/workflows/release.yml`
- Design rationale: `ADRs/` (agent split, DA workflow, plain-Python tests,
  5-phase pipeline, executable core, fileio containment)

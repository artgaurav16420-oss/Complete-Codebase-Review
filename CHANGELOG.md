# Changelog

## Unreleased

- **Anchor normalization**: `findings.normalize_anchor` rewrites ASCII separators
  (`[a.py:1] - flaw -> failure`, `-- flaw => failure`, or a missing separator before the flaw)
  into the canonical em dash and arrow before the DA gate runs. A sound finding is no longer
  rejected for punctuation, and `anchor_parts` accepts the same forms.
- **Rejections are reported**: `synthesize` prints a `[WARN]` line with the number of findings
  the DA gate rejected, instead of leaving them only in the report's Rejected Findings section.
- **`CODE_REVIEW_AGENTS` honoured by the CLI**: `plan` and `record` now read the documented
  environment variable as a fallback when `--agents` is absent.
- **Harness-style tests are discovered**: a filename token (`test`, `spec`, `harness`) counts as
  a test file, so repos whose suites live in `tools/*-harness.js` are no longer reported with
  zero tests and silently lose the `test_health` agent.
- **Tests**: normalization, rejection wiring, env fallback, and harness detection cases.
- **Review follow-ups**: the anchor prefix consumes the whole dash run (`[a.py:1] -- flaw` no
  longer leaves a stray hyphen) and accepts one level of nested brackets (`app/[id]/page.tsx`);
  the separator is the last ASCII arrow when no canonical `→` exists, so an arrow inside the
  flaw (`lambda -> proc => nil`) does not split it; an explicit `--agents ""` no longer falls
  back to `CODE_REVIEW_AGENTS`; and the token rule applies only to source extensions and only to
  a trailing marker token (`test.js` and `module-test.js` count, `src/test-utils.js` and
  `docs/load-harness.md` do not).
- **CI**: macOS runs only Python 3.9 and 3.15 in the `ci.yml` and `release.yml` matrices.
  Seven queued macOS jobs overflowed the concurrent macOS runner cap, and GitHub cancelled
  the overflow before it started, failing otherwise-green runs on `main` and on PRs. Linux
  and Windows still cover every interpreter.
- **Review fixes (2026-11-06)**:
  - Agent identity and calibration come from `ccr/pipeline.json` (`security_agent_id`,
    `calibration`, `tech_debt_labels`); `ccr.manifest.load()` pushes them into the engine,
    and ADR-007 records the calibration policy.
  - One result-file convention in `ccr.providers` (`discover_results`, `find_result`):
    `eval --fixtures` no longer aborts on a directory holding a `ccr-baseline.json`, and
    state resume and synthesize agree on what counts as an agent result. A canonical
    `phase_<id>.json` that will not parse is reported as malformed with its path, not
    mistaken for a missing result.
  - Completion ratio divides by the planned roster, so a stale `total_agents` cannot
    report 0% for a finished run.
  - Report cells neutralise HTML and Markdown links from agent text; sanitization drops
    Unicode `Cf` characters (bidi overrides, isolates, zero-width space).
  - The installer stages the copy, moves the previous tree aside instead of deleting it
    and puts it back when the swap fails; leftovers from a crashed run are swept by age,
    so a concurrent run's staging tree is left alone. The credential filter covers
    `.envrc` and `.direnv`.
  - The SKILL.md tech-debt table is generated from `pipeline.json` instead of duplicated,
    and the report validators are split into section checks.
  - CI: workflow-level permissions reduced to `contents: read` with per-job escalation,
    exact pins for `coverage` and `build`, a wheel smoke test before publishing, and a
    pull-request check that rejects empty commits.
  - CodeAnt round 1: `record` archives only files, so a directory named like a result is
    left alone; discovery compares the `.json` suffix case-insensitively, matching
    `find_result` on a case-sensitive filesystem; duplicate completed ids cannot push the
    completion ratio above the roster; and the re-review counter is updated under an
    advisory lock, so two syntheses cannot lose an increment.
  - Installer: a parked previous install is re-stamped so a concurrent age-based sweep
    cannot delete the backup a rollback needs; a link-like install is parked rather than
    unlinked, so a failed swap still restores it; and uninstall fails when its own
    leftovers cannot be removed instead of reporting a clean removal.
  - CodeAnt round 2: the release matrix splits its coverage pin by interpreter (coverage
    7.14 requires Python 3.10, so the 3.9 leg takes 7.10.7) instead of failing to install on
    the floor and blocking every tag; the re-review counter is skipped, not updated, when
    another run holds the lock; the installer refuses to sweep a target that has become a
    link; and a failed leftover removal fails the uninstall instead of reading as nothing
    to uninstall.
  - CodeAnt round 3: the state lock is an OS lock (`fcntl`/`msvcrt`) released by the kernel,
    so a crashed holder needs no staleness rule and two contenders cannot take over the same
    lock; `record` takes that lock too, so it cannot overwrite a re-review credited while it
    ran; the installer names its staging and backup trees for one run (pid plus random) so a
    reused pid cannot delete a crashed run's only backup; and a bare-layout result must carry
    only the agent-result keys, so a synthesized report sitting beside the fixtures is not
    read as an agent.
  - CodeAnt round 4: the completion denominator deduplicates the planned roster exactly as
    `pipeline.check_completion` does, so a repeated id cannot block the gate after every
    distinct agent finished; the parked backup is stamped before the rename, closing the
    window in which a concurrent age-based sweep could delete it; `_remove_tree` removes a
    directory symlink or junction through its reparse point instead of failing the unlink and
    leaving it under `.old-*`; report cells defuse bare `https://` and `www.` autolinks that
    GitHub would otherwise render as live links; and replay ignores a findings-only json
    beside the fixtures instead of aborting on an agent the manifest never planned.
  - CodeAnt round 5: `State.load` rejects a non-string `target_dir` (null still reads as an
    old state), so a hand-edited number exits with an error instead of a `TypeError`
    traceback in `synthesize`; and replay treats a file named for a planned agent as that
    agent's result whatever it contains, so a corrupt fixture is reported by path instead of
    being skipped as a stray file.
  - CodeAnt round 6: `synthesize` re-applies the identity and calibration of the manifest it
    was handed, so a second `manifest.load` cannot change an earlier report; a build without
    `fcntl`/`msvcrt` reports the state lock unheld instead of claiming one; a failed mtime
    stamp aborts the update before the live install is parked, since the backup would
    otherwise carry its old age; the score validator rejects any non-numeric cell rather
    than only `N/A`; and a test comment no longer cites stale line numbers.
  - CodeAnt round 7: result discovery returns regular files only, so a directory named
    `security.json` is not planned as an agent result when the manifest's id set is known;
    a cache that cannot be listed fails `record` with an error instead of reading as empty
    and leaving the previous run's results for `synthesize` to ingest; and a manifest agent
    id may not start with the reserved `phase_` prefix, which would make a bare fixture
    indistinguishable from another agent's canonical result.
  - CodeAnt round 8: discovery skips a link, so a `phase_<id>.json` symlink cannot pull a
    file from outside the cache into a report; a legacy state with `target_dir: null` falls
    back to the cache directory instead of naming the baseline target `null`; state roster
    entries must be strings, so a hand-edited `[{}]` is rejected at load rather than raising
    `TypeError` in `completion_ratio`; and `test.sh` plus `Test-Windows.ps1` match the
    section headings instead of a substring that also occurs in body prose.
  - CodeAnt round 9: a legacy state that records no target no longer lends its `facts` to
    the target a later run names; `record` leaves a linked result in place, because
    discovery skips links and archiving one would move an entry this run never wrote;
    an install re-checks the destination for link-likeness immediately before the copy,
    so a target swapped for a link during the leftover sweep cannot receive the staging
    tree; and the section checks compare the whole heading title, so a heading that merely
    contains the name (`## No Environment Variables`) no longer passes.
  - CodeAnt round 10: the engine's security-agent identity and calibration belong to the
    calling thread, so two syntheses running at once cannot overwrite each other's
    settings and report the wrong identity; a manifest agent id may not be empty, because
    it would name the result file `phase_.json` and discovery would strip the prefix back
    to nothing; the age-based leftover sweep no longer deletes a link-like entry, whose
    own timestamp cannot be refreshed on every platform, so a rollback copy parked by a
    running install can no longer be swept away from under it; and the `merge_resume`
    entry in `docs/api/ccr.md` now states what an empty planned roster means.
  - CodeAnt round 11: an explicit `"security_agent_id": null` is rejected at load instead
    of being read as an omitted field, because it would point the HIGH-finding check at an
    id the manifest may no longer declare and silently demote those findings; a bare email
    address in agent text is defanged like a URL, since GitHub autolinks it as a `mailto:`
    destination; and the install test that swaps the destination for a link now skips
    itself on a host that cannot create one, instead of failing the suite.

## v2.4.0 (2026-10-20)

- **Single source of truth**: `ccr/pipeline.json` generates the env-var tables, agent tables,
  version strings, and installer checksum via `tools/generate.py --check` in CI.
- **Executable core** (`ccr/`): discovery, agent planning, state gates, finding normalization,
  DA filtering, tech-debt aggregation, roadmap, and Markdown/JSON report rendering.
- **CLI**: `python -m ccr plan|record|synthesize|validate-results|eval`.
- **Eval harness**: recorded agent fixtures replayed through synthesis and scored against
  `tests/expected_issues.json`; `missing-test-assertions` replaced by `missing-test-coverage`
  to match the fixture repo.
- **Completion gate**: `synthesize` uses `ccr-state.json:agents_planned` and refuses to emit a
  report below 75% (full) / 66% (Quick Mode); `--allow-partial` overrides explicitly.
- **Severity caps and prompt checks**: documentation-only findings capped at MEDIUM, test-only
  reliability at MEDIUM unless it disables a release gate, HIGH Security findings routed to
  Phase 1, and every agent prompt carries its own domain `checks` block.
- **Write containment**: `ccr.fileio.write_text` keeps prompt and report writes beneath a root
  directory, refusing symlinked roots and paths that resolve outside it; on Windows the opened
  handle's final path is checked too, and the helper stays Python 3.9-compatible.
- **Review follow-ups**: state gates per phase, deduplicated agent accounting, discovery facts
  carried into reports, stale-result archiving on re-record, manifest tech-debt floors applied,
  roadmap phase objects in JSON, uninstall failure exit code, and generated `help.md` version.
- **Organizer benchmark**: first real recorded run with human-verified precision
  (`tests/fixtures/organizer/`), scored via a benchmark spec with known false positives.
- **Packaging**: `ccr` console script and declared build backend.
- **Installer**: `--uninstall`; `onexc` on Python 3.12+ replaces deprecated `onerror`.
- **CI**: generated-file drift check and release provenance workflow.

## v2.3.0 (2026-06-26)

- **Input sanitization**: Unicode normalization, shell command stripping, path validation for bot comments
- **Scoped tool permissions**: Phase 1-3 read-only agents restricted from write operations
- **Per-issue approval**: External loop auto-approve threshold configurable via `CODE_REVIEW_AUTO_APPROVE`
- **GraphQL pagination**: Large PR comment fetching with cursor-based pagination
- **Regex triggers**: Natural-language activation patterns ("review codebase", "run CCR", etc.)
- **New env vars**: `CODE_REVIEW_SANITIZE`, `CODE_REVIEW_AUTO_APPROVE`
- **New files**: `helpers/sanitization.md`, `helpers/github-commands.md`
- **Tests**: 4 new compliance tests for triggers, scoped tools, sanitization, helpers
- **Prompt hardening**: Strict Evidence Rule (file:line anchoring, zero generic advice, blast radius), DA Three-Strike Rejection Rule, weasel word ban with automated validation

## v2.2.0 (2026-06-20)

[#25](https://github.com/artgaurav16420-oss/Complete-Codebase-Review/pull/25)
- **Phase 5 rewrite**: Replaced linear 5e→5f with CodeRabbit-inspired
  review→autofix→re-review loop
- **skills/review/SKILL.md v2.0.0**: Added Phase 1.5 scope flags (`--json`, `-t`, `--base`, etc.),
  Phase 3.5 fix-review cycle, detailed JSON output schema, max-iteration loop control
- **Loop control**: 5e1 (run review) → 5e2 (autofix loop, per-issue
  AskUserQuestion) → 5e3 (loop control, exit on APPROVE/stall/max-iterations)
- **Env vars**: Added `REVIEW_MAX_ITERATIONS` (Phase 5 loop cap)
- **Tests**: Updated Phase 5 tests to match new section names (Autofix Loop, Run Code Review on PR)

## v2.1.0 (2026-06-17)
- **Phase 5**: Independent Review & Test — fresh agent audits all Phase 4 fixes,
  applies corrections, runs full test suite, produces final report
- **SKILL.md**: Added 5a–5h (spawn reviewer, apply corrections, full test suite,
  create PR, run review on PR, fix PR comments, re-test, final report)

## v2.0.1 (2026-05-24)
- **Environment Check**: Added Step 1a to Phase 1 Discovery
- **Output filter**: Added CODE_REVIEW_FILTER env var
- **DA ordering fixed**: Phase 3 order is now Synthesis → DA → Roadmap; DA-ESCALATION findings feed into roadmap
- **SKILL_DIR injection**: karpathy-guidelines.md now resolved via absolute SKILL_DIR injected by orchestrator at spawn time
- **RESOLVED_CACHE_DIR**: cache path resolved once in Phase 1 Step 3, used throughout Phases 3-4 (fixes temp-dir fallback propagation)
- **EST-CONFLICT logging**: Phase 4b reconciliation now logs conflicts and notifies user in fix plan footer
- **Token estimates corrected**: Pre-flight now shows 15K–80K input per agent (was ~5K)
- **Phase 4f**: LOW-ACTIVITY domains now skip agent spawn; previous scores carry forward
- **install.py**: gitignore warning on local fallback install
- **pyproject.toml**: corrected build-backend to setuptools.build_meta
- **CI**: removed invalid update-pip parameter from setup-python action
- **Tests**: dead regex fixed, temp-dir fallback assertion corrected, gitignore warning tests added

## v2.0.0 (2026-05-23)
- **Env vars**: Added `CODE_REVIEW_EFFORT`, `CODE_REVIEW_TIMEOUT_SEC`, `CODE_REVIEW_MAX_FILES`, `CODE_REVIEW_CACHE_DIR`, `CODE_REVIEW_BASELINE`, `CODE_REVIEW_AGENTS`, `CODE_REVIEW_STATUS_INTERVAL`
- **New sections**: Checkpointing, Quick Mode, Sample Output, Changelog
- **Dynamic effort**: Removed hardcoded `model: opus`, effort reads from `CODE_REVIEW_EFFORT` env var
- **Stricter thresholds**: Agent failure threshold changed from `<8 agents` / `≤6` to `75%` (full mode) / `66%` (quick mode)
- **Post-fix verification**: Added Phase 4g to verify fixes didn't introduce issues
- **Cache dir**: All hardcoded `$TEMP_DIR` replaced with `${CODE_REVIEW_CACHE_DIR:-.code-review-cache}`
- **Task invocation example**: Added concrete Task tool usage example in Orchestration
- **Status checkpoint**: Periodic progress logging via `CODE_REVIEW_STATUS_INTERVAL`
- **Cross-platform**: Cache verification fallback to OS temp directories
- **Tests**: Synced compliance and integration tests to match v2.0.0

---
name: review
description: Review local changes, commits, branches, or PRs — severity-graded findings with approve/block decision. Portable across runtimes (Claude Code, OpenCode, Codex, etc.).
version: 2.0.0
allowed-tools: "Read, Grep, Glob, Bash, WebSearch, Task"
argument-hint: "[hash|branch|pr|--json|-t scope|--base <branch>|--base-commit <sha>|--dir <path>|--format <markdown|json|both>|--chunk <module>|--force-full]"
---

# Code Review

## Overview

Review code changes and produce severity-graded findings with an approve/block decision. Works with uncommitted local changes, specific commits, branch comparisons, or GitHub PRs.

## Mode Selection

Examine `$ARGUMENTS` to determine mode:

| Input | Mode |
|-------|------|
| (empty) | **Local** — review unstaged + staged uncommitted changes |
| 40-char SHA or short hash | **Commit** — review that specific commit |
| Looks like branch name (no `/`, not a hash, not a URL) | **Branch compare** — diff current branch vs specified branch |
| Number (e.g. `42`) | **PR mode** — GitHub PR number |
| URL containing `github.com/.../pull/` | **PR mode** — extract PR number from URL |
| `--pr <n>` | **PR mode** — explicit PR flag |

Store result as `$REVIEW_MODE` and `$REVIEW_TARGET`.

---

## Phase 1 — Gather

### Local / Commit / Branch Mode

```bash
# Uncommitted changes (default)
git diff --name-only HEAD
git diff HEAD
git diff --cached

# Specific commit
git show --stat <hash>
git show <hash>

# Branch comparison
git diff --stat <branch>...HEAD
git diff <branch>...HEAD
```

Also fetch full file contents — read each changed file entirely, not just diff hunks.

### PR Mode

Check `gh` CLI availability first. If missing, warn and fall back to local mode (git fetch + merge-base diff):

```bash
# Check gh
command -v gh >/dev/null 2>&1 && gh auth status 2>&1 || echo "gh not available"

# PR info
gh pr view <NUMBER> --json number,title,body,author,baseRefName,headRefName,changedFiles,additions,deletions 2>&1

# PR diff
gh pr diff <NUMBER> 2>&1
```

Read each changed file in full via the diff or by fetching from the PR's head branch.

### Project Context

Detect project type from root config files:

| File | Project |
|------|---------|
| `package.json` | Node.js / TypeScript |
| `Cargo.toml` | Rust |
| `go.mod` | Go |
| `pyproject.toml` / `setup.py` | Python |
| `CMakeLists.txt` | C/C++ |

Check for conventions files: `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `.editorconfig`.

---

## Phase 1.5 — Scope Flags

Parse `$ARGUMENTS` for scope flags that control which changes to review:

| Flag | Meaning |
|------|---------|
| `-t all` | All changes (default) |
| `-t staged` | Staged changes only |
| `-t committed` | Committed changes only |
| `-t uncommitted` | Unstaged changes only |
| `--base <branch>` | Compare against a specific branch |
| `--base-commit <sha>` | Compare against a specific commit |
| `--dir <path>` | Review a specific directory (must be a git repo) |
| `--json` | Output findings as JSON only (no markdown report) |
| `--format <markdown\|json\|both>` | Control output format (default: `markdown`) |
| `--chunk <module>` | Review a specific module/chunk of a large PR |
| `--force-full` | Skip incremental checks, force full review |

Store parsed flags as `$REVIEW_SCOPE`. When `--json` is set, emit structured
JSON in Phase 4 instead of the markdown report. When `--format` is set to
`both`, emit both markdown and JSON. When `--chunk` is set, scope the review
to that module only (see Phase 1.6). When `--force-full` is set, bypass
incremental review tracking and run the full checklist. When `--dir`
is set, scope git operations to that directory.

---

## Phase 1.6 — Large PR Handling

When the diff exceeds 50 changed files or an estimated 30,000 tokens, apply
chunking to keep review quality high:

1. **Detect**: Count changed files via `git diff --name-only`. Estimate tokens
   from total diff size (rough heuristic: ~4 tokens per line of diff).
2. **Chunk**: If over threshold, split by module or directory. Use `--chunk
   <module>` if provided; otherwise auto-chunk by top-level directory.
3. **Prioritize**: Review source code and configuration changes first. Skip
   generated files, lockfiles, and vendored dependencies unless flagged.
4. **Iterate**: Review each chunk sequentially. Aggregate findings across
   chunks into a single report in Phase 4.
5. **Warn**: Emit a warning in the report summary: "Large PR: review was
   chunked into N parts. Some changes may not have been reviewed in depth."

If `--force-full` is set, skip chunking and review everything regardless of
size.

---

## Phase 2 — Review Checklist

Check every changed file against these categories:

### Correctness
- Logic errors, off-by-one mistakes, incorrect conditionals
- If-else guards: missing guards, incorrect branching, unreachable code paths
- Edge cases: null/empty/undefined inputs, error conditions, race conditions

### Security
- Hardcoded credentials, API keys, tokens, secrets
- Injection vulnerabilities (SQL, command, path traversal)
- Unsafe `shell=True`, `eval()`, `exec()` usage
- Missing input validation on untrusted data
- Path traversal: `os.chmod` on symlinks, TOCTOU races
- Exposed internal endpoints or debug routes

### Structure & Maintainability
- Does the code fit existing patterns and conventions?
- Excessive nesting (>4 levels) — consider early returns or extraction
- Functions >50 lines or files >800 lines
- Missing error handling — every error path should log, cleanup, and not crash
- `console.log`, `print()`, TODO/FIXME in production code
- Mutation of function parameters

### Behavior Changes
- Is this change introducing intentional behavioral changes?
- Could any change have unintended side effects on other modules?
- Public API changes (signatures, return types, error contracts)

### Cross-Platform
- Windows vs Unix: path separators, line endings, signal handling
- `.ps1`: `$ErrorActionPreference`, `Test-Path` guards, `-ExecutionPolicy Bypass`
- `.sh`: variable quoting, `set -e`, POSIX portability
- `Makefile`: `.PHONY` targets, tab indentation, shell portability

### Validation Commands

Run project-appropriate commands to verify:

| Detected | Commands |
|----------|----------|
| Node/TS | `npm run typecheck 2>&1` \|\| `npx tsc --noEmit 2>&1`, `npm run lint 2>&1`, `npm test 2>&1`, `npm run build 2>&1` |
| Rust | `cargo clippy -- -D warnings 2>&1`, `cargo test 2>&1`, `cargo build 2>&1` |
| Go | `go vet ./... 2>&1`, `go test ./... 2>&1`, `go build ./... 2>&1` |
| Python | `python -m pytest 2>&1` or `python -m unittest discover 2>&1` |
| Fallback | Try `make test`, `npm test`, `pytest` in order |

Record pass/fail for each command run. Capture both stdout and stderr for
diagnostic output (use `2>&1` not `2>/dev/null`).

### Cross-Platform Fallback Logic

When running validation commands, detect the current platform and shell to
select the right linter variants:

| Platform | Detection | Behavior |
|----------|-----------|----------|
| PowerShell | `$PSVersionTable.PSEdition` exists | Use `Invoke-Expression` or `&` call syntax; skip `.sh`-only linters |
| Bash/Unix | `$BASH_VERSION` or `uname` returns Linux/Darwin | Use standard shell syntax; skip `.ps1`-only linters |
| Windows (Git Bash) | `$MSYSTEM` set | Treat as Bash with Windows paths |

**Skip behavior**: If an optional linter binary is not installed, report
`"Skipped"` for that command and continue. If ALL linters for a detected
project type are missing, emit a warning: "No linters available for
<project type> — install <tool> to enable validation."

**Installation guidance**:
- Node/TS: `npm install -g typescript eslint` or use project-local via `npx`
- Rust: `rustup component add clippy`
- Go: included with Go toolchain
- Python: `pip install ruff` or `pip install flake8`

---

## Phase 3 — Grade & Decide

### Severity Levels

| Severity | Meaning | Action |
|----------|---------|--------|
| **CRITICAL** | Security vulnerability or data loss risk | Must fix before merge |
| **HIGH** | Bug or logic error likely to cause issues | Should fix before merge |
| **MEDIUM** | Code quality issue or missing best practice | Fix recommended |
| **LOW** | Style nit or minor suggestion | Optional |

### Decision

| Condition | Decision |
|-----------|----------|
| Zero CRITICAL/HIGH, validation passes | **APPROVE** |
| Only MEDIUM/LOW, validation passes | **APPROVE with comments** |
| Any HIGH or validation failures | **REQUEST CHANGES** |
| Any CRITICAL | **BLOCK** — must fix before merge |

### GitHub PR Posting (optional)

If `gh` CLI is available and in PR mode, post review to GitHub:

```bash
# COMMENT (non-blocking — use when already reviewed by Phase 5a)
gh pr review "$PR_NUMBER" --comment --body "<findings summary>"

# Inline comments for specific lines if applicable
gh api repos/:owner/:repo/pulls/"$PR_NUMBER"/reviews \
  --input comments.json
```

If `gh` is not available, print the report to stdout and note "gh not available — install GitHub CLI to post reviews directly."

---

## Phase 3.5 — Fix-Review Cycle

This skill supports iterative fix-review cycles for automated PR quality gates.

### When to Loop

After Phase 3 produces findings and the invoking orchestrator has applied fixes,
the orchestrator may re-invoke this skill to re-review the updated diff. This
creates a review → fix → re-review loop.

### Loop Control

The loop is controlled by the orchestrator, not by this skill. This skill provides the findings; the orchestrator decides whether to re-invoke.

On each re-invocation:
1. The diff has changed (fixes were applied)
2. Phase 1 re-gathers the updated changes
3. Phase 2 re-checks against the full checklist
4. Phase 3 re-grades
5. Results are emitted again

### Incremental Review Tracking

To avoid re-reviewing unchanged sections, maintain incremental state in
`ccr-state.json`:

**State fields**:
- `base_hash`: The git commit SHA used as the diff base for the last review
- `head_hash`: The git commit SHA of the last reviewed HEAD
- `reviewed_files`: Map of file path → hash of content at last review
- `findings_by_file`: Map of file path → array of finding IDs for that file
- `last_decision`: The decision from the last review (`APPROVE`, `REQUEST_CHANGES`, `BLOCK`)

**Hash computation**: Use `git rev-parse HEAD` for commit hashes and
`git rev-parse HEAD:<file>` for per-file content hashes.

**Precedence rules**:
1. If `--force-full` is set, ignore state and run full review
2. If `base_hash` or `head_hash` changed, re-review all files that differ
3. If only new commits were added on top of a known `head_hash`, review only
   files changed in the new commits
4. If no state file exists, run a full review and save state

**Incremental procedure**:
1. Load `ccr-state.json` from the project root (if it exists)
2. Compute current `head_hash` and compare to stored `head_hash`
3. If incremental: `git diff <old_head>..HEAD --name-only` to get changed files
4. Run Phase 2 checklist only on changed files
5. Merge new findings with preserved findings for unchanged files
6. Update `ccr-state.json` with new hashes and findings
7. If `--force-full`, skip steps 2-4 and review everything

### Structured JSON Output for Loop

When invoked with `--json`, emit findings as a JSON object to stdout after the markdown report:

```json
{
  "findings": [
    {
      "id": 1,
      "severity": "CRITICAL",
      "title": "Hardcoded credential",
      "file": "src/config.py",
      "line": 42,
      "description": "DB password hardcoded in source",
      "suggested_fix": "Move to env var"
    }
  ],
  "validation_results": {
    "typecheck": "PASS",
    "lint": "PASS",
    "tests": "FAIL"
  },
  "decision": "REQUEST_CHANGES",
  "total_findings": 5,
  "critical_count": 1,
  "high_count": 2,
  "medium_count": 1,
  "low_count": 1
}
```

The orchestrator uses `findings` array for the autofix loop and `decision` to determine whether to re-invoke.

### Termination Signals

The orchestrator should stop looping when:
- `decision == "APPROVE"` (zero CRITICAL/HIGH, validation passes)
- No new findings vs previous iteration (stalled)
- Max iterations reached (set by `REVIEW_MAX_ITERATIONS`, default 3)

---

## Phase 4 — Report

Produce a structured report. If `--json` was passed in `$REVIEW_SCOPE`, emit
JSON only (no markdown). If `--format both` was passed, emit both markdown
and JSON separated by `---REVIEW_JSON---`.

### Markdown Report

```markdown
# Code Review Report
**Decision**: APPROVE | REQUEST CHANGES | BLOCK

## Summary
<1-2 sentence overall assessment>

## Findings by Severity

### CRITICAL
- [file:line] — <description>

### HIGH
- [file:line] — <description>

### MEDIUM
- [file:line] — <description>

### LOW
- [file:line] — <description>

## Validation Results

| Check | Result |
|-------|--------|
| Type check | Pass / Fail / Skipped |
| Lint | Pass / Fail / Skipped |
| Tests | Pass / Fail / Skipped |
| Build | Pass / Fail / Skipped |

## Files Reviewed
<file list>
```

### JSON Output (when `--json` or `--format json|both` flag is set)

Emit after the markdown report (if `--format both`), separated by `---REVIEW_JSON---`:

```json
{
  "findings": [
    {
      "id": 1,
      "severity": "CRITICAL",
      "title": "Finding title",
      "file": "path/to/file.ext",
      "line": 42,
      "description": "Full description of the finding",
      "suggested_fix": "Suggested fix description"
    }
  ],
  "validation_results": {
    "typecheck": "PASS",
    "lint": "SKIPPED",
    "tests": "FAIL",
    "build": "PASS"
  },
  "decision": "APPROVE | REQUEST CHANGES | BLOCK",
  "total_findings": 5,
  "critical_count": 1,
  "high_count": 2,
  "medium_count": 1,
  "low_count": 1,
  "files_reviewed": ["path/to/file1.ext", "path/to/file2.ext"]
}
```

---

## Edge Cases & Fallbacks

- **No `gh` CLI**: Skip GitHub posting, print report to stdout. Warn user.
- **No git repo**: Error: "Not a git repository."
- **No changes**: "Nothing to review."
- **PR not found**: Error and exit.
- **Validation commands not found (required)**: Hard failure — required linter or
  test runner is missing. Report the missing command and exit with a non-zero
  status. The user must install the tool before review can proceed.
- **Validation commands not found (optional)**: Report "Skipped" for that command
  and continue with the rest of the checklist.
- **Large PR (>50 files)**: Apply Phase 1.6 chunking unless `--force-full` is set.
- **Incremental review bypass**: If `ccr-state.json` is corrupt or unreadable,
  fall back to a full review and overwrite the state file.
- **Max iterations**: Controlled by `REVIEW_MAX_ITERATIONS` env var (default 3).

## Cleanup

Delete any temporary files created during review. Do not leave cached diffs on
disk. Preserve `ccr-state.json` between review runs — it stores incremental
review state (see Incremental Review Tracking). Only delete it if the user
explicitly requests a full reset or if the file is corrupt.

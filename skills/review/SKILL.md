---
name: review
description: Review local changes, commits, branches, or PRs — severity-graded findings with approve/block decision. Portable across runtimes (Claude Code, OpenCode, Codex, etc.).
version: 2.0.0
allowed-tools: "Read, Grep, Glob, Bash, WebSearch, Task"
argument-hint: "[hash|branch|pr|--json|-t scope|--base <b>|--base-commit <sha>|--dir <path>]"
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
gh auth status 2>/dev/null || echo "gh not available"

# PR info
gh pr view <NUMBER> --json number,title,body,author,baseRefName,headRefName,changedFiles,additions,deletions 2>/dev/null

# PR diff
gh pr diff <NUMBER> 2>/dev/null
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
| `--json` | Output findings as JSON for programmatic consumption |

Store parsed flags as `$REVIEW_SCOPE`. When `--json` is set, emit structured
JSON in Phase 4 instead of (or in addition to) the markdown report. When `--dir`
is set, scope git operations to that directory.

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
| Node/TS | `npm run typecheck 2>/dev/null` \|\| `npx tsc --noEmit 2>/dev/null`, `npm run lint 2>/dev/null`, `npm test 2>/dev/null`, `npm run build 2>/dev/null` |
| Rust | `cargo clippy -- -D warnings 2>/dev/null`, `cargo test 2>/dev/null`, `cargo build 2>/dev/null` |
| Go | `go vet ./... 2>/dev/null`, `go test ./... 2>/dev/null`, `go build ./... 2>/dev/null` |
| Python | `python -m pytest 2>/dev/null` or `python -m unittest discover 2>/dev/null` |
| Fallback | Try `make test`, `npm test`, `pytest` in order |

Record pass/fail for each command run.

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

Produce a structured report. If `--json` was passed in `$REVIEW_SCOPE`, also emit
JSON to stdout after the markdown report (separated by `---REVIEW_JSON---`).

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

### JSON Output (when `--json` flag is set)

Emit after the markdown report, separated by `---REVIEW_JSON---`:

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
- **Validation commands not found**: Report "Skipped" for each, proceed with review.
- **Large PR (>50 files)**: Warn about review scope. Focus on source changes first.
- **Max iterations**: Controlled by `REVIEW_MAX_ITERATIONS` env var (default 3).

## Cleanup

Delete any temporary files created during review. Do not leave cached diffs on disk.

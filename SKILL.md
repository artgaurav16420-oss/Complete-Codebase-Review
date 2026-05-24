---
name: complete-codebase-review
description: Use when asked to review, audit, assess, or evaluate an entire codebase holistically — not a PR diff. Covers architecture, security, tech debt, test health, deps, docs, CI, and standards compliance. Read-only — produces a health score, quantified tech debt, and a fix plan for user approval before any changes.
user-invocable: true
argument-hint: "[target-directory] — path to the codebase to review. Defaults to current working directory."
allowed-tools: "Read, Grep, Glob, Bash, Skill, WebSearch, WebFetch, question, Task"
effort: ${CODE_REVIEW_EFFORT:-max}
version: 2.0.0
---

# Complete Codebase Review

## 🔧 Environment Variables

Customize the execution with these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CODE_REVIEW_EFFORT` | `max` | Execution effort. Set to `min` for Quick Mode. |
| `CODE_REVIEW_TIMEOUT_SEC` | `900` | Agent timeout in seconds. |
| `CODE_REVIEW_MAX_FILES` | (unlimited) | Max files to scan. |
| `CODE_REVIEW_CACHE_DIR` | `.code-review-cache` | Directory for checkpointing. |
| `CODE_REVIEW_BASELINE` | `ccr-baseline.json` | Baseline JSON file name. |
| `CODE_REVIEW_AGENTS` | (all applicable) | Comma-separated agent names to run. Defaults to all 13: Architecture, Code Quality, Security, Tech Debt, Test Health, Dependencies, Documentation, Build & CI, Performance, Database, UI/UX, DevOps, Standards. Filtered by project dimensions (see Step 2). |
| `CODE_REVIEW_STATUS_INTERVAL` | `300` | Seconds between status checkpoints reporting completed agent count. |


## Overview

**READ-ONLY (Phases 1-3).** Produces a diagnostic report and fix plan. Phase 4 optionally writes a baseline snapshot for trend tracking. All code changes wait for user approval.

Four-phase pattern for holistic codebase health assessment. Invoke with `/complete-codebase-review [path]`.

**Phase 1: Discovery** → Map structure, stack, modules, entry points
**Phase 2: Parallel Analysis** → Spawn N specialist agents across health dimensions
**Phase 3: Synthesis + Roadmap** → Unified health report with quantified tech debt and prioritized fix roadmap
**Phase 4: Fix Plan** → Generate per-agent code fix tasks, present for user review, wait for permission

### Argument Handling

If `$ARGUMENTS` is provided, treat it as the target codebase path (relative or absolute). Default to `.` (current working directory). Store as `$TARGET_DIR`.

## 💾 Checkpointing

Outputs from specialist agents and synthesis are cached in `${CODE_REVIEW_CACHE_DIR:-.code-review-cache}`. For instance, each agent's output is saved to `${CODE_REVIEW_CACHE_DIR:-.code-review-cache}/phase_<agent_name>.json`. This allows the orchestrator to resume analysis from cache in case of interruption, reducing redundant work.

## ⚡ Quick Mode

To run a fast, surface-level assessment, set `CODE_REVIEW_EFFORT=min`. In this mode:
- Timeouts drop to 120 seconds (`CODE_REVIEW_TIMEOUT_SEC=120`).
- Only a core subset of 3 agents will run (e.g., Security, Code Quality, Architecture).
- The codebase is sampled (approximately 10% sampling limit).

## When to Use

**NOT for:** reviewing PR diffs, single-file changes, or hotfixes. Use [`multi-agent-code-review`](skill:multi-agent-code-review) for those.

**Related skills:** [`multi-agent-code-review`](skill:multi-agent-code-review) (PR/diff reviews), [`requesting-code-review`](skill:requesting-code-review), [`receiving-code-review`](skill:receiving-code-review).

## Phase 1: Discovery

### Step 1: Map the Codebase

Use Glob, Grep, Read, and Bash (cross-platform: `ls`, `find`, `dir`) to collect:

| Dimension | What to Collect |
|-----------|----------------|
| Languages | Detect all languages used, % of each |
| Frameworks | Web frameworks, ORMs, state management, testing |
| Build system | package.json, Cargo.toml, pom.xml, Makefile, etc. |
| Directory structure | Top 3 levels, module organization |
| Entry points | Main files, CLI entry points, API routes |
| Configuration | Config files, env vars, feature flags |
| Database | Schema files, migration tool, connection setup |
| CI/CD | Pipeline configs, deployment scripts |
| Tests | Test framework(s), test directories, coverage tools |
| Git history | Churn hotspots, recent authors, module ownership, branch activity |

Cross-platform approach — detect the OS with `$IsWindows` (PowerShell) or `uname` (Unix), then use:

| Task | Windows | Unix |
|------|---------|------|
| List directory tree | `Get-ChildItem -Depth 3 -Directory` | `find . -maxdepth 3 -type d` |
| Count files by extension | `Get-ChildItem -Recurse \| Group Extension` | `find . -type f \| awk -F. '{print $NF}' \| sort \| uniq -c` |
| Read config file | `Get-Content package.json` | `cat package.json` |
| Recent git history | `git log --oneline -50` | `git log --oneline -50` |
| Find large files | `Get-ChildItem -Recurse \| Sort Length -Descending \| Select -First 20` | `find . -type f -exec ls -la {} \; \| sort -k5 -rn \| head -20` |

Glob tool and Read/Grep tools work identically on both platforms.

### Step 2: Identify Health Dimensions

| Dimension | Applies When |
|-----------|-------------|
| Architecture & Design | All projects |
| Code Quality | All projects |
| Security Posture | All projects (critical for web/API) |
| Tech Debt | All established projects |
| Test Health | Any project with tests |
| Dependency Audit | Any project with dependencies |
| Documentation Coverage | All projects |
| Build & CI | Any project with CI |
| Performance Baseline | Performance-sensitive projects |
| Database & Schema | Any project with a database |
| UI/UX Design & Accessibility | Any project with a user interface |
| DevOps & Infra | Any deployed project |
| Standards Compliance | Team projects |

### Step 3: Write Discovery Manifest

1. Verify Cache Access: Attempt to write a temporary test file to ${CODE_REVIEW_CACHE_DIR:-.code-review-cache}. If the directory is not writable (e.g., in a sandboxed CI environment), automatically fall back to a system temporary directory ($env:TEMP, $TMPDIR, or /tmp) for all subsequent caching.
2. Write Manifest: Write ccr-manifest.md to the verified cache directory.

Include:
- Language/stack summary
- Directory tree (top 3 levels)
- Key config values (dependency counts, test counts)
- Module map (entry points, core libs, legacy areas)
- Selected health dimensions

## Phase 2: Parallel Analysis

### Specialist Agents

| Agent | Coverage | Suggested Skill |
|-------|----------|----------------|
| Architecture Analyzer | Module coupling, layering violations, circular deps, patterns | *(general)* |
| Code Quality Auditor | Dead code, complexity (cyclomatic/cognitive), lint density, anti-patterns | `coding-standards` |
| Security Posture | Secrets in code, dependency CVEs, auth patterns, OWASP checklist | `security-review` |
| Tech Debt Tracker | TODO/FIXME/HACK density, outdated patterns, migration status | *(general)* |
| Test Health Auditor | Coverage % by module, test quality (assertions vs snapshots), CI flakiness | `python-testing` |
| Dependency Auditor | Outdated major/minor/patch, license compliance, supply chain risk | *(general)* |
| Documentation Auditor | README quality, API docs coverage, architecture docs, inline doc density | *(general)* |
| Build & CI Auditor | Build time trends, cache effectiveness, CI reliability, config drift | `deployment-patterns` |
| Performance Baseline | N+1 queries, O(n²) patterns, memory allocation hotspots, bundle size | `benchmark` |
| Database & Schema | Schema design, index health, migration history, raw SQL patterns | `postgres-patterns` |
| UI/UX Auditor | Visual consistency, accessibility (WCAG 2.2), responsive design, component reuse, UX patterns, form/input ergonomics | `ui-ux-pro-max`, `accessibility` |
| DevOps & Infra | Dockerfile quality, infra-as-code, secret management, deployment safety | `deployment-patterns`, `docker-patterns` |
| Standards Compliance | Style guide adherence, naming conventions, file organization | `coding-standards` |

Each agent follows the standard template:

```yaml
name: agent-name
description: |
  Use when auditing [domain] in a codebase. Focus ONLY on [domain].
  Do NOT flag [adjacent domains].
effort: ${CODE_REVIEW_EFFORT:-max}
tools: Read, Grep, Glob, Bash, WebSearch, WebFetch
```

Each agent MUST:
- **Load a relevant skill**: Use the Skill tool to load any skill matching the agent's domain (e.g. `accessibility`, `security-review`, `postgres-patterns`, `frontend-patterns`, `motion-foundations`, `ui-ux-pro-max`) before starting analysis
- **Include Methodology**: Step-by-step audit process
- **Quantify findings**: Numeric score or density metric wherever possible
- **Web Verify**: CVE lookups, framework best-practices checks
- **Output Format**: Standard severity-grouped findings

### Agent Report Format

Each specialist agent MUST return findings in this exact structure:

```markdown
## Agent: [name]
**Score:** X/10

### CRITICAL
| Finding | File(s) | Evidence |
|---------|---------|----------|
| ... | path/file | [metric/observation] |

### HIGH
...

### MEDIUM
...

### LOW
...
```

This ensures the synthesis agent can reliably parse, deduplicate, and score findings across all domains.

### Pre-flight Estimate

Before spawning agents, estimate and log expected resource consumption:

| Metric | Estimate Formula |
|--------|----------------|
| Files scanned | `CODE_REVIEW_MAX_FILES` or detected file count |
| Agents | N (from Orchestration step 1) |
| Min wall time | N × ~30s per agent (prompt + tool calls) |
| Max wall time | N × `CODE_REVIEW_TIMEOUT_SEC` (900s default) |
| Est. token cost per agent | ~5K input + ~3K output (avg), scales with codebase size |

Log: `"[PREFLIGHT] Scanning ~X files with N agents — est. ~M–Mmax minutes. Set CODE_REVIEW_EFFORT=min for Quick Mode (3 agents, 120s timeout)."`

### Orchestration

1. Determine which agents to run:
   - If `CODE_REVIEW_AGENTS` is set, use that comma-separated list (e.g. `CODE_REVIEW_AGENTS=security,architecture,code-quality`)
   - Otherwise, run all 13 agents that match the project's health dimensions (see Step 2)
   - In Quick Mode (`CODE_REVIEW_EFFORT=min`), run only Security, Code Quality, and Architecture
2. Log pre-flight estimate (see above).
3. Spawn N Task agents in parallel. Use the Task tool for each:

```
task name: security-posture-audit
subagent_type: general
prompt: "You are auditing the Security Posture of {TARGET_DIR}.
  Load the 'security-review' skill. Run OWASP checks, scan for
  hardcoded secrets, and check dependency CVEs.
  Return findings in the standard severity-grouped format."
```

3. Collect results as each returns. After every `CODE_REVIEW_STATUS_INTERVAL` seconds, log a checkpoint: "X/Y agents completed so far."
4. Once all N have reported, proceed to synthesis.

**CRITICAL:** After spawning all agents, do nothing else until every agent reports back. No messages, no drafting, no polling. When a result arrives: track it. Proceed only when all N are in. If any agent exceeds ${CODE_REVIEW_TIMEOUT_SEC:-900} seconds, proceed with partial results and note the gap. See Sub-Agent Failure Recovery below.

## Phase 3: Synthesis + Roadmap

### 3a. Synthesis Agent

Input: all N specialist reports
Actions:
- Deduplicate redundant observations: if two agents describe the same root cause in the same file/component → deduplicate
- Retain cross-domain impact: if two agents describe different observable consequences of the same underlying issue → retain both with a `Cross-domain impact` tag
- Flag conflicts explicitly: if two agents contradict each other about the same component → flag conflict rather than silent deduplication
- Normalize severity (CRITICAL/HIGH/MEDIUM/LOW/INFO)
- Quantify tech debt (estimated hours per finding)
- Group by domain, then severity
- Produce unified health report with conflict log

### Context Management

Each agent report MUST include a compact findings summary (severity + count + top 3 per severity) at the top of its output, in addition to the full report. The synthesis agent uses summaries for deduplication and cross-referencing, and reads full reports only for CRITICAL/HIGH findings. This prevents context window overflow on large codebase reviews where combined agent reports may exceed 100K tokens.

### 3b. Roadmap Agent

Input: synthesized report
Actions:
- Prioritize findings by impact vs effort
- Produce phased roadmap:
  - **Phase 1** (now): CRITICAL + quick wins
  - **Phase 2** (next quarter): HIGH + medium-effort items
  - **Phase 3** (backlog): MEDIUM/LOW + aspirational
- Estimate total tech debt in engineering hours
- Assign ownership suggestions by team/domain

### 3c. Devil's Advocate Agent

Input: roadmapped report + discovery manifest
Actions:
- Challenge EVERY finding
- Web-verify each claim
- Independently read code to confirm
- Assign: CONFIRMED / PLAUSIBLE / QUESTIONABLE / REJECTED
- DA may not introduce new finding *categories*. DA may escalate severity, add confirming evidence, or flag a finding as `DA-ESCALATION` if it independently discovers something material the specialists missed
- All DA additions are tagged `DA-ESCALATION` and reviewed separately in the synthesis report

### 3d. Output + Cleanup

1. Ask user: "Where should I write the health report? [file path | stdout]"
2. On file path → write report to that path
3. On stdout → print the report
4. Cleanup:
   - Delete `${CODE_REVIEW_CACHE_DIR:-.code-review-cache}/ccr-manifest.md` (resolved at write-time — see Phase 1 Step 3)
   - Clean up any agent temp files if not checkpointing

## Phase 4: Multi-Agent Fix Plan

After the health report is delivered, generate a fix plan — but do NOT apply it.

### 4a. Generate Fix Tasks

For each CONFIRMED/PLAUSIBLE finding in the DA-verified report, create a structured fix task:

| Field | Description |
|-------|-------------|
| Task ID | T-001, T-002, ... |
| Finding | Reference to the health report finding |
| Severity | CRITICAL / HIGH / MEDIUM / LOW |
| Target files | Specific files needing changes |
| Suggested change | Concise description of what to fix |
| Skill | Which skill(s) would be useful to load |
| Est. effort | Hours |
| Dependencies | Tasks that should be done first |

### 4b. Estimate Reconciliation

The fix plan generator MUST reconcile its effort estimates against the health report's per-finding hours. For each task where the estimate differs from the health report by >20%, document the variance and the reason. Fix plan estimates are the canonical source for `tech_debt_hours` in the baseline snapshot.

### 4c. Present to User

Print the fix plan table. Then ask:

> "I've generated a fix plan with N tasks. Review it above. Reply with the Task IDs you'd like me to apply (e.g. 'T-001, T-003, T-005') or 'all' to proceed with everything, or 'skip' to exit without changes."

**Do NOT apply any fix until the user explicitly lists Task IDs or says "all".**

### 4d. Apply Approved Fixes

Only after user approval:
- For each approved task, create a Task agent that loads the relevant skill, reads the target files, applies the fix, and verifies it.
- CRITICAL items first, then HIGH, then MEDIUM.

### 4e. Baseline Snapshot

After the fix plan is generated, save a baseline snapshot to `${CODE_REVIEW_CACHE_DIR:-.code-review-cache}/${CODE_REVIEW_BASELINE:-ccr-baseline.json}`:

```json
{
  "timestamp": "ISO-8601",
  "target": "$TARGET_DIR",
  "health_score": "GREEN/YELLOW/RED",
  "tech_debt_hours": 123,
  "critical_count": 5,
  "per_domain_scores": {},
  "task_count": 12
}
```

If a previous baseline exists, diff current vs previous and report trend in the executive summary:

```markdown
### Trend vs Previous Baseline
- **Health**: YELLOW → YELLOW (stable)
- **Tech Debt**: 120h → 95h (↓21%)
- **Critical Issues**: 5 → 2 (↓60%)
```

### 4f. Re-review After Partial Fixes

When the user applies only a subset of tasks and wants a follow-up scan:

1. Load the previous baseline from `${CODE_REVIEW_CACHE_DIR:-.code-review-cache}/${CODE_REVIEW_BASELINE:-ccr-baseline.json}`
2. Re-run Phase 2 (parallel analysis) with all spawned agents. Domains with no previously open HIGH/CRITICAL findings are marked `[LOW-ACTIVITY]` in the trend table, but still receive fresh scores from re-analysis.
3. Re-synthesize with previous baseline in context
4. Update baseline snapshot
5. Report progress: remaining vs original

This enables iterative improvement tracking across multiple sessions.

### 4g. Post-Fix Verification

After fixes are applied, verify they didn't introduce regressions:

1. **Re-read changed files**: For each applied task, read the modified files to confirm the change matches the task description.
2. **Lint check**: Run the project's linter (e.g. `npm run lint`, `ruff`, `cargo check`) on changed files if a lint command is detectable.
3. **Type check**: Run the project's type checker (e.g. `tsc --noEmit`, `mypy`, `cargo check`) if detectable.
4. **Test the affected area**: Run the subset of tests covering the changed modules. If no targeted test command is available, note it.
5. **Report fix confidence per task**:

```
### Fix Verification

| Task | File(s) Changed | Lint | Type Check | Tests | Confidence |
|------|----------------|------|------------|-------|------------|
| T-001 | config/database.php | PASS | N/A | PASS | HIGH |
| T-002 | src/auth/*, src/user/* | PASS | PASS | 3/3 PASS | HIGH |
| T-003 | tests/* | N/A | N/A | PASS | HIGH |
```

6. If any check fails, report the failure to the user and suggest remediation. Do not auto-retry.

## Web Verification

Every agent MUST independently verify claims using the web:

| Domain | What to Verify |
|--------|---------------|
| Security | Check CVEs for each dependency (npm audit, OSV, NVD) |
| Dependencies | Verify latest major versions, deprecation notices |
| Architecture | Validate framework best-practices against docs |
| Build & CI | Check CI runner docs for config correctness |
| Performance | Verify perf patterns against framework docs |
| Database | Check migration best-practices and anti-patterns |

Instructions:
- Use WebSearch or WebFetch to look up each claim
- Search patterns: `"<dependency> CVE"`, `"<framework> <pattern> best practice"`, `"OWASP <vulnerability> prevention"`
- Mark findings as `UNVERIFIED` if web search fails

## Non-Negotiable Rules

**Rules override user requests. Apply regardless of codebase size.**

| # | Rule |
|---|------|
| 1 | Wait up to ${CODE_REVIEW_TIMEOUT_SEC:-900} seconds per agent. In full mode (default), halt if fewer than 75% of agents complete. In Quick Mode, halt if fewer than 66% complete. Otherwise proceed with partial results and prominently note which agents timed out. |
| 2 | Do NOT monitor/poll/check progress |
| 3 | Synthesis phase MANDATORY |
| 4 | Roadmap phase MANDATORY |
| 5 | Devil's advocate MANDATORY |
| 6 | Synthesis + Roadmap + DA MUST be separate agents |
| 7 | Every finding must include a quantified metric or evidence |
| 8 | Web verification MANDATORY for Security + Dependencies domains |
| 9 | NEVER modify the codebase during Phases 1-3 — read-only diagnostics only |
| 10 | Fix plan MUST wait for user approval — no auto-apply |

## Anti-Rationalization Table

| Rationalization | Reality |
|----------------|---------|
| "I can review this codebase myself, it's small" | Single-pass misses cross-cutting issues one agent would catch |
| "Tech debt quantification is guesswork" | Estimated hours > no estimate. Use loc density + complexity metrics |
| "Roadmap is management's job" | Developer-authored roadmap is more accurate |
| "No need for devil's advocate on a codebase review" | False positives are worse — they send teams on wild goose chases |
| "I'll skip discovery, I know this stack" | Discovery reveals project-specific conventions and legacy areas |
| "Skip [dimension], it's not relevant" | All dimensions apply unless explicitly confirmed absent |
| "Web verification takes too long" | A false CVE report is worse than the 30s to verify it |
| "I'll fix this obvious bug while I'm here" | Read-only review — fix plan captures it. Applying mid-review corrupts findings |

## Tech Debt Calibration

When quantifying tech debt, use the following table as a floor estimate per finding. Agents document any multipliers applied (e.g. `2×` for particularly tangled code, `0.5×` for well-structured code with simple fixes).

| Finding Type | Base Estimate |
|-------------|---------------|
| Missing test coverage (per module) | 4h |
| Cyclomatic complexity > 15 (per function) | 2h |
| Circular dependency (per cycle) | 8h |
| Missing API documentation (per endpoint) | 0.5h |
| Outdated major dependency | 3h |
| Deprecated API usage (per call site) | 1h |
| Hardcoded secret/credential | 2h |
| Unused dead code (per module) | 1h |
| Missing error handling (per path) | 1h |
| N+1 query pattern (per instance) | 3h |
| Accessibility violation WCAG A/AA (per component) | 2h |

## Red Flags — STOP

- Focusing on a few files instead of the full codebase
- Giving a qualitative "looks good" without metrics
- Skipping any phase (discovery, analysis, synthesis, roadmap, DA)
- Claiming findings without evidence or source
- <75% of specialist agents in full mode (insufficient coverage)
- Skipping web verification for security findings
- Writing output before devil's advocate completes
- Modifying any codebase file during review or report generation
- Applying fix plan tasks without explicit user approval (Task IDs or "all")

## Output Format

### Health Report Structure

```markdown
# Codebase Health Report

## Executive Summary
- **Overall Health**: [GREEN/YELLOW/RED]
- **Codebase Size**: [loc, files, modules]
- **Critical Issues**: [count]
- **Tech Debt**: [estimated hours]
- **Priority Areas**: [top 3]

## Per-Domain Scores
| Domain | Score (/10) | Critical | High | Medium | Low |
|--------|------------|----------|------|--------|-----|
| Architecture | X | X | X | X | X |
| Security | X | X | X | X | X |
| ... | X | X | X | X | X |

## Detailed Findings
[Grouped by domain, then severity. Each finding includes DA verdict column.]

| Finding | Severity | Domain | Est. Hours | DA Verdict |
|---------|----------|--------|------------|------------|
| ... | CRITICAL | Security | 8h | CONFIRMED |
| ... | HIGH | Architecture | 4h | CONFIRMED |
| ... | MEDIUM | UI/UX | 2h | QUESTIONABLE |
| ... | LOW | Docs | 1h | PLAUSIBLE |

## Improvement Roadmap
### Phase 1 — Now (estimated: X hours)
### Phase 2 — Next Quarter (estimated: X hours)
### Phase 3 — Backlog (estimated: X hours)

## Tech Debt Summary
- Total estimated: X hours
- By domain: [table]
- Trend: [increasing/stable/decreasing]

## Trend vs Previous Baseline (if exists)
- **Health**: [previous] → [current] (improved/stable/declined)
- **Tech Debt**: [previous]h → [current]h (Δ%)
- **Critical Issues**: [previous] → [current] (Δ%)

## Agent Status
- Completed: X/X agents
- Report verified by devil's advocate
```

## Sample Output

Below is a realistic example of what a completed health report looks like for a medium-sized web application:

```markdown
# Codebase Health Report — my-web-app (src/)

## Executive Summary
- **Overall Health**: YELLOW
- **Codebase Size**: 47,320 LOC, 312 files, 8 modules
- **Critical Issues**: 3
- **Tech Debt**: 214 engineering hours
- **Priority Areas**: Security (hardcoded secrets), Architecture (circular deps), Test Health (low coverage)

## Per-Domain Scores
| Domain | Score (/10) | Critical | High | Medium | Low |
|--------|------------|----------|------|--------|-----|
| Architecture | 6 | 1 | 2 | 3 | 1 |
| Security | 4 | 2 | 3 | 1 | 0 |
| Code Quality | 7 | 0 | 1 | 4 | 2 |
| Test Health | 5 | 0 | 2 | 2 | 1 |
| Dependencies | 8 | 0 | 0 | 2 | 3 |
| Documentation | 6 | 0 | 1 | 1 | 4 |
| Build & CI | 9 | 0 | 0 | 1 | 1 |
| Database | 7 | 0 | 1 | 1 | 1 |
| **Overall** | **6.5** | **3** | **10** | **15** | **13** |

## Detailed Findings

| Finding | Severity | Domain | Est. Hours | DA Verdict |
|---------|----------|--------|------------|------------|
| Hardcoded DB password in config/database.php | CRITICAL | Security | 2h | CONFIRMED |
| Circular dep: auth → user → notification → auth | CRITICAL | Architecture | 8h | CONFIRMED |
| Hardcoded API key in tests/fixtures/auth.json | CRITICAL | Security | 2h | CONFIRMED |
| Module user/service.go: cyclomatic complexity 34 | HIGH | Code Quality | 4h | CONFIRMED |
| Test coverage <20% in 3 of 8 modules | HIGH | Test Health | 12h | PLAUSIBLE |
| Deprecated `lodash.set` used in 17 call sites | HIGH | Dependencies | 3h | CONFIRMED |
| Missing API docs for /admin/* endpoints (9 endpoints) | HIGH | Documentation | 4.5h | CONFIRMED |
| N+1 query in /orders endpoint | HIGH | Database | 3h | CONFIRMED |
| Mixed snake_case and camelCase in src/models | MEDIUM | Standards | 2h | QUESTIONABLE |
| ... | | | | |

## Improvement Roadmap

### Phase 1 — Now (estimated: 31 hours)
- T-001: Rotate hardcoded secrets → env vars → 4h
- T-002: Break auth→user→notification cycle via event bus → 8h
- T-003: Add unit tests for 3 uncovered modules → 12h
- T-004: Replace lodash.set with native optional chaining → 3h
- T-005: Add rate limiting to auth endpoints → 4h

### Phase 2 — Next Quarter (estimated: 47 hours)
- T-006: Refactor high-complexity functions (17 functions >15 cyclomatic) → 14h
- T-007: Document all undocumented API endpoints → 10h
- T-008: Fix N+1 queries (3 instances) → 9h
- T-009: Migrate from Moment.js to date-fns → 8h
- T-010: Add E2E tests for critical paths → 6h

### Phase 3 — Backlog (estimated: 136 hours)
- T-011: Implement design system component library → 40h
- T-012: Add performance benchmarking pipeline → 16h
- T-013: Full OWASP Top 10 hardening audit → 24h
- ... (remaining 8 tasks)

## Tech Debt Summary
- **Total estimated**: 214 hours
- **By domain**: Security 18h, Architecture 24h, Code Quality 32h, Test Health 48h, Dependencies 12h, Documentation 20h, Standards 16h, Database 18h, UI/UX 26h
- **Trend**: First baseline — no trend data

## Agent Status
- Completed: 11/13 agents
- Failed (timeout): Performance Baseline, UI/UX Auditor (noted in findings)
- Report verified by devil's advocate
- **DA Verdict**: 23 CONFIRMED, 8 PLAUSIBLE, 3 QUESTIONABLE, 1 REJECTED
```

## Graceful Degradation

| Missing | Fallback |
|---------|----------|
| LSP | Grep/Glob for structure analysis |
| WebSearch | Code-only; mark UNVERIFIED |
| Skill not found | Log `SKILL_MISSING: [name]`, proceed with general domain knowledge, note the gap in the agent's report header. Do not halt. |
| Rate limit hit on web verification | Fall back to code-only analysis for that agent, mark findings UNVERIFIED |
| Agent fails | See Sub-Agent Failure Recovery table. |
| Large codebase | Prioritize core modules; note "X modules not analyzed". Assign module subsets to specific agents to avoid overlap. |
| Cache directory not writable | Fall back to OS temporary directory |
| $ARGUMENTS path invalid | Ask user for a valid path; fall back to `.` |
| User declines fix plan | Clean up and exit — no changes written |

## Sub-Agent Failure Recovery

| Scenario | Action |
|----------|--------|
| **Transient tool error** (network timeout, rate limit) | Retry once after 10s backoff |
| **Persistent tool error** (same error after retry) | Skip that agent. Note `AGENT_FAILED` prominently in synthesis report |
| **Agent exceeds ${CODE_REVIEW_TIMEOUT_SEC:-900} seconds** | Proceed with partial results from completed agents. Document which agents were skipped and why |
| **<75% of agents complete (full mode) or <66% (Quick Mode)** | Halt — insufficient coverage. Report: "Only X/Y agents completed in {mode} mode. Reduce codebase size, increase CODE_REVIEW_TIMEOUT_SEC, or retry." |
| **Synthesis/DA agent fails** | Halt and report error. These phases are mandatory. Do not produce output without them. |

## Cross-Boundary Signals

Cross-domain signals are captured in a structured notes block by the orchestrator and included as context when spawning dependent agents. The orchestrator collects cross-references from agent reports and passes relevant signals to downstream agents.

| From | To | Signal |
|------|----|--------|
| Architecture | CodeQuality | Circular dependency causing high cyclomatic complexity |
| Security | Dependencies | CVE found in a dependency |
| Performance | Architecture | Performance bottleneck caused by layering abstraction |
| TestHealth | Build | Test failures correlated with CI configuration drift |
| UI/UX | Accessibility | Component missing ARIA attributes or keyboard navigation |
| UI/UX | Performance | Oversized assets or unoptimized images |
| UI/UX | Standards | Design system drift or inconsistent component usage |

## Common Mistakes

- Reviewing a diff instead of the full codebase (use multi-agent-code-review)
- Surface-level scanning without deep analysis
- Qualitative-only assessment (no metrics, no quantification)
- No roadmap — findings without a plan to fix them
- Skipping devil's advocate (false positives waste team time)
- Writing output before all agents complete
- Windows-only commands that fail on devs' MacBooks
- Fixing issues during the review instead of capturing them in the fix plan
- Applying the fix plan without user approval

## Changelog

### v2.0.0 (2026-05-24)
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

# Complete Codebase Review Help

This skill conducts a complete, multi-dimensional, read-only audit of your codebase and produces an actionable, prioritized roadmap without making immediate changes.

## 🔧 Environment Variables

You can configure the execution behavior by exporting these environment variables before invoking the agent:

> **Source of truth:** `SKILL.md` in the installed skill directory is the canonical reference for all environment variables. This page may be a subset.

*   `CODE_REVIEW_EFFORT` (default: `max`): Sets the effort level for AI analysis. Set to `min` for Quick Mode.
*   `CODE_REVIEW_TIMEOUT_SEC` (default: `900`): Maximum time (in seconds) to wait for individual specialist agents.
*   `CODE_REVIEW_MAX_FILES` (default: unlimited): Limits the number of files scanned in large codebases.
*   `CODE_REVIEW_CACHE_DIR` (default: `.code-review-cache`): Directory where phase outputs and agent findings are cached.
*   `CODE_REVIEW_BASELINE` (default: `ccr-baseline.json`): The filename for saving the baseline snapshot to track health trends across sessions.
*   `CODE_REVIEW_AGENTS` (default: all applicable): Comma-separated list of agent names to run (e.g. `security,architecture,code-quality`). Full default set (filtered by project dimensions): Architecture, Code Quality, Security, Tech Debt, Test Health, Dependencies, Documentation, Build & CI, Performance, Database, UI/UX, DevOps, Process Quality (Karpathy Compliance), Standards.
*   `CODE_REVIEW_STATUS_INTERVAL` (default: `300`): Minimum seconds between event-driven status log lines ('X/Y agents completed'). Status is emitted on agent result receipt, not on a background timer.
*   `CODE_REVIEW_FILTER` (default: `all`): Output filter. Set to `critical-high`
    to show only CRITICAL and HIGH severity findings in the report. Per-Domain
    Scores still show full counts for context.

## ⚡ Quick Mode

To run a rapid, surface-level assessment, use Quick Mode by exporting `CODE_REVIEW_EFFORT=min`. In Quick Mode:
*   Timeouts are reduced to 120 seconds (`CODE_REVIEW_TIMEOUT_SEC=120`).
*   The review focuses on the core 3 specialist agents.
*   The target codebase is aggressively sampled (~10% limit).

## 🔒 Read-Only Guarantee

Phases 1 through 3 of this skill are strictly **read-only**. The agents will not alter your source code, configuration, or structural directories. Only Phase 4 allows code fixes to be generated and applied, and ONLY if you explicitly approve individual tasks.

**Phase 5 (Independent Review & Test):** After Phase 4 fixes are applied, Phase 5 audits all changes, corrects regressions, and runs the full project test suite to ensure nothing was broken before finalizing.

## 💾 Checkpointing & Trend Tracking

Phase outputs and agent findings are cached in `$RESOLVED_CACHE_DIR` (default: `.code-review-cache/`). If the default cache directory is not writable, the system falls back to the OS temporary directory (`$TEMP` on Windows, `$TMPDIR` on Unix).

### Baseline Snapshots

After the fix plan is generated (Phase 4), a baseline snapshot is saved to `$RESOLVED_CACHE_DIR/$CODE_REVIEW_BASELINE` (default: `ccr-baseline.json`). This snapshot captures:

| Field | Description |
|-------|-------------|
| `health_score` | Overall health: GREEN/YELLOW/RED |
| `tech_debt_hours` | Total estimated tech debt |
| `critical_count` | Number of CRITICAL findings |
| `per_domain_scores` | Score per domain (0-10) |
| `per_domain_open_findings` | CRITICAL/HIGH counts per domain |

On re-review, the system compares against the previous baseline and reports trends:

```markdown
### Trend vs Previous Baseline
- **Health**: YELLOW → YELLOW (stable)
- **Tech Debt**: 120h → 95h (↓21%)
- **Critical Issues**: 5 → 2 (↓60%)
```

### Low-Activity Domains

Domains with zero CRITICAL and zero HIGH open findings are marked `[LOW-ACTIVITY]` on re-review. These domains are excluded from re-analysis — their previous scores carry forward in the trend table, reducing analysis time.

## 🚦 Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — review completed, fix applied, dry-run finished, or `--version` shown |
| `1` | Review halted mid-pipeline (<75% agents in full mode, <66% in Quick Mode) |
| `1` | Install failed (permission denied, copy error, or path traversal detected) |
| `1` | Post-fix verification failed (lint, typecheck, or test suite regression) |
| `1` | Compliance test failed (one or more SKILL.md assertions not met) |

## ⚙️ Windows Environment Variables

PowerShell syntax:
```powershell
# Quick Mode
$env:CODE_REVIEW_EFFORT="min"
$env:CODE_REVIEW_TIMEOUT_SEC="120"

# Filter to critical/high only
$env:CODE_REVIEW_FILTER="critical-high"

# Run the review
/complete-codebase-review src/

# Unset when done
Remove-Item env:CODE_REVIEW_EFFORT
```

CMD syntax:
```cmd
set CODE_REVIEW_EFFORT=min
set CODE_REVIEW_TIMEOUT_SEC=120
/complete-codebase-review src/
```

## 🔧 Troubleshooting

**Review hangs or takes too long:**
- Increase `CODE_REVIEW_TIMEOUT_SEC` (default 900s). Try 1800 for large codebases.
- Use Quick Mode (`CODE_REVIEW_EFFORT=min`) for a rapid surface scan.

**Specialist agents time out:**
- Reduce scope with `CODE_REVIEW_MAX_FILES=<N>`.
- Use Quick Mode which runs only 3 core agents with 120s timeout.
- Filter to critical/high findings with `CODE_REVIEW_FILTER=critical-high`.

**Installation fails:**
- Use `--dry-run` first to verify paths: `python install.py --dry-run`.
- On Linux, check `XDG_CONFIG_HOME` if agent configs are in a non-standard location.

## 🤖 CI Integration

```yaml
# .github/workflows/review.yml
name: Codebase Review
on: [push, pull_request]
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run compliance tests
        run: python tests/test_compliance.py
      - name: Run unit tests
        run: python -m unittest discover -s tests -p "test_*.py" -v
```

## 📖 Usage Example

```bash
# Standard comprehensive review
/complete-codebase-review src/

# Quick mode review
export CODE_REVIEW_EFFORT=min
/complete-codebase-review src/

# Dry-run install first
python install.py --dry-run

# Show version
python install.py --version
```

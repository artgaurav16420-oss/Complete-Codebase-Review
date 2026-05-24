# Complete Codebase Review Help

This skill conducts a complete, multi-dimensional, read-only audit of your codebase and produces an actionable, prioritized roadmap without making immediate changes.

## 🔧 Environment Variables

You can configure the execution behavior by exporting these environment variables before invoking the agent:

*   `CODE_REVIEW_EFFORT` (default: `max`): Sets the effort level for AI analysis. Set to `min` for Quick Mode.
*   `CODE_REVIEW_TIMEOUT_SEC` (default: `900`): Maximum time (in seconds) to wait for individual specialist agents.
*   `CODE_REVIEW_MAX_FILES` (default: unlimited): Limits the number of files scanned in large codebases.
*   `CODE_REVIEW_CACHE_DIR` (default: `.code-review-cache`): Directory where phase outputs and agent findings are cached.
*   `CODE_REVIEW_BASELINE` (default: `ccr-baseline.json`): The filename for saving the baseline snapshot to track health trends across sessions.
*   `CODE_REVIEW_AGENTS` (default: all applicable): Comma-separated list of agent names to run (e.g. `security,architecture,code-quality`). Full default set (filtered by project dimensions): Architecture, Code Quality, Security, Tech Debt, Test Health, Dependencies, Documentation, Build & CI, Performance, Database, UI/UX, DevOps, Standards.
*   `CODE_REVIEW_STATUS_INTERVAL` (default: `300`): Seconds between status checkpoints reporting completed agent count.
*   `CODE_REVIEW_FILTER` (default: `all`): Output filter. Set to `critical-high` to show only CRITICAL and HIGH severity findings in the report (Per-Domain Scores still show full counts).

## ⚡ Quick Mode

To run a rapid, surface-level assessment, use Quick Mode by exporting `CODE_REVIEW_EFFORT=min`. In Quick Mode:
*   Timeouts are reduced to 120 seconds (`CODE_REVIEW_TIMEOUT_SEC=120`).
*   The review focuses on the core 3 specialist agents.
*   The target codebase is aggressively sampled (~10% limit).

## 🔒 Read-Only Guarantee

Phases 1 through 3 of this skill are strictly **read-only**. The agents will not alter your source code, configuration, or structural directories. Only Phase 4 allows code fixes to be generated and applied, and ONLY if you explicitly approve individual tasks.

## 📖 Usage Example

```bash
# Standard comprehensive review
/complete-codebase-review src/

# Quick mode review
export CODE_REVIEW_EFFORT=min
/complete-codebase-review src/
```

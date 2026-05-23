# Complete Codebase Review

A holistic, read-only codebase audit skill for Claude Code / AI coding agents. Produces a health score (GREEN/YELLOW/RED), quantified tech debt, and a prioritized multi-agent fix plan — without modifying any code until you approve.

## Features

- **13 parallel specialist agents** — Architecture, Security, Code Quality, Tech Debt, Test Health, Dependencies, Documentation, Build/CI, Performance, Database, UI/UX, DevOps, Standards
- **Four-phase execution**: Discovery → Parallel Analysis → Synthesis + Roadmap → Fix Plan
- **Devil's Advocate quality gate** — independently verifies every finding to eliminate false positives
- **Web verification** — CVEs, framework best-practices, OWASP checks
- **Baseline tracking** — compares results across sessions to measure improvement
- **Read-only by design** — never modifies codebase during Phases 1-3
- **Cross-platform** — works on Windows and Unix

## Usage

```
/complete-codebase-review [target-directory]
```

Default target is the current working directory.

## Requirements

- Claude Code or compatible AI coding agent
- Access to `Read`, `Grep`, `Glob`, `Bash`, `Skill`, `WebSearch`, `WebFetch`, `question`, `Task` tools
- WebSearch/WebFetch for CVE and best-practice verification (falls back gracefully if unavailable)

## Output

- Health report with per-domain scores (0-10)
- Prioritized 3-phase improvement roadmap
- Quantified tech debt in engineering hours
- Structured fix tasks (T-001, T-002, ...) with suggested skills
- Baseline snapshot for trend tracking across sessions

## License

MIT

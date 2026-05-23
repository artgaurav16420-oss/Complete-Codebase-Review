# Complete Codebase Review

A holistic, read-only codebase audit skill for Claude Code / AI coding agents. Produces a health score (GREEN/YELLOW/RED), quantified tech debt, and a prioritized multi-agent fix plan — without modifying any code until you approve.

## Features

- **Parallel specialist agents** — Architecture, Security, Code Quality, Tech Debt, Test Health, Dependencies, Documentation, Build/CI, Performance, Database, UI/UX, DevOps, Standards
- **Four-phase execution**: Discovery → Parallel Analysis → Synthesis + Roadmap → Fix Plan
- **Devil's Advocate quality gate** — independently verifies every finding to eliminate false positives
- **Web verification** — CVEs, framework best-practices, OWASP checks
- **Baseline tracking** — compares results across sessions to measure improvement
- **Read-only by design** — never modifies codebase during Phases 1-3
- **Cross-platform** — works on Windows and Unix


## 🚀 One-line Install

```
curl -fsSL https://raw.githubusercontent.com/artgaurav16420-oss/Complete-Codebase-Review/main/install.py -o install.py && python install.py
```

## 🧪 Tested On

| OS | Supported |
|----|-----------|
| macOS | ✅ |
| Linux | ✅ |
| Windows | ✅ |

## Installation

Clone the repo into your Claude Code skills directory:

```bash
# macOS / Linux
git clone https://github.com/artgaurav16420-oss/Complete-Codebase-Review.git ~/.claude/skills/complete-codebase-review
```

```powershell
# Windows (PowerShell)
git clone https://github.com/artgaurav16420-oss/Complete-Codebase-Review.git "$env:USERPROFILE\.claude\skills\complete-codebase-review"
```

Or clone anywhere and run the install script:

```bash
# Unix
./install.sh

# Windows / Unix (PowerShell)
./install.ps1
```


## 🔧 Environment Variables

Execution is fully configurable. See [help.txt](help.txt) for a complete list of environment variables (like `CODE_REVIEW_EFFORT` and `CODE_REVIEW_TIMEOUT_SEC`), Quick Mode usage, and our read-only guarantees.

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

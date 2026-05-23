<div align="center">

# Complete Codebase Review 🚀

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/artgaurav16420-oss/Complete-Codebase-Review/graphs/commit-activity)
[![GitHub issues](https://img.shields.io/github/issues/artgaurav16420-oss/Complete-Codebase-Review.svg)](https://github.com/artgaurav16420-oss/Complete-Codebase-Review/issues)
[![GitHub stars](https://img.shields.io/github/stars/artgaurav16420-oss/Complete-Codebase-Review.svg?style=social)](https://github.com/artgaurav16420-oss/Complete-Codebase-Review/stargazers)

**A holistic, read-only codebase audit skill for Claude Code / AI coding agents.**

*Produces a health score (GREEN/YELLOW/RED), quantified tech debt, and a prioritized multi-agent fix plan — without modifying any code until you approve.*

</div>

---

## 📑 Table of Contents

- [Features](#-features)
- [Installation](#-installation)
  - [One-line Install](#one-line-install)
  - [Manual Installation](#manual-installation)
- [Usage](#-usage)
- [Requirements](#-requirements)
- [Configuration](#-configuration)
- [Output](#-output)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Features

- **Parallel Specialist Agents**: Architecture, Security, Code Quality, Tech Debt, Test Health, Dependencies, Documentation, Build/CI, Performance, Database, UI/UX, DevOps, Standards.
- **Four-Phase Execution**: Discovery → Parallel Analysis → Synthesis + Roadmap → Fix Plan.
- **Devil's Advocate Quality Gate**: Independently verifies every finding to eliminate false positives.
- **Web Verification**: CVEs, framework best-practices, OWASP checks.
- **Baseline Tracking**: Compares results across sessions to measure improvement.
- **Read-Only by Design**: Never modifies the codebase during Phases 1-3.
- **Cross-Platform**: Works seamlessly on Windows, macOS, and Linux.

---

## 🚀 Installation

### One-line Install

```bash
curl -fsSL https://raw.githubusercontent.com/artgaurav16420-oss/Complete-Codebase-Review/main/install.py -o install.py && python3 install.py
```

### Manual Installation

You can also clone the repository directly to your local skills directory:

```bash
git clone https://github.com/artgaurav16420-oss/Complete-Codebase-Review.git ~/.claude/skills/complete-codebase-review
```

---

## 💡 Usage

Run the following command in your AI coding agent:

```bash
/complete-codebase-review [target-directory]
```

> **Note**: The default target is the current working directory if no directory is specified.

---

## 📋 Requirements

- **Claude Code** or a compatible AI coding agent.
- Access to the following tools: `Read`, `Grep`, `Glob`, `Bash`, `Skill`, `WebSearch`, `WebFetch`, `question`, `Task`.
- **WebSearch/WebFetch**: Highly recommended for CVE and best-practice verification (gracefully falls back if unavailable).

---

## 🔧 Configuration (Environment Variables)

Execution is fully configurable. See [help.txt](help.txt) for a complete list of environment variables, Quick Mode usage, and our read-only guarantees.

**Common Variables:**
- `CODE_REVIEW_EFFORT`
- `CODE_REVIEW_TIMEOUT_SEC`

---

## 📊 Output

What you can expect after a complete review:

1. **Health Report**: Per-domain scores (0-10).
2. **Prioritized 3-Phase Roadmap**: A clear path for improvement.
3. **Quantified Tech Debt**: Estimated in engineering hours.
4. **Structured Fix Tasks**: Actionable items (T-001, T-002, ...) with suggested skills.
5. **Baseline Snapshot**: Trend tracking across multiple sessions.

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/artgaurav16420-oss/Complete-Codebase-Review/issues).

---

## 📝 License

This project is licensed under the **MIT** License. See the [LICENSE](LICENSE) file for details.

<div align="center">
  <i>Made with ❤️ by the community.</i>
</div>
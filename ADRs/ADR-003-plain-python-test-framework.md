# ADR-003: Plain-Python Test Framework (No pytest)

**Status:** Accepted  
**Date:** 2026-06-16  
**Deciders:** Project maintainers

## Context

The project targets zero dependencies — `pip install` is never required. pytest would introduce a dependency chain that violates this constraint.

## Decision

Test suites use only Python stdlib:

| Suite | Framework | Reason |
|-------|-----------|--------|
| `test_compliance.py` | Custom `make_checker()` DSL | String-matching checks against SKILL.md — simpler than unittest boilerplate for 130+ assertions |
| `test_install.py` | `unittest.TestCase` | Standard unittest — 7 classes, 35 tests, complex mocking |
| New suites | `unittest.TestCase` preferred | `make_checker()` is legacy; new tests should use standard patterns |

The `main()` entry point in `test_compliance.py` provides exit-code output and colored pass/fail display without requiring pytest's test runner.

## Consequences

- **Positive:** Zero dependencies for contributors.
- **Positive:** CI runs `python tests/test_compliance.py` directly — no test runner discovery needed.
- **Negative:** No pytest fixtures, parametrization, or plugins.
- **Negative:** Custom framework makes it harder for new contributors to read.
- **Mitigation:** Future test suites use standard `unittest.TestCase`; `make_checker()` is legacy-only.

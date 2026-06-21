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
| `test_compliance.py` | `unittest.TestCase` | String-matching checks against SKILL.md (139 assertions across 63 tests) |
| `test_install.py` | `unittest.TestCase` | Standard unittest — 9 classes, complex mocking |
| `test_smoke.py` | `unittest.TestCase` | CLI smoke tests via subprocess |
| `test_pipeline.py` | `unittest.TestCase` | Schema-contract validation for review output |
| `test_env_config.py` | `unittest.TestCase` | Env-var table completeness checks |
| New suites | `unittest.TestCase` | All new tests must use standard patterns |

No custom DSLs — all suites use standard `unittest.TestCase`. (Earlier versions used a `make_checker()` DSL; this was removed during the migration to pure unittest.)

## Consequences

- **Positive:** Zero dependencies for contributors.
- **Positive:** CI runs `python -m unittest discover -s tests -p "test_*.py"` directly — no test runner discovery needed.
- **Positive:** All tests follow the same standard pattern — no custom DSL to learn.
- **Negative:** No pytest fixtures, parametrization, or plugins.
- **Mitigation:** `unittest.TestCase` with `subTest()` covers parametrization needs; `tempfile.TemporaryDirectory()` covers filesystem fixtures.
